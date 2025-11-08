import pickle
import os
from pathlib import Path
from itertools import (
    combinations,
    product,
)

import pandas as pd
import polars as pl
from tqdm import tqdm
from joblib import (
    Parallel,
    delayed,
)

from deepecohab.antenna_analysis import activity
from deepecohab.utils import auxfun

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

    temp_df = (
        binary_df
        .stack(level=0, future_stack=True)
        .reorder_levels(['phase', 'day', 'phase_count', 'cage', 'datetime'])
        .sort_index()
    )

    time_alone = pd.DataFrame(columns=animals, index=temp_df.droplevel('datetime').index.drop_duplicates())

    print('Calculating time spent alone...')
    for animal in tqdm(animals):
        time_alone[animal] = temp_df.loc[
                                        (temp_df.sum(axis=1) == 1) 
                                        & (temp_df.loc[:, animal]), animal
                                        ].groupby(level=['phase', 'day', 'phase_count', 'cage'], observed=False).sum()
        
    if save_data:
        time_alone.to_hdf(results_path, key=key, mode='a', format='table')
        
    return time_alone

def calculate_pairwise_meetings(
    cfp: str | Path | dict, 
    minimum_time: int | float | None = 2, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pl.DataFrame:
    """Calculates time spent together and number of meetings by animals on a per phase, day and cage basis. Slow due to the nature of datetime overlap calculation.

    Args:
        cfg: dictionary with the project config.
        minimum_time: sets minimum time together to be considered an interaction - in seconds i.e., if set to 2 any time spent in the cage together
                   that is shorter than 2 seconds will be omited. 
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        
    Returns:
        Multiindex DataFrame of time spent together per phase, per cage.
    """    
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'pairwise_meetings.parquet'
    padded_path = Path(cfg['project_location']) / 'results' / 'padded_df.parquet' # TODO: padded df should be created at the end of creating the main_df as it is the same data structure just with phase split of events so no reason to check for it's existance here
    cages = cfg['cages'] # TODO: add cages to the config similarily to tunnels being there
    
    pairwise_meetings = None if overwrite else auxfun.load_ecohab_data(cfp, 'pairwise_meetings', verbose=False)
    
    if isinstance(pairwise_meetings, pl.DataFrame):
        return pairwise_meetings
    
    lf = (
        pl.scan_parquet(padded_path)
        .filter(pl.col("position").is_in(cages))
        .with_columns([
            (pl.col("datetime") - pl.duration(seconds=pl.col("timedelta"))).alias("event_start"),
            pl.col("datetime").alias("event_end"),
        ])
    )

    joined = (
        lf.join(
            lf,
            on=["position", "phase", "day", "phase_count"],
            how="inner",
            suffix="_2",
        )
        .filter(pl.col("animal_id") < pl.col("animal_id_2"))
        .with_columns([
            (
                pl.min_horizontal(["event_end", "event_end_2"]) - 
                pl.max_horizontal(["event_start", "event_start_2"])
            ).dt.total_seconds(fractional=True).round(3).alias("overlap_duration")
            ,
        ])
        .filter(pl.col("overlap_duration") > minimum_time)
    )

    pairwise_meetings = (
        joined.group_by([
            "phase", "day", "phase_count", "position", "animal_id", "animal_id_2"
        ])
        .agg([
            pl.sum("overlap_duration").alias("time_together"),
            pl.len().alias("pairwise_encounters"),
        ])
        
    ).collect(engine='streaming').sort(['phase', 'day', 'phase_count', 'position', 'animal_id', 'animal_id_2'])
    
    if save_data:
        pairwise_meetings.write_parquet(results_path, compression='lz4')
    
    return pairwise_meetings

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
    time_per_cage = time_per_position.loc[slice(None), slice(None), slice(None), cages]

    # Normalize times as proportion of the phase duration
    spent_proportion = time_per_cage.div(phase_durations, axis=0)

    # animal_1*animal2 summed across cages - likelihood of meeting
    col_pairs = list(combinations(spent_proportion.columns, 2))
    pairwise = pd.DataFrame(columns=[f'{a}_{b}' for a,b in col_pairs])

    for col1, col2 in col_pairs:
        pairwise[f'{col1}_{col2}'] = spent_proportion[col1] * spent_proportion[col2]
        
    pairwise_time_overall = pairwise.groupby(level=['phase', 'day', 'phase_count'], observed=True).sum()

    # sum of time spent together across all cages
    time_together_df = time_together_df.unstack()
    time_together_df.columns = [f'{a}_{b}' for a, b in time_together_df.columns.to_flat_index()]
    proportion_together = time_together_df.groupby(level=['phase', 'day', 'phase_count'], observed=True).sum(min_count=1).div(phase_durations, axis=0)

    incohort_sociability = (proportion_together - pairwise_time_overall).round(3)
    incohort_sociability.columns = incohort_sociability.columns.str.split("_", expand=True)
    incohort_sociability = incohort_sociability.stack(future_stack=True)
    incohort_sociability.index = incohort_sociability.index.set_names(['phase', 'day', 'phase_count', 'animal_2'])
    
    if save_data:
        incohort_sociability.to_hdf(results_path, key=key, mode='a', format='table')

    return incohort_sociability