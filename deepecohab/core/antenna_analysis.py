import datetime as dt

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.core import grids, transforms
from deepecohab.core.data_model import (
	CALENDAR_COLUMNS,
	AnalysisParams,
	DataFrameRegistry,
	Layout,
	Recording,
)


def _get_activity(padded: pl.LazyFrame, recording: Recording) -> pl.LazyFrame:
	"""Frame of per-animal dwell time and visit counts for every position.

	Drops tunnel directionality so the two ends of a tunnel collapse to one position,
	then sums dwell time and counts visits per animal in each position and hour.
	Interpolated pieces are excluded from the visit count but still contribute their
	time.
	"""
	return (
		transforms.remove_tunnel_directionality(padded, recording)
		.group_by([*CALENDAR_COLUMNS, "position", "animal_id"])
		.agg(
			pl.sum("time_spent").alias("time_in_position"),
			(~pl.col("interpolated")).sum().alias("visits_to_position"),
		)
	)


def _occupancy_intervals(padded: pl.LazyFrame, recording: Recording) -> pl.LazyFrame:
	"""Frame of occupancy intervals for every real position, tunnels undirected.

	The shared front half of the occupancy sweep. Solitary time and co-presence read the
	same spans and differ only in how many animals they keep, so the two have to see the
	same positions. Directionality is dropped first, or two animals passing through one
	tunnel in opposite directions would sit in different positions and never meet, and
	``undefined`` is excluded because it is not a place.
	"""
	return (
		transforms.remove_tunnel_directionality(padded, recording)
		.filter(pl.col("position") != Layout.UNDEFINED)
		.pipe(transforms.add_occupancy_bounds)
	)


def _get_time_alone(
	padded: pl.LazyFrame, recording: Recording, params: AnalysisParams
) -> pl.LazyFrame:
	"""Frame of how long each animal occupied a position with no other animal present.

	A span from :func:`transforms.occupancy_spans` holding one animal is time that
	animal spent alone. Spans shorter than ``params.minimum_time_alone`` and
	``undefined`` positions are excluded.
	"""
	return (
		transforms.occupancy_spans(_occupancy_intervals(padded, recording))
		.filter(
			pl.col("animals_present") == 1,
			pl.col("end") - pl.col("time") > pl.duration(seconds=params.minimum_time_alone),
		)
		.select(
			"animal_id",
			"position",
			pl.col("time").alias("datetime"),
			pl.col("end").sub(pl.col("time")).alias("duration"),
		)
		# The spans are new intervals rather than registrations, so they take their own
		# calendar columns instead of inheriting any.
		.with_columns(
			grids.get_phase(recording), grids.get_day(recording), grids.get_hour(recording)
		)
		.pipe(grids.assign_phase_count, recording)
		.group_by("animal_id", "position", *CALENDAR_COLUMNS)
		.agg(pl.col("duration").sum().alias("time_alone"))
	)


