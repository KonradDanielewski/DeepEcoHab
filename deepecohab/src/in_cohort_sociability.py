import os
from pathlib import Path
from itertools import (
    combinations,
    product,
)

import numpy as np
import pandas as pd
from joblib import (
    Parallel,
    delayed,
)

from deepecohab.utils.auxfun import (
    check_save_data,
    check_cfp_validity
)

from deepecohab.src.activity import (
    create_padded_df,
    calculate_time_spent_per_position,
    get_phase_durations,
)

def generate_sociability_combinations(cfg: dict, df: pd.DataFrame) -> list:
    """Auxfun to generate a product of phases, phase_count, cages and mouse pairs for in-cohort sociability calculation.
    """    
    mouse_pairs = combinations(cfg["animal_ids"], 2)
    cages = [position for position in list(cfg["antenna_combinations"].keys()) if "cage" in position]
    phases = list(cfg["phase"].keys())
    phase_N = df.phase_count.unique()
    
    sociability_combinations = [
        (animal1, animal2, cage, n, phs) for 
        (animal1, animal2), cage, n, phs in 
        (product(mouse_pairs, cages, phase_N, phases))
        ]
    
    return sociability_combinations    

def _pairwise_time_together(
    padded_df: pd.DataFrame, 
    animal_1: str, 
    animal_2: str, 
    cage: str, 
    phase: str, 
    phase_count: int,
    minimum_time: int | float| None,
    ) -> list:
    """Calculates time spent together per condition set.
    """    
    animal1 = padded_df.query("animal_id == @animal_1 and position == @cage and phase == @phase and phase_count == @phase_count")
    animal2 = padded_df.query("animal_id == @animal_2 and position == @cage and phase == @phase and phase_count == @phase_count")

    animal1_visit_start = animal1.datetime - pd.to_timedelta(animal1.timedelta, "s")
    animal2_visit_start = animal2.datetime - pd.to_timedelta(animal2.timedelta, "s")
    animal1_visit_end = animal1.datetime
    animal2_visit_end = animal2.datetime

    overlaps = []

    for visit_start, visit_end in zip(animal2_visit_start, animal2_visit_end):
        res = animal1.loc[(visit_start <= animal1_visit_end) & (visit_end >= animal1_visit_start)]
        if len(res) > 0:
            for i in res.index:
                time = (min(visit_end, animal1_visit_end.loc[i]) - max(visit_start, animal1_visit_start.loc[i])).total_seconds()
                if isinstance(minimum_time, (int, float)) and time <= minimum_time:
                    continue
                overlaps.append(time)
        
    return [overlaps, animal_1, animal_2, cage, phase, phase_count]

