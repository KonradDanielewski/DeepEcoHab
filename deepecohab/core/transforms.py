import datetime as dt

import polars as pl

from deepecohab.core import grids
from deepecohab.core.data_model import Layout, Recording


def calculate_time_spent(frame: pl.LazyFrame) -> pl.LazyFrame:
	"""Frame with ``time_spent``: the gap to the same animal's previous registration.

	This is how long the animal spent in the state the row describes, held as a
	duration so that arithmetic against ``datetime`` stays exact. The first
	registration of each animal has no predecessor and gets zero.
	"""
	time_spent = (
		(pl.col("datetime") - pl.col("datetime").shift(1))
		.over("animal_id")
		.cast(pl.Duration("us"))
		.fill_null(pl.duration(microseconds=0))
	)
	return frame.with_columns(time_spent.alias("time_spent"))


def get_animal_position(frame: pl.LazyFrame, antenna_combinations: dict[str, str]) -> pl.LazyFrame:
	"""Frame with ``position`` derived from each row's antenna and the previous one.

	Per animal, the previous and current antenna form a ``"<previous>_<current>"``
	key, which ``antenna_combinations`` resolves to a cage or a directional tunnel. Pairs the
	map does not name become ``"undefined"``, as does the first reading of each
	animal, which has no predecessor to pair with.
	"""
	# Filled after the cast, and with a non-numeric sentinel, so the unpaired first
	# reading cannot collide with a layout that numbers an antenna 0.
	previous_antenna = (
		pl.col("antenna").shift(1).over("animal_id").cast(pl.Utf8).fill_null("missing")
	)
	current_antenna = pl.col("antenna").cast(pl.Utf8)
	antenna_pair = pl.concat_str([previous_antenna, pl.lit("_"), current_antenna])

	return frame.with_columns(
		antenna_pair.replace_strict(antenna_combinations, default=Layout.UNDEFINED)
		.alias("position")
		.cast(pl.Categorical)
	)


def extrapolate_last_position(frame: pl.LazyFrame, end: dt.datetime, limit: float) -> pl.LazyFrame:
	"""Frame with each animal's last position carried on towards ``end``.

	This gives a better estimate of time spent in positions and of cage occupancy in
	recordings with low activity, but silence is only weak evidence of staying put: the
	carry stops ``limit`` seconds after the last registration, and an animal silent
	past that gets a second row at ``end`` marked ``__tail`` for the caller to turn into
	:attr:`Layout.UNDEFINED`. Targeting the window end rather than the last read in the
	data is what keeps a recording's final stretch attributed at all.

	Both added rows repeat the last antenna, so :func:`get_animal_position` resolves the
	cap row as the self-pair - the cage at that antenna, where the animal *is* - rather
	than the position the last row named, which is where it was coming from.

	Args:
		frame: registrations, with ``animal_id``, ``antenna`` and ``datetime``.
		end: the analysed window's end, which the carry and the tail row target.
		limit: how many seconds the last position may be carried for.

	Returns:
		``frame`` plus the added rows, with a ``__tail`` flag the caller consumes.
	"""
	columns = [*frame.collect_schema().names(), "__tail"]
	window_end = pl.lit(end).alias("__end")

	last_rows = frame.group_by("animal_id").agg(pl.all().sort_by("datetime").last())
	capped = last_rows.with_columns(
		pl.min_horizontal(pl.col("datetime") + pl.duration(seconds=limit), window_end).alias(
			"__cap"
		)
	)

	carried = capped.filter(pl.col("__cap") > pl.col("datetime")).with_columns(
		pl.col("__cap").alias("datetime"), pl.lit(False).alias("__tail")
	)
	tail = capped.filter(window_end > pl.col("__cap")).with_columns(
		window_end.alias("datetime"), pl.lit(True).alias("__tail")
	)

	return pl.concat(
		[
			frame.with_columns(pl.lit(False).alias("__tail")),
			carried.select(columns),
			tail.select(columns),
		]
	).sort("datetime")


def remove_tunnel_directionality(frame: pl.LazyFrame, recording: Recording) -> pl.LazyFrame:
	"""Frame with directional tunnel positions mapped to their undirected names."""
	return frame.with_columns(
		pl.col("position").cast(pl.Utf8).replace(recording.layout.tunnels_map).cast(pl.Categorical)
	)


def add_occupancy_bounds(frame: pl.LazyFrame) -> pl.LazyFrame:
	"""Frame with ``start`` and ``end`` bounding each occupancy interval.

	``datetime`` is the interval end, so ``start`` is ``datetime - time_spent``.
	"""
	return frame.with_columns(
		pl.col("datetime").alias("end"),
		(pl.col("datetime") - pl.col("time_spent")).alias("start"),
	)


