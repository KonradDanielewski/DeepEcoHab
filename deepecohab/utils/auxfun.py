import datetime as dt
import importlib
import subprocess
import sys
from pathlib import Path

import polars as pl
import toml


def get_data_paths(data_path: Path) -> list:
    """Auxfun to load all raw data paths"""
    data_files = list(data_path.glob("COM*.txt"))
    if len(data_files) == 0:
        data_files = list(data_path.glob("20*.txt"))
    return data_files


def read_config(config_path: str | Path | dict) -> dict:
    """Auxfun to check validity of the passed config_path variable (config path or dict)"""
    if isinstance(config_path, (str, Path)):
        cfg = toml.load(config_path)
    elif isinstance(config_path, dict):
        cfg = config_path
    else:
        return print(
            f"config_path should be either a dict, Path or str, but {type(config_path)} provided."
        )
    return cfg


def load_ecohab_data(
    config_path: str, key: str, return_df: bool = False
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
    cfg = read_config(config_path)

    results_path = Path(cfg["project_location"]) / "results" / f"{key}.parquet"

    if results_path.is_file():
        try:
            if return_df:
                res_frame = pl.read_parquet(results_path)
            else:
                res_frame = pl.scan_parquet(results_path)
            return res_frame
        except KeyError:
            print(
                f"{key} not found in the specified location: {results_path}. Perhaps not analyzed yet!"
            )


def make_project_path(project_location: str, experiment_name: str) -> str:
    """Auxfun to make a name of the project directory using its name and time of creation"""
    project_name = experiment_name + "_" + dt.datetime.today().strftime("%Y-%m-%d")
    project_location = Path(project_location) / project_name

    return str(project_location)


def get_phase_durations(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun to calculate approximate phase durations.
    Assumes the length is the closest full hour of the total length in seconds (first to last datetime in this phase).
    """
    return (
        lf.group_by(["phase", "phase_count"])
        .agg(
            duration_s=(
                (
                    pl.col("datetime").last() - pl.col("datetime").first()
                ).dt.total_seconds()
            )
        )
        .with_columns(
            ((pl.col("duration_s") / 3600).round(0).clip(1, 12) * 3600)
            .cast(pl.Int64)
            .alias("duration_seconds")
        )
        .select("phase", "phase_count", "duration_seconds")
        .sort(["phase", "phase_count"])
    )


def get_day(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun for getting the day"""
    start_midnight = pl.col("datetime").first().dt.truncate("1d")

    lf = lf.with_columns(
        (pl.col("datetime") - start_midnight)
        .dt.total_days()
        .floor()
        .cast(pl.Int16)
        .add(1)
        .alias("day")
    )
    return lf


def get_phase(cfg: dict, lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun for getting the phase"""
    start_str, end_str = list(cfg["phase"].values())
    phase_names = list(cfg["phase"].keys())
    start_t = dt.time.fromisoformat(start_str)
    end_t = dt.time.fromisoformat(end_str)

    return lf.with_columns(
        pl.when(pl.col("datetime").dt.time().is_between(start_t, end_t, closed="both"))
        .then(pl.lit("light_phase"))
        .otherwise(pl.lit("dark_phase"))
        .cast(pl.Enum(phase_names))
        .alias("phase")
    )


def get_phase_count(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun used to count phases"""
    lf_with_run = lf.with_columns(
        (
            (pl.col("phase") != pl.col("phase").shift(1))
            .fill_null(True)
            .cast(pl.Int8)
            .cum_sum()
            .alias("run_id")
        )
    )

    runs = (
        lf_with_run.select("run_id", "phase")
        .unique()
        .sort("run_id")
        .with_columns(
            pl.col("run_id")
            .rank(method="dense")
            .over("phase")
            .cast(pl.Int16)
            .alias("phase_count")
        )
        .drop("phase")
    )

    return lf_with_run.join(runs, on="run_id", how="left").drop("run_id")


def infer_animal_ids(
    config_path: str,
    lf: pl.LazyFrame,
    sanitize_animal_ids: bool = False,
    min_antenna_crossings: int = 100,
) -> pl.LazyFrame:
    """Auxfun to infer animal ids from data, optionally removing ghost tags (random radio noise reads)."""
    cfg = read_config(config_path)

    animal_ids = (
        lf.select(pl.col("animal_id").unique().alias("animal_id"))
        .collect()["animal_id"]
        .to_list()
    )

    if sanitize_animal_ids:
        antenna_crossings = lf.group_by(pl.col("animal_id")).len().collect()

        animals_to_drop = (
            antenna_crossings.filter(pl.col("len") < min_antenna_crossings)
            .get_column("animal_id")
            .to_list()
        )

        if animals_to_drop:
            print(f"IDs dropped from dataset {animals_to_drop}")
            drop = set(animals_to_drop)
            animal_ids = sorted(set(animal_ids) - drop)
            lf = lf.filter(pl.col("animal_id").is_in(pl.lit(animal_ids)))

        cfg["dropped_ids"] = animals_to_drop
    else:
        print("No ghost tags detected :)")

    cfg["animal_ids"] = animal_ids
    with config_path.open("w") as f:
        toml.dump(cfg, f)

    return lf


def append_start_end_to_config(config_path: str, lf: pl.LazyFrame) -> dict:
    """Auxfun to append start and end datetimes of the experiment if not user provided.

    Returns:
        Config with updated start and end datetimes
    """
    cfg = read_config(config_path)
    bounds = lf.select(
        [
            pl.col("datetime").first().alias("start_time"),
            pl.col("datetime").last().alias("end_time"),
        ]
    ).collect()

    start_time = str(bounds["start_time"][0])
    end_time = str(bounds["end_time"][0])

    f = open(config_path, "w")
    cfg["experiment_timeline"] = {
        "start_date": start_time,
        "finish_date": end_time,
    }

    toml.dump(cfg, f)
    f.close()

    print(
        f"Start of the experiment established as: {start_time} and end as {end_time}.\nIf you wish to set specific start and end, please change them in the config file and create the data structure again setting overwrite=True"
    )

    return cfg


def add_cages_to_config(config_path: str) -> None:
    """Auxfun to add cage names to config for reading convenience"""
    cfg = read_config(config_path)

    positions = list(set(cfg["antenna_combinations"].values()))
    cages = [pos for pos in positions if "cage" in pos]

    f = open(config_path, "w")
    cfg["cages"] = cages

    toml.dump(cfg, f)
    f.close()


def run_dashboard(config_path: str | dict):
    """Auxfun to open dashboard for experiment from provided config"""
    cfg = read_config(config_path)
    data_path = Path(cfg["project_location"]) / "results" / "results.h5"
    cfg_path = Path(cfg["project_location"]) / "config.toml"

    path_to_dashboard = importlib.util.find_spec("deepecohab.dash.dashboard").origin

    process = subprocess.Popen(
        [
            sys.executable,
            path_to_dashboard,
            "--results-path",
            data_path,
            "--config-path",
            cfg_path,
        ]
    )

    return process


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


def remove_tunnel_directionality(lf: pl.LazyFrame, cfg: dict) -> pl.LazyFrame:
    """Auxfun to map directional tunnels in a LazyFrame to undirected ones"""
    tunnels = cfg["tunnels"]

    return lf.with_columns(
        pl.col("position")
        .cast(pl.Utf8)
        .replace(tunnels)
        .cast(pl.Categorical)
        .alias("position")
    )