def calculate_time_together(
    cfp: str | Path | dict, 
    minimum_time: int | float | None = None, 
    n_workers: int | None = None, 
    save_data: bool = True, 
    overwrite: bool = True,
    ) -> pd.DataFrame:
    """Calculates time spent together by animals on a per phase and per cage basis. Slow due to the nature of datetime overlap calculation.

    Args:
        cfg: dictionary with the project config.
        minimum_time: sets minimum time together to be considered an interaction - in seconds i.e., if set to 2 any time spent in the cage together
                   that is shorter than 2 seconds will be omited. 
        n_workers: number of CPU threads used to paralelize the calculation, by defualt half of the threads are allocated.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        Multiindex DataFrame of time spent together per phase, per cage.
    """    
    cfg = check_cfp_validity(cfp)
    data_path = Path(cfg["results_path"])
    key="time_together"
    
    time_together_df = None if overwrite else check_save_data(data_path, key)
    
    if isinstance(time_together_df, pd.DataFrame):
        return time_together_df
    
    df = pd.read_hdf(data_path, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    cages = [position for position in list(cfg["antenna_combinations"].keys()) if "cage" in position]
    phases = list(cfg["phase"].keys())
    phase_N = padded_df.phase_count.unique()
    mouse_pairs = combinations(cfg["animal_ids"], 2)
    
    # By default use half of the available cpu threads
    if not isinstance(n_workers, int):
        n_workers = os.cpu_count() / 2 
    
    sociability_combinations = generate_sociability_combinations(cfg, padded_df)

    # Calc time spent together per cage for each phase
    results = Parallel(n_jobs=n_workers, prefer='processes')(
        delayed(_pairwise_time_together)(padded_df=padded_df, animal_1=animal_1, animal_2=animal_2, cage=cage, phase_count=phase_N, phase=phase, minimum_time=minimum_time) 
        for animal_1, animal_2, cage, phase_N, phase in sociability_combinations
    )
    # Prep df
    cols = [f"{animal_1}_{animal_2}" for animal_1, animal_2 in mouse_pairs]
    idx = pd.MultiIndex.from_product([phases, phase_N, cages], names=["phase", "phase_count", "position"])
    time_together_df = pd.DataFrame(columns=cols, index=idx).sort_index()

    # fill df with data
    for time, animal_1, animal_2, cage, phase, n in results:
        animal_col = f"{animal_1}_{animal_2}"
        time_together_df.loc[(phase, n, cage), animal_col] = sum(time)
        
    time_together_df = time_together_df.dropna(axis=1, how="all").astype(float).round(3)

    if save_data:
        time_together_df.to_hdf(data_path, key=key, mode="a", format="table")

    return time_together_df

def calculate_in_cohort_sociability(
    cfp: dict, 
    save_data: bool = True, 
    overwrite: bool = False, 
    minimum_time: int | float | None = None,
    n_workers: int | None = None,
    ) -> pd.DataFrame:
    """Calculates in-cohort sociability. For more info: DOI:10.7554/eLife.19532.

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        minimum_time: sets minimum time together to be considered an interaction - in seconds. Passed to calculate_time_together.
        n_workers: number of CPU threads used to paralelize the calculation. Passed to calculate_time_together.

    Returns:
        Multiindex DataFrame of in-cohort sociability per phase for each possible pair of mice.
    """    
    cfg = check_cfp_validity(cfp)
    data_path = Path(cfg["results_path"])
    key="in_cohort_sociability"
    
    in_cohort_sociability = None if overwrite else check_save_data(data_path, key)
    
    if isinstance(in_cohort_sociability, pd.DataFrame):
        return in_cohort_sociability
    
    df = pd.read_hdf(data_path, key="main_df")
    padded_df = create_padded_df(cfg, df)
    
    mouse_pairs = combinations(cfg["animal_ids"], 2)
    cages = [position for position in list(cfg["antenna_combinations"].keys()) if "cage" in position]
    
    phase_durations = get_phase_durations(cfg, padded_df)
    
    # Get time spent together in cages
    time_together_df = calculate_time_together(cfg, minimum_time, n_workers)
    
    # Get time per position
    time_per_position = calculate_time_spent_per_position(cfg, padded_df)
    time_per_cage = time_per_position.loc[slice(None), slice(None), cages].copy()
    
    # Sum time together over all cages
    time_together_df = time_together_df.groupby(level=[0,1], observed=False).sum()
    
    # Normalize times as proportion of the phase duration
    proportion_alone = time_per_cage.div(phase_durations, axis=0)
    proportion_together = time_together_df.div(phase_durations, axis=0)
    
    per_mouse_pair = []
    
    for mouse1, mouse2 in mouse_pairs:
        per_cage_arr = (proportion_alone.loc[:, [mouse1]].values * proportion_alone.loc[:, [mouse2]].values).reshape(-1)
        per_cage_arr = np.add.reduceat(per_cage_arr, np.arange(0, len(proportion_alone), len(cages)))
        
        pair_sociability = proportion_together.loc[:, f"{mouse1}_{mouse2}"] - per_cage_arr
        per_mouse_pair.append(pair_sociability)
        
    in_cohort_sociability = pd.concat(per_mouse_pair, axis=1)
    
    if save_data:
        in_cohort_sociability.to_hdf(data_path, key=key, mode="a", format="table")

    return in_cohort_sociability