@DataFrameRegistry.register("activity_df", requires=["padded_df"])
def calculate_activity(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of per-animal occupancy, visits and solitary time for every position.

	Combines dwell time and visit counts with solitary occupancy and reindexes both
	onto the dense experiment grid, so every animal, position and hour is present and
	cells with no activity read ``0``.

	Returns:
		``time_in_position``, ``visits_to_position`` and ``time_alone`` per animal,
		position and hour.
	"""
	padded = recording.load_results("padded_df")

	activity = pl.concat(
		[_get_activity(padded, recording), _get_time_alone(padded, recording, params)],
		how="align",
	)

	return grids.reindex_onto_grid(
		activity, recording, "animal_id", positions=recording.layout.positions_non_directional
	)


@DataFrameRegistry.register("match_df", requires=["main_df"])
def calculate_matches(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of chasing events, one row each.

	A chasing event is a loser entering a tunnel from a cage and a winner following
	through the same tunnel within ``params.chasing_time_window`` seconds. This table
	is the shared input for both the per-hour chasing counts and the ranking, so it is
	computed once here.

	Returns:
		One row per chasing event, with winner, loser, tunnel, how long the chase
		lasted, and the calendar columns of the winner's registration.
	"""
	registrations = recording.load_results("main_df").sort("datetime")

	cages = recording.layout.cage_names
	tunnels = recording.layout.tunnel_names_directional

	# A row's `position`/`datetime` mark the position the animal left and when, so the winner's
	# `tunnel_entry` is its entry and the loser's `loser_exit` is its exit at the far end.
	# Winner candidates: a tunnel exit whose previous read was a cage, carrying that tunnel's
	# entry time. Each event is dated by the winner, so it also takes the winner's calendar.
	chasing = (
		registrations.with_columns(
			pl.col("datetime").shift(1).over("animal_id").alias("tunnel_entry"),
			pl.col("position").shift(1).over("animal_id").alias("previous_position"),
		)
		.filter(pl.col("position").is_in(tunnels), pl.col("previous_position").is_in(cages))
		.select(
			"position",
			pl.col("animal_id").alias("winner"),
			pl.col("datetime").alias("winner_exit"),
			"tunnel_entry",
			*CALENDAR_COLUMNS,
		)
	)

	chased = registrations.filter(pl.col("position").is_in(tunnels)).select(
		"position",
		pl.col("animal_id").alias("loser"),
		pl.col("datetime").alias("loser_exit"),
	)

	# Pair each loser exit with every winner still inside the same tunnel via a sweep (as in
	# calculate_pairwise_meetings). Each winner pass is an enter(+bit)/leave(-bit) event and each
	# loser exit a zero-delta query, so the per-tunnel cumulative bit-sum is the presence bitmask
	# of winners inside (one bit per animal, capped at ~63, far above any EcoHab study).
	elapsed = pl.col("loser_exit") - pl.col("tunnel_entry")
	shortest, longest = (pl.duration(seconds=bound) for bound in params.chasing_time_window)

	winners = chasing.with_columns(
		pl.lit(2, dtype=pl.Int64)
		.pow(pl.col("winner").to_physical().cast(pl.Int64))
		.cast(pl.Int64)
		.alias("bit")
	)
	# Maps each winner's single-bit mask value back to its id, for decoding the bitmask.
	winner_lookup = winners.select("winner", "bit").unique()

	# `kind` orders ties at equal timestamps -- enter(0) < query(1) < leave(2) -- so a winner counts
	# as inside iff tunnel_entry <= loser_exit < winner_exit; the strict window below re-asserts this.
	enters = winners.select(
		pl.col("tunnel_entry").alias("time"),
		"position",
		pl.col("bit").alias("bit_delta"),
		pl.lit(0, dtype=pl.Int8).alias("kind"),
	)
	leaves = winners.select(
		pl.col("winner_exit").alias("time"),
		"position",
		pl.col("bit").neg().alias("bit_delta"),
		pl.lit(2, dtype=pl.Int8).alias("kind"),
	)
	queries = chased.select(
		pl.col("loser_exit").alias("time"),
		"position",
		pl.lit(0, dtype=pl.Int64).alias("bit_delta"),
		pl.lit(1, dtype=pl.Int8).alias("kind"),
		"loser",
	)

	# At each loser exit, `mask` is the OR-set of bits of the winners then inside the tunnel.
	mask_at_query = (
		pl.concat([enters, leaves, queries], how="diagonal")
		.sort("position", "time", "kind")
		.with_columns(pl.col("bit_delta").cum_sum().over("position").alias("mask"))
		.filter(pl.col("kind") == 1)
		.select("position", "loser", pl.col("time").alias("loser_exit"), "mask")
	)

	# Decode the mask into candidate winners, then recover each winner's open pass with an as-of join
	# (its latest entry at or before the loser exit); a plain equi-join would match all passes and be quadratic.
	candidates = mask_at_query.join(winner_lookup, how="cross").filter(
		(pl.col("mask") & pl.col("bit")) != 0
	)

	return (
		candidates.sort("loser_exit")
		.join_asof(
			winners.select(
				"position", "winner", "winner_exit", "tunnel_entry", *CALENDAR_COLUMNS
			).sort("tunnel_entry"),
			left_on="loser_exit",
			right_on="tunnel_entry",
			by=["position", "winner"],
			strategy="backward",
			# Both sides are globally sorted on the as-of key above, which polars can't verify per `by` group.
			check_sortedness=False,
		)
		.filter(
			elapsed > shortest,
			elapsed < longest,
			pl.col("loser_exit") < pl.col("winner_exit"),
			pl.col("winner") != pl.col("loser"),
		)
		.select(
			"position",
			"winner",
			"loser",
			pl.col("winner_exit").alias("datetime"),
			elapsed.alias("chasing_length"),
			*CALENDAR_COLUMNS,
		)
		.sort("datetime")
	)


@DataFrameRegistry.register("chasings_df", requires=["match_df"])
def calculate_chasings(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame counting chasing events per ordered pair of animals, tunnel and hour.

	The event-level ``winner``/``loser`` become ``chaser``/``chased`` here, since in a
	chasing the winner is the one doing the chasing.

	Returns:
		A ``chasings`` count per chaser, chased, tunnel and hour, on the dense grid.
	"""
	chasings = (
		recording.load_results("match_df")
		.group_by([*CALENDAR_COLUMNS, "position", "winner", "loser"])
		.len(name="chasings")
		.rename({"winner": "chaser", "loser": "chased"})
	)

	return grids.reindex_onto_grid(
		chasings,
		recording,
		("chaser", "chased"),
		ordered=True,
		positions=recording.layout.tunnel_names_directional,
	)


@DataFrameRegistry.register("ranking", requires=["match_df"])
def calculate_ranking(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of a dominance ranking, from replaying chasing events as matches.

	Each chasing event is a one-on-one match the winner won. Replaying them in order
	updates every animal's skill rating after each match, so the result is the full
	rating trajectory rather than only the final standings. ``params.prev_ranking``
	continues from an earlier recording of the same animals instead of from scratch.

	Returns:
		One row per animal after each match, with ``mu``, ``sigma``, ``ordinal``, the
		``social_rank`` its ordinal puts it in at that point, and the calendar columns
		of the match.
	"""
	animal_tags = recording.cohort.animal_tags

	model = PlackettLuce(limit_sigma=True, balance=True)
	ranking = {player: model.rating() for player in animal_tags}

	previous_ranking = params.prev_ranking
	if previous_ranking is not None:
		if isinstance(previous_ranking, pl.LazyFrame):
			previous_ranking = previous_ranking.lazy().collect()

		foreign_animals = set(previous_ranking.get_column("animal_id").to_list()) - set(animal_tags)
		if foreign_animals:
			raise ValueError(
				"prev_ranking contains animals that are not in the current cohort: "
				f"{sorted(foreign_animals)}. It must come from a recording of the same animals."
			)

		for name, mu, sigma in previous_ranking.select("animal_id", "mu", "sigma").iter_rows():
			ranking[name] = model.rating(mu=mu, sigma=sigma)

	matches = (
		recording.load_results("match_df")
		.select("loser", "winner", "datetime", *CALENDAR_COLUMNS)
		.sort("datetime")
		.collect()
	)

	rows: list[dict] = []
	for loser_name, winner_name, moment, *calendar in matches.iter_rows():
		new_ratings = model.rate([[ranking[loser_name]], [ranking[winner_name]]], ranks=[1, 0])

		ranking[loser_name] = new_ratings[0][0]
		ranking[winner_name] = new_ratings[1][0]

		for animal, rating in ranking.items():
			rows.append(
				{
					"animal_id": animal,
					"mu": rating.mu,
					"sigma": rating.sigma,
					"ordinal": round(rating.ordinal(), 3),
					"datetime": moment,
					**dict(zip(CALENDAR_COLUMNS, calendar, strict=True)),
				}
			)

	schema = {
		"animal_id": pl.String,
		"mu": pl.Float64,
		"sigma": pl.Float64,
		"ordinal": pl.Float64,
	} | {name: matches.schema[name] for name in ("datetime", *CALENDAR_COLUMNS)}

	return pl.LazyFrame(rows, schema=schema).with_columns(
		pl.when(pl.col("ordinal") == pl.col("ordinal").max().over("datetime"))
		.then(pl.lit("dominant"))
		.when(pl.col("ordinal") == pl.col("ordinal").min().over("datetime"))
		.then(pl.lit("subordinate"))
		.otherwise(pl.lit("middle"))
		.cast(pl.Enum(["dominant", "middle", "subordinate"]))
		.alias("social_rank")
	)


def get_prev_ranking(ranking: pl.LazyFrame | pl.DataFrame) -> pl.LazyFrame:
	"""Frame collapsing a ranking trajectory to each animal's latest rating.

	:func:`calculate_ranking` emits one row per animal after every match; this keeps
	only the last ``mu``/``sigma`` per animal, which is what
	``AnalysisParams.prev_ranking`` expects. Feed it back to continue ranking the same
	animals from where a previous recording left off.
	"""
	return (
		ranking.lazy()
		.sort("datetime")
		.group_by("animal_id", maintain_order=True)
		.agg(pl.last("mu"), pl.last("sigma"))
	)


@DataFrameRegistry.register("pairwise_meetings", requires=["padded_df"])
def calculate_pairwise_meetings(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of co-occurrences and shared time for every pair of animals, position and hour.

	A sweep over occupancy exposes, at every instant, which animals are present. Pairs are
	formed from each span's occupants, contiguous spans of the same pair are stitched into
	one continuous meeting, meetings shorter than ``params.minimum_time`` seconds are
	dropped, and the rest are summed onto the dense grid.

	Cages and tunnels are both covered, on the same intervals ``_get_time_alone`` reads.
	Tunnel co-presence is physically different - two animals in a two-antenna tunnel are in
	contact, and such a meeting is what the tube test reads as a contest - but it is held to
	the same ``params.minimum_time`` for now; whether that threshold suits tunnels is a
	question for real data.

	Returns:
		``time_together`` in seconds and ``pairwise_encounters`` per pair, position and
		hour.
	"""
	padded = recording.load_results("padded_df")

	pairs = transforms.cooccupancy_spans(_occupancy_intervals(padded, recording)).with_columns(
		(pl.col("end") - pl.col("time")).alias("duration")
	)

	# Drop meetings whose total continuous co-presence is below minimum_time.
	pair_group = ["animal_id", "animal_id_2", "position"]
	meeting_duration = pairs.group_by(*pair_group, "meeting_id").agg(
		pl.sum("duration").alias("meeting_duration")
	)
	pairs = pairs.join(meeting_duration, on=[*pair_group, "meeting_id"]).filter(
		pl.col("meeting_duration") > dt.timedelta(seconds=params.minimum_time)
	)

	pairwise_meetings = (
		# The spans are new intervals rather than registrations, so they take their own
		# calendar columns instead of inheriting any.
		pairs.with_columns(
			grids.get_phase(recording, "time"),
			grids.get_day(recording, "time"),
			grids.get_hour(recording, "time"),
		)
		.pipe(grids.assign_phase_count, recording)
		.group_by([*CALENDAR_COLUMNS, "position", "animal_id", "animal_id_2"])
		.agg(
			pl.sum("duration").alias("time_together"),
			pl.col("is_new").sum().alias("pairwise_encounters"),
		)
	)

	return grids.reindex_onto_grid(
		pairwise_meetings,
		recording,
		("animal_id", "animal_id_2"),
		ordered=False,
		positions=recording.layout.positions_non_directional,
	)


@DataFrameRegistry.register(
	"incohort_sociability", requires=["pairwise_meetings", "activity_df", "phase_durations"]
)
def calculate_incohort_sociability(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of in-cohort sociability: observed togetherness minus chance expectation.

	For each pair and cage, the time the pair actually spent together, as a fraction
	of phase duration, is compared against the time they would be expected to share by
	chance given each animal's independent occupancy of that cage. ``sociability`` is
	the observed-minus-chance difference summed over cages, so a positive value means
	the pair sought each other out. For background see DOI:10.7554/eLife.19532.

	Returns:
		``proportion_together`` and ``sociability`` per phase for every pair.
	"""
	phase_durations = recording.load_results("phase_durations")
	time_together = recording.load_results("pairwise_meetings")
	activity = recording.load_results("activity_df")

	core_columns = ["phase", "day", "phase_count", "animal_id", "animal_id_2"]
	phase_seconds = pl.col("duration").dt.total_seconds(fractional=True)

	time_together = (
		time_together.filter(pl.col("position").is_in(recording.layout.cage_names))
		.group_by([*core_columns, "position"])
		.agg(pl.sum("time_together"))
	)

	activity_per_phase = (
		activity.filter(pl.col("position").is_in(recording.layout.cage_names))
		.group_by(["phase", "day", "phase_count", "position", "animal_id"])
		.agg(pl.sum("time_in_position"))
	)

	expected_together = activity_per_phase.join(
		activity_per_phase, on=["phase", "day", "phase_count", "position"], suffix="_2"
	).filter(pl.col("animal_id") < pl.col("animal_id_2"))

	return (
		time_together.join(expected_together, on=[*core_columns, "position"], how="left")
		.join(phase_durations, on=["phase_count", "phase"], how="left")
		.with_columns(
			pl.col("time_together").dt.total_seconds(fractional=True) / phase_seconds,
			(
				pl.col("time_in_position").dt.total_seconds(fractional=True)
				* pl.col("time_in_position_2").dt.total_seconds(fractional=True)
				/ phase_seconds**2
			).alias("chance"),
		)
		.group_by(core_columns)
		.agg(
			pl.sum("time_together").alias("proportion_together"),
			(pl.col("time_together") - pl.col("chance")).sum().alias("sociability"),
		)
		.sort(core_columns)
	)


@DataFrameRegistry.register(
	"feature_df",
	requires=["chasings_df", "pairwise_meetings", "activity_df", "main_df"],
)
def calculate_features(recording: Recording, params: AnalysisParams) -> pl.LazyFrame:
	"""Frame of per-animal metrics, each paired with the opportunity it arose from.

	Collapses the upstream tables to one value per animal per hour for each metric -
	chasings given and received, activity, time alone, and time together with
	encounters - and pairs every value with the exposure it should be read against. A
	rate is ``sum(value) / sum(exposure)`` over whatever grouping is wanted, so the
	hourly rows sum to a phase, a day or the whole recording without distorting the
	result.

	Durations are held in hours, so a duration metric's rate is a fraction of the time
	observed and a count metric's rate is a count per hour. Metrics that need a partner
	are exposed per available partner, which keeps cohorts of different sizes
	comparable. ``n_chasing_per_detection`` is the same chase count as ``n_chasing``
	exposed per antenna detection instead, normalising by how much the animal was seen
	rather than by how many partners it had.

	Returns:
		One row per animal, hour and metric, with ``value`` and ``exposure``.
	"""
	solo = ["activity", "time_alone"]
	paired = ["time_together", "pairwise_encounters", "n_chasing", "n_chased"]
	per_detection = ["n_chasing_per_detection"]
	keys = [*CALENDAR_COLUMNS, "animal_id"]

	chasings = recording.load_results("chasings_df")
	pairwise_meetings = recording.load_results("pairwise_meetings")

	# padded_df tiles each animal's whole timeline, so its time summed over positions is
	# how long that animal was observed for in the cell - the denominator for the rest.
	observed = (
		recording.load_results("activity_df")
		.group_by(keys)
		.agg(
			pl.sum("visits_to_position").alias("activity"),
			pl.sum("time_alone").dt.total_hours(fractional=True),
			pl.sum("time_in_position").dt.total_hours(fractional=True).alias("observed_hours"),
		)
	)

	n_detections = (
		recording.load_results("main_df").group_by(keys).agg(pl.len().alias("n_detections"))
	)

	n_chasing = (
		chasings.group_by([*CALENDAR_COLUMNS, "chaser"])
		.agg(pl.sum("chasings").alias("n_chasing"))
		.rename({"chaser": "animal_id"})
	)

	n_chased = (
		chasings.group_by([*CALENDAR_COLUMNS, "chased"])
		.agg(pl.sum("chasings").alias("n_chased"))
		.rename({"chased": "animal_id"})
	)

	pairwise_meetings = (
		pairwise_meetings.unpivot(
			on=["animal_id", "animal_id_2"],
			index=[*CALENDAR_COLUMNS, "time_together", "pairwise_encounters"],
			variable_name="_drop",
			value_name="col",
		)
		.drop("_drop")
		.group_by([*CALENDAR_COLUMNS, "col"])
		.agg(
			pl.sum("time_together").dt.total_hours(fractional=True),
			pl.sum("pairwise_encounters"),
		)
		.rename({"col": "animal_id"})
	)

	partners = recording.cohort.n_mice - 1

	return (
		pl.concat(
			[observed, n_detections, n_chasing, n_chased, pairwise_meetings],
			how="align",
		)
		.fill_null(0)
		.with_columns(pl.col("n_chasing").alias("n_chasing_per_detection"))
		.with_columns(pl.col([*solo, *paired, *per_detection]).cast(pl.Float64))
		.unpivot(
			on=[*solo, *paired, *per_detection],
			index=[*keys, "observed_hours", "n_detections"],
			variable_name="metric",
			value_name="value",
		)
		.with_columns(
			pl.when(pl.col("metric").is_in(per_detection))
			.then(pl.col("n_detections"))
			.when(pl.col("metric").is_in(paired))
			.then(pl.col("observed_hours") * partners)
			.otherwise(pl.col("observed_hours"))
			.alias("exposure")
		)
		.drop("observed_hours", "n_detections")
		.sort(*keys, "metric")
	)
