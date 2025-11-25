import datetime as dt
import importlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import polars as pl
import toml

import subprocess
import sys

from deepecohab.utils import auxfun


def get_data_paths(data_path: Path) -> list:
    """Auxfun to load all raw data paths
    """    
    data_files = list(data_path.glob('COM*.txt'))
    if len(data_files) == 0:
        data_files = list(data_path.glob('20*.txt'))
    return data_files

def read_config(cfp: str | Path | dict) -> dict:
    """Auxfun to check validity of the passed cfp variable (config path or dict)
    """    
    if isinstance(cfp, (str, Path)):
        cfg = toml.load(cfp)
    elif isinstance(cfp, dict):
        cfg=cfp
    else:
        return print(f'cfp should be either a dict, Path or str, but {type(cfp)} provided.')
    return cfg

def load_ecohab_data(cfp: str, key: str, verbose: bool = True) -> pl.LazyFrame:
    """Loads already analyzed main data structure

    Args:
        cfp: config file path
        key: key under which dataframe is stored in HDF

    Raises:
        KeyError: raised if the key not found in file.

    Returns:
        Desired data structure loaded from the file.
    """
    cfg = read_config(cfp)
    
    results_path = Path(cfg['project_location']) / 'results' / f"{key}.parquet"
 
    if results_path.is_file():
        try:
            lf = pl.scan_parquet(results_path) 
            return lf
        except KeyError:
            if verbose:
                print(f'{key} not found in the specified location: {results_path}. Perhaps not analyzed yet!')
            else:
                pass
    
def get_animal_ids(data_path: str) -> list:
    """Auxfun to read animal IDs from the data if not provided
    """    
    data_files = get_data_paths(Path(data_path))
    
    dfs = [pd.read_csv(file, delimiter='\t', names=['ind', 'date', 'time', 'antenna', 'time_under', 'animal_id']) for file in data_files[:10]]
    animal_ids = pd.concat(dfs).animal_id.astype(str).unique()
    return animal_ids

def make_project_path(project_location: str, experiment_name: str) -> str:
    """Auxfun to make a name of the project directory using its name and time of creation
    """    
    project_name = experiment_name + '_' + dt.datetime.today().strftime('%Y-%m-%d')
    project_location = Path(project_location) / project_name

    return str(project_location)


def get_phase_durations(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Auxfun to calculate approximate phase durations.
       Assumes the length is the closest full hour of the total length in seconds (first to last datetime in this phase).
    """    
    return (
        lf.group_by(["phase", "phase_count"])
          .agg(
              duration_s = (
                  (pl.col("datetime").last() - pl.col("datetime").first())
                  .dt.total_seconds()
              )
          )
          .with_columns(
              (
                  (pl.col("duration_s") / 3600).round(0).clip(1, 12) * 3600
              ).cast(pl.Int64).alias("duration_seconds")
          )
          .select("phase", "phase_count", "duration_seconds")
          .sort(["phase", "phase_count"])
    )
    
def _sanitize_animal_ids(cfp: str, lf: pd.DataFrame, min_antenna_crossings: int = 100) -> pd.DataFrame:
    """Auxfun to remove ghost tags (random radio noise reads).
    """    
    cfg = read_config(cfp)
    
    animal_ids = (
        lf.select(pl.col("animal_id").unique().alias("animal_id"))
          .collect()["animal_id"]
          .to_list()
    )

    antenna_crossings = (
        lf.group_by(pl.col("animal_id")).count().collect()
    )

    animals_to_drop = (
        antenna_crossings.filter(pl.col("count") < min_antenna_crossings)
                 .get_column("animal_id")
                 .to_list()
    )
    
    
    if animals_to_drop:
        print(f"IDs dropped from dataset {animals_to_drop}")
        new_ids = sorted([a for a in animal_ids if a not in animals_to_drop])
        lf = lf.filter(pl.col("animal_id").is_in(pl.lit(new_ids)))

        cfg["dropped_ids"] = animals_to_drop
        cfg["animal_ids"]  = new_ids
        with cfp.open("w") as f:
            toml.dump(cfg, f)            
    else:
        print('No ghost tags detected :)')
    
    return lf

def _append_start_end_to_config(cfp: str, lf: pl.LazyFrame) -> None:
    """Auxfun to append start and end datetimes of the experiment if not user provided.
    """    
    cfg = read_config(cfp)
    bounds = (
        lf.select([
            pl.col("datetime").first().alias("start_time"),
            pl.col("datetime").last().alias("end_time"),
        ])
        .collect()
    )

    start_time = str(bounds["start_time"][0])
    end_time   = str(bounds["end_time"][0])
    
    f = open(cfp,'w')
    cfg['experiment_timeline'] = {
        'start_date': start_time,
        'finish_date': end_time,
    }
    
    toml.dump(cfg, f)
    f.close()
    
    print(f'Start of the experiment established as: {start_time} and end as {end_time}.\nIf you wish to set specific start and end, please change them in the config file and create the data structure again setting overwrite=True')

def _set_cages(cfp: str) -> None:
    cfg = read_config(cfp)
    
    positions = list(set(cfg['antenna_combinations'].values()))
    cages = [pos for pos in positions if 'cage' in pos]

    f = open(cfp,'w')
    cfg['cages'] = cages
    
    toml.dump(cfg, f)
    f.close()

def run_dashboard(cfp: str | dict):
    cfg = auxfun.read_config(cfp)
    data_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    cfg_path = Path(cfg['project_location']) / 'config.toml'
    
    path_to_dashboard = importlib.util.find_spec('deepecohab.dash.dashboard').origin

    process = subprocess.Popen([sys.executable, path_to_dashboard, '--results-path', data_path, '--config-path' , cfg_path])
    
    return process

def get_timedelta_expression(
    time_col: str = "datetime",
    group_col: str = "animal_id",
    alias: str | None = "timedelta",
) -> pl.Expr:
    expr = (
        (pl.col(time_col) - pl.col(time_col).shift(1))
        .over(group_col)
        .dt.total_seconds(fractional=True)
        .fill_null(0)
        .cast(pl.Float64)
        .round(2)
    )
    return expr.alias(alias) if alias is not None else expr


def _drop_empty_phase_counts(cfp: str | dict, df: pd.DataFrame):
    """Auxfun to drop parts of DataFrame where no data was recorded.
    """    
    main_df = load_ecohab_data(cfp, 'main_df')
    possible_dark_phases = main_df.query('phase == "dark_phase"').phase_count.unique()
    possible_light_phases = main_df.query('phase == "light_phase"').phase_count.unique()
    
    filtered_df = df[
        (df.index.get_level_values(0) == 'dark_phase') & 
        (df.index.get_level_values(1).isin(possible_dark_phases)) |
        
        (df.index.get_level_values(0) == 'light_phase') & 
        (df.index.get_level_values(1).isin(possible_light_phases))
    ]

    return filtered_df

def remove_tunnel_directionality(lf: pl.LazyFrame, cfg: dict) -> pl.LazyFrame:
    tunnels = cfg['tunnels']
    positions = cfg['cages'] + list(set(tunnels.values())) + ['undefined']

    return lf.with_columns(
        pl.col('position')
        .cast(pl.Utf8)              
        .replace(tunnels)           
        .cast(pl.Enum(positions))
        .alias('position')   
    )

def get_agg_expression(
    value_col: str,
    animal_ids: list,
    agg_fn: Callable[[pl.Expr], pl.Expr],
) -> list[pl.Expr]:

    return [
        agg_fn(
            pl.col(value_col).filter(pl.col("animal_id") == aid)
        ).alias(str(aid))
        for aid in animal_ids
    ]