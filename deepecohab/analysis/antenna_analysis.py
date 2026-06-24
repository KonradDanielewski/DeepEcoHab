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

	# Re-derive phase_count from the grid so this table bins identically to _get_time_alone,
	# otherwise calculate_activity's left-joins drop occupancy rows and time_alone exceeds time_in_position.
	return (
		lf.drop("phase_count")
		.pipe(auxfun.get_grid_phase_count, cfg)
		.group_by(["phase", "day", "phase_count", "hour", "position", "animal_id"])
		.agg(
			pl.sum("time_spent").alias("time_in_position"),
			(~pl.col("interpolated")).sum().alias("visits_to_position"),
		)
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

	# Maps physical codes back to enum labels after the sweep.
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
		.pipe(auxfun.get_grid_phase_count, cfg)
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
	# Every animal starts at the model default; prev_ranking overrides with prior mu/sigma below.
	ranking = {player: model.rating() for player in animal_ids}

	if prev_ranking is not None:
		if isinstance(prev_ranking, pl.LazyFrame):
			prev_ranking = prev_ranking.collect()

		foreign_ids = set(prev_ranking.get_column("animal_id").to_list()) - set(animal_ids)
		if foreign_ids:
			raise ValueError(
				"prev_ranking contains animals that are not in the current cohort: "
				f"{sorted(foreign_ids)}. It must come from a recording of the same animals."
			)

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

	if rows:
		ranking_df = pl.LazyFrame(rows)
	else:
		# No chasing events to replay: emit an empty ranking with the expected schema.
		ranking_df = pl.LazyFrame(
			schema={
				"animal_id": pl.String,
				"mu": pl.Float64,
				"sigma": pl.Float64,
				"ordinal": pl.Float64,
				"datetime": match_df.schema["datetime"],
			}
		)

	ranking_df = ranking_df.with_columns(
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
	lf: pl.LazyFrame = auxfun._get_data(cfg, key="main_df").sort("datetime")

	cages: list[str] = cfg["cages"]
	tunnels: list[str] = list(cfg["tunnels"])  # directional tunnel positions

	# A row's `position`/`datetime` mark the position the animal left and when, so the winner's
	# `tunnel_entry` is its entry and the loser's `loser_exit` is its exit at the far end.

	# Winner candidates: a tunnel exit whose previous read was a cage, carrying that tunnel's entry time.
	chasing = (
		lf.with_columns(
			pl.col("datetime").shift(1).over("animal_id").alias("tunnel_entry"),
			pl.col("position").shift(1).over("animal_id").alias("prev_position"),
		)
		.filter(pl.col("position").is_in(tunnels), pl.col("prev_position").is_in(cages))
		.select(
			"position",
			pl.col("animal_id").alias("winner"),
			pl.col("datetime").alias("winner_exit"),
			"tunnel_entry",
		)
	)

	# Loser candidates: any tunnel exit.
	chased = lf.filter(pl.col("position").is_in(tunnels)).select(
		"position",
		pl.col("animal_id").alias("loser"),
		pl.col("datetime").alias("loser_exit"),
	)

	# Pair each loser exit with every winner still inside the same tunnel via a sweep (as in
	# calculate_pairwise_meetings). Each winner pass is an enter(+bit)/leave(-bit) event and each
	# loser exit a zero-delta query, so the per-tunnel cumulative bit-sum is the presence bitmask
	# of winners inside (one bit per animal, capped at ~63, far above any EcoHab study).
	elapsed = (pl.col("loser_exit") - pl.col("tunnel_entry")).dt.total_seconds(fractional=True)

	winners = chasing.with_columns(
		pl.lit(2, dtype=pl.Int64)
		.pow(pl.col("winner").to_physical().cast(pl.Int64))
		.cast(pl.Int64)
		.alias("bit")
	)
	# Maps each winner's single-bit mask value back to its id, for decoding the bitmask.
	id_lookup = winners.select("winner", "bit").unique()

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
	candidates = mask_at_query.join(id_lookup, how="cross").filter(
		(pl.col("mask") & pl.col("bit")) != 0
	)

	# Each event lands at the winner's timestamp so a boundary-straddling chase falls in one cell;
	# phase_count comes from the grid to align with the reindex in calculate_chasings.
	return (
		candidates.sort("loser_exit")
		.join_asof(
			winners.select("position", "winner", "winner_exit", "tunnel_entry").sort(
				"tunnel_entry"
			),
			left_on="loser_exit",
			right_on="tunnel_entry",
			by=["position", "winner"],
			strategy="backward",
			# Both sides are globally sorted on the as-of key above, which polars can't verify per `by` group.
			check_sortedness=False,
		)
		.filter(
			elapsed > chasing_time_window[0],
			elapsed < chasing_time_window[1],
			pl.col("loser_exit") < pl.col("winner_exit"),
			pl.col("winner") != pl.col("loser"),
		)
		.select(
			"position",
			"winner",
			"loser",
			pl.col("winner_exit").alias("datetime"),
			elapsed.alias("chasing_length"),
		)
		.sort("datetime")
		.with_columns(auxfun.get_phase(cfg), auxfun.get_day(), auxfun.get_hour())
		.pipe(auxfun.get_grid_phase_count, cfg)
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
	# Sorted at load so the order-dependent ops below (run-length encoding, shift().over) are chronological.
	lf: pl.LazyFrame = auxfun._get_data(cfg, key="main_df").sort("datetime")

	tunnels: list[str] = auxfun.get_positions(cfg, "tunnels")

	lf = auxfun.update_repeat_antenna_position(lf)
	lf = auxfun.remove_tunnel_directionality(lf, cfg)
	lf = lf.with_columns(
		(pl.col("datetime") - pl.duration(seconds=pl.col("time_spent"))).alias("tunnel_entry"),
		pl.col("position").shift(1).over("animal_id").alias("prev_position"),
		pl.col("position").shift(-1).over("animal_id").alias("next_position"),
	)

	# Loser: entered a tunnel and retreated to the cage it came from; the dwell cap drops
	# inflated repeat-antenna segments that are not real tunnel time.
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

	Uses the same sweep-line over occupancy intervals as :func:`_get_time_alone`:
	each cage stay becomes an enter (+1) and a leave (-1) event, and the per-cage
	running counts expose, at every instant, who is present. Here the per-animal
	signed counter is generalised from a sum of codes to a *bitmask* (``2**code``
	per animal): because an animal occupies a cage 0 or 1 times at any instant, the
	signed cumulative sum is an exact presence bitmask that decodes to the full set
	of co-present animals for any number of simultaneous occupants. Pairs are formed
	from each span's occupant set, temporally contiguous spans of the same pair are
	stitched into one continuous meeting, meetings shorter than ``minimum_time`` are
	dropped, and the rest are summed onto the dense grid.

	Args:
	    cfg: resolved project config.
	    minimum_time: minimum continuous co-presence, in seconds, for a meeting to
	        count; shorter meetings are dropped. Defaults to 2.

	Returns:
	    LazyFrame with ``time_together`` (seconds) and ``pairwise_encounters`` per
	    pair/cage/hour.
	"""
	padded_df = auxfun._get_data(cfg, key="padded_df")

	cages: list[str] = cfg["cages"]

	lf = (
		padded_df.filter(pl.col("position").is_in(cages))
		.with_columns(
			pl.col("datetime").alias("end"),
			(pl.col("datetime") - pl.duration(seconds=pl.col("time_spent"))).alias("start"),
			pl.col("animal_id").to_physical().cast(pl.Int64).alias("code"),
		)
		.with_columns(pl.lit(2, dtype=pl.Int64).pow(pl.col("code")).cast(pl.Int64).alias("bit"))
	)

	# Maps each animal's single-bit mask value back to its id, for decoding the bitmask.
	id_lookup = lf.select("animal_id", "bit").unique()

	enters = lf.select(
		pl.col("start").alias("time"),
		"position",
		pl.lit(1, dtype=pl.Int32).alias("delta"),
		pl.col("bit").alias("bit_delta"),
	)
	leaves = lf.select(
		pl.col("end").alias("time"),
		"position",
		pl.lit(-1, dtype=pl.Int32).alias("delta"),
		pl.col("bit").neg().alias("bit_delta"),
	)

	# Sweep per cage: n_active counts occupants and mask is the OR-set of their bits
	# (one bit per animal, so the signed cumulative bit-sum is a true presence bitmask).
	events = (
		pl.concat([enters, leaves])
		.sort("position", "time")
		.with_columns(
			pl.col("delta").cum_sum().over("position").alias("n_active"),
			pl.col("bit_delta").cum_sum().over("position").alias("mask"),
			pl.col("time").shift(-1).over("position").alias("time_next"),
		)
	)

	spans = events.filter(
		pl.col("time_next").is_not_null(),
		pl.col("n_active") >= 2,
		pl.col("time_next") > pl.col("time"),
	).select(
		"position",
		pl.col("time"),
		pl.col("time_next").alias("end"),
		pl.col("mask"),
	)

	# Decode each span's bitmask into the set of present animals, then pair them up.
	active = spans.join(id_lookup, how="cross").filter((pl.col("mask") & pl.col("bit")) != 0)

	pairs = (
		active.join(active, on=["position", "time", "end"], suffix="_2")
		.filter(pl.col("animal_id") < pl.col("animal_id_2"))
		.select(
			"position",
			"time",
			"end",
			"animal_id",
			"animal_id_2",
			(pl.col("end") - pl.col("time")).dt.total_seconds(fractional=True).alias("duration"),
		)
	)

	# Stitch contiguous spans of the same pair into one meeting: a new meeting starts
	# whenever this span's start != the previous span's end within the same pair and cage.
	pairs = (
		pairs.sort("animal_id", "animal_id_2", "position", "time")
		.with_columns(
			(pl.col("time") != pl.col("end").shift(1).over("animal_id", "animal_id_2", "position"))
			.fill_null(True)
			.alias("is_new")
		)
		.with_columns(
			pl.col("is_new")
			.cum_sum()
			.over("animal_id", "animal_id_2", "position")
			.alias("meeting_id")
		)
	)

	# Drop meetings whose total continuous co-presence is below minimum_time.
	meeting_dur = pairs.group_by("animal_id", "animal_id_2", "position", "meeting_id").agg(
		pl.sum("duration").alias("meeting_duration")
	)
	pairs = pairs.join(meeting_dur, on=["animal_id", "animal_id_2", "position", "meeting_id"])
	if minimum_time is not None:
		pairs = pairs.filter(pl.col("meeting_duration") > minimum_time)

	# Bin by each span's start time, taking phase_count from the grid so it aligns with the
	# reindex; each meeting is counted once via is_new.
	pairwise_meetings = (
		pairs.with_columns(
			auxfun.get_phase(cfg, "time"), auxfun.get_day("time"), auxfun.get_hour("time")
		)
		.pipe(auxfun.get_grid_phase_count, cfg)
		.group_by("phase", "day", "phase_count", "hour", "position", "animal_id", "animal_id_2")
		.agg(
			pl.sum("duration").alias("time_together"),
			pl.col("is_new").sum().alias("pairwise_encounters"),
		)
	)

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
			[
				# Guard constant metrics: a zero/undefined std would yield inf/nan
				# z-scores that then flow silently into the feature table.
				pl.when(pl.col(col).std().fill_null(0) == 0)
				.then(pl.lit(0.0))
				.otherwise((pl.col(col) - pl.col(col).mean()) / pl.col(col).std())
				.alias(col)
				for col in columns
			]
		)
		.unpivot(
			index=["phase", "day", "phase_count", "animal_id"],
			variable_name="metric",
			value_name="z-score",
		)
		.with_columns(pl.col("z-score").round(2))
	)

	return feature_lf
