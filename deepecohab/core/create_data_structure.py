import datetime as dt
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, available_timezones

import polars as pl
from polars.exceptions import ComputeError
from tzlocal import get_localzone

from deepecohab.core.registries import df_registry
from deepecohab.utils import auxfun


def load_data(
	config_path: str | Path,
	fname_prefix: str,
	custom_layout: bool,
	sanitize_animal_ids: bool,
	min_antenna_crossings: int,
	animal_ids: list | None = None,
) -> pl.LazyFrame:
	"""Load and combine the raw EcoHab ``.txt`` files into a single LazyFrame.

	Globs every ``<fname_prefix>*.txt`` under the configured ``data_path`` and reads
	them as one tab-separated source, tagging each row with the COM port (board)
	extracted from its filename. Animal ids are resolved (and ghost tags optionally
	dropped) via ``auxfun.set_animal_ids``, and antennas are remapped when a custom
	layout is in use.

	Raises:
	    FileNotFoundError: No matching ``.txt`` files were found under ``data_path``.

	Returns:
	    A LazyFrame with the combined registrations and a ``COM`` board column.
	"""
	cfg: dict[str, Any] = auxfun.read_config(config_path)
	data_path = Path(cfg["data_path"])

	try:
		lf = pl.scan_csv(
			source=data_path / f"{fname_prefix}*.txt",
			separator="\t",
			has_header=False,
			new_columns=["ind", "date", "time", "antenna", "time_under", "animal_id"],
			include_file_paths="file",
			glob=True,
			schema={
				"ind": pl.Int64,
				"date": pl.String,
				"time": pl.String,
				"antenna": pl.Int64,
				"time_under": pl.Int64,
				"animal_id": pl.String,
			},
			truncate_ragged_lines=True,
		)
	except ComputeError as e:
		# NOTE: maybe we should catch lack fo data earlier? otherwise this error is fragile and can be false
		raise FileNotFoundError(
			f"No .txt files found at {data_path} with prefix '{fname_prefix}'"
		) from e

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
	"""Add a ``time_spent`` column: seconds between consecutive rows per animal.

	The value is the gap to the previous registration of the same animal, i.e. the
	time spent in the current state, rounded to two decimals (tens of milliseconds).
	The first registration of each animal has no predecessor and gets 0.
	"""
	time_spent = (
		(pl.col("datetime") - pl.col("datetime").shift(1))
		.over("animal_id")
		.dt.total_seconds(fractional=True)
		.fill_null(0)
		.cast(pl.Float64)
		.round(2)
	)
	return lf.with_columns(time_spent.alias("time_spent"))


def get_animal_position(lf: pl.LazyFrame, antenna_pairs: dict) -> pl.LazyFrame:
	"""Derive each row's ``position`` from its antenna and the previous one.

	Per animal, the previous and current antenna are joined as a ``"<prev>_<curr>"``
	key and looked up in ``antenna_pairs`` to name the position (cage or directional
	tunnel). The first reading of each animal has no predecessor, so a ``0`` previous
	antenna is used; unmapped pairs become ``"undefined"``.
	"""
	prev_ant = pl.col("antenna").shift(1).over("animal_id").fill_null(0).cast(pl.Utf8)
	curr_ant = pl.col("antenna").cast(pl.Utf8)

	pair = pl.concat_str([prev_ant, pl.lit("_"), curr_ant])

	return lf.with_columns(
		[
			pair.replace_strict(antenna_pairs, default="undefined")
			.alias("position")
			.cast(pl.Categorical)
		]
	)


def _rename_antennas(lf: pl.LazyFrame, rename_dicts: dict) -> pl.LazyFrame:
	"""Auxfun for antenna name mapping when custom layout is used."""
	lf = lf.with_columns(
		pl.coalesce(
			pl.when(pl.col("COM") == com).then(pl.col("antenna").replace(d))
			for com, d in rename_dicts.items()
		)
	)

	return lf


def _prepare_columns(cfg: dict, lf: pl.LazyFrame, timezone: str) -> pl.LazyFrame:
	"""Cast raw columns to their final types and build the ``datetime`` column.

	Animal ids become an enum, antennas a small int and ``time_under`` a duration.
	The separate date/time strings are combined into a single timezone-aware
	``datetime`` (offset by ``time_under`` so it marks the end of the reading), and
	duplicate (datetime, animal) rows are dropped.
	"""
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
					"%Y.%m.%d %H:%M:%S%.f",
					time_unit="us",
					time_zone=timezone,
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
			pl.when(pl.col("is_after_jump"))
			.then(pl.col("datetime").dt.replace_time_zone(timezone.key, ambiguous="latest"))
			.otherwise(pl.col("datetime").dt.replace_time_zone(timezone.key, ambiguous="earliest")),
		)
		.drop("is_after_jump", "index")
	)


