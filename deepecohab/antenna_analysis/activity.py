from pathlib import Path

import pandas as pd
import numpy as np
from tqdm import tqdm

from deepecohab.utils import auxfun
from deepecohab.core import create_data_structure

def _split_datetime(phase_start: str) -> tuple[str, ...]:
    """Auxfun to split datetime string.
    """    
    hour = int(phase_start.split(":")[0])
    minute = int(phase_start.split(":")[1])
    second = int(phase_start.split(":")[2].split(".")[0])
    
    return hour, minute, second

def _extract_phase_switch_indices(animal_df: pd.DataFrame):
    """Auxfun to find indices of phase switching.
    """    
    animal_df["phase_map"] = animal_df.phase.map({"dark_phase": 0, "light_phase": 1})
    shift = animal_df["phase_map"].astype("int").diff()
    shift.loc[0] = 0
    indices = shift[shift != 0]
    
    return indices

def _correct_padded_info(animal_df: pd.DataFrame, location: int) -> pd.DataFrame:
    """Auxfun to correct information in duplicated indices to match the previous phase.
    """    
    day_col, phase_col, phase_count_col = animal_df.columns.get_loc("day"), animal_df.columns.get_loc("phase"), animal_df.columns.get_loc("phase_count")
   
    animal_df.iloc[location, day_col] = animal_df.iloc[location-1, day_col]
    animal_df.iloc[location, phase_col] = animal_df.iloc[location-1, phase_col]
    animal_df.iloc[location, phase_count_col] = animal_df.iloc[location-1, phase_count_col]
    
    return animal_df

def create_padded_df(
    cfg: dict,
    df: pd.DataFrame,
    save_data: bool = True, 
    overwrite: bool = False
    ) ->  pd.DataFrame:
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
    data_path = Path(cfg["results_path"])
    key="padded_df"
    
    padded_df = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(padded_df, pd.DataFrame):
        return padded_df
    
    animals = cfg["animal_ids"]
    phases = list(cfg["phase"].keys())

    animal_dfs = []

    for animal in animals:
        animal_df = df.query("animal_id == @animal").copy()

        indices = _extract_phase_switch_indices(animal_df)

        light_phase_starts = indices[indices == 1].index
        dark_phase_starts = indices[indices == -1].index

        for phase in phases:
            if phase == "light_phase":
                idx = light_phase_starts
            else:
                idx = dark_phase_starts
            
            # Duplicate indices where phase change is happening
            animal_df = pd.concat([animal_df, animal_df.loc[idx]]).sort_index()
            # Indices are duplicated so take every second value
            times = animal_df.loc[idx].index[::2] 
            
            # Phase start time split
            phase_start = cfg["phase"][phase]
            hour, minute, second = _split_datetime(phase_start)

            for i in times: 
                location = animal_df.index.get_loc(animal_df.loc[i, "datetime"].index[0]).start # iloc of the duplicated index for data assignement purposes
                # Get timedelta between the start of phase and first datetime. Subtract this time + 1 microsecond to create a datetime in the previuous phase
                phase_start_diff = animal_df.iloc[location, 2] - animal_df.iloc[location, 2].replace(hour=hour, minute=minute, second=second, microsecond=0) + pd.Timedelta(microseconds=1)
                animal_df.iloc[location, 2] = animal_df.iloc[location, 2] - phase_start_diff
                
                # Correct also day, phase and phase_count
                animal_df = _correct_padded_info(animal_df, location)
        
        animal_dfs.append(animal_df)

    padded_df = (
        pd.concat(animal_dfs)
        .sort_values("datetime")
        .reset_index(drop=True)
        .drop("phase_map", axis=1)
    )

    # Overwrite with new timedelta
    padded_df = create_data_structure.calculate_timedelta(padded_df)
    
    if save_data:
        padded_df.to_hdf(data_path, key=key, mode="a", format="table")
    
    return padded_df

