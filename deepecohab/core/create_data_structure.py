import datetime as dt
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, available_timezones

import polars as pl
from tzlocal import get_localzone

from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry


def load_data(
	config_path: str | Path,
	fname_prefix: str,
	custom_layout: bool,
	sanitize_animal_ids: bool,
	min_antenna_crossings: int,
	animal_ids: list | None = None,
) -> pl.LazyFrame:
	"""Auxfun to load and combine text files into a LazyFrame"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	data_path = Path(cfg["data_path"])

	lf = pl.scan_csv(
		source=data_path / f"{fname_prefix}*.txt",
		separator="\t",
		has_header=False,
		new_columns=["ind", "date", "time", "antenna", "time_under", "animal_id"],
		include_file_paths="file",
		glob=True,
		infer_schema=True,
		infer_schema_length=10,
	)

	lf = lf.with_columns(
		pl.col("file").str.extract(r"([^/\\]+)$").str.split("_").list.get(0).alias("COM")
	).drop(["ind", "file"])

	lf = auxfun.set_animal_ids(
		config_path,
		lf=lf,
		sanitize_animal_ids=sanitize_animal_ids,
		min_antenna_crossings=min_antenna_crossings,
		animal_ids=animal_ids,
	)

	if custom_layout:
		rename_dicts: list[dict[int, int]] = cfg["antenna_rename_scheme"]
		lf = _rename_antennas(lf, rename_dicts)

	auxfun.add_cages_to_config(config_path)

	return lf


def calculate_time_spent(lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds"""

	lf = lf.with_columns(auxfun.get_time_spent_expression())
	return lf


def get_animal_position(lf: pl.LazyFrame, antenna_pairs: dict) -> pl.LazyFrame:
	"""Auxfun, groupby mapping of antenna pairs to position"""
	prev_ant = pl.col("antenna").shift(1).over("animal_id").fill_null(0).cast(pl.Utf8)
	curr_ant = pl.col("antenna").cast(pl.Utf8)

	pair = pl.concat_str([prev_ant, pl.lit("_"), curr_ant])

	return lf.with_columns(
		[pair.replace(antenna_pairs, default="undefined").alias("position").cast(pl.Categorical)]
	)


def _rename_antennas(lf: pl.LazyFrame, rename_dicts: dict) -> pl.LazyFrame:
	"""Auxfun for antenna name mapping when custom layout is used"""
	lf = lf.with_columns(
		pl.coalesce(
			pl.when(pl.col("COM") == com).then(pl.col("antenna").replace(d))
			for com, d in rename_dicts.items()
		)
	)

	return lf


