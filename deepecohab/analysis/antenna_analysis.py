import datetime as dt
from itertools import combinations, product
from pathlib import Path
from typing import Any, Literal

import polars as pl
from openskill.models import PlackettLuce

from deepecohab.core.registries import df_registry
from deepecohab.utils import auxfun


@df_registry.register("cage_occupancy")
def calculate_cage_occupancy(
	config_path: str | Path | dict,
	save_data: bool = True,
	overwrite: bool = False,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates time spent per animal per phase in every cage.

	Args:
	    config_path: path to projects' config file or dict with the config.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    LazyFrame of time spent in each cage with 1s resolution.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "cage_occupancy"

	cage_occupancy: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(cage_occupancy, pl.LazyFrame):
		return cage_occupancy

	results_path = Path(cfg["project_location"]) / "results"

	binary_lf: pl.LazyFrame = auxfun._get_data(config_path, "binary_df")

	cols = ["day", "hour", "cage", "animal_id"]

	bounds: tuple[dt.datetime, dt.datetime] = (
		binary_lf.select(
			pl.col("datetime").min().dt.truncate("1h").alias("start"),
			pl.col("datetime").max().dt.truncate("1h").alias("end"),
		)
		.collect()
		.row(0)
	)

	time_lf = (
		pl.LazyFrame()
		.select(pl.datetime_range(bounds[0], bounds[1], "1h").alias("datetime"))
		.with_columns(auxfun.get_hour(), auxfun.get_day())
		.drop("datetime")
	)

	full_group_list = time_lf.join(auxfun.get_animal_position_grid(cfg, "cages"), how="cross")

	agg = (
		binary_lf.with_columns(auxfun.get_hour(), auxfun.get_day())
		.group_by(cols)
		.agg(pl.len().alias("time_spent"))
	)

	cage_occupancy = full_group_list.join(agg, on=cols, how="left").fill_null(0)

	if save_data:
		cage_occupancy.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return cage_occupancy


@df_registry.register("activity_df")
def calculate_activity(
	config_path: str | Path | dict,
	save_data: bool = True,
	overwrite: bool = False,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates time spent and visits to every possible position per phase for every mouse.

	Args:
	    config_path: path to projects' config file or dict with the config.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    LazyFrame of time and visits
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "activity_df"

	time_per_position_lf: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(time_per_position_lf, pl.LazyFrame):
		return time_per_position_lf

	results_path: Path = Path(cfg["project_location"]) / "results"

	padded_lf: pl.LazyFrame = auxfun._get_data(cfg, key="padded_df")
	padded_lf = auxfun.remove_tunnel_directionality(padded_lf, cfg)

	per_position_lf = padded_lf.group_by(
		["phase", "day", "phase_count", "position", "animal_id"]
	).agg(
		pl.sum("time_spent").alias("time_in_position"),
		pl.len().alias("visits_to_position"),
	)

	time_grid = per_position_lf.select("phase", "day", "phase_count").unique()
	full_grid = time_grid.join(auxfun.get_animal_position_grid(cfg, "positions"), how="cross")

	per_position_lf = full_grid.join(
		per_position_lf, on=["phase", "day", "phase_count", "position", "animal_id"], how="left"
	).fill_null(0)

	if save_data:
		per_position_lf.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return per_position_lf


@df_registry.register("ranking")
def calculate_ranking(
	config_path: str | Path | dict,
	overwrite: bool = False,
	save_data: bool = True,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculate ranking using Plackett Luce algortihm. Each chasing event is a match
	   Args:
	       config_path: path to project config file.
	       save_data: toogles whether to save data.
	       overwrite: toggles whether to overwrite the data.
	       ranking: optionally, user can pass a DataFrame from a different
	recording of same animals to start ranking from a certain point instead of 0 by applying:

	ranking.group_by('animal_id').agg(pl.last('mu'), pl.last('sigma'))

	on the previous rec of the same animals to get their last rank estimation.

	   Returns:
	       LazyFrame of ranking
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "ranking"

	ranking: pl.LazyFrame | None = None if overwrite else auxfun.load_ecohab_data(config_path, key)

	if isinstance(ranking, pl.LazyFrame):
		return ranking

	results_path: Path = Path(cfg["project_location"]) / "results"

	prev_ranking = kwargs.get("prev_ranking", None)
	animal_ids: list[str] = cfg["animal_ids"]

	if isinstance(prev_ranking, dict):
		ranking: dict[str, dict[str, float]] = {
			name: PlackettLuce(mu=mu, sigma=sigma, limit_sigma=True, balance=True)
			for name, mu, sigma in prev_ranking.iter_rows()
		}
	else:
		model = PlackettLuce(limit_sigma=True, balance=True)
		ranking: dict[str, dict[str, float]] = {player: model.rating() for player in animal_ids}

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

	if save_data:
		ranking_df.sink_parquet(
			results_path / "ranking.parquet", compression="lz4", engine="streaming"
		)

	return ranking


@df_registry.register("match_df")
def get_matches(lf: pl.LazyFrame, results_path: Path, save_data: bool) -> None:
	"""Creates a lazyframe of matches"""
	matches = lf.select(
		"animal_id", "animal_id_chasing", "datetime_chasing", "position", "chasing_length"
	).rename(
		{
			"animal_id": "loser",
			"animal_id_chasing": "winner",
			"datetime_chasing": "datetime",
		}
	)
	if save_data:
		matches.sink_parquet(
			results_path / "match_df.parquet", compression="lz4", engine="streaming"
		)


@df_registry.register("chasings_df")
def calculate_chasings(
	config_path: str | Path | dict,
	overwrite: bool = False,
	save_data: bool = True,
	chasing_time_window: list[int, int] = [0.1, 1.2],
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates chasing events per pair of mice for each phase

	Args:
	    config_path: path to project config file.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.
		chasing_time_window: defines min and max length of the chasing event in seconds. Defaults to [0.1, 1.2]

	Returns:
	    LazyFrame of chasings
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "chasings_df"

	chasings: pl.LazyFrame | None = None if overwrite else auxfun.load_ecohab_data(config_path, key)

	if isinstance(chasings, pl.LazyFrame):
		return chasings

	results_path = Path(cfg["project_location"]) / "results"

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

	get_matches(
		intermediate.with_columns(
			(pl.col("datetime") - pl.col("tunnel_entry"))
			.dt.total_seconds(fractional=True)
			.alias("chasing_length")
		),
		results_path,
		save_data,
	)

	chasings = (
		intermediate.group_by(
			["phase", "day", "phase_count", "hour", "position", "animal_id_chasing", "animal_id"]
		)
		.len(name="chasings")
		.rename({"animal_id": "chased", "animal_id_chasing": "chaser"})
	)

	# Perform empty join
	all_pairs = [
		(a1, a2) for a1, a2 in list(product(cfg["animal_ids"], cfg["animal_ids"])) if a1 != a2
	]
	directional_tunnels = [pos for pos in cfg["antenna_combinations"].values() if "cage" not in pos]
	pairs_df = pl.LazyFrame(
		[(*p, c) for p, c in product(all_pairs, directional_tunnels)],
		schema={
			"chaser": pl.Enum(cfg["animal_ids"]),
			"chased": pl.Enum(cfg["animal_ids"]),
			"position": pl.Categorical,
		},
		orient="row",
	)

	time_grid = chasings.select("phase", "day", "phase_count").unique()

	full_grid = time_grid.join(pairs_df, how="cross")

	chasings = full_grid.join(
		chasings,
		on=["phase", "day", "phase_count", "position", "chaser", "chased"],
		how="left",
	).fill_null(0)

	if save_data:
		chasings.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return chasings


@df_registry.register("tube_test_df")
def calculate_tube_test(
	config_path: str | Path | dict,
	winner_behavior: Literal["CHASE", "GUARD", "BOTH"] = "BOTH",
	overwrite: bool = False,
	save_data: bool = True,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates tube test events per pair of mice for each hour

	Args:
	    config_path: path to project config file.
	    winner_behavior: specifies whether to include events where the winning mouse followed the loser
						or returned to the guarded resource
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    LazyFrame of tube test events
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "tube_test_df"

	tube_test: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(tube_test, pl.LazyFrame):
		return tube_test

	results_path = Path(cfg["project_location"]) / "results"

	lf: pl.LazyFrame = auxfun._get_data(cfg, key="main_df")

	cages: list[str] = cfg["cages"]

	lf = auxfun.update_repeat_antenna_position(lf)
	lf = auxfun.remove_tunnel_directionality(lf, cfg)
	lf = lf.with_columns(
		(pl.col("datetime") - pl.duration(seconds=pl.col("time_spent"))).alias("tunnel_entry"),
		pl.col("position").shift(1).over("animal_id").alias("prev_position"),
		pl.col("position").shift(-1).over("animal_id").alias("next_position"),
	)

	loser = lf.filter(
		~pl.col("position").is_in(cages), pl.col("prev_position") == pl.col("next_position")
	)

	intermediate = (
		loser.join(lf, on=["phase", "day", "phase_count", "position"], suffix="_winner")
		.filter(
			pl.col("animal_id") != pl.col("animal_id_winner"),
			pl.col("prev_position") != pl.col("prev_position_winner"),
			pl.col("datetime") < pl.col("datetime_winner"),
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

	if winner_behavior == "CHASE":
		intermediate = intermediate.filter(
			pl.col("next_position") == pl.col("next_position_winner"),
		)
	elif winner_behavior == "GUARD":
		intermediate = intermediate.filter(
			pl.col("next_position") != pl.col("next_position_winner"),
		)

	tube_test = (
		intermediate.group_by(
			["phase", "day", "phase_count", "hour", "animal_id", "animal_id_winner"]
		)
		.len(name="tube_test")
		.rename({"animal_id": "loser", "animal_id_winner": "winner"})
	)

	# Perform empty join
	all_pairs = [
		(a1, a2) for a1, a2 in list(product(cfg["animal_ids"], cfg["animal_ids"])) if a1 != a2
	]
	pairs_df = pl.LazyFrame(
		all_pairs,
		schema={
			"winner": pl.Enum(cfg["animal_ids"]),
			"loser": pl.Enum(cfg["animal_ids"]),
		},
		orient="row",
	)

	time_grid = tube_test.select("phase", "day", "phase_count").unique()

	full_grid = time_grid.join(pairs_df, how="cross")

	tube_test = full_grid.join(
		tube_test,
		on=["phase", "day", "phase_count", "winner", "loser"],
		how="left",
	).fill_null(0)

	if save_data:
		tube_test.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return tube_test


@df_registry.register("time_alone")
def calculate_time_alone(
	config_path: Path | str | dict,
	save_data: bool = True,
	overwrite: bool = False,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates time spent alone by animal per phase/day/cage

	Args:
	    config_path: path to project config file.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    DataFrame containing time spent alone in seconds.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "time_alone"

	time_alone: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)
	if isinstance(time_alone, pl.LazyFrame):
		return time_alone

	results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"

	binary_df: pl.LazyFrame = auxfun._get_data(config_path, "binary_df")

	group_cols = ["datetime", "cage"]
	result_cols = ["phase", "day", "animal_id", "cage"]

	time_lf = binary_df.select(
		auxfun.get_day().alias("day"),
		auxfun.get_phase(cfg).alias("phase"),
	).unique()

	full_group_list = time_lf.join(auxfun.get_animal_position_grid(cfg, "cages"), how="cross")

	time_alone = (
		binary_df.group_by(group_cols, maintain_order=True)
		.agg(pl.len().alias("n"), pl.col("animal_id").first())
		.filter(pl.col("n") == 1)
		.with_columns(auxfun.get_phase(cfg), auxfun.get_day())
		.group_by(result_cols, maintain_order=True)
		.agg(pl.len().alias("time_alone"))
	)

	time_alone = full_group_list.join(time_alone, on=result_cols, how="left").fill_null(0)

	time_alone = auxfun.get_phase_count(time_alone.sort("day", "phase"))

	if save_data:
		time_alone.sink_parquet(results_path, compression="lz4", engine="streaming")

	return time_alone


@df_registry.register("pairwise_meetings")
def calculate_pairwise_meetings(
	config_path: str | Path | dict,
	save_data: bool = True,
	overwrite: bool = False,
	minimum_time: int | float | None = 2,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates time spent together and number of meetings by animals on a per phase, day and cage basis. Slow due to the nature of datetime overlap calculation.

	Args:
	    cfg: dictionary with the project config.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.
		minimum_time: sets minimum time together to be considered an interaction - in seconds i.e., if set to 2 any time spent in the cage together
			that is shorter than 2 seconds will be omited. Defaults to 2.

	Returns:
	    LazyFrame of time spent together per phase, per cage.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "pairwise_meetings"

	pairwise_meetings: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(pairwise_meetings, pl.DataFrame):
		return pairwise_meetings

	results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"
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
		joined.group_by("phase", "day", "phase_count", "position", "animal_id", "animal_id_2").agg(
			pl.sum("overlap_duration").alias("time_together"),
			pl.len().alias("pairwise_encounters"),
		)
	).sort(["phase", "day", "phase_count", "position", "animal_id", "animal_id_2"])

	# Perform empty join
	all_pairs = list(combinations(cfg["animal_ids"], 2))
	temp_df = pl.LazyFrame(
		[(*p, c) for p, c in product(all_pairs, cfg["positions"])],
		schema={
			"animal_id": pl.Enum(cfg["animal_ids"]),
			"animal_id_2": pl.Enum(cfg["animal_ids"]),
			"position": pl.Categorical,
		},
		orient="row",
	)

	time_grid = pairwise_meetings.select("phase", "day", "phase_count").unique()

	full_grid = time_grid.join(temp_df, how="cross")

	pairwise_meetings = full_grid.join(
		pairwise_meetings,
		on=["phase", "day", "phase_count", "position", "animal_id", "animal_id_2"],
		how="left",
	).fill_null(0)

	if save_data:
		pairwise_meetings.sink_parquet(results_path, compression="lz4", engine="streaming")

	return pairwise_meetings


@df_registry.register("incohort_sociability")
def calculate_incohort_sociability(
	config_path: dict,
	save_data: bool = True,
	overwrite: bool = False,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates in-cohort sociability. For more info: DOI:10.7554/eLife.19532.

	Args:
	    config_path: path to project config file.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    Long format LazyFrame of in-cohort sociability per phase for each possible pair of mice.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "incohort_sociability"

	incohort_sociability: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(incohort_sociability, pl.LazyFrame):
		return incohort_sociability

	results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"

	phase_durations: pl.LazyFrame = auxfun._get_data(config_path, "phase_durations")
	time_together_df: pl.LazyFrame = auxfun._get_data(config_path, "pairwise_meetings")
	activity_df: pl.LazyFrame = auxfun._get_data(config_path, "activity_df")

	core_columns = ["phase", "day", "phase_count", "animal_id", "animal_id_2"]

	estimated_proportion_together = activity_df.join(
		activity_df, on=["phase_count", "phase", "position"], suffix="_2"
	).filter(pl.col("animal_id") < pl.col("animal_id_2"))

	incohort_sociability = (
		time_together_df.join(
			estimated_proportion_together, on=core_columns + ["position"], how="left"
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

	if save_data:
		incohort_sociability.sink_parquet(results_path, compression="lz4", engine="streaming")

	return incohort_sociability


@df_registry.register("feature_df")
def calculate_features(
	config_path: Path | str | dict,
	save_data: bool = True,
	overwrite: bool = False,
	**kwargs,
) -> pl.LazyFrame:
	"""Calculates z-score of ecohab metrics for further machine learning analysis.

	Args:
	    config_path: path to project config file.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
		Long format LazyFrame of features per phase, day and phase_count for each mouse.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "feature_df"

	feature_df: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)
	if isinstance(feature_df, pl.LazyFrame):
		return feature_df

	results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"
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

	chasings = auxfun._get_data(config_path, "chasings_df")
	tube_test = auxfun._get_data(config_path, "tube_test_df")
	pairwise_meetings = auxfun._get_data(config_path, "pairwise_meetings")

	time_alone = (
		auxfun._get_data(config_path, "time_alone")
		.group_by("phase", "phase_count", "day", "animal_id")
		.agg(pl.sum("time_alone"))
	)

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
		auxfun._get_data(config_path, "activity_df")
		.group_by("phase", "phase_count", "day", "animal_id")
		.agg(pl.sum("visits_to_position").alias("activity"))
	)

	pairwise_meetings = (
		pl.concat(
			[
				pairwise_meetings.select(
					"animal_id",
					"day",
					"phase",
					"phase_count",
					"time_together",
					"pairwise_encounters",
				),
				pairwise_meetings.select(
					pl.col("animal_id_2").alias("animal_id"),
					"day",
					"phase",
					"phase_count",
					"time_together",
					"pairwise_encounters",
				),
			]
		)
		.group_by("phase", "phase_count", "day", "animal_id")
		.agg([pl.sum("time_together"), pl.sum("pairwise_encounters")])
	)

	lfs = [time_alone, n_chasing, n_chased, n_wins, n_loses, activity, pairwise_meetings]

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

	if save_data:
		feature_lf.sink_parquet(results_path, compression="lz4", engine="streaming")

	return feature_lf
