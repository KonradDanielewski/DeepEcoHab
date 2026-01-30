from itertools import combinations
from pathlib import Path
from typing import Any

import polars as pl

from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry


@df_registry.register("time_alone")
def calculate_time_alone(
	config_path: Path | str | dict,
	save_data: bool = True,
	overwrite: bool = False,
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

	binary_df: pl.LazyFrame = auxfun.load_ecohab_data(config_path, "binary_df")

	group_cols = ["datetime", "cage"]
	result_cols = ["phase", "day", "animal_id", "cage"]

	time_lf = binary_df.select(
		auxfun.get_day().alias("day"),
		auxfun.get_phase(cfg).alias("phase"),
	).unique()

	full_group_list = time_lf.join(auxfun.get_animal_cage_grid(cfg), how="cross")

	time_alone = (
		binary_df.group_by(group_cols, maintain_order=True)
		.agg(pl.len().alias("n"), pl.col("animal_id").first())
		.filter(pl.col("n") == 1)
		.with_columns(auxfun.get_phase(cfg), auxfun.get_day())
		.group_by(result_cols, maintain_order=True)
		.agg(pl.len().alias("time_alone"))
	)

	time_alone = auxfun.get_phase_count(time_alone)

	time_alone = full_group_list.join(time_alone, on=result_cols, how="left").fill_null(0)

	if save_data:
		time_alone.sink_parquet(results_path, compression="lz4", engine="streaming")

	return time_alone


@df_registry.register("pairwise_meetings")
def calculate_pairwise_meetings(
	config_path: str | Path | dict,
	minimum_time: int | float | None = 2,
	save_data: bool = True,
	overwrite: bool = False,
) -> pl.LazyFrame:
	"""Calculates time spent together and number of meetings by animals on a per phase, day and cage basis. Slow due to the nature of datetime overlap calculation.

	Args:
	    cfg: dictionary with the project config.
	    minimum_time: sets minimum time together to be considered an interaction - in seconds i.e., if set to 2 any time spent in the cage together
	               that is shorter than 2 seconds will be omited.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

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
	padded_df = auxfun.load_ecohab_data(cfg, key="padded_df")

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
	pairs_df = pl.LazyFrame(
		all_pairs,
		schema={
			"animal_id": pl.Enum(cfg["animal_ids"]),
			"animal_id_2": pl.Enum(cfg["animal_ids"]),
		},
		orient="row",
	)

	cages_df = pl.LazyFrame(cages, schema={"position": pl.Categorical})

	time_grid = pairwise_meetings.select("phase", "day", "phase_count").unique()

	full_grid = time_grid.join(cages_df, how="cross").join(pairs_df, how="cross")

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

	phase_durations: pl.LazyFrame = auxfun.load_ecohab_data(config_path, "phase_durations")
	time_together_df: pl.LazyFrame = auxfun.load_ecohab_data(config_path, "pairwise_meetings")
	activity_df: pl.LazyFrame = auxfun.load_ecohab_data(config_path, "activity_df")

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
