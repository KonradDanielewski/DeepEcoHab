import datetime as dt
import os
from itertools import product
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd
import toml

def get_data_paths(data_path: str) -> list:
    """Auxfun to load all raw data paths
    """    
    data_files = glob(os.path.join(data_path, "COM*.txt"))
    if len(data_files) == 0:
        data_files = glob(os.path.join(data_path, "20*.txt"))
    return data_files

def check_cfp_validity(cfp: str | Path | dict):
    """Auxfun to check validity of the passed cfp variable (config path or dict)
    """    
    if isinstance(cfp, (str, Path)):
        cfg = read_config(cfp)
    elif isinstance(cfp, dict):
        cfg=cfp
    else:
        return print(f"cfp should be either a dict, Path or str, but {type(cfp)} provided.")
    return cfg

def load_ecohab_data(cfp: str, key: str) -> pd.DataFrame:
    """Loads already analyzed main data structure

    Args:
        cfp: config file path
        key: key under which dataframe is stored in HDF

    Raises:
        KeyError: raised if the key not found in file.

    Returns:
        Desired data structure loaded from the file.
    """
    cfg = check_cfp_validity(cfp)
    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]
    
    data_path = Path(make_results_path(project_location, experiment_name))
    
    if data_path.is_file():
        try:
            df = pd.read_hdf(data_path, key=key)
        except KeyError:
            print(f"{key} not found in the specified location: {data_path}. Perhaps not analyzed yet!")
    
    return df

def read_config(cfp: str | Path) -> dict:
    """Auxfun reads the config and returns it as a dictionary
    """
    if isinstance(cfp, (str, Path)):
        cfg = toml.load(cfp)
    else:
        raise ValueError(f"Config path should be a str or a Path object. Type {type(cfp)} provided!")
    
    return cfg

def check_save_data(data_path: Path, key: str):
    try:
        df = pd.read_hdf(data_path, key=key)
        # NOTE: should this be printed? Feels annoying
        #print(f"Already calculated for {key}. Loading from {data_path}. If you wish to overwrite the data please set overwrite=True")
        return df
    except (KeyError, FileNotFoundError):
        return None
    
def get_animal_ids(data_path: str) -> list:
    """Auxfun to read animal IDs from the data if not provided
    """    
    data_files = get_data_paths(data_path)
    
    dfs = [pd.read_csv(file, delimiter="\t", names=["ind", "date", "time", "antenna", "time_under", "animal_id"]) for file in data_files[:10]]
    animal_ids = pd.concat(dfs).animal_id.unique()
    return animal_ids

def make_project_path(project_location: str, experiment_name: str):
    """Auxfun to make a name of the project directory using its name and time of creation
    """    
    project_name = experiment_name + "_" + dt.datetime.today().strftime('%Y-%m-%d')
    project_location = Path(project_location) / project_name

    return str(project_location)

def make_results_path(project_location: str, experiment_name: str):
    """Auxfun to make a name of the project directory using its name and time of creation
    """    
    experiment_name = experiment_name
    results_path = Path(project_location) / "results" / f"{experiment_name}_data.h5"

    return str(results_path)

def _create_phase_multiindex(cfg: dict, position: bool = False, cages: bool = False) -> pd.MultiIndex:
    data_path = Path(cfg["results_path"])
    
    df = pd.read_hdf(data_path, key="main_df")
    
    phase_Ns = list(df.phase_count.unique())
    phases = list(cfg["phase"].keys())
    positions = list(set(cfg["antenna_combinations"].values()))

    if not position and not cages:
        idx = pd.MultiIndex.from_product([phases, phase_Ns], names=["phase", "phase_count"])
        return idx
    elif position and not cages:
        positions.append("undefined")
        idx = pd.MultiIndex.from_product([phases, phase_Ns, positions], names=["phase", "phase_count", "position"])
        return idx
    elif not position and cages:
        cages = [position for position in positions if "cage" in position]
        idx = pd.MultiIndex.from_product([phases, phase_Ns, cages], names=["phase", "phase_count", "position"])
        return idx

def get_phase_durations(cfg: dict, df: pd.DataFrame) -> pd.Series:
    """Auxfun to calculate approximate phase durations.
       Assumes the length is the closest full hour of the total length in seconds (first to last datetime in this phase).
    """    
    phase_Ns = list(df.phase_count.unique())
    phases = list(cfg["phase"].keys())

    hours = [60*60*i for i in range(1,13)]
    # Prep data and index
    phase_product = product(phases, phase_Ns)
    idx = _create_phase_multiindex(cfg)
    phase_durations = pd.Series(index=idx).sort_index()
    # Find closest full hour
    for phase, phase_N in phase_product:
        try:
            temp = df.query("phase == @phase and phase_count == @phase_N")
            total_time = (temp.datetime.iloc[-1] - temp.datetime.iloc[0]).total_seconds()
            time_calculated = np.abs(total_time - np.array(hours))
            closest_hour = np.where(np.min(time_calculated) == time_calculated)[0][0]
            phase_durations.loc[(phase, phase_N)] = hours[closest_hour]
        except IndexError: # happens when phase_N doesn't exist for a specific phase
            continue
    
    phase_durations = phase_durations.dropna()
    
    return phase_durations
    
def _sanitize_animal_ids(cfp: str, df: pd.DataFrame, min_antenna_crossings: int = 100) -> pd.DataFrame:
    """Auxfun to remove ghost tags (random radio noise reads).
    """    
    cfg = check_cfp_validity(cfp)
    
    animal_ids = df.animal_id.unique()
    
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
        
        df = df.query("animal_id in @new_ids").reset_index(drop=True)
        
    else:
        print("No ghost tags detected :)")
    
    return df

def _append_start_end_to_config(cfp: str, df: pd.DataFrame) -> None:
    """Auxfun to append start and end datetimes of the experiment if not user provided.
    """    
    cfg = check_cfp_validity(cfp)
    start_time = str(df.datetime.iloc[0])
    end_time = str(df.datetime.iloc[-1])
    
    f = open(cfp,'w')
    cfg["experiment_timeline"] = {"start_date": start_time}
    cfg["experiment_timeline"] = {"finish_date": end_time}
    
    toml.dump(cfg, f)
    f.close()
    
    print(f"Start of the experiment established as: {start_time} and end as {end_time}.\nIf you wish to set specific start and end, please change them in the config file and create the data structure again setting overwrite=True")