def calculate_time_spent_per_position(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pd.DataFrame:
    """Calculates time spent in each possible position per phase for every mouse.

    Args:
        cfp: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        Multiindex DataFrame of time spent per position in seconds.
    """
    cfg = auxfun.read_config(cfp)
    
    data_path = Path(cfg["results_path"])
    key="time_per_position"
    
    time_per_position = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(time_per_position, pd.DataFrame):
        return time_per_position
    
    tunnels = cfg["tunnels"]
    
    df = auxfun.load_ecohab_data(cfg, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    # Map directional tunnel position to non-directional
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.position = padded_df.position.astype(str)
    padded_df.loc[mapper, "position"] = padded_df.loc[mapper, "position"].map(tunnels).values
    
    # Calculate time spent per position per phase
    time_per_position = (
        padded_df
        .loc[:, ["animal_id", "position", "phase", "phase_count", "timedelta"]]
        .groupby(["animal_id", "phase", "phase_count", "position"], observed=False)
        .sum()
        .unstack(level=0)
        .droplevel(0, axis=1)
        .fillna(0)
        .round(3)
    )
    
    time_per_position = auxfun._drop_empty_slices(time_per_position)
    
    if save_data:
        time_per_position.to_hdf(data_path, key=key, mode="a", format="table")
    
    return time_per_position

def calculate_visits_per_position(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False
    ) -> pd.DataFrame:
    """Calculates number of visits to each possible position per phase for every mouse.

    Args:
        cfp: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        Multiindex DataFrame with number of visits per position.
    """
    cfg = auxfun.read_config(cfp)
    data_path = Path(cfg["results_path"])
    key="visits_per_position"
    
    visits_per_position = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(visits_per_position, pd.DataFrame):
        return visits_per_position
    
    tunnels = cfg["tunnels"]
    
    df = auxfun.load_ecohab_data(cfg, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    # Map directional tunnel position to non-directional
    padded_df.position = padded_df.position.astype(str)
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.loc[mapper, "position"] = padded_df.loc[mapper, "position"].map(tunnels).values
    
    # Calculate visits to each position
    visits_per_position = (
        padded_df
        .loc[:, ["animal_id", "position", "phase", "phase_count"]]
        .groupby(["phase", "phase_count", "position"], observed=False)
        .value_counts()
        .unstack()
    )
    
    visits_per_position = auxfun._drop_empty_slices(visits_per_position)
    
    if save_data:
        visits_per_position.to_hdf(data_path, key=key, mode="a", format="table")
    
    return visits_per_position

def create_binary_df(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    precision: int = 10,
    ) -> pd.DataFrame:
    """Creates a binary DataFrame of the position of the animals. Multiindexed on the columns, for each position, each animal. 
       Indexed with datetime for easy time-based slicing.

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        precision: Multiplier of the time. Time is in seconds, multiplied by 10 gives index per 100ms, 5 per 200 ms etc. 

    Returns:
        _description_
    """
    cfg = auxfun.read_config(cfp)
    data_path = Path(cfg["results_path"])
    key="binary_df"
    
    binary_df = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(binary_df, pd.DataFrame):
        return binary_df
    
    if precision > 20:
        print("Warning! High precision may result in a very large DataFrame and potential python kernel crash!")
    
    df = auxfun.load_ecohab_data(cfg, key="main_df")
    animals = cfg["animal_ids"]
    positions = list(set(cfg["antenna_combinations"].values()))
    positions = [pos for pos in positions if "cage" in pos]

    # Prepare empty DF
    index_len = np.ceil((df.datetime.iloc[-1] - df.datetime.iloc[0]).total_seconds()*precision).astype(int)
    cols = pd.MultiIndex.from_product([positions, animals])
    idx = pd.date_range(df.datetime.iloc[0], df.datetime.iloc[-1], index_len).round("ms")

    binary_df = pd.DataFrame(False, index=idx, columns=cols, dtype=bool)
    df = df.query("position in @positions")

    print("Filling the DataFrame for each animal...")
    for animal in tqdm(animals):
        data_slice = df.query("animal_id == @animal").iloc[1:]
        starts = data_slice.datetime - pd.to_timedelta(data_slice.timedelta, "s") 
        stops = data_slice.datetime
        ending_pos = df.query("animal_id == @animal").position.iloc[1:]
        
        for i in range(len(starts)):
            binary_df.loc[starts.iloc[i]:stops.iloc[i], (ending_pos.iloc[i], animal)] = True

    if save_data:
        binary_df.to_hdf(cfg["results_path"], key=key, format="table")
    
    return binary_df