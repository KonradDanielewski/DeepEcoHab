from pathlib import Path

import numpy as np
import pandas as pd

import polars as pl

from datetime import (
    datetime,
    time,
)

import pytz
from tzlocal import get_localzone

from deepecohab.utils import auxfun

def load_data(cfp: str | Path, 
              custom_layout: bool, 
              sanitize_animal_ids: bool, 
              fname_prefix: str,
              min_antenna_crossings: int = 100, 
              animal_ids: list | None = None) -> pl.LazyFrame:
    """Auxfun to load and combine text files into a pandas dataframe
    """    
    cfg = auxfun.read_config(cfp)   
    data_path = Path(cfg['data_path'])
    
    
    lf = pl.scan_csv(
        source=data_path/f"{fname_prefix}*.txt",           
        separator="\t",
        has_header=False,
        new_columns=["ind","date","time","antenna","time_under","animal_id"],
        include_file_paths="file",
        glob=True,
        infer_schema=True,
        infer_schema_length=10,
    )

    lf = (
        lf.with_columns(
            pl.col("file")
              .str.split(r"[\\/]").list.get(-1)
              .str.split("_").list.get(0)
              .alias("COM")
        )
        .drop(["ind", "file"])
    )
    
    if sanitize_animal_ids:
        lf = auxfun._sanitize_animal_ids(cfp, lf, min_antenna_crossings)
    if isinstance(animal_ids, list):
        lf = lf.filter(pl.col('animal_id').is_in(animal_ids))
    
    if custom_layout:
        rename_dicts = cfg['antenna_rename_scheme']
        lf = _rename_antennas(lf, rename_dicts)

    #TODO confirm
    auxfun._add_cages_to_config(cfp)

    return lf

def correct_phases_dst(cfg: dict, lf: pl.LazyFrame) -> pl.LazyFrame:
    start_time, end_time = cfg['phase'].values()
    start_time = time.fromisoformat(start_time)
    end_time = time.fromisoformat(end_time)

    time_offset = (pl.col("datetime").dt.dst_offset() - pl.col("datetime").first().dt.dst_offset())

    lf = lf.with_columns(
            (pl.col("datetime") + time_offset).alias("datetime_shifted")
        ).with_columns(
            pl.when(pl.col('datetime')!=pl.col('datetime_shifted'))
                .then(
                    pl.when(
                        pl.col('datetime_shifted').dt.time().is_between(
                                start_time, 
                                end_time, 
                                closed="both"
                            )
                    ).then(
                        pl.lit("light_phase")
                    ).otherwise(
                        pl.lit("dark_phase")
                    )
                )
                .otherwise(pl.col("phase"))
                .alias('phase')
            ).drop('datetime_shifted')

    return lf


