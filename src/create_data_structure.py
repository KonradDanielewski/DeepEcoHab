import os
from pathlib import Path

import numpy as np
import pandas as pd
import toml

from deepecohab.utils.auxfun import get_data_paths

def load_data(cfp: str, custom_layout: bool = False) -> pd.DataFrame:
    """Auxfum to load and combine text files into a pandas dataframe
    """    
    cfg = toml.load(cfp)
    data_path = cfg["data_path"]
    
    data_files = get_data_paths(data_path)

    dfs = []
    for file in data_files:
        df = pd.read_csv(file, delimiter="\t", names=["ind", "date", "time", "antenna", "time_under", "animal_id"])
        comport = os.path.basename(file).split("_")[0]
        df["COM"] = comport
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).drop(["ind", "time_under"], axis=1)
    if custom_layout:
        rename_dicts = cfg["antenna_rename_scheme"]
        for com_name in rename_dicts.keys():
            df = _rename_antennas(df, com_name, rename_dicts)
    return df

def get_first_read_cage(antenna: int, possible_first: dict):
    """Auxfun to get first location of an animal
    """    
    for key in possible_first.keys():
        if antenna in possible_first[key]:
            return key

def calculate_timedelta(df: pd.DataFrame):
    """Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds
    """    
    timedelta = (
        df
        .loc[:, ["datetime", "animal_id"]]
        .groupby("animal_id", observed=False)
        .diff()
        .fillna(pd.Timedelta(seconds=0))
        .iloc[:, 0]
        .dt.total_seconds()
        .round(2)
    )
    return timedelta

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