def _prepare_columns(cfg: dict, lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Auxfun to prepare the df, adding new columns"""
	animal_ids: list[str] = cfg["animal_ids"]
	return (
		lf.with_columns(
			pl.col("animal_id").cast(pl.Enum(animal_ids)),
			pl.col("antenna").cast(pl.UInt8),
			(pl.col("time_under") * 1000).cast(pl.Duration(time_unit="us")),
		)
		.with_columns(
			(
				pl.concat_str([pl.col("date"), pl.col("time")], separator=" ").str.to_datetime(
					"%Y.%m.%d %H:%M:%S%.f", time_unit="us"
				)
				+ pl.col("time_under")
			).alias("datetime"),
		)
		.drop(["date", "time"])
		.unique(subset=["datetime", "animal_id"], keep="first")
	)


def apply_timezone_fix(frame: pl.DataFrame | pl.LazyFrame, timezone: ZoneInfo) -> pl.DataFrame:
	"""Auxfun to handle winter DST due to time ambiguity. Finds a pivot point (time suddenly going backwards) and establishes it as DST onset."""
	df = frame.collect() if isinstance(frame, pl.LazyFrame) else frame

	diffs = df["datetime"].diff().fill_null(dt.timedelta(microseconds=0))

	if diffs.min() >= dt.timedelta(microseconds=0):
		return df.with_columns(pl.col("datetime").dt.replace_time_zone(timezone.key))

	pivot_index = diffs.arg_min()

	return (
		df.with_row_index()
		.with_columns(pl.col("index").ge(pivot_index).alias("is_after_jump"))
		.with_columns(
			(pl.col("time_under") / 1000).cast(pl.Int64()),
			pl.when(pl.col("is_after_jump"))
			.then(pl.col("datetime").dt.replace_time_zone(timezone.key, ambiguous="latest"))
			.otherwise(pl.col("datetime").dt.replace_time_zone(timezone.key, ambiguous="earliest")),
		)
		.drop("is_after_jump", "index")
	)


def sanitize_timezone(timezone: str) -> ZoneInfo:
	"""Auxfun to check timezone correctness"""
	if timezone is None:
		return get_localzone()
	elif isinstance(timezone, str) and timezone in available_timezones():
		return ZoneInfo(timezone)
	else:
		raise ValueError(
			"Provided timezone not in available timezones or wrong type. To check available timezones run zoneinfo.available_timezones()"
		)


@df_registry.register("padded_df")
def create_padded_df(
	config_path: Path | str | dict,
	lf: pl.LazyFrame,
	save_data: bool = True,
	overwrite: bool = False,
) -> pl.LazyFrame:
	"""Creates a padded DataFrame based on the original main_df. Duplicates indices where the lenght of the detection crosses between phases.
	   Timedeltas for those are changed such that that the detection ends at the very end of the phase and starts again in the next phase as a new detection.

	Args:
	    cfg: dictionary with the project config.
	    df: main_df calculated by get_ecohab_data_structure.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.

	Returns:
	    Padded DataFrame of the main_df.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "padded_df"

	padded_df: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(padded_df, pl.LazyFrame):
		return padded_df

	results_path = Path(cfg["project_location"]) / "results"

	relevant_cols = [
		"animal_id",
		"datetime",
		"phase",
		"phase_count",
		"time_spent",
		"position",
		"antenna",
	]

	lf = lf.select(relevant_cols)

	animals_lf = lf.select("animal_id").unique()

	full_phase_lf = auxfun.get_phase_edge_grid(lf, cfg)

	grid_lf = animals_lf.join(full_phase_lf, how="cross")

	full_lf = (
		grid_lf.join(lf, on=["animal_id", "phase", "phase_count"], how="left")
		.filter(
			(pl.col("phase_end") < pl.col("phase_end").max()).over("animal_id")
			| (pl.col("datetime").is_not_null())
		)
		.with_columns(pl.coalesce([pl.col("datetime"), pl.col("phase_end")]).alias("datetime"))
		.sort(["animal_id", "datetime"])
		.with_columns(pl.col("position").fill_null(strategy="backward").over("animal_id"))
	)
	full_lf = full_lf.with_columns(
		(pl.col("phase") != pl.col("phase").shift(-1).over("animal_id")).alias("mask")
	)

	extension_lf = full_lf.filter(
		pl.col("mask"), pl.col("datetime").ne(pl.col("phase_end"))
	).with_columns(pl.col("phase_end").alias("datetime"))

	padded_lf = pl.concat([full_lf, extension_lf]).sort(["datetime"])

	padded_lf = padded_lf.with_columns(
		pl.when(pl.col("mask"))
		.then(auxfun.get_time_spent_expression(alias=None))
		.otherwise(
			pl.when(pl.col("mask").shift(1).over("animal_id"))
			.then(auxfun.get_time_spent_expression(alias=None))
			.otherwise(pl.col("time_spent"))
		)
		.alias("time_spent"),
		pl.when(pl.col("mask"))
		.then(pl.col("position").shift(-1).over("animal_id"))
		.otherwise(pl.col("position"))
		.alias("position"),
	).drop("mask", "phase_end")

	if save_data:
		padded_lf.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return padded_lf


@df_registry.register("binary_df")
def create_binary_df(
	config_path: str | Path | dict,
	lf: pl.LazyFrame,
	save_data: bool = True,
	overwrite: bool = False,
) -> pl.LazyFrame:
	"""Creates a long format binary DataFrame of the position of the animals.

	Args:
	    config_path: path to project config file.
	    save_data: toogles whether to save data.
	    overwrite: toggles whether to overwrite the data.
	    return_df: toggles whether to return the LazyFrame.

	Returns:
	    Binary LazyFrame (True/False) of position of each animal per second per cage.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "binary_df"

	binary_lf: pl.LazyFrame | None = (
		None if overwrite else auxfun.load_ecohab_data(config_path, key)
	)

	if isinstance(binary_lf, pl.LazyFrame):
		return binary_lf

	results_path = Path(cfg["project_location"]) / "results"

	cages: list[str] = cfg["cages"]
	animal_ids: list[str] = cfg["animal_ids"]

	animals_lf = auxfun.get_lf_from_enum(
		animal_ids, "animal_id", sorted=True, col_type=pl.Enum(animal_ids)
	)

	lf = lf.select(["animal_id", "datetime", "position"]).sort(["animal_id", "datetime"])

	time_range = pl.datetime_range(
		pl.col("datetime").min(),
		pl.col("datetime").max(),
		"1s",
	).alias("datetime")

	range_lf = lf.select(time_range)

	grid_lf = animals_lf.join(range_lf, how="cross", maintain_order="right_left")

	binary_lf = grid_lf.join_asof(
		lf, on="datetime", by="animal_id", strategy="forward", check_sortedness=False
	)

	binary_lf = binary_lf.filter(pl.col("position").is_in(cages)).rename({"position": "cage"})

	if save_data:
		binary_lf.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return binary_lf


@df_registry.register("main_df")
def get_ecohab_data_structure(
	config_path: str,
	fname_prefix: Literal["COM", "20"] = "COM",
	sanitize_animal_ids: bool = True,
	min_antenna_crossings: int = 100,
	custom_layout: bool = False,
	timezone: str | None = None,
	overwrite: bool = False,
	save_data: bool = True,
) -> pl.LazyFrame:
	"""Prepares EcoHab data for further analysis

	Args:
	    config_path: path to project config file
	    sanitize_animal_ids: toggle whether to remove animals. Removes animals that had less than 10 antenna crossings during the whole experiment.
	    fname_prefix: Prefix in the raw data files - used to find correct files in the provided location.
	    min_antenna_crossings: Minimum number of antenna crossings - anything below is considered a ghost tag. Defaults to 100.
	    custom_layout: if multiple boards where added/antennas are in non-default location set to True.
	    overwrite: toggles whether to overwrite existing data file.
	    save_data: toogles whether to save data.
	    timezone: Timezone in IANA format i.e. 'Europe/Warsaw'. If not provided timezone of the computer running the analysis is used.

	Returns:
	    EcoHab data structure as a pl.LazyFrame
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	key = "main_df"

	lf: pl.LazyFrame | None = None if overwrite else auxfun.load_ecohab_data(config_path, key)

	if isinstance(lf, pl.LazyFrame):
		return lf

	results_path = Path(cfg["project_location"]) / "results"

	antenna_pairs: dict[str, str] = cfg["antenna_combinations"]

	try:
		animal_ids: list[str] = cfg["animal_ids"]
	except KeyError:
		animal_ids = None

	lf = load_data(
		config_path=config_path,
		fname_prefix=fname_prefix,
		custom_layout=custom_layout,
		sanitize_animal_ids=sanitize_animal_ids,
		min_antenna_crossings=min_antenna_crossings,
		animal_ids=animal_ids,
	)

	cfg = auxfun.read_config(
		config_path
	)  # reload config potential animal_id changes due to sanitation

	timezone = sanitize_timezone(timezone)

	lf = _prepare_columns(cfg, lf)

	try:
		start_date: str = cfg["experiment_timeline"]["start_date"]
		finish_date: str = cfg["experiment_timeline"]["finish_date"]
	except KeyError:
		print("Start and end dates not provided. Extracting from data...")
		cfg, start_date, finish_date = auxfun.append_start_end_to_config(config_path, lf)

	# Handle timezone, DST and trimming
	has_com = not lf.filter(pl.col("COM").str.contains("COM")).collect().is_empty()

	if not has_com:
		lf = apply_timezone_fix(lf, timezone).lazy()
	else:
		dfs = [
			apply_timezone_fix(lf.filter(pl.col("COM") == com), timezone)
			for com in lf.select("COM").unique().collect()["COM"].to_list()
		]
		lf = pl.concat(dfs).lazy()

	start_date: dt.datetime = dt.datetime.fromisoformat(start_date).astimezone(timezone)
	finish_date: dt.datetime = dt.datetime.fromisoformat(finish_date).astimezone(timezone)

	lf = lf.filter((pl.col("datetime") >= start_date) & (pl.col("datetime") <= finish_date)).sort(
		"datetime"
	)

	# After trimming get phases, days and phase count
	lf = lf.with_columns(
		auxfun.get_phase(cfg),
		auxfun.get_day(),
		auxfun.get_hour(),
	)
	lf = auxfun.get_phase_count(lf)

	lf = calculate_time_spent(lf)
	lf = get_animal_position(lf, antenna_pairs)
	lf = lf.drop("COM")

	auxfun.add_cages_to_config(config_path)
	try:
		cfg["days_range"]
	except KeyError:
		auxfun.add_days_to_config(config_path, lf)

	create_padded_df(config_path, lf, save_data, overwrite)
	create_binary_df(config_path, lf, save_data, overwrite)

	phase_durations_lf: pl.LazyFrame = auxfun.get_phase_durations(lf, cfg)

	positions = (
		auxfun.remove_tunnel_directionality(lf, cfg).collect()["position"].unique().to_list()
	)
	auxfun.add_positions_to_config(config_path, positions)

	if save_data:
		lf.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine="streaming")
		phase_durations_lf.sink_parquet(
			results_path / "phase_durations.parquet", engine="streaming"
		)

	return lf
