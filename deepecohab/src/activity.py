from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

from deepecohab.utils.auxfun import (
    check_save_data, 
    load_ecohab_data,
    check_cfp_validity
)
from deepecohab.src.create_data_structure import calculate_timedelta

def split_datetime(phase_start: str) -> tuple[str, ...]:
    """Auxfun to split datetime string.
    """    
    hour = int(phase_start.split(":")[0])
    minute = int(phase_start.split(":")[1])
    second = int(phase_start.split(":")[2].split(".")[0])
    
    return hour, minute, second

def extract_phase_switch_indices(animal_df: pd.DataFrame):
    """Auxfun to find indices of phase switching.
    """    
    animal_df["phase_map"] = animal_df.phase.map({"dark_phase": 0, "light_phase": 1})
    shift = animal_df["phase_map"].astype("int").diff()
    shift.loc[0] = 0
    indices = shift[shift != 0]
    
    return indices

def correct_padded_info(animal_df: pd.DataFrame, location: int) -> pd.DataFrame:
    """Auxfun to correct information in duplicated indices to match the previous phase.
    """    
    day_col, phase_col, phase_count_col = animal_df.columns.get_loc("day"), animal_df.columns.get_loc("phase"), animal_df.columns.get_loc("phase_count")
   
    animal_df.iloc[location, day_col] = animal_df.iloc[location-1, day_col]
    animal_df.iloc[location, phase_col] = animal_df.iloc[location-1, phase_col]
    animal_df.iloc[location, phase_count_col] = animal_df.iloc[location-1, phase_count_col]
    
    return animal_df

def get_phase_durations(cfg: dict, df: pd.DataFrame) -> pd.Series:
    """Auxfun to calculate approximate phase durations.
       Assumes the length is the closest full hour of the total length in seconds (first to last datetime in this phase).
    """    
    phase_Ns = list(df.phase_count.unique())
    phases = list(cfg["phase"].keys())

    hours = [60*60*i for i in range(1,13)]

    phase_product = list(product(phases, phase_Ns))
    idx = pd.MultiIndex.from_product([phases, phase_Ns], names=["phase", "phase_count"])
    phase_durations = pd.Series(index=idx)

    for phase, phase_N in phase_product:
        temp = df.query("phase == @phase and phase_count == @phase_N")
        total_time = (temp.datetime.iloc[-1] - temp.datetime.iloc[0]).total_seconds()
        time_calculated = np.abs(total_time - np.array(hours))
        closest_hour = np.where(np.min(time_calculated) == time_calculated)[0][0]
        phase_durations.loc[(phase, phase_N)] = hours[closest_hour]
    
    return phase_durations

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
    
    padded_df = None if overwrite else check_save_data(data_path, key)
    
    if isinstance(padded_df, pd.DataFrame):
        return padded_df
    
    animals = cfg["animal_ids"]
    phases = list(cfg["phase"].keys())

    animal_dfs = []

    for animal in animals:
        animal_df = df.query("animal_id == @animal").copy()

        indices = extract_phase_switch_indices(animal_df)

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
            hour, minute, second = split_datetime(phase_start)

            for i in times: 
                location = animal_df.index.get_loc(animal_df.loc[i, "datetime"].index[0]).start # iloc of the duplicated index for data assignement purposes
                # Get timedelta between the start of phase and first datetime. Subtract this time + 1 microsecond to create a datetime in the previuous phase
                phase_start_diff = animal_df.iloc[location, 2] - animal_df.iloc[location, 2].replace(hour=hour, minute=minute, second=second, microsecond=0) + pd.Timedelta(microseconds=1)
                animal_df.iloc[location, 2] = animal_df.iloc[location, 2] - phase_start_diff
                
                # Correct also day, phase and phase_count
                animal_df = correct_padded_info(animal_df, location)
        
        animal_dfs.append(animal_df)

    padded_df = (pd.concat(animal_dfs)
                .sort_values("datetime")
                .reset_index(drop=True)
                .drop("phase_map", axis=1)
                )

    # Overwrite with new timedelta
    padded_df["timedelta"] = calculate_timedelta(padded_df)
    
    if save_data:
        padded_df.to_hdf(data_path, key=key, mode="a", format="table")
    
    return padded_df

def calculate_time_spent_per_position(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False
    ) -> pd.DataFrame:
    """Calculates time spent in each possible position per phase for every mouse.

    Args:
        cfp: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        Multiindex DataFrame of time spent per position in seconds.
    """
    cfg = check_cfp_validity(cfp)
    
    data_path = Path(cfg["results_path"])
    key="time_per_position"
    
    time_per_position = None if overwrite else check_save_data(data_path, key)
    
    if isinstance(time_per_position, pd.DataFrame):
        return time_per_position
    
    tunnels = cfg["tunnels"]
    
    df = load_ecohab_data(cfg, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    # Map directional tunnel position to non-directional
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.position = padded_df.position.astype(str)
    padded_df.loc[mapper, "position"] = padded_df.loc[mapper, "position"].map(tunnels).values
    
    # Calculate time spent per position per phase
    time_per_position = (padded_df
            .loc[:, ["animal_id", "position", "phase", "phase_count", "timedelta"]]
            .groupby(["animal_id", "phase", "phase_count", "position"], observed=False)
            .sum()
            .unstack(level=0)
            .droplevel(0, axis=1)
            .fillna(0)
            )
 
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
    cfg = check_cfp_validity(cfp)
    data_path = Path(cfg["results_path"])
    key="visits_per_position"
    
    visits_per_position = None if overwrite else check_save_data(data_path, key)
    
    if isinstance(visits_per_position, pd.DataFrame):
        return visits_per_position
    
    tunnels = cfg["tunnels"]
    
    df = load_ecohab_data(cfg, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    # Map directional tunnel position to non-directional
    padded_df.position = padded_df.position.astype(str)
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.loc[mapper, "position"] = padded_df.loc[mapper, "position"].map(tunnels).values
    
    # Calculate visits to each position
    visits_per_position = (padded_df
            .loc[:, ["animal_id", "position", "phase", "phase_count"]]
            .groupby(["phase", "phase_count", "position"], observed=False)
            .value_counts()
            .unstack()
            )
    
    if save_data:
        visits_per_position.to_hdf(data_path, key=key, mode="a", format="table")
    
    return visits_per_position