import datetime as dt
import importlib
import subprocess
import sys
from pathlib import Path
from typing import (
	Callable,
	Any,
)

import polars as pl
import toml


class DataFrameRegistry:
	def __init__(self):
		self._registry: dict[str, Callable] = {}

	def register(self, name: str):
		"""Decorator to register a new plot type."""

		def wrapper(func: Callable):
			self._registry[name] = func
			return func

		return wrapper

	def get_function(self, name: str) -> Callable:
		"""Retrieve a function by its registered name."""
		if name not in self._registry:
			available = ", ".join(self._registry.keys())
			raise ValueError(f"'{name}' not found. Available: {available}")
		return self._registry[name]

	def list_available(self) -> list[str]:
		"""Returns a list of all registered function names."""
		return list(self._registry.keys())


df_registry = DataFrameRegistry()


def read_config(config_path: str | Path | dict[str, Any]) -> dict:
	"""Auxfun to check validity of the passed config_path variable (config path or dict)"""
	if isinstance(config_path, dict):
		return config_path

	elif isinstance(config_path, (str, Path)):
		with open(config_path, "r") as f:
			config = toml.load(f)
		return config

	else:
		raise TypeError(
			f"config_path should be either a dict, Path or str, but {type(config_path)} provided."
		)


def load_ecohab_data(
	config_path: str | Path | dict[str, Any], key: str, return_df: bool = False
) -> pl.LazyFrame | pl.DataFrame:
	"""Loads already analyzed main data structure

	Args:
	    config_path: config file path
	    key: name of the parquet file where data is stored.

	Raises:
	    KeyError: raised if the key not found in file.

	Returns:
	    Desired data structure loaded from the file.
	"""
	if key not in df_registry.list_available():
		raise KeyError(f"{key} not found. Available keys: {df_registry.list_available()}")

	cfg = read_config(config_path)
	results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"

	if not results_path.is_file():
		return None

	return pl.read_parquet(results_path) if return_df else pl.scan_parquet(results_path)


def make_project_path(project_location: str, experiment_name: str) -> Path:
	"""Auxfun to make a name of the project directory using its name and time of creation"""
	project_name = experiment_name + "_" + dt.datetime.today().strftime("%Y-%m-%d")
	project_location: Path = project_location / project_name

	return project_location

def get_phase_lens(cfg: dict[str, Any]) -> tuple[int, int]:
	"""Helper to extract default phase duration in seconds"""
	SECONDS_PER_DAY = 24 * 3600
	
	start_time, end_time = cfg["phase"].values()

	start_t = dt.time.fromisoformat(start_time)
	end_t   = dt.time.fromisoformat(end_time)
	
	duration_light = (
		(end_t.hour * 3600 + end_t.minute * 60 + end_t.second)
		- (start_t.hour * 3600 + start_t.minute * 60 + start_t.second)
	) % SECONDS_PER_DAY

	duration_dark = SECONDS_PER_DAY - duration_light

	return duration_light, duration_dark

def _split_datetime(phase_start: str) -> dt.datetime:
	"""Auxfun to split datetime string."""
	return dt.datetime.strptime(phase_start, "%H:%M:%S")

def get_phase_offset(time_str: str) -> pl.Duration:
	"Helper to return offset from midnight for given hh:mm:ss string" 
	start = _split_datetime(time_str)
	offset = pl.duration(
		hours=24 if start.hour == 0 else start.hour,
		minutes=start.minute,
		seconds=start.second,
		microseconds=-1,
	)

	return offset