def occupancy_spans(intervals: pl.LazyFrame) -> pl.LazyFrame:
	"""Frame of every span of time a position was occupied, one row per animal inside.

	A sweep over the occupancy intervals turns each stay into an enter and a leave
	event, so at every instant the running count says how many animals the position
	holds and the running signed bit-sum says which ones (one bit per animal, so the
	cumulative sum is a true presence bitmask, capped at ~63 animals - far above any
	EcoHab study). Every arrival and departure closes a span and opens the next, so a
	span holds one fixed set of animals, recovered by decoding its bitmask.

	Args:
		intervals: table with ``animal_id``, ``position`` and the ``start``/``end``
			bounds :func:`add_occupancy_bounds` adds.

	Returns:
		One row per span and animal inside it, with ``position``, ``time``, ``end`` and
		``animals_present``.
	"""
	codes = intervals.select(
		"animal_id",
		"position",
		"start",
		"end",
		pl.lit(2, dtype=pl.Int64)
		.pow(pl.col("animal_id").to_physical().cast(pl.Int64))
		.cast(pl.Int64)
		.alias("bit"),
	)
	# Maps each animal's single-bit mask value back to its id, for decoding the bitmask.
	animal_lookup = codes.select("animal_id", "bit").unique()

	enters = codes.select(
		pl.col("start").alias("time"),
		"position",
		pl.lit(1, dtype=pl.Int32).alias("delta"),
		pl.col("bit").alias("bit_delta"),
	)
	leaves = codes.select(
		pl.col("end").alias("time"),
		"position",
		pl.lit(-1, dtype=pl.Int32).alias("delta"),
		pl.col("bit").neg().alias("bit_delta"),
	)

	events = (
		pl.concat([enters, leaves])
		.sort("position", "time")
		.with_columns(
			pl.col("delta").cum_sum().over("position").alias("animals_present"),
			pl.col("bit_delta").cum_sum().over("position").alias("mask"),
			pl.col("time").shift(-1).over("position").alias("next_time"),
		)
	)

	spans = events.filter(
		pl.col("next_time").is_not_null(),
		pl.col("animals_present") >= 1,
		pl.col("next_time") > pl.col("time"),
	).select("position", "time", pl.col("next_time").alias("end"), "animals_present", "mask")

	return (
		spans.join(animal_lookup, how="cross")
		.filter((pl.col("mask") & pl.col("bit")) != 0)
		.select("position", "time", "end", "animals_present", "animal_id")
	)


def cooccupancy_spans(intervals: pl.LazyFrame) -> pl.LazyFrame:
	"""Frame of every span of time two animals shared a position, one row per pair.

	The occupied spans of :func:`occupancy_spans` holding two or more animals, paired
	up. A pair's co-presence is cut into a new span whenever any third animal arrives
	or leaves, so contiguous spans of one pair are numbered with a single ``meeting_id``
	and read as one meeting.

	Args:
		intervals: table with ``animal_id``, ``position`` and the ``start``/``end``
			bounds :func:`add_occupancy_bounds` adds.

	Returns:
		One row per span and pair, with ``position``, ``time``, ``end``, ``animal_id``,
		``animal_id_2``, ``is_new`` marking the span that opens a meeting, and
		``meeting_id`` numbering meetings within the pair and position.
	"""
	present = occupancy_spans(intervals).filter(pl.col("animals_present") >= 2)

	pairs = present.join(present, on=["position", "time", "end"], suffix="_2").filter(
		pl.col("animal_id") < pl.col("animal_id_2")
	)

	# A new meeting starts wherever a span's start != the previous span's end for that pair.
	group = ["animal_id", "animal_id_2", "position"]
	return (
		pairs.select("position", "time", "end", "animal_id", "animal_id_2")
		.sort(*group, "time")
		.with_columns(
			(pl.col("time") != pl.col("end").shift(1).over(group)).fill_null(True).alias("is_new")
		)
		.with_columns(pl.col("is_new").cum_sum().over(group).alias("meeting_id"))
	)


def split_on_minute_boundaries(frame: pl.LazyFrame, recording: Recording) -> pl.LazyFrame:
	"""Frame with visits that straddle minute boundaries cut into per-minute pieces.

	Each row is the interval ``[datetime - time_spent, datetime)``. Cutting it at
	every minute mark means no piece crosses one, so its time can be attributed to
	the right minute, hour and phase. ``time_spent`` becomes each piece's own length
	and ``time_under`` is shared out in proportion.

	Within a split visit only the first piece keeps ``interpolated=False``, so
	filtering ``interpolated == False`` recovers one row per original visit.

	Args:
		frame: table with ``datetime``, ``time_spent`` and ``time_under``.
		recording: the recording whose phases the pieces are assigned to.

	Returns:
		One row per minute-aligned piece, with ``interpolated`` and a ``row_id``
		identifying the visit the piece came from.
	"""
	minute = pl.duration(minutes=1)

	return (
		frame.with_row_index("row_id")
		.with_columns((pl.col("datetime") - pl.col("time_spent")).alias("__start"))
		.with_columns(
			pl.datetime_ranges(
				pl.col("__start").dt.truncate("1m") + minute,
				pl.col("datetime"),
				interval="1m",
				closed="left",
			).alias("__marks")
		)
		.with_columns(
			pl.concat_list("__start", "__marks").alias("__piece_start"),
			pl.concat_list("__marks", "datetime").alias("__piece_end"),
		)
		.explode("__piece_start", "__piece_end", empty_as_null=True)
		.with_columns(
			(pl.col("datetime") - pl.col("__start")).dt.total_microseconds().alias("__visit"),
			(pl.col("__piece_end") - pl.col("__piece_start"))
			.dt.total_microseconds()
			.alias("__piece"),
		)
		.with_columns(
			(pl.col("__piece_end") - pl.col("__piece_start")).alias("time_spent"),
			pl.when(pl.col("__visit") > 0)
			.then(
				pl.duration(
					microseconds=(
						pl.col("time_under")
						.dt.total_microseconds()
						.mul(pl.col("__piece"))
						.truediv(pl.col("__visit").clip(lower_bound=1))
					)
					.round()
					.cast(pl.Int64)
				)
			)
			.otherwise(pl.col("time_under"))
			.alias("time_under"),
			(pl.int_range(pl.len()).over("row_id") > 0).alias("interpolated"),
		)
		.with_columns(
			grids.get_phase(recording, "__piece_start"),
			grids.get_day(recording, "__piece_start"),
			grids.get_hour(recording, "__piece_start"),
			pl.col("__piece_end").alias("datetime"),
		)
		.select(pl.exclude("^__.*$"))
	)
