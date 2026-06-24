import datetime as dt
from itertools import combinations, product
from pathlib import Path
from typing import (
	Any,
	Literal,
	overload,
)

import polars as pl
import toml

from deepecohab.core.registries import df_registry


def read_config(config_path: str | Path | dict[str, Any]) -> dict:
	"""Auxfun to check validity of the passed config_path variable (config path or dict)."""
	if isinstance(config_path, dict):
		return config_path

	elif isinstance(config_path, (str, Path)):
		with open(config_path) as f:
			config: dict[str, Any] = toml.load(f)
		return config

	else:
		raise TypeError(
			f"config_path should be either a dict, Path or str, but {type(config_path)} provided."
		)


@overload
def load_ecohab_data(
	config_path: str | Path | dict[str, Any], key: str, return_df: Literal[False] = False
) -> pl.LazyFrame | None: ...
@overload
def load_ecohab_data(
	config_path: str | Path | dict[str, Any], key: str, return_df: Literal[True]
) -> pl.DataFrame | None: ...
def load_ecohab_data(
	config_path: str | Path | dict[str, Any], key: str, return_df: bool = False
) -> pl.LazyFrame | pl.DataFrame | None:
	"""Loads already analyzed main data structure.

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

	cfg: dict[str, Any] = read_config(config_path)
	results_path: Path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"

	if not results_path.is_file():
		return None

	return pl.read_parquet(results_path) if return_df else pl.scan_parquet(results_path)


def _get_data(config_path: str | Path | dict[str, Any], key: str) -> pl.LazyFrame:
	"""Like load_ecohab_data but raises if the file doesn't exist."""
	lf = load_ecohab_data(config_path, key)
	if lf is None:
		raise FileNotFoundError(
			f"'{key}.parquet' not found. Run the appropriate pipeline step first."
		)
	return lf


def make_project_path(project_location: Path, experiment_name: str) -> Path:
	"""Auxfun to make a name of the project directory using its name and time of creation."""
	project_name: Path = Path(experiment_name + "_" + dt.datetime.today().strftime("%Y-%m-%d"))
	project_location: Path = project_location / project_name

	return project_location


