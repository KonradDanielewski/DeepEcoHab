import datetime as dt
from collections.abc import Sequence

import polars as pl

from deepecohab.core import grids, topology, transforms
from deepecohab.core.data_model import (
	CALENDAR_COLUMNS,
	AnalysisParams,
	DataFrameRegistry,
	Layout,
	Recording,
)


@DataFrameRegistry.register("animals")
def build_animals(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of the cohort's metadata, one row per animal.

	``animal_id`` carries the same type as in every other table, so this joins onto
	any of them and lets results be grouped by genotype, sex, treatment, mouse line
	or any other recorded attribute.

	Returns:
		One row per animal, with its ``age`` at the start of the recording alongside
		the recorded metadata.
	"""
	recording_start = recording.timeline.local_span[0].date()

	return pl.LazyFrame(
		[
			{
				**animal.model_dump(exclude={"tag"}),
				"animal_id": animal.tag,
				"age": recording_start - animal.date_of_birth,
			}
			for animal in recording.cohort.animals
		],
		schema={
			"animal_id": pl.Enum(recording.cohort.animal_tags),
			"subject_name": pl.String,
			"mouse_line": pl.String,
			"genotype": pl.String,
			"sex": pl.String,
			"date_of_birth": pl.Date,
			"age": pl.Duration("us"),
			"genetic_background": pl.String,
			"treatment": pl.String,
			"notes": pl.String,
		},
	).sort("animal_id")


@DataFrameRegistry.register("main_df")
def build_main_df(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of every antenna registration, annotated with where and when it happened.

	This is the table the whole analysis is built on. Positions are resolved first,
	from the antenna each registration crossed and the one before it, and only then is
	the lead-in before the experiment start dropped: trimming first would leave every
	animal's first in-window registration with no predecessor to pair with, so a
	recording with a discarded lead lost that position. The row that survives the trim
	keeps its true position and a ``time_spent`` clipped to the window, so no occupancy
	is attributed to time the analysis does not cover.

	Returns:
		One row per registration, with ``position``, ``time_spent`` and the calendar
		columns added to the raw ``animal_id``, ``antenna``, ``datetime`` and
		``time_under``.
	"""
	start, end = recording.timeline.local_span

	return (
		recording.data.sort("datetime")
		# Trailing data out first, so the extrapolation anchors on the window and not on it.
		.filter(pl.col("datetime") <= end)
		.pipe(transforms.extrapolate_last_position, end, params.extrapolation_limit)
		.pipe(transforms.calculate_time_spent)
		.pipe(transforms.get_animal_position, recording.layout.antenna_combinations)
		.with_columns(
			pl.when(pl.col("__tail"))
			.then(pl.lit(Layout.UNDEFINED))
			.otherwise(pl.col("position"))
			.cast(pl.Categorical)
			.alias("position")
		)
		.filter(pl.col("datetime") >= start)
		.with_columns(
			pl.min_horizontal("time_spent", pl.col("datetime") - pl.lit(start)).alias("time_spent")
		)
		.with_columns(
			grids.get_phase(recording), grids.get_day(recording), grids.get_hour(recording)
		)
		.pipe(grids.assign_phase_count, recording)
		.drop("__tail")
		.sort("datetime")
	)


@DataFrameRegistry.register("padded_df", requires=["main_df"])
def build_padded_df(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of ``main_df`` visits cut at every wall-clock minute boundary.

	Occupancy has to be attributed to the minute it happened in, so a visit spanning
	several minutes is split into one piece per minute. Tables that measure time
	rather than events read this instead of ``main_df``.
	"""
	pieces = transforms.split_on_minute_boundaries(recording.load_results("main_df"), recording)

	# A piece is dated by its own start, not by the end of the visit it came from, so
	# the phase_count inherited from that visit no longer applies. Every piece starts
	# inside the window - build_main_df clips the first visit's time_spent to it - so
	# this left join always resolves and no piece leaves with a null phase_count.
	return grids.assign_phase_count(pieces.drop("phase_count"), recording).sort("datetime")


@DataFrameRegistry.register("phase_durations")
def build_phase_durations(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame with how long each phase occurrence of the recording lasted.

	Durations are accurate to roughly one minute, which is the resolution the
	recording window is walked at.

	Returns:
		One row per phase occurrence, with ``phase``, ``phase_count`` and
		``duration``.
	"""
	start, end = recording.timeline.local_span

	return (
		pl.LazyFrame()
		.select(
			pl.datetime_range(
				start,
				end,
				interval="1m",
				closed="left",
				time_zone=recording.timeline.recording_timezone.key,
			)
			.dt.round("1m")
			.alias("datetime")
		)
		.with_columns(
			grids.get_phase(recording), grids.get_day(recording), grids.get_hour(recording)
		)
		.pipe(grids.assign_phase_count, recording)
		.group_by("phase", "phase_count")
		.agg(
			((pl.col("datetime").max() - pl.col("datetime").min()) + dt.timedelta(minutes=1)).alias(
				"duration"
			)
		)
	)


@DataFrameRegistry.register("event_bouts")
def build_event_bouts(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame placing every bout of the recording's events on its calendar.

	A bout gets one row for each hourly cell of the time grid it overlaps, so the table
	joins onto any analysis table by the calendar columns, and a plot finds the bins a
	bout covers with a filter. A bout ending on the hour does not reach into the next.

	Returns:
		One row per bout and calendar cell, with the bout's ``event``, ``position``
		(null for the whole habitat), ``start`` and ``end``. Empty when the recording
		declares no events.
	"""
	bouts = pl.LazyFrame(
		[
			{"event": event.name, "position": bout.position, "start": bout.start, "end": bout.end}
			for event in recording.events
			for bout in event.bouts
		],
		schema={
			"event": pl.Enum([event.name for event in recording.events]),
			"position": pl.String,
			"start": pl.Datetime("us", time_zone=recording.timeline.recording_timezone.key),
			"end": pl.Datetime("us", time_zone=recording.timeline.recording_timezone.key),
		},
	)

	return (
		bouts.with_columns(
			pl.datetime_ranges(
				pl.col("start").dt.truncate("1m"),
				(pl.col("end") - pl.duration(microseconds=1)).dt.truncate("1m"),
				interval="1m",
			).alias("minute")
		)
		.explode("minute", empty_as_null=True)
		.with_columns(
			grids.get_phase(recording, "minute"),
			grids.get_day(recording, "minute"),
			grids.get_hour(recording, "minute"),
		)
		.drop("minute")
		.unique()
		.pipe(grids.assign_phase_count, recording)
		.select("event", "position", "start", "end", *CALENDAR_COLUMNS)
		.sort("start", "event", "day", "hour", "phase_count")
	)


def event_status(recording: Recording, event_names: Sequence[str]) -> pl.LazyFrame:
	"""Per ``(day, hour)`` status of ``event_names``, for one recording's calendar.

	Not a registered step: ``Project.generate_project_table`` calls this directly, once
	it knows the union of event names declared anywhere in the project, so every
	recording's frame carries the same event columns before the vertical concat.

	A bout marks every calendar hour it touches, matching ``event_bouts``. A cell a
	bout itself covers reads ``"During"``; one sharing the bout's hour-of-day on a
	different day reads ``"Same hours, other days"``; anything else this recording
	declares the event on reads ``"Other hours"``. A name this recording does not
	declare - including ``"Any event"`` when it declares nothing at all - is null
	throughout: the recording is left out of the event, not counted as outside it.

	Args:
		recording: the recording whose calendar and ``event_bouts`` this reads.
		event_names: columns to produce; ``"Any event"`` matches every declared event.

	Returns:
		``day``, ``hour`` and one ``String`` column per name in ``event_names``.
	"""
	grid = grids.build_time_grid(recording).select("day", "hour").unique()
	declared = {event.name for event in recording.events}
	bouts = recording.load_results("event_bouts") if declared else None

	def status_column(name: str, name_bouts: pl.LazyFrame) -> pl.LazyFrame:
		during = name_bouts.select("day", "hour").unique().with_columns(_during=pl.lit(True))
		same_hour = name_bouts.select("hour").unique().with_columns(_same_hour=pl.lit(True))

		return (
			grid.join(during, on=["day", "hour"], how="left")
			.join(same_hour, on="hour", how="left")
			.select(
				"day",
				"hour",
				pl.when(pl.col("_during").is_not_null())
				.then(pl.lit("During"))
				.when(pl.col("_same_hour").is_not_null())
				.then(pl.lit("Same hours, other days"))
				.otherwise(pl.lit("Other hours"))
				.alias(name),
			)
		)

	result = grid
	for name in event_names:
		if bouts is None or (name != "Any event" and name not in declared):
			result = result.with_columns(pl.lit(None, dtype=pl.String).alias(name))
			continue

		name_bouts = bouts if name == "Any event" else bouts.filter(pl.col("event") == name)
		result = result.join(status_column(name, name_bouts), on=["day", "hour"], how="left")

	return result


def _routes_frame(routes: dict[tuple[str, str], list[str]]) -> pl.LazyFrame:
	"""``topology.unique_routes`` as a frame joinable on the step it describes."""
	return pl.LazyFrame(
		[
			(int(source), int(target), [int(antenna) for antenna in route])
			for (source, target), route in routes.items()
		],
		schema={"previous_antenna": pl.Int8, "antenna": pl.Int8, "crossed": pl.List(pl.Int8)},
		orient="row",
	)


@DataFrameRegistry.register("recording_quality")
def build_recording_quality(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of how much of each animal's movement the antennas actually caught.

	An animal that turns up at an antenna the layout does not join to the one before
	it passed antennas that never fired. Every such step is charged to the antennas
	the animal must have crossed, which is what makes the rate one per antenna rather
	than one per recording: a column that stands out is a weak antenna, a row a weak
	transponder.

	Returns:
		One row per animal and antenna, with the ``detected`` and ``missed`` pass
		counts and ``miss_rate``, the percentage of that animal's passes over that
		antenna which went unrecorded. The rate is a lower bound.
	"""
	start, end = recording.timeline.local_span
	antenna_combinations = recording.layout.antenna_combinations

	steps = (
		recording.data.filter(pl.col("datetime").is_between(start, end))
		.sort("datetime")
		.with_columns(pl.col("antenna").shift(1).over("animal_id").alias("previous_antenna"))
		.join(
			_routes_frame(topology.unique_routes(antenna_combinations)),
			on=["previous_antenna", "antenna"],
			how="left",
		)
	)

	detected = steps.group_by("animal_id", "antenna").len("detected")
	missed = (
		steps.filter(pl.col("crossed").is_not_null())
		.explode("crossed")
		.group_by("animal_id", pl.col("crossed").alias("antenna"))
		.len("missed")
	)

	antennas = sorted(int(antenna) for antenna in topology.antennas(antenna_combinations))
	grid = grids.build_animal_grid(recording, "animal_id").join(
		pl.LazyFrame({"antenna": antennas}, schema={"antenna": pl.Int8}), how="cross"
	)

	return (
		grid.join(detected, on=["animal_id", "antenna"], how="left")
		.join(missed, on=["animal_id", "antenna"], how="left")
		.with_columns(pl.col("detected", "missed").fill_null(0))
		.with_columns(
			pl.when(pl.col("detected") + pl.col("missed") > 0)
			.then(100 * pl.col("missed") / (pl.col("detected") + pl.col("missed")))
			.otherwise(0.0)
			.alias("miss_rate")
		)
		.sort("animal_id", "antenna")
	)
