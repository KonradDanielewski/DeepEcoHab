import datetime as dt
import os
from glob import glob
from pathlib import Path

import pandas as pd
import toml

def get_data_paths(data_path: str) -> list:
    """Auxfun to load all raw data paths
    """    
    data_files = glob(os.path.join(data_path, "COM*.txt"))
    if len(data_files) == 0:
        data_files = glob(os.path.join(data_path, "20*.txt"))
    return data_files

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
    cfg = read_config(cfp)
    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]
    
    data_path = make_results_path(project_location, experiment_name)
    
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
        print("Already calculated. Loading from {data_path}. If you wish to overwrite the data please set overwrite=True")
        return df
    except (KeyError, FileNotFoundError):
        # print(f"Data not found at location {data_path}. Perhaps not analyzed.") # NOTE: Feels annoying. Need a better way
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