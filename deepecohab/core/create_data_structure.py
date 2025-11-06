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

def load_data(cfp: str | Path, custom_layout: bool, sanitize_animal_ids: bool, min_antenna_crossings: int = 100, animal_ids: list | None = None) -> pl.LazyFrame:
    """Auxfum to load and combine text files into a pandas dataframe
    """    
    cfg = auxfun.read_config(cfp)   
    data_path = Path(cfg['data_path'])
    
    data_files = auxfun.get_data_paths(data_path)
    
    lf = pl.scan_csv(
        source=data_files,           
        separator="\t",
        has_header=False,
        new_columns=["ind","date","time","antenna","time_under","animal_id"],
        include_file_paths="file",
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
    #TODO incorporate into lazy workflow
    # if isinstance(animal_ids, list):
    #     df = df[df.animal_id.isin(animal_ids)].reset_index(drop=True)
    
    if custom_layout:
        rename_dicts = cfg['antenna_rename_scheme']
        lf = _rename_antennas(lf, rename_dicts)

    return lf

def check_for_dst(df: pd.DataFrame) -> tuple[int, int]:
    zone_offset = df.datetime.dt.strftime('%z').map(lambda x: x[1:3]).astype(int)
    time_change_happened = len(np.where((zone_offset != zone_offset[0]))[0]) > 0
    if time_change_happened:
        time_change_ind = np.where((zone_offset != zone_offset[0]))[0][0]
        time_change = zone_offset[time_change_ind] - zone_offset[time_change_ind-1]
        return int(time_change), int(time_change_ind)
    else:
        return None, None

def correct_phases_dst(cfg: dict, df: pd.DataFrame, time_change: int, time_change_index: int) -> pd.DataFrame:
    """Auxfun to correct phase start and end when daylight saving happens during the recording
    """    
    start_time, end_time = cfg['phase'].values()

    end_time = (':').join(
        (str(int(end_time.split(':')[0]) + time_change), 
            end_time.split(':')[1], 
            end_time.split(':')[2])
    )

    temp_df = df.loc[time_change_index:].copy()

    index = pd.DatetimeIndex(temp_df['datetime'])
    temp_df.loc[index.indexer_between_time(start_time, end_time) + time_change_index, 'phase'] = 'light_phase'
    temp_df['phase'] = temp_df.phase.fillna('dark_phase')

    df.loc[time_change_index:, 'phase'] = temp_df['phase'].values

    return df

def calculate_timedelta(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds
    """    

    lf = lf.with_columns(
        (pl.col("datetime") - pl.col("datetime").shift(1))
        .over("animal_id") 
        .dt.total_seconds(fractional=True)
        .fill_null(0)
        .cast(pl.Float32)
        .round(2)
        .alias("timedelta")
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
        .cast(pl.Int32)
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

def get_ecohab_data_structure(
    cfp: str,
    sanitize_animal_ids: bool = True,
    min_antenna_crossings: int = 100,
    custom_layout: bool = False,
    overwrite: bool = False,
    timezone: str | None = None,
    animal_ids: list | None = None,
) -> pl.DataFrame:
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
    results_path = Path(cfg['project_location']) / 'results/'
    key = 'main_df'
    
    df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(df, pd.DataFrame):
        return df
    
    antenna_pairs = cfg['antenna_combinations']
    positions = list(set(antenna_pairs.values())) + ['undefined']
    
    lf = load_data(
        cfp=cfp,
        custom_layout=custom_layout,
        sanitize_animal_ids=sanitize_animal_ids,
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
    #TODO check if get_animal_position works as it's supposed to
    lf = get_animal_position(lf, antenna_pairs, positions)
    lf = get_phase(cfg, lf)


    #TODO
    # time_change, time_change_ind = check_for_dst(df)
    # if isinstance(time_change, int):
    #     print('Correcting for daylight savings...')
    #     df = correct_phases_dst(cfg, df, time_change, time_change_ind)

    lf = get_phase_count(lf)

    lf = lf.drop("COM")
    df_pl = lf.collect()
    df_pl = df_pl.select(sorted(df_pl.columns))

    phase_durations = auxfun.get_phase_durations(lf).collect()

    df_pl.write_parquet(results_path / f"{key}.parquet", compression='lz4')
    phase_durations.write_parquet(results_path / "phase_durations.parquet")

    return df_pl