def calculate_timedelta(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds
    """    

    lf = lf.with_columns(
        auxfun.get_timedelta_expression()
    )
    return lf


def get_day(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun for getting the day
    """    
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
    """Auxfun for getting the phase
    """
    start_str, end_str = list(cfg["phase"].values())
    phase_names = list(cfg["phase"].keys())
    start_t = time.fromisoformat(start_str)
    end_t   = time.fromisoformat(end_str)

    return lf.with_columns(
        pl.when(
            pl.col("datetime").dt.time().is_between(start_t, end_t, closed="both")
        )
        .then(pl.lit("light_phase"))
        .otherwise(pl.lit("dark_phase"))
        .cast(pl.Enum(phase_names))
        .alias("phase")
    )

def get_phase_count(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun used to count phases
    """   

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
        lf_with_run
        .select("run_id", "phase")
        .unique()
        .sort("run_id")
        .with_columns(
            pl.col("run_id")
            .rank(method="dense")
            .over("phase")
            .cast(pl.Int16)
            .alias("phase_count")
        )
        .drop('phase')
    )

    return (
        lf_with_run.join(runs, on="run_id", how="left")
                   .drop("run_id")
    )

def get_animal_position(lf: pl.LazyFrame, antenna_pairs: dict, positions: list) -> pl.LazyFrame:
    """Auxfun, groupby mapping of antenna pairs to position
    """    
    prev_ant = (
        pl.col("antenna")
        .shift(1)
        .over("animal_id")
        .fill_null(0)
        .cast(pl.Utf8)
    )
    curr_ant = pl.col("antenna").cast(pl.Utf8)
    
    pair = pl.concat_str([prev_ant, pl.lit("_"), curr_ant])

    return lf.with_columns([
        pair
        .replace(antenna_pairs, default="undefined")
        .alias("position")
        .cast(pl.Enum(positions))
    ])

def _rename_antennas(lf: pl.LazyFrame, rename_dicts: dict) -> pl.LazyFrame:
    """Auxfun for antenna name mapping when custom layout is used
    """    

    rows = []
    for com, d in rename_dicts.items():
        for k, v in d.items():
            rows.append({
                "COM": com,
                "antenna_from": int(k),
                "antenna_to": v,
            })


    if not rows:
        return lf

    map_lf = pl.DataFrame(rows).lazy()

    lf = (
        lf.join(
            map_lf,
            left_on=["COM", "antenna"],
            right_on=["COM", "antenna_from"],
            how="left",
        )
        .with_columns(
            pl.coalesce([pl.col("antenna_to"), pl.col("antenna")]).alias("antenna")
        )
        .drop(["antenna_from", "antenna_to"])
    )

    return lf

def _prepare_columns(cfg: dict, lf: pl.LazyFrame, timezone: str | None = None) -> pl.LazyFrame:
    """Auxfun to prepare the df, adding new columns
    """    
    animal_ids = list(cfg["animal_ids"])

    datetime_df = (
        pl.concat_str([pl.col("date"), pl.col("time")], separator=" ")
          .str.strptime(pl.Datetime, strict=False)              
          .dt.replace_time_zone(timezone)
    )

    return (
        lf.with_columns(
            pl.col("animal_id").cast(pl.Enum(animal_ids)).alias("animal_id"),

            datetime_df.alias("datetime"),
            pl.col("antenna").cast(pl.Int8).alias("antenna"),
            pl.col('time_under').cast(pl.Int32).alias('time_under')
        )
        .with_columns(
            pl.col("datetime").dt.hour().cast(pl.Int8).alias("hour")
        )
        .drop(["date", "time"])
        .unique(subset=["datetime", "animal_id"], keep="first")
    )


def _split_datetime(phase_start: str) -> datetime:
    """Auxfun to split datetime string.
    """    
    return datetime.strptime(phase_start, "%H:%M:%S")

def create_padded_df(
    cfp: Path | str | dict,
    df: pl.LazyFrame,
    save_data: bool = True, 
    overwrite: bool = False,
    ) ->  pl.LazyFrame:
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
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results'
    key='padded_df'
    
    padded_df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(padded_df, pl.LazyFrame):
        return padded_df
    
    dark_start = _split_datetime(cfg['phase']['dark_phase'])
    light_start = _split_datetime(cfg['phase']['light_phase'])

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
    base_midnight = pl.col("datetime").dt.date().cast(pl.Datetime("us")).dt.replace_time_zone(tz)


    df = df.with_columns(
        (pl.col('phase') != pl.col('phase').shift(-1).over('animal_id')).alias('mask')
    )

    extension_df = df.filter(pl.col('mask')).with_columns(
        pl.when(pl.col('phase') == 'light_phase').then(
            base_midnight + dark_offset
        ).otherwise(
            base_midnight + light_offset
        ).alias("datetime")
    )

    padded_lf = pl.concat([
        df,
        extension_df    
    ]).sort(['datetime'])

    padded_lf = padded_lf.with_columns(
        pl.when(
            pl.col('mask')
        ).then(
            auxfun.get_timedelta_expression(alias = None)
        ).otherwise(
            pl.when(
                pl.col('mask').shift(1).over('animal_id')
            ).then(
                auxfun.get_timedelta_expression(alias = None)
            ).otherwise(
                pl.col('timedelta')
            )
        ).alias('timedelta'),
        pl.when(pl.col('mask')).then(
            pl.col('position').shift(-1).over('animal_id')
        ).otherwise(pl.col('position')).alias('position')
    ).drop('mask')

    if save_data:
        padded_lf.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    return padded_lf

def get_ecohab_data_structure(
    cfp: str,
    sanitize_animal_ids: bool = True,
    fname_prefix: str = "COM",
    min_antenna_crossings: int = 100,
    custom_layout: bool = False,
    overwrite: bool = False,
    timezone: str | None = None,
    animal_ids: list | None = None,
) -> pl.LazyFrame:
    """Prepares EcoHab data for further analysis

    Args:
        cfp: path to project config file
        sanitize_animal_ids: toggle whether to remove animals. Removes animals that had less than 10 antenna crossings during the whole experiment.
        custom_layout: if multiple boards where added/antennas are in non-default location set to True
        overwrite: toggles whether to overwrite existing data file

    Returns:
        EcoHab data structure as a pl.DataFrame
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results'
    key = 'main_df'
    
    df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(df, pl.LazyFrame):
        return df
    
    antenna_pairs = cfg['antenna_combinations']
    positions = list(set(antenna_pairs.values())) + ['undefined']
    
    lf = load_data(
        cfp=cfp,
        custom_layout=custom_layout,
        sanitize_animal_ids=sanitize_animal_ids,
        fname_prefix=fname_prefix,
        min_antenna_crossings=min_antenna_crossings,
        animal_ids=animal_ids,
    )
    
    cfg = auxfun.read_config(cfp) # reload config potential animal_id changes due to sanitation

    if not isinstance(timezone, str):
        timezone = get_localzone().key

    lf = _prepare_columns(cfg, lf, timezone)

    # Slice to start and end date
    try:
        start_date = cfg['experiment_timeline']['start_date']
        finish_date = cfg['experiment_timeline']['finish_date']
        
        if isinstance(start_date, str) and isinstance(finish_date, str):
            tz = pytz.timezone(timezone)
            start = tz.localize(datetime.fromisoformat(start_date))
            finish = tz.localize(datetime.fromisoformat(finish_date))

            lf = (
                lf.filter(
                    (pl.col("datetime") >= pl.lit(start)) &
                    (pl.col("datetime") <= pl.lit(finish))
                )
                .sort("datetime")
            )
    except KeyError:
        print('Start and end dates not provided. Extracting from data...')
        auxfun._append_start_end_to_config(cfp, lf)
    

    lf = lf.sort('datetime')
    lf = calculate_timedelta(lf)
    lf = get_day(lf)

    lf = get_animal_position(lf, antenna_pairs, positions)
    lf = get_phase(cfg, lf)

    lf = correct_phases_dst(cfg, lf) 

    lf = get_phase_count(lf)

    lf = lf.drop("COM")


    sorted_cols = sorted(lf.collect_schema().keys())
    lf_sorted = lf.select(sorted_cols)

    phase_durations_lf = auxfun.get_phase_durations(lf)

    create_padded_df(cfp, lf_sorted)

    lf_sorted.sink_parquet(results_path / f"{key}.parquet", compression="lz4")
    phase_durations_lf.sink_parquet(results_path / "phase_durations.parquet")

    return lf_sorted

