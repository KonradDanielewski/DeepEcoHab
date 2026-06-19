from typing import Any, Literal

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.core.registries import df_registry
from deepecohab.utils import auxfun


def _get_activity(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Aggregate per-animal occupancy and visit counts for every position.

	Drops tunnel directionality so the two ends of a tunnel collapse to one
	position, then sums dwell time and counts visits per animal in each
	position/hour cell. Interpolated reads (synthesised to bridge gaps, not real
	antenna detections) are excluded from the visit count but still contribute
	their time.

	Args:
		lf: Padded antenna table (``padded_df``).
		cfg: Path or mapping resolved by ``read_config``.

	Returns:
		LazyFrame with ``time_in_position`` and ``visits_to_position`` per
		phase/day/phase_count/hour/position/animal.
	"""
	lf = auxfun.remove_tunnel_directionality(lf, cfg)

	return lf.group_by(["phase", "day", "phase_count", "hour", "position", "animal_id"]).agg(
		pl.sum("time_spent").alias("time_in_position"),
		(~pl.col("interpolated")).sum().alias("visits_to_position"),
	)


def _get_time_alone(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Compute how long each animal occupied a position with no other animal present.

	Uses a sweep-line over occupancy intervals: each animal's stay in a position
	becomes an enter (+1) and a leave (-1) event, and a running ``n_active`` count
	per position tracks how many animals are present at any instant. Spans where
	exactly one animal is present (``n_active == 1``) are solitary; their length is
	the time until the next event. The occupant is recovered with a second signed
	counter (``id_active``): summing the per-animal physical codes leaves the lone
	occupant's code standing when only one is active, which is mapped back to the
	enum label via ``id_lookup``. ``undefined`` positions are excluded.

	Args:
		lf: Padded antenna table (``padded_df``).
		cfg: Path or mapping resolved by ``read_config``.

	Returns:
		LazyFrame with ``time_alone`` (seconds) per
		phase/day/phase_count/hour/position/animal.
	"""
	lf = auxfun.remove_tunnel_directionality(lf, cfg)
	df_intervals = lf.filter(pl.col("position") != "undefined").with_columns(
		pl.col("datetime").alias("end"),
		(pl.col("datetime").sub(pl.col("time_spent").mul(1000_000).cast(pl.Duration("us")))).alias(
			"start"
		),
		pl.col("animal_id").to_physical().cast(pl.Int64).alias("id_code"),
	)

	# Small lookup to restore enum labels after the sweep (one row per animal).
	id_lookup = df_intervals.select("animal_id", "id_code").unique()

	enters = df_intervals.select(
		pl.col("start").alias("time"),
		"position",
		pl.lit(1, dtype=pl.Int32).alias("delta"),
		pl.col("id_code").alias("id_delta"),
	)
	leaves = df_intervals.select(
		pl.col("end").alias("time"),
		"position",
		pl.lit(-1, dtype=pl.Int32).alias("delta"),
		pl.col("id_code").neg().alias("id_delta"),
	)

	events = (
		pl.concat([enters, leaves])
		.sort("position", "time")
		.with_columns(
			pl.col("delta").cum_sum().over("position").alias("n_active"),
			pl.col("id_delta").cum_sum().over("position").alias("id_active"),
			pl.col("time").shift(-1).over("position").alias("time_next"),
		)
	)

	time_alone = (
		events.filter(
			pl.col("time_next").is_not_null(),
			(pl.col("n_active") == 1),
			(pl.col("time_next") > pl.col("time")),
		)
		.select(
			pl.col("position"),
			pl.col("time").alias("datetime"),
			pl.col("time_next").sub(pl.col("time")).alias("duration"),
			pl.col("id_active").alias("id_code"),
		)
		.with_columns(auxfun.get_phase(cfg), auxfun.get_day(), auxfun.get_hour())
		.sort("day", "phase")
		.pipe(auxfun.get_phase_count)
		.group_by("id_code", "position", "phase", "day", "phase_count", "hour")
		.agg(pl.col("duration").sum().dt.total_seconds(fractional=True).alias("time_alone"))
		.join(id_lookup, on="id_code", how="left")
		.select("animal_id", "position", "phase", "day", "phase_count", "hour", "time_alone")
	)

	return time_alone


@df_registry.register_step("activity_df", requires=["padded_df"])
def calculate_activity(cfg: dict[str, Any], **kwargs) -> pl.LazyFrame:
	"""Build the per-animal activity table: occupancy, visits and solitary time.

	Combines two views of ``padded_df`` (per-position dwell time and visit counts
	from :func:`_get_activity`, and solitary occupancy from :func:`_get_time_alone`)
	and reindexes them onto the dense experiment grid, so every animal/position/hour
	cell is present with absent cells filled with ``0``.

	Args:
	    cfg: resolved project config.

	Returns:
	    LazyFrame with ``time_in_position``, ``visits_to_position`` and
	    ``time_alone`` per phase/day/phase_count/hour/position/animal.
	"""
	padded_df: pl.LazyFrame = auxfun._get_data(cfg, key="padded_df")

	per_position_lf: pl.LazyFrame = _get_activity(padded_df, cfg)
	time_alone: pl.LazyFrame = _get_time_alone(padded_df, cfg)

	return (
		auxfun.build_experiment_grid(cfg)
		.join(
			per_position_lf,
			on=["phase", "day", "phase_count", "hour", "position", "animal_id"],
			how="left",
		)
		.join(
			time_alone,
			on=["phase", "day", "phase_count", "hour", "position", "animal_id"],
			how="left",
		)
		.fill_null(0)
	)


@df_registry.register_step("ranking", requires=["match_df"])
def calculate_ranking(cfg: dict[str, Any], **kwargs) -> pl.LazyFrame:
	"""Estimate a dominance ranking by replaying chasing events as Plackett-Luce matches.

	Each chasing event in ``match_df`` is treated as a one-on-one match (winner
	beats loser) and replayed in chronological order, updating every animal's
	skill rating (``mu``/``sigma`` and its derived ``ordinal``) after each match.
	One row per animal is emitted after every match, so the result is the full
	rating trajectory over time, not just the final standings.

	Args:
	    cfg: resolved project config.
	    prev_ranking: optional starting ratings from an earlier recording of the
	        same animals, so ranking continues from their previous estimate instead
	        of from scratch. Expects a DataFrame/LazyFrame with ``animal_id``,
	        ``mu`` and ``sigma`` columns; build it from a prior ``ranking`` with
	        :func:`get_prev_ranking`.

	Returns:
	    LazyFrame with ``mu``, ``sigma``, ``ordinal`` and ``datetime`` per animal,
	    one row per animal after each match.
	"""
	prev_ranking = kwargs.get("prev_ranking")
	animal_ids: list[str] = cfg["animal_ids"]

	model = PlackettLuce(limit_sigma=True, balance=True)
	# Every animal starts at the model default; animals present in prev_ranking
	# resume from their previously estimated mu/sigma instead.
	ranking = {player: model.rating() for player in animal_ids}

	if prev_ranking is not None:
		if isinstance(prev_ranking, pl.LazyFrame):
			prev_ranking = prev_ranking.collect()
		for name, mu, sigma in prev_ranking.select("animal_id", "mu", "sigma").iter_rows():
			ranking[name] = model.rating(mu=mu, sigma=sigma)

	match_df: pl.DataFrame = (
		auxfun._get_data(cfg, "match_df")
		.select("loser", "winner", "datetime")
		.sort("datetime")
		.collect()
	)
	rows: list[dict[str, Any]] = []

	for loser_name, winner_name, dtime in match_df.iter_rows():
		new_ratings = model.rate(
			[[ranking[loser_name]], [ranking[winner_name]]],
			ranks=[1, 0],
		)

		ranking[loser_name] = new_ratings[0][0]
		ranking[winner_name] = new_ratings[1][0]

		for animal, rating in ranking.items():
			rows.append(
				{
					"animal_id": animal,
					"mu": rating.mu,
					"sigma": rating.sigma,
					"ordinal": round(rating.ordinal(), 3),
					"datetime": dtime,
				}
			)

	ranking_df = pl.LazyFrame(rows).with_columns(
		auxfun.get_phase(cfg),
		auxfun.get_day(),
		auxfun.get_hour(),
	)

	return ranking_df


def get_prev_ranking(ranking: pl.LazyFrame | pl.DataFrame) -> pl.LazyFrame:
	"""Collapse a ``ranking`` trajectory to each animal's latest rating.

	``calculate_ranking`` emits one row per animal after every match; this keeps
	only the chronologically last ``mu``/``sigma`` per animal, yielding exactly
	the ``animal_id``/``mu``/``sigma`` frame that ``calculate_ranking`` accepts as
	its ``prev_ranking`` argument. Feed it back to continue ranking the same
	animals from where a previous recording left off.

	Args:
	    ranking: a ``ranking`` result (LazyFrame or DataFrame).

	Returns:
	    LazyFrame with one row per animal and columns ``animal_id``, ``mu``,
	    ``sigma``.
	"""
	return (
		ranking.lazy()
		.sort("datetime")
		.group_by("animal_id", maintain_order=True)
		.agg(pl.last("mu"), pl.last("sigma"))
	)


@df_registry.register_step("match_df", requires=["main_df"])
def calculate_matches(
	cfg: dict[str, Any],
	chasing_time_window: tuple[float, float] = (0.1, 1.2),
	**kwargs,
) -> pl.LazyFrame:
	"""Builds the event-level chasing table: one row per chasing event.

	A chasing event is a loser entering a tunnel from a cage and a winner
	following through the same tunnel within ``chasing_time_window`` seconds.
	This table is the shared input for both ``chasings_df`` (per-hour counts) and
	``ranking`` (sequential match outcomes), so it is computed once here.

	Args:
	    cfg: resolved project config.
	    chasing_time_window: min and max length of the chasing event in seconds.
	        Defaults to [0.1, 1.2].

	Returns:
	    LazyFrame of chasing events with winner/loser, the grid columns and the
	    chasing length.
	"""
	lf: pl.LazyFrame = auxfun._get_data(cfg, key="main_df")

	cages: list[str] = cfg["cages"]
	tunnels: list[str] = cfg["tunnels"]

	chased = lf.filter(
		pl.col("position").is_in(tunnels),
	)
	chasing = lf.with_columns(
		pl.col("datetime").shift(1).over("animal_id").alias("tunnel_entry"),
		pl.col("position").shift(1).over("animal_id").alias("prev_position"),
	)

	intermediate = chased.join(
		chasing, on=["phase", "day", "hour", "phase_count"], suffix="_chasing"
	).filter(
		pl.col("animal_id") != pl.col("animal_id_chasing"),
		pl.col("position") == pl.col("position_chasing"),
		pl.col("prev_position").is_in(cages),
		(pl.col("datetime") - pl.col("tunnel_entry"))
		.dt.total_seconds(fractional=True)
		.is_between(*chasing_time_window, closed="none"),
		pl.col("datetime") < pl.col("datetime_chasing"),
	)

	# Event-level table. Grid columns are kept so chasings_df can aggregate it
	# directly; datetime is the winner's read time (matches the ranking order).
	return intermediate.select(
		pl.col("phase"),
		pl.col("day"),
		pl.col("phase_count"),
		pl.col("hour"),
		pl.col("position"),
		pl.col("animal_id_chasing").alias("winner"),
		pl.col("animal_id").alias("loser"),
		pl.col("datetime_chasing").alias("datetime"),
		(pl.col("datetime") - pl.col("tunnel_entry"))
		.dt.total_seconds(fractional=True)
		.alias("chasing_length"),
	)


@df_registry.register_step("chasings_df", requires=["match_df"])
def calculate_chasings(cfg: dict[str, Any], **kwargs) -> pl.LazyFrame:
	"""Count chasing events per ordered pair of animals for each tunnel and hour.

	Per-hour aggregation of the event-level ``match_df``, reindexed onto the dense
	grid so every chaser/chased/tunnel/hour cell is present (absent cells are ``0``).
	The match-level ``winner``/``loser`` are renamed to ``chaser``/``chased`` here,
	since in a chasing the winner is the chaser and the loser is the chased.

	Args:
	    cfg: resolved project config.

	Returns:
	    LazyFrame with a ``chasings`` count per chaser/chased/tunnel/hour.
	"""
	matches: pl.LazyFrame = auxfun._get_data(cfg, key="match_df")

	chasings = (
		matches.group_by(["phase", "day", "phase_count", "hour", "position", "winner", "loser"])
		.len(name="chasings")
		.rename({"winner": "chaser", "loser": "chased"})
	)

	return auxfun.reindex_onto_grid(
		chasings,
		cfg,
		("chaser", "chased"),
		ordered=True,
		positions=auxfun.get_positions(cfg, "tunnels_directional"),
	)


@df_registry.register_step("tube_test_df", requires=["main_df"])
def calculate_tube_test(
	cfg: dict[str, Any],
	winner_behavior: Literal["CHASE", "GUARD", "BOTH"] = "BOTH",
	max_dwell: float = 10.0,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates tube test events per pair of mice for each hour.

	A tube test event is a head-on tunnel encounter: the loser entered a tunnel
	and retreated to the cage it came from, while the winner entered the same
	tunnel from the opposite end during an overlapping interval and exited later.

	Args:
	    cfg: resolved project config.
	    winner_behavior: which winner outcomes to include.
	        ``"CHASE"`` - the winner follows the loser into the cage the loser
	        retreated to (``next_position_winner == next_position``).
	        ``"GUARD"`` - the winner returns to its own origin cage to hold the
	        resource (``next_position_winner == prev_position_winner``).
	        ``"BOTH"`` - either of the above (the union; events where the winner
	        ends up in neither cage, e.g. a third tunnel, are excluded).
	    max_dwell: maximum tunnel dwell time, in seconds, for a segment to count.
	        Retreat segments synthesised from repeated antenna reads can have
	        inflated durations (the mouse left the tunnel and returned to the same
	        antenna); capping the dwell prevents those from producing phantom
	        overlaps. Defaults to 10.0.

	Returns:
	    LazyFrame of tube test events
	"""
	lf: pl.LazyFrame = auxfun._get_data(cfg, key="main_df")

	tunnels: list[str] = auxfun.get_positions(cfg, "tunnels")

	lf = auxfun.update_repeat_antenna_position(lf)
	lf = auxfun.remove_tunnel_directionality(lf, cfg)
	lf = lf.with_columns(
		(pl.col("datetime") - pl.duration(seconds=pl.col("time_spent"))).alias("tunnel_entry"),
		pl.col("position").shift(1).over("animal_id").alias("prev_position"),
		pl.col("position").shift(-1).over("animal_id").alias("next_position"),
	)

	# Loser: entered a tunnel and retreated to the cage it came from. The dwell
	# cap drops inflated repeat-antenna segments that are not real tunnel time.
	loser = lf.filter(
		pl.col("position").is_in(tunnels),
		pl.col("prev_position") == pl.col("next_position"),
		pl.col("time_spent") <= max_dwell,
	)

	intermediate = (
		loser.join(lf, on=["phase", "day", "phase_count", "position"], suffix="_winner")
		.filter(
			pl.col("animal_id") != pl.col("animal_id_winner"),
			# entered from opposite ends of the same tunnel
			pl.col("prev_position") != pl.col("prev_position_winner"),
			# loser exits first (also dedups the symmetric winner/loser pairing)
			pl.col("datetime") < pl.col("datetime_winner"),
			# winner genuinely occupied the tunnel, not an inflated segment
			pl.col("time_spent_winner") <= max_dwell,
		)
		.with_columns(
			(
				pl.min_horizontal(["datetime", "datetime_winner"])
				- pl.max_horizontal(["tunnel_entry", "tunnel_entry_winner"])
			)
			.dt.total_seconds(fractional=True)
			.alias("overlap_duration")
		)
		.filter(pl.col("overlap_duration") > 0)
	)

	# CHASE: winner follows the loser into the cage it retreated to.
	# GUARD: winner returns to its own origin cage to hold the resource.
	chase = pl.col("next_position_winner") == pl.col("next_position")
	guard = pl.col("next_position_winner") == pl.col("prev_position_winner")
	match winner_behavior:
		case "CHASE":
			intermediate = intermediate.filter(chase)
		case "GUARD":
			intermediate = intermediate.filter(guard)
		case "BOTH":
			intermediate = intermediate.filter(chase | guard)

	tube_test = (
		intermediate.group_by(
			["phase", "day", "phase_count", "hour", "animal_id", "animal_id_winner"]
		)
		.len(name="tube_test")
		.rename({"animal_id": "loser", "animal_id_winner": "winner"})
	)

	return auxfun.reindex_onto_grid(tube_test, cfg, ("winner", "loser"), ordered=True)


@df_registry.register_step("pairwise_meetings", requires=["padded_df"])
def calculate_pairwise_meetings(
	cfg: dict[str, Any],
	minimum_time: int | float | None = 2,
	**kwargs,
) -> pl.LazyFrame:
	"""Count co-occurrences and shared time for every pair of animals per cage and hour.

	Self-joins cage occupancy intervals and, for each unordered pair sharing a
	cage, measures the temporal overlap of their stays. Overlaps shorter than
	``minimum_time`` are discarded, then the survivors are summed into shared time
	and meeting counts and reindexed onto the dense grid. Slow, because it
	materialises every overlapping interval pair before aggregating.

	Args:
	    cfg: resolved project config.
	    minimum_time: minimum overlap, in seconds, for a co-occurrence to count as
	        a meeting; shorter overlaps are dropped. Defaults to 2.

	Returns:
	    LazyFrame with ``time_together`` (seconds) and ``pairwise_encounters`` per
	    pair/cage/hour.
	"""
	padded_df = auxfun._get_data(cfg, key="padded_df")

	cages: list[str] = cfg["cages"]

	lf = (
		padded_df.filter(pl.col("position").is_in(cages))
		.with_columns(
			(pl.col("datetime") - pl.duration(seconds=pl.col("time_spent"))).alias("event_start")
		)
		.rename({"datetime": "event_end"})
	)

	joined = (
		lf.join(
			lf,
			on=["phase", "day", "phase_count", "position"],
			how="inner",
			suffix="_2",
		)
		.filter(
			pl.col("animal_id") < pl.col("animal_id_2"),
		)
		.with_columns(
			(
				pl.min_horizontal(["event_end", "event_end_2"])
				- pl.max_horizontal(["event_start", "event_start_2"])
			)
			.dt.total_seconds(fractional=True)
			.round(3)
			.alias("overlap_duration")
		)
		.filter(pl.col("overlap_duration") > minimum_time)
	)

	pairwise_meetings = (
		joined.group_by(
			"phase", "day", "phase_count", "hour", "position", "animal_id", "animal_id_2"
		).agg(
			pl.sum("overlap_duration").alias("time_together"),
			pl.len().alias("pairwise_encounters"),
		)
	).sort(["phase", "day", "phase_count", "hour", "position", "animal_id", "animal_id_2"])

	return auxfun.reindex_onto_grid(
		pairwise_meetings,
		cfg,
		("animal_id", "animal_id_2"),
		ordered=False,
		positions=auxfun.get_positions(cfg, "all"),
	)


@df_registry.register_step(
	"incohort_sociability", requires=["pairwise_meetings", "activity_df", "phase_durations"]
)
def calculate_incohort_sociability(cfg: dict[str, Any], **kwargs) -> pl.LazyFrame:
	"""Compute in-cohort sociability: observed togetherness minus chance expectation.

	For each pair and cage, the time the pair actually spent together (as a
	fraction of phase duration) is compared against the time they would be
	expected to share by chance given each animal's independent occupancy of that
	cage (the product of their occupancy proportions). ``sociability`` is the
	observed-minus-chance difference summed over cages; positive values indicate
	the pair sought each other out. For background see DOI:10.7554/eLife.19532.

	Args:
	    cfg: resolved project config.

	Returns:
	    Long-format LazyFrame with ``proportion_together`` and ``sociability`` per
	    phase for every pair of animals.
	"""
	phase_durations: pl.LazyFrame = auxfun._get_data(cfg, "phase_durations")
	time_together_df: pl.LazyFrame = auxfun._get_data(cfg, "pairwise_meetings")
	activity_df: pl.LazyFrame = auxfun._get_data(cfg, "activity_df")

	core_columns = ["phase", "day", "phase_count", "animal_id", "animal_id_2"]
	cages: list[str] = cfg["cages"]

	# Collapse the hourly pairwise grid to phase level so the per-row chance term
	# below is not summed once per hour.
	time_together_df = time_together_df.group_by([*core_columns, "position"]).agg(
		pl.sum("time_together")
	)

	activity_per_phase = (
		activity_df.filter(pl.col("position").is_in(cages))
		.group_by(["phase", "day", "phase_count", "position", "animal_id"])
		.agg(pl.sum("time_in_position"))
	)

	estimated_proportion_together = activity_per_phase.join(
		activity_per_phase, on=["phase", "day", "phase_count", "position"], suffix="_2"
	).filter(pl.col("animal_id") < pl.col("animal_id_2"))

	incohort_sociability = (
		time_together_df.join(
			estimated_proportion_together, on=[*core_columns, "position"], how="left"
		)
		.join(phase_durations, on=["phase_count", "phase"], how="left")
		.with_columns(
			pl.col("time_together") / pl.col("duration_seconds"),
			(
				(pl.col("time_in_position") * pl.col("time_in_position_2"))
				/ (pl.col("duration_seconds") ** 2)
			).alias("chance"),
		)
		.group_by(core_columns)
		.agg(
			pl.sum("time_together").alias("proportion_together"),
			(pl.col("time_together") - pl.col("chance")).sum().alias("sociability"),
		)
		.sort(core_columns)
	)

	return incohort_sociability


@df_registry.register_step(
	"feature_df",
	requires=["chasings_df", "tube_test_df", "pairwise_meetings", "activity_df"],
)
def calculate_features(cfg: dict[str, Any], **kwargs) -> pl.LazyFrame:
	"""Assemble a per-animal feature table of z-scored EcoHAB metrics for ML analysis.

	Collapses the upstream tables to one value per animal per phase/day for each
	metric -- chasings given (``n_chasing``) and received (``n_chased``), tube-test
	wins (``n_wins``) and losses (``n_loses``), ``activity`` and ``time_alone``,
	and ``time_together``/``pairwise_encounters`` -- aligns them, and z-scores each
	metric across the table so they are comparable on a common scale. The result is
	returned in long form, one row per animal/metric.

	Args:
	    cfg: resolved project config.

	Returns:
	    Long-format LazyFrame with ``metric`` and its ``z-score`` per
	    phase/day/phase_count for each animal.
	"""
	columns = [
		"time_alone",
		"n_chasing",
		"n_chased",
		"n_wins",
		"n_loses",
		"activity",
		"time_together",
		"pairwise_encounters",
	]

	chasings = auxfun._get_data(cfg, "chasings_df")
	tube_test = auxfun._get_data(cfg, "tube_test_df")
	pairwise_meetings = auxfun._get_data(cfg, "pairwise_meetings")

	n_chasing = (
		chasings.group_by("phase", "phase_count", "day", "chaser")
		.agg(pl.sum("chasings").alias("n_chasing"))
		.rename({"chaser": "animal_id"})
	)

	n_chased = (
		chasings.group_by("phase", "phase_count", "day", "chased")
		.agg(pl.sum("chasings").alias("n_chased"))
		.rename({"chased": "animal_id"})
	)

	n_wins = (
		tube_test.group_by("phase", "phase_count", "day", "winner")
		.agg(pl.sum("tube_test").alias("n_wins"))
		.rename({"winner": "animal_id"})
	)

	n_loses = (
		tube_test.group_by("phase", "phase_count", "day", "loser")
		.agg(pl.sum("tube_test").alias("n_loses"))
		.rename({"loser": "animal_id"})
	)

	activity = (
		auxfun._get_data(cfg, "activity_df")
		.group_by("phase", "phase_count", "day", "animal_id")
		.agg(pl.sum("visits_to_position").alias("activity"), pl.sum("time_alone"))
	)

	pairwise_meetings = (
		pairwise_meetings.unpivot(
			on=["animal_id", "animal_id_2"],
			index=["day", "phase", "phase_count", "time_together", "pairwise_encounters"],
			variable_name="_drop",
			value_name="col",  # can't be animal_id cause lazyframe freaks out, hence we rename
		)
		.drop("_drop")
		.group_by("phase", "phase_count", "day", "col")
		.agg(pl.sum("time_together"), pl.sum("pairwise_encounters"))
		.rename({"col": "animal_id"})
	)

	lfs = [n_chasing, n_chased, n_wins, n_loses, activity, pairwise_meetings]

	feature_lf = (
		pl.concat(lfs, how="align")
		.fill_null(0)
		.with_columns(
			[((pl.col(col) - pl.col(col).mean()) / pl.col(col).std()).alias(col) for col in columns]
		)
		.unpivot(
			index=["phase", "day", "phase_count", "animal_id"],
			variable_name="metric",
			value_name="z-score",
		)
		.with_columns(pl.col("z-score").round(2))
	)

	return feature_lf