def get_phase(cfp: str, df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the phase
    """
    start_time, end_time = toml.load(cfp)["phase"].values()

    index = pd.DatetimeIndex(df['datetime'])
    df.loc[index.indexer_between_time(start_time, end_time), "phase"] = "light_phase"
    df["phase"] = df.phase.fillna("dark_phase")
    
    return df

def get_phase_count(df: pd.DataFrame) -> pd.DataFrame: #NOTE: This doesn't work correctly at the moment (I think date overlap can happen that triggers multiple counts in a row)
    """Auxfun used to count phases
    """   
    df["phase_id"] = df.phase.map({"dark_phase": 0, "light_phase": 1}).astype(int)
    # Get phase count
    m = df['phase_id'].eq(1)
    df['phase_count'] = m.ne(m.shift() & m).cumsum()
    df = df.drop("phase_id", axis=1)
    return df

def get_antenna_pair_array(antenna_column: np.array) -> np.array:
    """Auxfun to get 2D array of antenna pairs. Done per animal to get position of each
    """    
    arr1 = np.insert(antenna_column, 0, 0)
    arr2 = np.insert(antenna_column, len(antenna_column), 0)

    antenna_pairs = np.array([arr1, arr2]).T[:-1]

    return antenna_pairs

def get_position_conditions(key: str, antenna_pairs: np.array, antenna_combinations: dict) -> np.array:
    """Auxfun to get animal position for a specific antenna pair
    """
    conditions = []
    for i in antenna_combinations[key]:
        conditions.append(np.where(np.logical_and(antenna_pairs[:, 0] == i[0], antenna_pairs[:, 1] == i[1])))

    indices = np.concatenate(conditions, axis=1)[0]
    
    return indices

def get_animal_position(df: pd.DataFrame, antenna_combinations: dict, possible_first: dict, animal_ids: list) -> pd.DataFrame:
    """Auxfun to get position of the animal
    """
    for animal in animal_ids:
        antenna_col = df.loc[df.loc[:, "animal_id"] == animal].antenna.values
        
        antenna_pairs = get_antenna_pair_array(antenna_col)

        for key in antenna_combinations.keys():
            indices = get_position_conditions(key, antenna_pairs, antenna_combinations)

            position_update = df.query("animal_id == @animal").iloc[indices].index
            df.loc[position_update, "position"] = key

        first_read = df.query("animal_id == @animal").index[0]
        df.loc[first_read, "position"] = get_first_read_cage(df.loc[first_read].antenna, possible_first)

    df.loc[:, "position"] = df["position"].fillna("undefined")

    return df

def _rename_antennas(df: pd.DataFrame, com_name: str, rename_dicts: dict) -> pd.DataFrame:
    """Auxfun for antenna name mapping when custom layout is used
    """    
    mapping = {int(k):v for k,v in rename_dicts[com_name].items()}
    df.loc[df.COM == com_name, "antenna"] = df.query("COM == @com_name")["antenna"].map(mapping)
    return df

def _prepare_columns(df: pd.DataFrame, antenna_combinations: list) -> pd.DataFrame:
    """Auxfun to prepare the df, adding new columns
    """    
    df["timedelta"] = np.nan
    df["day"] = np.nan
    antenna_combinations.append("undefined")
    df["position"] = pd.Series(dtype="category").cat.set_categories(antenna_combinations)
    df["phase"] = pd.Series(dtype="category").cat.set_categories(["light_phase", "dark_phase"])

    df["antenna"] = df["antenna"]
    df["animal_id"] = df["animal_id"].astype("category")
    df["datetime"] = df["date"] + " " + df["time"]
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop(["date", "time"], axis=1)
    df = df.drop_duplicates(["datetime", "animal_id"])
    return df

def _sanitize_animal_ids(cfp: str, cfg: dict, df: pd.DataFrame, animal_ids: list[str], min_antenna_crossings: int = 100) -> None:
    """Auxfun to remove ghost tags (random radio noise reads).
    """    
    antenna_crossings = df.animal_id.value_counts()
    animals_to_drop = list(antenna_crossings[antenna_crossings < min_antenna_crossings].index)
    if len(animals_to_drop) > 0:
        df = df.query("animal_id not in @animals_to_drop")
        print(f"IDs dropped from dataset {animals_to_drop}")
        
        f = open(cfp,'w')
        new_ids = [animal_id for animal_id in animal_ids if animal_id not in animals_to_drop]
        
        cfg["dropped_ids"] = animals_to_drop
        cfg["animal_ids"] = new_ids
        toml.dump(cfg, f)
        f.close()

def get_ecohab_data_structure(
    cfp: str,
    sanitize_animal_ids: bool = True,
    custom_layout: bool = False,
    overwrite: bool = False,
    save_as_csv: bool = True,
    retain_comport: bool = False,
) -> pd.DataFrame:
    """Prepares EcoHab data for further analysis

    Args:
        cfp: path to project config file
        sanitize_animal_ids: toggle whether to remove animals. Removes animals that had less than 10 antenna crossings during the whole experiment.
        custom_layout: if multiple boards where added/antennas are in non-default location set to True
        overwrite: toggles whether to overwrite existing data file
        save_as_csv: toggles whether the data will also be saved as a csv file
        retain_comport: toggles whether to retain the column that contains the comport index

    Returns:
        EcoHab data structure as a pd.DataFrame
    """
    cfg = toml.load(cfp)

    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]

    data_path = project_location / "data" / f"{experiment_name}_data.h5"
    if data_path.exists() and not overwrite:
        print("Data structure already created! Loading existing data. If you wish to overwrite existing data set overwrite=True !")
        df = pd.read_hdf(data_path)
        return df
    
    antenna_combinations = cfg["antenna_combinations"]
    possible_first = cfg["possible_first"]
    animal_ids = cfg["animal_ids"]
    start_date = cfg["experiment_timeline"]["start_date"]
    finish_date = cfg["experiment_timeline"]["finish_date"]
    
    df = load_data(cfp, custom_layout)
    df = _prepare_columns(df, list(antenna_combinations.keys()))

    # Slice to start and end date
    if isinstance(start_date, str) & isinstance(finish_date, str): 
        start, finish = pd.to_datetime(start_date), pd.to_datetime(finish_date)
        timeframe = (df.datetime >= start) & (df.datetime <= finish)
        df = df.loc[timeframe, :].sort_values("datetime").reset_index(drop=True)
    
    df = df.sort_values("datetime")
    
    # Calculates time spent in each position (state)
    df["timedelta"] = calculate_timedelta(df)
    # Get additional columns
    df = get_day(df)
    df = get_animal_position(df, antenna_combinations, possible_first, animal_ids)
    df = get_phase(cfp, df)
    df = get_phase_count(df)
    
    condition_map = {key: i+1 for i, key in enumerate(antenna_combinations.keys())}
    df["position_keys"] = df.position.map(condition_map).fillna(0).astype(int)

    if sanitize_animal_ids:
        _sanitize_animal_ids(cfp, cfg, df, animal_ids)

    df = df.sort_index(axis=1).reset_index(drop=True)

    if not retain_comport:
        df = df.drop("COM", axis=1)
    
    df.to_hdf(data_path, key="df", format="table")
    if save_as_csv:
        data_path = str(data_path).replace("h5", "csv")
        df.to_csv(Path(data_path), sep=",")

    return df
