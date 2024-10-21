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

def load_ecohab_data(cfp: str, structure_type: str) -> pd.DataFrame:
    """Loads already analyzed data structure

    Args:
        cfp: config file path
        structure_type: accepts either 'chasings' to load the chasings matrix or 'ecohab' to load the general data structure

    Raises:
        ValueError: raised if unexpected value provided in structure_type
        FileNotFoundError: raised if the data file not found.

    Returns:
        returns desired data structure loaded from the file.
    """    
    cfg = toml.load(cfp)
    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]
    
    if structure_type == "chasings":
        suffix = "_chasings.h5"
    elif structure_type == "ecohab":
        suffix = "_data.h5"
    else:
        raise ValueError(f"'chasings' or 'ecohab' supported but {structure_type} provided! Please use one of the available structure types")
    
    data_path = project_location / "data" / (experiment_name + suffix)
    
    if data_path.is_file():
        df = pd.read_hdf(data_path)
    else:
        raise FileNotFoundError(f"{structure_type.capitalize()} data file not found in the specified location: {data_path}. Perhaps not analyzed yet!")
    
    return df