import datetime as dt
from pathlib import Path
from typing import Literal

import polars as pl
from tzlocal import get_localzone

from deepecohab.utils import auxfun
from deepecohab.utils.auxfun import df_registry


def load_data(
    config_path: str | Path,
    custom_layout: bool,
    sanitize_animal_ids: bool,
    fname_prefix: str,
    min_antenna_crossings: int = 100,
    animal_ids: list | None = None,
) -> pl.LazyFrame:
    """Auxfun to load and combine text files into a LazyFrame"""
    cfg = auxfun.read_config(config_path)
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
        pl.col("file")
        .str.extract(r"([^/\\]+)$")
        .str.split("_")
        .list.get(0)
        .alias("COM")
    ).drop(["ind", "file"])

    
    lf = auxfun.set_animal_ids(
        config_path, lf, animal_ids, sanitize_animal_ids, min_antenna_crossings
    )

    if custom_layout:
        rename_dicts = cfg["antenna_rename_scheme"]
        lf = _rename_antennas(lf, rename_dicts)

    auxfun.add_cages_to_config(config_path)

    return lf


def correct_phases_dst(cfg: dict, lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun to adjust phase start/end to dayligh saving time shift"""
    start_time, end_time = cfg["phase"].values()
    start_time = dt.time.fromisoformat(start_time)
    end_time = dt.time.fromisoformat(end_time)

    time_offset = (
        pl.col("datetime").dt.dst_offset() - pl.col("datetime").first().dt.dst_offset()
    )

    lf = (
        lf.with_columns((pl.col("datetime") + time_offset).alias("datetime_shifted"))
        .with_columns(
            pl.when(pl.col("datetime") != pl.col("datetime_shifted"))
            .then(
                pl.when(
                    pl.col("datetime_shifted")
                    .dt.time()
                    .is_between(start_time, end_time, closed="both")
                )
                .then(pl.lit("light_phase"))
                .otherwise(pl.lit("dark_phase"))
            )
            .otherwise(pl.col("phase"))
            .alias("phase")
        )
        .drop("datetime_shifted")
    )

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
        [
            pair.replace(antenna_pairs, default="undefined")
            .alias("position")
            .cast(pl.Categorical)
        ]
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


def _prepare_columns(
    cfg: dict, lf: pl.LazyFrame, timezone: str | None = None
) -> pl.LazyFrame:
    """Auxfun to prepare the df, adding new columns"""
    animal_ids = list(cfg["animal_ids"])

    datetime_df = (
        pl.concat_str([pl.col("date"), pl.col("time")], separator=" ")
        .str.strptime(pl.Datetime, strict=False)
        .dt.replace_time_zone(timezone.key)
    )

    return (
        lf.with_columns(
            pl.col("animal_id").cast(pl.Enum(animal_ids)).alias("animal_id"),
            datetime_df.alias("datetime"),
            pl.col("antenna").cast(pl.Int8).alias("antenna"),
            pl.col("time_under").cast(pl.Int32).alias("time_under"),
        )
        .with_columns(pl.col("datetime").dt.hour().cast(pl.Int8).alias("hour"))
        .drop(["date", "time"])
        .unique(subset=["datetime", "animal_id"], keep="first")
    )


def _split_datetime(phase_start: str) -> dt.datetime:
    """Auxfun to split datetime string."""
    return dt.datetime.strptime(phase_start, "%H:%M:%S")


@df_registry.register('padded_df')
def create_padded_df(
    config_path: Path | str | dict,
    df: pl.LazyFrame,
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
    cfg = auxfun.read_config(config_path)
    results_path = Path(cfg["project_location"]) / "results"
    key = "padded_df"

    padded_df = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(padded_df, pl.LazyFrame):
        return padded_df

    dark_start = _split_datetime(cfg["phase"]["dark_phase"])
    light_start = _split_datetime(cfg["phase"]["light_phase"])

    dark_offset = pl.duration(
        hours=dark_start.hour,
        minutes=dark_start.minute,
        seconds=dark_start.second,
        microseconds=-1,
    )

    light_offset = pl.duration(
        hours=24 if light_start.hour == 0 else light_start.hour,
        minutes=light_start.minute,
        seconds=light_start.second,
        microseconds=-1,
    )

    tz = df.collect_schema()["datetime"].time_zone
    base_midnight = (
        pl.col("datetime").dt.date().cast(pl.Datetime("us")).dt.replace_time_zone(tz)
    )

    df = df.sort("datetime").with_columns(
        (pl.col("phase") != pl.col("phase").shift(-1).over("animal_id")).alias("mask")
    )

    extension_df = df.filter(pl.col("mask")).with_columns(
        pl.when(pl.col("phase") == "light_phase")
        .then(base_midnight + dark_offset)
        .otherwise(base_midnight + light_offset)
        .alias("datetime")
    )

    padded_lf = pl.concat([df, extension_df]).sort(["datetime"])

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
    ).drop("mask")

    if save_data:
        padded_lf.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')

    return padded_lf


@df_registry.register('binary_df')
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
    cfg = auxfun.read_config(config_path)
    results_path = Path(cfg["project_location"]) / "results"
    key = "binary_df"

    binary_lf = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(binary_lf, pl.LazyFrame) :
        return binary_lf
    
    cages = cfg["cages"]
    animal_ids = list(cfg["animal_ids"])

    animals_lf = auxfun.get_lf_from_enum(animal_ids, 'animal_id', sorted = True, col_type = pl.Enum(animal_ids))

    lf = lf.select(['animal_id', 'datetime', 'position']).sort(["animal_id", "datetime"])

    time_range = pl.datetime_range(
        pl.col("datetime").min(),
        pl.col("datetime").max(),
        "1s",
    ).alias("datetime")

    range_lf = lf.select(time_range)

    grid_lf = animals_lf.join(range_lf, how="cross", maintain_order='right_left')


    binary_lf = grid_lf.join_asof(
        lf,
        on="datetime",
        by="animal_id",
        strategy="forward",
        check_sortedness=False
    )

    binary_lf = binary_lf.filter(
        pl.col('position').is_in(cages)
    ).rename({'position':'cage'})

    if save_data:
        binary_lf.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')

    
    return binary_lf


@df_registry.register('main_df')
def get_ecohab_data_structure(
    config_path: str,
    sanitize_animal_ids: bool = True,
    fname_prefix: Literal["COM", "20"] = "COM",
    min_antenna_crossings: int = 100,
    custom_layout: bool = False,
    overwrite: bool = False,
    save_data: bool = True,
    timezone: str | None = None,
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
        animal_ids: list of animal RFID tags. If provided sanitation is not performed based on antenna crossings - only provided IDs will be used.

    Returns:
        EcoHab data structure as a pl.LazyFrame
    """
    cfg = auxfun.read_config(config_path)
    results_path = Path(cfg["project_location"]) / "results"
    key = "main_df"

    df = None if overwrite else auxfun.load_ecohab_data(config_path, key)

    if isinstance(df, pl.LazyFrame):
        return df

    antenna_pairs = cfg["antenna_combinations"]
    
    try:
        animal_ids = cfg["animal_ids"]
    except KeyError:
        animal_ids = None

    lf = load_data(
        config_path=config_path,
        custom_layout=custom_layout,
        sanitize_animal_ids=sanitize_animal_ids,
        fname_prefix=fname_prefix,
        min_antenna_crossings=min_antenna_crossings,
        animal_ids=animal_ids,
    )

    cfg = auxfun.read_config(
        config_path
    )  # reload config potential animal_id changes due to sanitation

    if not isinstance(timezone, str):
        timezone = get_localzone()

    lf = _prepare_columns(cfg, lf, timezone)

    try:
        start_date = cfg["experiment_timeline"]["start_date"]
        finish_date = cfg["experiment_timeline"]["finish_date"]
    except KeyError:
        print("Start and end dates not provided. Extracting from data...")
        cfg, start_date, finish_date = auxfun.append_start_end_to_config(config_path, lf)

    if isinstance(start_date, str) and isinstance(finish_date, str):
        start_date = dt.datetime.fromisoformat(start_date).astimezone(timezone)
        finish_date = dt.datetime.fromisoformat(finish_date).astimezone(timezone)

        lf = lf.filter(
            (pl.col("datetime") >= start_date) & (pl.col("datetime") <= finish_date)
        ).sort("datetime")

    lf = lf.sort("datetime")
    lf = (
        lf
        .with_columns([
            auxfun.get_phase(cfg),
            auxfun.get_day(), 
            auxfun.get_hour()
        ])
        .with_columns(
            auxfun.get_phase_count()
        )
        )
    lf = calculate_time_spent(lf)
    lf = get_animal_position(lf, antenna_pairs)
    lf = correct_phases_dst(cfg, lf)
    lf = lf.drop("COM")


    sorted_cols = sorted(lf.collect_schema().keys())
    lf_sorted = lf.select(sorted_cols)

    phase_durations_lf = auxfun.get_phase_durations(lf)
    
    auxfun.add_cages_to_config(config_path)

    create_padded_df(config_path, lf_sorted, save_data, overwrite)
    create_binary_df(config_path, lf_sorted, save_data, overwrite)

    if save_data:
        lf_sorted.sink_parquet(results_path / f"{key}.parquet", compression="lz4", engine='streaming')
        phase_durations_lf.sink_parquet(results_path / "phase_durations.parquet", engine='streaming')

    return lf_sorted
