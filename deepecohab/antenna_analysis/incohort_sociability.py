import pickle
import os
from pathlib import Path
from itertools import (
    combinations,
    product,
)

import pandas as pd
from tqdm import tqdm
from joblib import (
    Parallel,
    delayed,
)

from deepecohab.antenna_analysis import activity
from deepecohab.utils import auxfun

def _generate_sociability_combinations(cfg: dict) -> list:
    """Auxfun to generate a product of phases, phase_count, cages and mouse pairs for in-cohort sociability calculation."""    
    mouse_pairs = combinations(cfg['animal_ids'], 2)
    positions = list(set(cfg['antenna_combinations'].values()))
    
    cages = [position for position in positions if 'cage' in position]
    
    sociability_combinations = list(product(mouse_pairs, cages))
    
    return sociability_combinations

def _pairwise_time_together(
    padded_df: pd.DataFrame, 
    animal_1: str, 
    animal_2: str, 
    cage: str, 
    minimum_time: int | float | None = None,
) -> pd.DataFrame:
    """Helper to paralelize calculation of time together"""
    animal1 = padded_df.query('animal_id == @animal_1 and position == @cage')
    animal2 = padded_df.query('animal_id == @animal_2 and position == @cage')

    df1 = pd.DataFrame({
        'event1_start': animal1.datetime - pd.to_timedelta(animal1.timedelta, 's'),
        'event1_end': animal1.datetime,
        'key': 1,
    })

    df2 = pd.DataFrame({
        'event2_start': animal2.datetime - pd.to_timedelta(animal2.timedelta, 's'),
        'event2_end': animal2.datetime,
        'key': 1,
    })

    merged = df1.merge(df2, on='key').drop(columns='key')

    merged['overlap_start'] = merged[['event1_start', 'event2_start']].max(axis=1)
    merged['overlap_end'] = merged[['event1_end', 'event2_end']].min(axis=1)
    merged['overlap_duration'] = (merged['overlap_end'] - merged['overlap_start']).dt.total_seconds()

    overlaps = merged[merged['overlap_duration'] > minimum_time].reset_index(drop=True)

    output = padded_df.loc[padded_df.datetime.searchsorted(overlaps.overlap_end), ['phase', 'day', 'phase_count']].reset_index(drop=True)

    output['animal_1'] = animal_1
    output['animal_2'] = animal_2
    output['cage'] = cage
    output['time_together'] = overlaps.overlap_duration.values
    
    return output