def get_phase_edge_grid(lf : pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"Auxfun that creates a LazyFrame with all phases of the experiment and their ends"

	dark_offset = get_phase_offset(cfg["phase"]["dark_phase"])
	light_offset = get_phase_offset(cfg["phase"]["light_phase"])

	exp_start = lf.select(
			pl.col("datetime").min()
		).collect().item()

	days_lf = lf.select(
			pl.datetime_range(
				pl.col("datetime").min().dt.truncate("1d"),
				pl.col("datetime").max().dt.truncate("1d"),
				interval="24h",
			).alias("phase_end")
			.explode()
		)

	light_ends_lf = days_lf.select(
		pl.lit("light_phase").alias("phase"),
		(pl.col("phase_end") + dark_offset).alias("phase_end")
	)

	dark_ends_lf = days_lf.select(
		pl.lit("dark_phase").alias("phase"),
		(pl.col("phase_end") + light_offset).alias("phase_end")
	)
	full_phase_lf = (
		pl.concat([light_ends_lf, dark_ends_lf])
		.with_columns(pl.col('phase').cast(pl.Enum(['light_phase', 'dark_phase'])))
		.filter(
			pl.col('phase_end') >= exp_start
		)
		.select(['phase', 'phase_end'])
		.sort("phase_end")
		.pipe(get_phase_count)
	).join(lf, on=['phase', 'phase_count'], how = 'semi')

	return full_phase_lf

def get_phase_edges(lf : pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"Helper to return durations of edge phases of the experiment"
	base_midnight = pl.col("datetime").dt.truncate("1d")
	time_offset = pl.col("datetime").dt.dst_offset()
	time_diff  = (pl.col("utc_off") - pl.col("utc_off").first()).dt.total_seconds()

	dark_offset = get_phase_offset(cfg["phase"]["dark_phase"])
	light_offset = get_phase_offset(cfg["phase"]["light_phase"])

	start = lf.filter(
		pl.col('datetime') == pl.col('datetime').min()
	).with_columns(
		time_offset.alias('utc_off'),
		pl.when(pl.col("phase") == "light_phase")
		.then(base_midnight + dark_offset)
		.otherwise(base_midnight + light_offset)
		.alias("datetime_")).with_columns(
			(pl.col('datetime_') - pl.col('datetime')).dt.total_seconds().alias("duration_seconds"),
			time_offset.alias('utc_off')
		)

	stop = lf.filter(
		pl.col('datetime') == pl.col('datetime').max()
	).with_columns(
		time_offset.alias('utc_off'),
		pl.when(pl.col("phase") == "light_phase")
		.then(base_midnight + light_offset)
		.otherwise(base_midnight + dark_offset)
		.alias("datetime_")).with_columns(
			(pl.col('datetime') - pl.col('datetime_')).dt.total_seconds().alias("duration_seconds")
		)

	edges = pl.concat([start, stop]).with_columns(
		(pl.col('duration_seconds')- time_diff).alias('duration_seconds')
	).select(["phase", "phase_count", "duration_seconds"])

	return edges

@df_registry.register("phase_durations")
def get_phase_durations(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Auxfun to calculate approximate phase durations.
	Assumes the length is the closest full hour of the total length in seconds (first to last datetime in this phase).
	"""

	duration_light, duration_dark = get_phase_lens(cfg)

	edges = get_phase_edges(lf, cfg)

	inner_phases = lf.select(
    	['phase', 'phase_count']
    ).unique()

	phase_durations = inner_phases.join(
		edges, 
		on=["phase", "phase_count"], 
		how='left').with_columns(
			pl.when(
				pl.col('duration_seconds').is_null()
			).then(
				pl.when(
					pl.col('phase') == 'light_phase'
				).then(
					pl.lit(duration_light)
				).otherwise(
					pl.lit(duration_dark)
				)
			).otherwise(
				pl.col('duration_seconds')
			).alias("duration_seconds").cast(pl.Int64)
		)
		
	return phase_durations




def get_day() -> pl.Expr:
	"""Auxfun for getting the day"""
	return (
		(
			pl.col("datetime").dt.date() - pl.col("datetime").dt.date().min()
		).dt.total_days()
    ).add(1).cast(pl.Int16).alias('day')


def get_phase(cfg: dict[str, Any]) -> pl.Expr:
	"""Auxfun for getting the phase"""
	start_str, end_str = list(cfg["phase"].values())
	phase_names = list(cfg["phase"].keys())
	start_t = dt.time.fromisoformat(start_str)
	end_t = dt.time.fromisoformat(end_str)

	time_offset = pl.col("datetime").dt.dst_offset() - pl.col("datetime").first().dt.dst_offset()

	return (
		pl.when((pl.col("datetime")-time_offset).dt.time().is_between(start_t, end_t, closed="left"))
		.then(pl.lit("light_phase"))
		.otherwise(pl.lit("dark_phase"))
		.cast(pl.Enum(phase_names))
		.alias("phase")
	)


def get_hour(dt_col: str = "datetime") -> pl.Expr:
	return pl.col(dt_col).dt.hour().cast(pl.Int8).alias("hour")


def get_phase_count(lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Auxfun used to count phases"""
	lf = lf.with_columns(
		pl.col("phase").rle_id().alias("run_id")
	).with_columns(
		pl.col("run_id").rank("dense").over("phase").alias("phase_count")
	).drop("run_id")
	return lf


def get_lf_from_enum(
	values: list, col_name: str, col_type: pl.DataType, sorted: bool = False
) -> pl.LazyFrame:
	"""Auxfun for creating LazyFrames from lists of values"""

	res = pl.LazyFrame(
		{col_name: values},
		schema={col_name: col_type},
	)

	return res.sort(col_name) if sorted else res


def get_animal_cage_grid(cfg: dict) -> pl.LazyFrame:
	"""Auxfun to prepare LazyFrame of all animal x cage combos"""
	animal_ids: list[str] = cfg["animal_ids"]
	cages: list[str] = cfg["cages"]
	animals_lf = get_lf_from_enum(
		animal_ids, "animal_id", sorted=True, col_type=pl.Enum(animal_ids)
	)
	cages_lf = get_lf_from_enum(cages, "cage", col_type=pl.Categorical)
	return animals_lf.join(cages_lf, how="cross")


def set_animal_ids(
	config_path: str | Path | dict[str, Any],
	lf: pl.LazyFrame,
	sanitize_animal_ids: bool,
	min_antenna_crossings: int,
	animal_ids: list | None = None,
) -> pl.LazyFrame:
	"""Auxfun to infer animal ids from data, optionally removing ghost tags (random radio noise reads)."""
	cfg: dict[str, Any] = read_config(config_path)
	dropped_ids: list[str] = []

	if isinstance(animal_ids, list):
		lf = lf.filter(pl.col("animal_id").is_in(animal_ids))
	else:
		animal_detections = lf.group_by("animal_id").len().collect()

		if sanitize_animal_ids:
			is_ghost = pl.col("len") < min_antenna_crossings

			dropped_ids = animal_detections.filter(is_ghost)["animal_id"].to_list()
			animal_ids = animal_detections.filter(~is_ghost)["animal_id"].to_list()

			if dropped_ids:
				print(f"IDs dropped from dataset {dropped_ids}")
			else:
				print("No ghost tags detected :)")
		else:
			animal_ids: list[str] = animal_detections["animal_id"].to_list()

		animal_ids = sorted(animal_ids)
		lf = lf.filter(pl.col("animal_id").is_in(animal_ids))

	cfg.update({"animal_ids": animal_ids, "dropped_ids": dropped_ids})
	with open(config_path, "w") as f:
		toml.dump(cfg, f)

	return lf


def append_start_end_to_config(
	config_path: str | Path | dict[str, Any], lf: pl.LazyFrame
) -> tuple[dict[str, Any], str, str]:
	"""Auxfun to append start and end datetimes of the experiment if not user provided.

	Returns:
	    Config with updated start and end datetimes
	"""
	cfg: dict[str, Any] = read_config(config_path)
	bounds = (
		lf.sort("datetime")
		.select(
			[
				pl.col("datetime").first().alias("start_time"),
				pl.col("datetime").last().alias("end_time"),
			]
		)
		.collect()
	)

	start_time = str(bounds["start_time"][0])
	end_time = str(bounds["end_time"][0])

	with open(config_path, "w") as config:
		cfg["days_range"] = [
			1,
			(bounds["end_time"] - bounds["start_time"]).item().days + 1,
		]
		cfg["experiment_timeline"] = {
			"start_date": start_time,
			"finish_date": end_time,
		}
		toml.dump(cfg, config)

	print(
		f"Start of the experiment established as: {start_time} and end as {end_time}.\nIf you wish to set specific start and end, please change them in the config file and create the data structure again setting overwrite=True"
	)

	return cfg, start_time, end_time


def add_cages_to_config(config_path: str | Path | dict[str, Any]) -> None:
	"""Auxfun to add cage names to config for reading convenience"""
	cfg: dict[str, Any] = read_config(config_path)

	positions: list[str] = list(set(cfg["antenna_combinations"].values()))
	cages: list[str] = [pos for pos in positions if "cage" in pos]

	with open(config_path, "w") as config:
		cfg["cages"] = sorted(cages)
		toml.dump(cfg, config)


def add_days_to_config(config_path: str | Path | dict[str, Any], lf: pl.LazyFrame) -> None:
	"""Auxfun to add days range to config for reading convenience"""
	cfg: dict[str, Any] = read_config(config_path)

	days: list[int] = lf.collect().get_column("day").unique(maintain_order=True).to_list()

	with open(config_path, "w") as config:
		cfg["days_range"] = [*days]
		toml.dump(cfg, config)


def run_dashboard(config_path: str | Path | dict[str, Any]):
	"""Auxfun to open dashboard for experiment from provided config"""
	cfg: dict[str, Any] = read_config(config_path)

	project_loc = Path(cfg["project_location"])
	data_path = project_loc / "results"
	cfg_path = project_loc / "config.toml"

	path_to_dashboard: str = importlib.util.find_spec("deepecohab.dash.dashboard").origin

	cmd: list[str] = [
		sys.executable,
		path_to_dashboard,
		"--results-path",
		str(data_path),
		"--config-path",
		str(cfg_path),
	]

	process = subprocess.Popen(
		cmd,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)
	try:
		output, _ = process.communicate(timeout=1)
		print(output)
	except subprocess.TimeoutExpired:
		pass


def get_time_spent_expression(
	time_col: str = "datetime",
	group_col: str = "animal_id",
	alias: str | None = "time_spent",
) -> pl.Expr:
	"""Auxfun to build a polars expression object to perform timedelta calculation on a dataframe with specified column names"""
	expr = (
		(pl.col(time_col) - pl.col(time_col).shift(1))
		.over(group_col)
		.dt.total_seconds(fractional=True)
		.fill_null(0)
		.cast(pl.Float64)
		.round(2)
	)
	return expr.alias(alias) if alias is not None else expr


def remove_tunnel_directionality(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Auxfun to map directional tunnels in a LazyFrame to undirected ones"""
	tunnels: list[str] = cfg["tunnels"]

	return lf.with_columns(
		pl.col("position").cast(pl.Utf8).replace(tunnels).cast(pl.Categorical).alias("position")
	)