@df_registry.register("phase_durations")
def get_phase_durations(cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Compute the duration in seconds of every phase occurrence in the experiment.

	Walks the experiment window in one-minute steps, assigns each minute to its
	phase and occurrence count, and sums the per-occurrence span. Durations are
	therefore approximate, accurate to roughly one minute.

	Returns:
	    A LazyFrame with ``phase``, ``phase_count`` and ``duration_seconds`` columns.
	"""
	phase_durations = (
		pl.LazyFrame(
			pl.datetime_range(
				dt.datetime.fromisoformat(cfg["experiment_timeline"]["start_date"]),
				dt.datetime.fromisoformat(cfg["experiment_timeline"]["finish_date"]),
				interval="1m",
				time_zone=cfg["timezone"],
				closed="left",
				eager=True,
			).dt.round("1m")
		)
		.rename({"literal": "datetime"})
		.with_columns(get_phase(cfg))
		.pipe(get_phase_count)
		.group_by("phase", "phase_count")
		.agg(
			((pl.col("datetime").max() - pl.col("datetime").min()) + pl.duration(minutes=1))
			.dt.total_seconds()
			.alias("duration_seconds")
		)
	)

	return phase_durations


def get_phase(cfg: dict[str, Any], dt_col: str = "datetime") -> pl.Expr:
	"""Assign each row to a circadian phase from its local time of day.

	cfg["phase"] maps each phase name to the wall-clock time it begins, e.g.
	    {"light_phase": "07:00:00", "dark_phase": "20:00:00"}
	means light_phase runs [07:00, 20:00) and dark_phase runs [20:00, 07:00),
	wrapping around midnight. Phases are assumed to tile the full 24h day.
	"""
	phase_names = list(cfg["phase"])

	boundaries = sorted(
		(dt.time.fromisoformat(start), name) for name, start in cfg["phase"].items()
	)

	dst_shift = pl.col(dt_col).dt.dst_offset() - pl.col(dt_col).first().dt.dst_offset()
	time_of_day = (pl.col(dt_col) - dst_shift).dt.time()

	expr = pl.lit(boundaries[-1][1])
	for start, name in boundaries:
		expr = pl.when(time_of_day >= start).then(pl.lit(name)).otherwise(expr)

	return expr.cast(pl.Enum(phase_names)).alias("phase")


def get_phase_count(lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Number each phase's successive occurrences in a ``phase_count`` column.

	Consecutive rows sharing a ``phase`` form one run (via run-length ids); the runs
	of a given phase are then densely ranked so the first dark phase is 1, the second
	2, and so on. Requires a ``phase`` column and the frame to be in chronological order.
	"""
	lf = (
		lf.with_columns(pl.col("phase").rle_id().alias("run_id"))
		.with_columns(
			pl.col("run_id").rank("dense").over("phase").cast(pl.UInt16).alias("phase_count")
		)
		.drop("run_id")
	)
	return lf


@overload
def get_grid_phase_count(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame: ...
@overload
def get_grid_phase_count(lf: pl.DataFrame, cfg: dict[str, Any]) -> pl.DataFrame: ...
def get_grid_phase_count(
	lf: pl.LazyFrame | pl.DataFrame, cfg: dict[str, Any]
) -> pl.LazyFrame | pl.DataFrame:
	"""Attach the grid-authoritative ``phase_count`` by lookup against the time grid.

	Unlike :func:`get_phase_count`, which run-length-encodes whatever rows it is
	handed -- and so depends on those rows being in chronological order and on every
	phase occurrence being represented -- this joins against the dense experiment
	skeleton from :func:`build_time_grid` on ``(day, phase, hour)``. The result
	therefore equals ``build_time_grid``'s numbering by construction, which is what
	tables later reindexed onto that grid (via :func:`reindex_onto_grid`) require.

	``lf`` must already carry ``day``, ``phase`` and ``hour`` (e.g. derived via
	:func:`get_day`, :func:`get_phase` and :func:`get_hour`); ``(day, phase, hour)``
	functionally determines ``phase_count`` in the grid, so the join is one-to-one.
	"""
	grid_counts = build_time_grid(cfg).select("day", "phase", "hour", "phase_count").unique()
	on = ["day", "phase", "hour"]
	if isinstance(lf, pl.DataFrame):
		return lf.join(grid_counts.collect(), on=on, how="left")
	return lf.join(grid_counts, on=on, how="left")


def get_day(dt_col: str = "datetime") -> pl.Expr:
	"""Auxfun for getting the day."""
	return (
		((pl.col(dt_col).dt.date() - pl.col(dt_col).dt.date().min()).dt.total_days())
		.add(1)
		.cast(pl.UInt16)
		.alias("day")
	)


def get_hour(dt_col: str = "datetime") -> pl.Expr:
	"""Expression extracting the hour of day (0-23) as ``hour``."""
	return pl.col(dt_col).dt.hour().cast(pl.UInt8).alias("hour")


def get_positions(
	cfg: dict[str, Any],
	kind: Literal["all", "cages", "tunnels", "tunnels_directional"] = "all",
) -> list[str]:
	"""Return a position subset of the requested ``kind``.

	- ``"all"``: every position (cages, undirected tunnels and ``undefined``).
	- ``"cages"``: cage positions only.
	- ``"tunnels"``: undirected tunnel positions (e.g. ``tunnel_1``).
	- ``"tunnels_directional"``: directional tunnel positions (e.g. ``c1_c2``),
	  as they appear in ``main_df`` before ``remove_tunnel_directionality``.
	"""
	cfg = read_config(cfg)
	match kind:
		case "all":
			return cfg["positions"]
		case "cages":
			return cfg["cages"]
		case "tunnels":
			return [
				pos for pos in cfg["positions"] if pos not in cfg["cages"] and pos != "undefined"
			]
		case "tunnels_directional":
			return [pos for pos in cfg["antenna_combinations"].values() if "cage" not in pos]
		case _:
			raise ValueError(f"Unknown position kind: {kind!r}")


def set_animal_ids(
	config_path: str | Path,
	lf: pl.LazyFrame,
	sanitize_animal_ids: bool,
	min_antenna_crossings: int,
	animal_ids: list | None = None,
) -> pl.LazyFrame:
	"""Auxfun to infer animal ids from data, optionally removing ghost tags (random radio noise reads)."""
	cfg: dict[str, Any] = read_config(config_path)
	dropped_ids: list[str] = []

	if isinstance(animal_ids, list):
		lf: pl.LazyFrame = lf.filter(pl.col("animal_id").is_in(animal_ids))
	else:
		animal_detections: pl.DataFrame = lf.group_by("animal_id").len().collect()

		if sanitize_animal_ids:
			is_ghost: pl.Expr = pl.col("len") < min_antenna_crossings

			dropped_ids: list[str] = animal_detections.filter(is_ghost)["animal_id"].to_list()
			animal_ids: list[str] = animal_detections.filter(~is_ghost)["animal_id"].to_list()

			if dropped_ids:
				print(f"IDs dropped from dataset {dropped_ids}")
			else:
				print("No ghost tags detected :)")
		else:
			animal_ids: list[str] = animal_detections.get_column("animal_id").to_list()

		animal_ids: list[str] = sorted(animal_ids)
		lf: pl.LazyFrame = lf.filter(pl.col("animal_id").is_in(animal_ids))

	cfg.update({"animal_ids": animal_ids, "dropped_ids": dropped_ids})
	with open(config_path, "w") as f:
		toml.dump(cfg, f)

	return lf


def update_repeat_antenna_position(lf: pl.LazyFrame) -> pl.LazyFrame:
	"""Map repeat antenna registrations to repeated cage/tunnel movement.

	Repeat registrations under the same antenna become repeated movement
	between the corresponding cage and tunnel.

	Args:
		lf: a LazyFrame containing mouse position data

	Returns:
	    lf: a LazyFrame with updated positions
	"""
	# TODO
	tunnel_dict = {
		"1": "c1_c2",
		"2": "c2_c1",
		"3": "c2_c3",
		"4": "c3_c2",
		"5": "c3_c4",
		"6": "c4_c3",
		"7": "c4_c1",
		"8": "c1_c4",
	}

	lf = lf.with_columns(
		pl.struct("position", "antenna").rle_id().over("animal_id").alias("run_id")
	).with_columns(
		pl.cum_count("position").over(["animal_id", "run_id"]).alias("consecutive_antenna_readout")
	)
	lf = lf.with_columns(
		pl.when(pl.col("consecutive_antenna_readout").mod(2) == 0)
		.then(pl.col("antenna").cast(pl.Utf8).replace(tunnel_dict).cast(pl.Categorical))
		.otherwise(pl.col("position"))
		.alias("position")
	)

	return lf


def append_start_end_to_config(
	config_path: str | Path, lf: pl.LazyFrame
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

	start_time = str(bounds.get_column("start_time")[0])
	end_time = str(bounds.get_column("end_time")[0])

	with open(config_path, "w") as config:
		cfg["experiment_timeline"] = {
			"start_date": start_time,
			"finish_date": end_time,
		}
		toml.dump(cfg, config)

	print(
		f"Start of the experiment established as: {start_time} and end as {end_time}.\nIf you wish to set specific start and end, please change them in the config file and create the data structure again setting overwrite=True"
	)

	return cfg, start_time, end_time


def add_cages_to_config(config_path: str | Path) -> None:
	"""Auxfun to add cage names to config for reading convenience."""
	cfg: dict[str, Any] = read_config(config_path)

	positions: list[str] = list(set(cfg["antenna_combinations"].values()))
	cages: list[str] = [pos for pos in positions if "cage" in pos]

	with open(config_path, "w") as config:
		cfg["cages"] = sorted(cages)
		toml.dump(cfg, config)


def add_positions_to_config(config_path: str | Path) -> None:
	"""Add the sorted list of all positions to config under ``positions``.

	Covers undirected tunnels, cages and ``undefined``; stored for reading
	convenience.
	"""
	cfg: dict[str, Any] = read_config(config_path)

	positions = {
		cfg["tunnels"].get(value, value) for value in cfg["antenna_combinations"].values()
	} | {"undefined"}

	with open(config_path, "w") as config:
		cfg["positions"] = sorted(positions)
		toml.dump(cfg, config)


def add_days_to_config(config_path: str | Path, lf: pl.LazyFrame) -> None:
	"""Auxfun to add days range to config for reading convenience."""
	cfg: dict[str, Any] = read_config(config_path)

	days: pl.Series = lf.collect().get_column("day").unique(maintain_order=True)

	with open(config_path, "w") as config:
		cfg["days_range"] = [days.min(), days.max()]
		toml.dump(cfg, config)


def remove_tunnel_directionality(lf: pl.LazyFrame, cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Auxfun to map directional tunnels in a LazyFrame to undirected ones."""
	return lf.with_columns(
		pl.col("position").cast(pl.Utf8).replace(cfg["tunnels"]).cast(pl.Categorical)
	)


def _get_minute_padding(lf: pl.LazyFrame, cfg: dict[str, Any]):
	"""Split rows that straddle minute boundaries into per-minute pieces.

	Each input row describes an interval ending at ``datetime`` that lasted
	``time_spent`` seconds (with ``time_under`` an associated duration). A single
	interval may span several wall-clock minutes; this splits it at every minute
	boundary so that no resulting piece crosses one, which lets time be attributed
	to the correct minute/phase/hour bin downstream.

	``time_spent`` is recomputed as each piece's own length, and ``time_under`` is
	redistributed across pieces in proportion to their duration (the parent total
	is preserved up to rounding). Pieces are timestamped by their start: ``phase``,
	``day`` and ``hour`` are derived from the piece start, while ``datetime`` is set
	to the piece end. Rows that were actually split are flagged ``interpolated``.

	Args:
		lf: Frame with at least ``datetime``, ``time_spent`` (seconds) and
			``time_under`` (duration) columns.
		cfg: Config mapping used by ``get_phase`` for phase assignment.

	Returns:
		Frame with the same schema plus ``interpolated`` and a ``row_id`` index
		identifying the original (pre-split) row; one row per minute-aligned piece.
	"""
	minute: pl.Expr = pl.duration(minutes=1)

	minute_padded: pl.LazyFrame = (
		lf.with_row_index("row_id")
		.with_columns(
			pl.col("datetime")
			.sub(
				pl.duration(microseconds=(pl.col("time_spent") * 1_000_000).round().cast(pl.Int64))
			)
			.alias("__start")
		)
		.with_columns(
			pl.datetime_ranges(
				pl.col("__start").dt.truncate("1m") + minute,
				pl.col("datetime"),
				interval="1m",
				closed="left",
			).alias("__marks")
		)
		.with_columns(
			pl.concat_list("__start", "__marks").alias("__pstart"),
			pl.concat_list("__marks", "datetime").alias("__pend"),
		)
		.explode("__pstart", "__pend", empty_as_null=True)
		.with_columns(
			(pl.col("datetime") - pl.col("__start")).dt.total_microseconds().alias("__total_us"),
			(pl.col("__pend") - pl.col("__pstart")).dt.total_microseconds().alias("__piece_us"),
		)
		.with_columns(
			(pl.col("__piece_us") / 1_000_000).alias("time_spent"),
			pl.when(pl.col("__total_us") > 0)
			.then(
				pl.duration(
					microseconds=(
						(
							pl.col("time_under").dt.total_microseconds().mul(pl.col("__piece_us"))
						).truediv(pl.col("__total_us").clip(lower_bound=1))
					)
					.round()
					.cast(pl.Int64)
				)
			)
			.otherwise(pl.col("time_under"))
			.alias("time_under"),
			(pl.len().over("row_id") > 1).alias("interpolated"),
		)
		.with_columns(
			get_phase(cfg, "__pstart"),
			get_day("__pstart"),
			get_hour("__pstart"),
			pl.col("__pend").alias("datetime"),
		)
		.select(
			pl.exclude("^__.*$")
		)  # row_id preserved to keep information on original rows unique('row_id', keep='first')
	)

	return minute_padded


@df_registry.register("padded_df")
def padded_df(
	lf: pl.LazyFrame, cfg: dict[str, Any], save_data: bool = True, overwrite: bool = False
) -> pl.LazyFrame:
	"""Split each visit interval at wall-clock minute boundaries.

	Each row is the half-open interval [datetime - time_spent, datetime).
	Intervals crossing one or more minute marks are cut into per-minute pieces.
	Pieces originating from a cut are flagged interpolated=True; untouched
	rows are interpolated=False.
	"""
	cfg: dict[str, Any] = read_config(cfg)
	key = "padded_df"

	minute_padded: pl.LazyFrame | None = None if overwrite else load_ecohab_data(cfg, key)

	if isinstance(minute_padded, pl.LazyFrame):
		return minute_padded

	results_path = Path(cfg["project_location"]) / "results"

	minute_padded = _get_minute_padding(lf, cfg)

	if save_data:
		minute_padded.sink_parquet(
			results_path / f"{key}.parquet", compression="lz4", engine="streaming"
		)

	return minute_padded


def build_time_grid(cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Build the dense hourly time skeleton spanning the experiment.

	Produces one row per hourly bin between the experiment's start and finish
	dates (both inclusive), with both bounds floored to the hour so the grid is
	independent of the sub-hour offsets of the raw timestamps. Each bin is
	annotated with its day, circadian phase, hour of day and phase occurrence
	count (see ``get_day``, ``get_phase``, ``get_hour`` and ``get_phase_count``).

	This is the temporal half of the dense reference grid that observed data is
	reindexed onto, so bins with no activity are still represented (e.g. as zero
	counts) downstream. Cross-join it with :func:`build_animal_grid` to obtain the
	full grid for a given table.

	Args:
		cfg: Path or mapping resolved by ``read_config``; must provide
			``experiment_timeline`` (``start_date``/``finish_date``), ``timezone``
			and ``phase``.

	Returns:
		Frame with columns ``day``, ``phase``, ``hour`` and ``phase_count``.
	"""
	cfg = read_config(cfg)

	start = dt.datetime.fromisoformat(cfg["experiment_timeline"]["start_date"]).replace(
		minute=0, second=0, microsecond=0
	)
	finish = dt.datetime.fromisoformat(cfg["experiment_timeline"]["finish_date"]).replace(
		minute=0, second=0, microsecond=0
	)

	return (
		pl.LazyFrame()
		.select(
			pl.datetime_range(
				start,
				finish,
				interval="1h",
				closed="both",
				time_zone=cfg["timezone"],
			).alias("__datetime")
		)
		.with_columns(
			get_day(dt_col="__datetime"),
			get_phase(cfg, dt_col="__datetime"),
			get_hour(dt_col="__datetime"),
		)
		.pipe(get_phase_count)
		.drop("__datetime")
	)


def build_animal_grid(
	cfg: dict[str, Any],
	columns: str | tuple[str, str],
	ordered: bool = True,
	positions: list[str] | None = None,
) -> pl.LazyFrame:
	"""Build the entity half of a reference grid: every animal (or animal pair).

	Depending on ``columns`` this enumerates either single animals or animal
	pairs, optionally crossed with a set of positions. Cross-join the result with
	:func:`build_time_grid` to obtain the dense grid a table is reindexed onto.

	Args:
		cfg: Path or mapping resolved by ``read_config``; must provide
			``animal_ids``.
		columns: A single column name for a per-animal grid (e.g. ``"animal_id"``),
			or a pair of names for a per-pair grid (e.g. ``("winner", "loser")`` or
			``("animal_id", "animal_id_2")``).
		ordered: For pair grids only, whether to enumerate ordered pairs
			(``a != b`` in both directions, for directed measures like chasings) or
			unordered combinations (``a < b``, for symmetric measures like
			pairwise encounters). Ignored for single-animal grids.
		positions: When given, the grid is crossed with these positions under a
			``position`` column. When ``None`` no position column is added.

	Returns:
		Frame with the requested animal column(s) and, if ``positions`` is given,
		a ``position`` column.
	"""
	cfg = read_config(cfg)
	animal_ids: list[str] = cfg["animal_ids"]
	enum = pl.Enum(animal_ids)

	if isinstance(columns, str):
		schema: dict[str, Any] = {columns: enum}
		rows = [(animal,) for animal in animal_ids]
	else:
		if len(columns) != 2:
			raise ValueError(f"columns must be a single name or a pair of names, got {columns!r}")
		first, second = columns
		if ordered:
			rows = [(a, b) for a, b in product(animal_ids, animal_ids) if a != b]
		else:
			rows = list(combinations(animal_ids, 2))
		schema: dict[str, Any] = {first: enum, second: enum}

	if positions is not None:
		rows = [(*row, pos) for row, pos in product(rows, positions)]
		schema["position"] = pl.Categorical

	return pl.LazyFrame(rows, schema=schema, orient="row")


def build_experiment_grid(cfg: dict[str, Any]) -> pl.LazyFrame:
	"""Build the complete animal x position x hour grid spanning the experiment.

	Thin convenience wrapper that cross-joins :func:`build_time_grid` with a
	single-animal :func:`build_animal_grid` over every position. This is the dense
	reference grid that per-animal, per-position tables (e.g. ``activity_df``) are
	reindexed onto, so that bins with no activity are still represented as zeros.

	Returns:
		Frame with columns ``day``, ``phase``, ``hour``, ``phase_count``,
		``position`` and ``animal_id`` covering every animal x position x hour cell.
	"""
	cfg = read_config(cfg)
	return build_time_grid(cfg).join(
		build_animal_grid(cfg, "animal_id", positions=cfg["positions"]),
		how="cross",
	)


def reindex_onto_grid(
	data: pl.LazyFrame,
	cfg: dict[str, Any],
	columns: str | tuple[str, str],
	ordered: bool = True,
	positions: list[str] | None = None,
) -> pl.LazyFrame:
	"""Reindex an observed table onto the dense time x animal(x position) grid.

	Cross-joins :func:`build_time_grid` with :func:`build_animal_grid` to obtain
	the dense reference grid, then left-joins ``data`` onto it so every grid cell
	is present, filling cells with no observed value with ``0``. The join keys are
	derived from the grid: the time columns (``phase``, ``day``, ``phase_count``,
	``hour``), the ``position`` column when ``positions`` is given, and the animal
	column(s) named in ``columns``.

	Args:
		data: Observed table to reindex; must contain the derived join columns.
		cfg: Path or mapping resolved by ``read_config``.
		columns: Animal column(s) for :func:`build_animal_grid` (a single name or
			a pair).
		ordered: For pair grids, whether to enumerate ordered pairs. See
			:func:`build_animal_grid`.
		positions: When given, the grid is crossed with these positions and
			``position`` becomes a join key. When ``None`` no position column is used.

	Returns:
		``data`` reindexed onto the dense grid, with absent cells filled with ``0``.
	"""
	cfg = read_config(cfg)
	full_grid = build_time_grid(cfg).join(
		build_animal_grid(cfg, columns, ordered=ordered, positions=positions),
		how="cross",
	)

	animal_cols = [columns] if isinstance(columns, str) else list(columns)
	on = ["phase", "day", "phase_count", "hour"]
	if positions is not None:
		on.append("position")
	on += animal_cols

	return full_grid.join(data, on=on, how="left").fill_null(0)
