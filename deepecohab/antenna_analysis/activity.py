import datetime as dt
from pathlib import Path
from typing import Any
from itertools import product

import polars as pl

from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry


@df_registry.register("cage_occupancy")
def calculate_cage_occupancy(
	config_path: str | Path | dict,
	save_data: bool = True,
	overwrite: bool = False,
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


	lf: pl.LazyFrame = auxfun.load_ecohab_data(config_path, "main_df")

	results_path = Path(cfg["project_location"]) / "results"

	full_lf = get_hourly_padded(lf)

	agg = full_lf.with_columns(
		auxfun.get_hour(), auxfun.get_day()
		).group_by(
			["day", "hour", "position", "animal_id"]
		).agg(pl.sum("time_spent").round(0).cast(pl.UInt32).alias("time_spent"))

	bounds: tuple[dt.datetime, dt.datetime] = (
		lf.select(
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

	animal_pos_lf = pl.LazyFrame(
		product(cfg["animal_ids"], set(cfg["cages"])),
		schema={
			"animal_id": pl.Enum(cfg["animal_ids"]),
			"position": pl.Categorical,
		},
		orient="row",
	)
	full_group_list = time_lf.join(animal_pos_lf, how="cross")

	cage_occupancy = full_group_list.join(agg, on=["day", "hour", "position", "animal_id"], how="left").fill_null(0)

	if save_data:
		cage_occupancy.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return cage_occupancy

def get_hourly_padded(lf: pl.LazyFrame):
	lf = lf.select(['animal_id', 'datetime', 'time_spent', 'position']).with_columns(
			(pl.col('datetime')-pl.col('datetime').dt.truncate('1h')).dt.total_seconds(fractional=True).alias('seconds_after_hour')
		)

	unmodified_rows = lf.filter(
			pl.col('seconds_after_hour') >= pl.col("time_spent")
		).drop('seconds_after_hour')
	eps = pl.duration(microseconds=1)
	to_multiply = lf.with_columns(
		(pl.col('datetime').dt.truncate('1h')-eps).alias('end_hr'),
		((pl.col('datetime')-pl.duration(seconds = pl.col('time_spent'))+pl.duration(hours=1)).dt.truncate('1h')-eps).alias('start_hr'),  
	).filter(
		pl.col('seconds_after_hour') < pl.col("time_spent")
	).with_columns(
		(pl.col('time_spent')-pl.col('seconds_after_hour')).alias('time_spent')
	)

	seconds_per_hr = 3600

	ends = to_multiply.with_columns(
		(pl.col('seconds_after_hour')).alias('time_spent')
	)

	starts = to_multiply.with_columns(
		pl.col('start_hr').alias('datetime'),
		(pl.col('time_spent').mod(seconds_per_hr)).alias('time_spent')
	)
	full_hours = to_multiply.filter(
		pl.col('start_hr') != pl.col('end_hr')
	).with_columns(
		pl.datetime_ranges(
			pl.col("start_hr"), pl.col("end_hr"),
			interval="1h",
		).alias('range')
	).with_columns(pl.lit(seconds_per_hr).cast(pl.Float64).alias("time_spent")).explode('range').with_columns(
		pl.col('range').alias('datetime')).drop("range")

	multiplied = pl.concat([starts, ends, full_hours]).select("animal_id", "datetime","time_spent", "position")
	full_lf = pl.concat([unmodified_rows, multiplied])
	
	return full_lf


@df_registry.register("activity_df")
def calculate_activity(
	config_path: str | Path | dict,
	save_data: bool = True,
	overwrite: bool = False,
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

	padded_lf: pl.LazyFrame = auxfun.load_ecohab_data(cfg, key="padded_df")

	per_position_lf = padded_lf.with_columns(
		auxfun.remove_tunnel_directionality(cfg)
	).group_by(
		["phase", "day", "phase_count", "position", "animal_id"]
	).agg(
		pl.sum("time_spent").alias("time_in_position"),
		pl.len().alias("visits_to_position"),
	)

	# Perform empty join
	animal_df = pl.LazyFrame(
		cfg["animal_ids"],
		schema={
			"animal_id": pl.Enum(cfg["animal_ids"]),
		},
	)

	cages_df = pl.LazyFrame(cfg["positions"], schema={"position": pl.Categorical})
	time_grid = per_position_lf.select("phase", "day", "phase_count").unique()
	full_grid = time_grid.join(cages_df, how="cross").join(animal_df, how="cross")

	per_position_lf = full_grid.join(
		per_position_lf, on=["phase", "day", "phase_count", "position", "animal_id"], how="left"
	).fill_null(0)

	if save_data:
		per_position_lf.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return per_position_lf
