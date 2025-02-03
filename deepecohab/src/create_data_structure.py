import os
from pathlib import Path

import numpy as np
import pandas as pd

from deepecohab.utils import auxfun

def load_data(cfp: str | Path, animal_ids: list[str], custom_layout: bool = False, sanitize_animal_id: bool = True) -> pd.DataFrame:
    """Auxfum to load and combine text files into a pandas dataframe
    """    
    cfg = auxfun.check_cfp_validity(cfp)   
    data_path = cfg["data_path"]
    
    data_files = auxfun.get_data_paths(data_path)

    dfs = []
    for file in data_files:
        df = pd.read_csv(file, delimiter="\t", names=["ind", "date", "time", "antenna", "time_under", "animal_id"])
        comport = os.path.basename(file).split("_")[0]
        df["COM"] = comport
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).drop(["ind", "time_under"], axis=1)
    
    if sanitize_animal_id:
        df = auxfun._sanitize_animal_ids(cfp, df)
    
    if custom_layout:
        rename_dicts = cfg["antenna_rename_scheme"]
        for com_name in rename_dicts.keys():
            df = _rename_antennas(df, com_name, rename_dicts)
    return df

def calculate_timedelta(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds
    """    
    df.loc[:, "timedelta"] = (
        df
        .loc[:, ["datetime", "animal_id"]]
        .groupby("animal_id", observed=False)
        .diff()
        .iloc[:, 0]
        .dt.total_seconds()
        .fillna(0)
        .round(2)
    )
    return df

def get_day(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the day
    """    
    df["day"] = ((df.datetime - df.datetime.iloc[0]) + pd.Timedelta(str(df.datetime.dt.time[0]))).dt.days + 1
    return df

def get_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the hour
    """    
    hour = (df.datetime - df.datetime[0]).dt.total_seconds()/3600
    hour[0] = 0.01
    df["hour"] = np.ceil(hour).astype(int)
    return df

def get_phase(cfg: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the phase
    """
    start_time, end_time = cfg["phase"].values()

    index = pd.DatetimeIndex(df['datetime'])
    df.loc[index.indexer_between_time(start_time, end_time), "phase"] = "light_phase"
    df["phase"] = df.phase.fillna("dark_phase")
    
    return df

def get_phase_count(cfg: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun used to count phases
    """   
    df['phase_count'] = None
    phases = list(cfg["phase"].keys())
    
    for phase in phases:
        phase_bool = df['phase'].eq(phase)
        shift = phase_bool.shift()
        indices = df.phase.loc[df.phase == phase].index
        df.loc[indices, 'phase_count'] = (phase_bool.ne(shift & phase_bool).cumsum()).loc[indices].values
    df.phase_count = df.phase_count.astype(int)
    return df

def map_antenna2position(antenna_column: pd.Series, positions: dict) -> pd.Series:
    """Auxfun to map antenna pairs to animal position
    """    
    arr1 = np.insert(antenna_column, 0, 0).astype(str)
    arr2 = np.insert(antenna_column, len(antenna_column), 0).astype(str)

    antenna_pairs = (pd.Series(arr1) + pd.Series(arr2))[:-1]
    antenna_pairs.index = antenna_column.index
    
    location = antenna_pairs.map(positions)

    return location

def get_animal_position(df: pd.DataFrame, positions: dict) -> pd.DataFrame:
    """Auxfun, groupby mapping of antenna pairs to position
    """    
    df.loc[:, "position"] = (
        df
        .loc[:, ["animal_id", "antenna"]]
        .groupby("animal_id", observed=False)
        .apply(map_antenna2position, positions=positions, include_groups=False)
        .fillna("undefined")
        .droplevel(level=0, axis=0)
        .sort_index()
        .values
    )

    return df

def _rename_antennas(df: pd.DataFrame, com_name: str, rename_dicts: dict) -> pd.DataFrame:
    """Auxfun for antenna name mapping when custom layout is used
    """    
    mapping = {int(k):v for k,v in rename_dicts[com_name].items()}
    df.loc[df.COM == com_name, "antenna"] = df.query("COM == @com_name")["antenna"].map(mapping)
    return df

def _prepare_columns(cfg: dict, df: pd.DataFrame, positions: list) -> pd.DataFrame:
    """Auxfun to prepare the df, adding new columns
    """    
    # Establish all possible categories for position
    positions.append("undefined")
    
    df["timedelta"] = np.nan
    df["day"] = np.nan
    
    df["position"] = pd.Series(dtype="category").cat.set_categories(positions)
    df["phase"] = pd.Series(dtype="category").cat.set_categories(cfg["phase"].keys())

    df["antenna"] = df["antenna"]
    df["animal_id"] = df["animal_id"].astype("category").cat.set_categories(cfg["animal_ids"])
    df["datetime"] = df["date"] + " " + df["time"]
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop(["date", "time"], axis=1)
    df = df.drop_duplicates(["datetime", "animal_id"])
    
    return df

def get_ecohab_data_structure(
    cfp: str,
    sanitize_animal_ids: bool = True,
    custom_layout: bool = False,
    overwrite: bool = False,
    retain_comport: bool = False,
) -> pd.DataFrame:
    """Prepares EcoHab data for further analysis

    Args:
        cfp: path to project config file
        sanitize_animal_ids: toggle whether to remove animals. Removes animals that had less than 10 antenna crossings during the whole experiment.
        custom_layout: if multiple boards where added/antennas are in non-default location set to True
        overwrite: toggles whether to overwrite existing data file
        retain_comport: toggles whether to retain the column that contains the comport index

    Returns:
        EcoHab data structure as a pd.DataFrame
    """
    cfg = auxfun.read_config(cfp)
    data_path = Path(cfg["results_path"])
    key = "main_df"
    
    df = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(df, pd.DataFrame):
        return df
    
    remapping_dict = cfg["antenna_combinations"]
    positions = list(set(remapping_dict.values()))
    
    start_date = cfg["experiment_timeline"]["start_date"]
    finish_date = cfg["experiment_timeline"]["finish_date"]
    
    df = load_data(cfp, custom_layout)
    df = _prepare_columns(cfg, df, positions)

    # Slice to start and end date
    if isinstance(start_date, str) & isinstance(finish_date, str): 
        start, finish = pd.to_datetime(start_date), pd.to_datetime(finish_date)
        timeframe = (df.datetime >= start) & (df.datetime <= finish)
        df = df.loc[timeframe, :].sort_values("datetime").reset_index(drop=True)
    
    df = df.sort_values("datetime")
    
    df = calculate_timedelta(df)
    df = get_day(df)
    df = get_animal_position(df, remapping_dict)
    df = get_phase(cfg, df)
    df = get_phase_count(cfg, df)
    
    condition_map = {key: i+1 for i, key in enumerate(positions)}
    df["position_keys"] = df.position.map(condition_map).astype(int).fillna(0)

    df = df.sort_index(axis=1).reset_index(drop=True)

    if not retain_comport:
        df = df.drop("COM", axis=1)
    
    df.to_hdf(data_path, key=key, mode="a", format="table")
    
    phase_durations = auxfun.get_phase_durations(cfg, df)
    phase_durations.to_hdf(data_path, key="phase_durations", mode="a", format="table")

    return df