def calculate_time_alone(
    cfp: Path | str | dict,
    save_data: bool = True, 
    overwrite: bool = False,
):
    """Calculates time spent alone by animal per phase/day/cage

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        
    Returns:
        DataFrame containing time spent alone in seconds.
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='time_alone'

    time_alone = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)

    if isinstance(time_alone, pd.DataFrame):
        return time_alone

    animals = cfg['animal_ids']
    binary_df = activity.create_binary_df(cfp, save_data, overwrite, return_df=True)

    temp_df = binary_df.stack(level=0, future_stack=True).reorder_levels([0,1,3,2]).sort_index()
    temp_df.index = temp_df.index.set_names(['phase', 'phase_count', 'cage', 'datetime'])

    time_alone = pd.DataFrame(columns=animals, index=temp_df.droplevel('datetime').index.drop_duplicates())

    print('Calculating time spent alone...')
    for animal in tqdm(animals):
        time_alone[animal] = temp_df.loc[(temp_df.sum(axis=1) == 1) & (temp_df.loc[:, animal]), animal].groupby(level=['phase', 'phase_count', 'cage'], observed=False).sum()
        
    if save_data:
        time_alone.to_hdf(results_path, key=key, mode='a', format='table')
        
    return time_alone

def calculate_pairwise_meetings(
    cfp: str | Path | dict, 
    minimum_time: int | float | None = 2, 
    n_workers: int | None = None, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pd.DataFrame:
    """Calculates time spent together and number of meetings by animals on a per phase, day and cage basis. Slow due to the nature of datetime overlap calculation.

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
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key1='time_together'
    key2='pairwise_encounters'
    
    time_together_df = None if overwrite else auxfun.load_ecohab_data(cfp, key1, verbose=False)
    pairwise_encounters_df = None if overwrite else auxfun.load_ecohab_data(cfp, key2, verbose=False)
    
    if isinstance(time_together_df, pd.DataFrame) and isinstance(pairwise_encounters_df, pd.DataFrame):
        return time_together_df, pairwise_encounters_df
    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_df = activity.create_padded_df(cfp, df, save_data, overwrite)
    animals = cfg['animal_ids']
    
    # By default use half of the available cpu threads
    if not isinstance(n_workers, int):
        n_workers = os.cpu_count() // 2 
    
    print('Calculating pairwise time spent together...')
    # Calc time spent together per cage for each phase
    results = Parallel(n_jobs=8, prefer='processes')(
        delayed(_pairwise_time_together)(padded_df=padded_df, animal_1=animal_1, animal_2=animal_2, cage=cage, minimum_time=minimum_time) 
        for (animal_1, animal_2), cage in tqdm(_generate_sociability_combinations(cfg))
    )   
    pickle_path = results_path.parent / 'time_together.pickle' # TODO: does it have to be a pickle? Would be better to store it with other data in h5 and avoid pickle overall
    with open(pickle_path, 'wb') as output_file:
        pickle.dump(results, output_file)
    
    output = pd.concat(results)

    index = padded_df.loc[:, ['phase', 'day', 'phase_count', 'position', 'animal_id']]
    index = sorted(pd.MultiIndex.from_frame(index[index.position.str.contains('cage')].drop_duplicates()))

    pairwise_encounters_df = (
        output
        .iloc[:, :-1] # don't use time together for encounter counting
        .value_counts()
        .unstack('animal_1')
        .reorder_levels(['phase', 'day', 'phase_count', 'cage', 'animal_2'])
        .reindex(index)
        .reindex(animals, axis=1)
    )

    time_together_df = (
        output
        .groupby(['phase', 'day', 'phase_count', 'cage', 'animal_2', 'animal_1'], observed=True)
        .agg('sum', min_count=1)
        .unstack('animal_1')
        .reindex(index)
        .droplevel(0, axis=1)
        .reindex(animals, axis=1)
    )

    if save_data:
        time_together_df.to_hdf(results_path, key=key1, mode='a', format='table')
        pairwise_encounters_df.to_hdf(results_path, key=key2, mode='a', format='table')
    
    return time_together_df, pairwise_encounters_df

def calculate_incohort_sociability(
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
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='incohort_sociability'

    incohort_sociability = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)

    if isinstance(incohort_sociability, pd.DataFrame):
        return incohort_sociability

    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_df = activity.create_padded_df(cfp, df)
    
    positions = list(set(cfg['antenna_combinations'].values()))
    cages = sorted([position for position in positions if 'cage' in position])
    phase_durations = auxfun.get_phase_durations(cfg, padded_df)

    # Get time spent together in cages
    time_together_df = calculate_pairwise_meetings(cfg, minimum_time, n_workers, save_data, overwrite)[0]

    # Get time per position
    time_per_position = activity.calculate_time_spent_per_position(cfg, save_data, overwrite)
    time_per_cage = time_per_position.loc[slice(None), slice(None), cages]

    # Normalize times as proportion of the phase duration
    spent_proportion = time_per_cage.div(phase_durations, axis=0)

    # animal_1*animal2 summed across cages - likelihood of meeting
    col_pairs = list(combinations(spent_proportion.columns, 2))
    pairwise = pd.DataFrame(columns=[f'{a}_{b}' for a,b in col_pairs])

    for col1, col2 in col_pairs:
        pairwise[f'{col1}_{col2}'] = spent_proportion[col1] * spent_proportion[col2]
        
    pairwise_time_overall = pairwise.groupby(level=['phase', 'phase_count'], observed=True).sum()

    # sum of time spent together across all cages
    time_together_df = time_together_df.unstack()
    time_together_df.columns = [f'{a}_{b}' for a, b in time_together_df.columns.to_flat_index()]
    proportion_together = time_together_df.groupby(level=['phase', 'phase_count'], observed=True).sum(min_count=1).div(phase_durations, axis=0)

    incohort_sociability = (proportion_together - pairwise_time_overall).round(3)
    incohort_sociability.columns = incohort_sociability.columns.str.split("_", expand=True)
    incohort_sociability = incohort_sociability.stack(future_stack=True)
    incohort_sociability.index = incohort_sociability.index.set_names(['phase', 'phase_count', 'animal_2'])
    
    if save_data:
        incohort_sociability.to_hdf(results_path, key=key, mode='a', format='table')

    return incohort_sociability