def sanitize_timezone(
	timezone: str,
) -> ZoneInfo:  # TODO: This should be happening at user input not dataset creation
	"""Auxfun to check timezone correctness."""
	if timezone is None:
		return get_localzone()
	elif isinstance(timezone, str) and timezone in available_timezones():
		return ZoneInfo(timezone)
	else:
		raise ValueError(
			"Provided timezone not in available timezones or wrong type. To check available timezones run zoneinfo.available_timezones()"
		)


def extrapolate_last_position(lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Extrapolate the last position for each animal to the experiment end.

	This allows better calculation of time spent in positions and cage
	occupancy in experiments with low activity.
	"""
	last_rows_lf = lf.group_by("animal_id").agg(pl.all().sort_by("datetime").last())

	global_last_lf = lf.select(pl.col("datetime").max().alias("global_last_dt"))

	artificial_rows = (
		last_rows_lf.join(global_last_lf, how="cross")
		.filter(pl.col("datetime") != pl.col("global_last_dt"))
		.with_columns(pl.col("global_last_dt").alias("datetime"))
		.drop("global_last_dt")
		.select(["antenna", "time_under", "animal_id", "datetime"])
	)

	return pl.concat([lf, artificial_rows]).sort("datetime")


@df_registry.register("main_df")
def get_ecohab_data_structure(
	config_path: str,
	fname_prefix: Literal["COM", "20"] = "COM",
	sanitize_animal_ids: bool = True,
	min_antenna_crossings: int = 100,
	custom_layout: bool = False,
	overwrite: bool = False,
	save_data: bool = True,
) -> pl.LazyFrame:
	"""Build the main EcoHab data structure (``main_df``) from raw registrations.

	This is the entry point of the data-structure stage. It loads and combines the
	raw ``.txt`` files, resolves animal ids and the timezone, parses timestamps,
	applies the DST fix, trims to the experiment window, annotates each row with its
	phase/day/hour and position, and extrapolates the final position. Several config
	conveniences (cages, positions, day range) and the ``phase_durations`` table are
	written as side effects. The result is cached as ``results/main_df.parquet`` and
	reused on subsequent calls unless ``overwrite`` is set.

	Args:
	    config_path: Path to the project config file.
	    fname_prefix: Prefix of the raw data files, used to locate them in
	        ``data_path``.
	    sanitize_animal_ids: Drop animals whose total antenna crossings fall below
	        ``min_antenna_crossings`` (treated as ghost tags).
	    min_antenna_crossings: Crossing count below which a tag is considered a
	        ghost tag. Defaults to 100.
	    custom_layout: Set True when multiple boards are used or antennas are in
	        non-default locations, so ``antenna_rename_scheme`` is applied.
	    overwrite: Rebuild and overwrite the cached data file instead of loading it.
	    save_data: Whether to persist the resulting parquet files.

	Returns:
	    The EcoHab data structure as a ``pl.LazyFrame``.
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

	timezone = sanitize_timezone(cfg["timezone"])
	cfg["timezone"] = timezone

	cfg = auxfun.read_config(config_path)

	lf = _prepare_columns(cfg, lf, str(timezone))

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

	# Trim then get phases, days and phase count
	lf = (
		lf.drop("COM")
		.filter((pl.col("datetime") >= start_date) & (pl.col("datetime") <= finish_date))
		.sort("datetime")
		.pipe(extrapolate_last_position)
		.with_columns(
			auxfun.get_phase(cfg),
			auxfun.get_day(),
			auxfun.get_hour(),
		)
		.pipe(auxfun.get_phase_count)
		.pipe(calculate_time_spent)
		.pipe(get_animal_position, antenna_pairs)
	)

	auxfun.add_cages_to_config(config_path)
	auxfun.add_positions_to_config(config_path)

	try:
		cfg["days_range"]
	except KeyError:
		auxfun.add_days_to_config(config_path, lf)

	auxfun.padded_df(lf, cfg, save_data, overwrite)

	phase_durations_lf: pl.LazyFrame = auxfun.get_phase_durations(cfg)

	if save_data:
		lf.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine="streaming")
		phase_durations_lf.sink_parquet(
			results_path / "phase_durations.parquet", engine="streaming"
		)

	return lf
