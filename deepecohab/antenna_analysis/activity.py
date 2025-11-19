from pathlib import Path

import pandas as pd
import polars as pl

import numpy as np
from tqdm import tqdm

from deepecohab.utils import auxfun
from deepecohab.core import create_data_structure

def _split_datetime(phase_start: str) -> tuple[str, ...]:
    """Auxfun to split datetime string.
    """    
    hour = int(phase_start.split(':')[0])
    minute = int(phase_start.split(':')[1])
    second = int(phase_start.split(':')[2].split('.')[0])
    
    return hour, minute, second

def _extract_phase_switch_indices(animal_df: pd.DataFrame):
    """Auxfun to find indices of phase switching.
    """    
    animal_df['phase_map'] = animal_df.phase.map({'dark_phase': 0, 'light_phase': 1})
    shift = animal_df['phase_map'].astype('int').diff()
    shift.loc[0] = 0
    indices = shift[shift != 0]
    
    return indices

def _correct_padded_info(animal_df: pd.DataFrame, location: int) -> pd.DataFrame:
    """Auxfun to correct information in duplicated indices to match the previous phase.
    """    
    hour_col, day_col, phase_col, phase_count_col = (
        animal_df.columns.get_loc('hour'), 
        animal_df.columns.get_loc('day'), 
        animal_df.columns.get_loc('phase'), 
        animal_df.columns.get_loc('phase_count')
    )
   
    animal_df.iloc[location, hour_col] = animal_df.iloc[location-1, hour_col]
    animal_df.iloc[location, day_col] = animal_df.iloc[location-1, day_col]
    animal_df.iloc[location, phase_col] = animal_df.iloc[location-1, phase_col]
    animal_df.iloc[location, phase_count_col] = animal_df.iloc[location-1, phase_count_col]
    
    return animal_df

def calculate_cage_occupancy(
    cfp: str | Path | dict, 
    save_data: bool = True,
    overwrite: bool = False, 
) -> pd.DataFrame:
    cfg = auxfun.read_config(cfp)
    
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key = 'cage_occupancy'
    
    cage_occupancy = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(cage_occupancy, pd.DataFrame):
        return cage_occupancy
    
    binary_df = create_binary_df(cfp, save_data, overwrite, return_df=True)
    
    print('Calculating per hour cage time...')
    day = ((binary_df.index.get_level_values('datetime') 
             - binary_df.index.get_level_values('datetime')[0]) + pd.Timedelta(str(binary_df.index.get_level_values('datetime').time[0]))).days + 1
    hours = binary_df.index.get_level_values('datetime').hour
    
    binary_df.index = pd.MultiIndex.from_arrays([day, hours], names=['day', 'hours'])
    binary_df = binary_df.stack(0, future_stack=True)
    binary_df.index = binary_df.index.set_names(['day', 'hours', 'cage'])
    binary_df.columns = binary_df.columns.set_names(['animal_id'])

    cage_occupancy = binary_df.stack().groupby(level=['day', 'hours', 'cage', 'animal_id']).sum().reset_index()
    cage_occupancy.columns = ['day', 'hours', 'cage', 'animal_id', 'time_sum']
    
    if save_data:
        cage_occupancy.to_hdf(results_path, key=key, mode='a', format='table')
        
    return cage_occupancy

def create_padded_df(
    cfp: Path | str | dict,
    df: pd.DataFrame,
    save_data: bool = True, 
    overwrite: bool = False,
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
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='padded_df'
    
    padded_df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(padded_df, pd.DataFrame):
        return padded_df
    
    animals = cfg['animal_ids']
    phases = list(cfg['phase'].keys())

    animal_dfs = []

    for animal in animals:
        animal_df = df.query('animal_id == @animal').copy()

        indices = _extract_phase_switch_indices(animal_df)

        light_phase_starts = indices[indices == 1].index
        dark_phase_starts = indices[indices == -1].index

        for phase in phases:
            if phase == 'light_phase':
                idx = light_phase_starts
            else:
                idx = dark_phase_starts
            
            # Duplicate indices where phase change is happening
            animal_df = pd.concat([animal_df, animal_df.loc[idx]]).sort_index()
            # Indices are duplicated so take every second value
            times = animal_df.loc[idx].index[::2] 
            
            # Phase start time split
            phase_start = cfg['phase'][phase]
            hour, minute, second = _split_datetime(phase_start)

            for i in times: 
                location = animal_df.index.get_loc(animal_df.loc[i, 'datetime'].index[0]).start # iloc of the duplicated index for data assignement purposes
                # Get timedelta between the start of phase and first datetime. Subtract this time + 1 microsecond to create a datetime in the previuous phase
                phase_start_diff = animal_df.iloc[location, 2] - animal_df.iloc[location, 2].replace(hour=hour, minute=minute, second=second, microsecond=0) + pd.Timedelta(microseconds=1)
                animal_df.iloc[location, 2] = animal_df.iloc[location, 2] - phase_start_diff
                
                # Correct also day, phase and phase_count
                animal_df = _correct_padded_info(animal_df, location)
        
        animal_dfs.append(animal_df)

    padded_df = (
        pd.concat(animal_dfs)
        .sort_values('datetime')
        .reset_index(drop=True)
        .drop('phase_map', axis=1)
    )

    # Overwrite with new timedelta
    padded_df = create_data_structure.calculate_timedelta(padded_df)
    
    if save_data:
        padded_df.to_hdf(results_path, key=key, mode='a', format='table')
    
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
    
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='time_per_position'
    
    time_per_position = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(time_per_position, pd.DataFrame):
        return time_per_position
    
    tunnels = cfg['tunnels']
    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_df = create_padded_df(cfp, df, overwrite=overwrite)
    
    # Map directional tunnel position to non-directional
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.position = padded_df.position.astype(str)
    padded_df.loc[mapper, 'position'] = padded_df.loc[mapper, 'position'].map(tunnels).values
    
    # Calculate time spent per position per phase
    time_per_position = (
        padded_df
        .groupby(['phase', 'day', 'phase_count', 'position', 'animal_id'], observed=True)['timedelta']
        .sum()
        .unstack('animal_id')
    )
    
    if save_data:
        time_per_position.to_hdf(results_path, key=key, mode='a', format='table')
    
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
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='visits_per_position'
    
    visits_per_position = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(visits_per_position, pd.DataFrame):
        return visits_per_position
    
    tunnels = cfg['tunnels']
    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_df = create_padded_df(cfp, df)
    
    # Map directional tunnel position to non-directional
    padded_df.position = padded_df.position.astype(str)
    mapper = padded_df.position.isin(tunnels.keys())
    padded_df.loc[mapper, 'position'] = padded_df.loc[mapper, 'position'].map(tunnels).values
    
    # Calculate visits to each position
    visits_per_position = (
        padded_df
        .groupby(['phase', 'day', 'phase_count', 'hour', 'position', 'animal_id'], observed=True)['animal_id']
        .agg('count')
        .unstack('animal_id')
        .fillna(0)
        .astype(int)
    )
    
    if save_data:
        visits_per_position.to_hdf(results_path, key=key, mode='a', format='table')
    
    return visits_per_position

def create_binary_df(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    return_df: bool = False,
    precision: int = 1,
    ) -> pl.DataFrame:
    """Creates a binary DataFrame of the position of the animals. Multiindexed on the columns, for each position, each animal. 
       Indexed with datetime for easy time-based slicing.

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        precision: Multiplier of the time. Time is in seconds, multiplied by 10 gives index per 100ms, 5 per 200 ms etc. 

    Returns:
        Binary dataframe (True/False) of position of each animal per second (by default) per cage. 
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' 
    key='binary_df'
    
    
    binary_lf = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(binary_lf, pl.LazyFrame) and return_df:
        return binary_lf.collect(engine='streaming')

    if precision > 20:
        print('Warning! High precision may result in a very large DataFrame and potential python kernel crash!')

    positions = list(set(cfg['antenna_combinations'].values()))
    positions = [pos for pos in positions if 'cage' in pos]
    animal_ids = list(cfg['animal_ids'])

    lf = auxfun.load_ecohab_data(cfg, key='main_df')

    animals_lf = pl.DataFrame({'animal_id': animal_ids}).lazy().with_columns(
        pl.col('animal_id').cast(pl.Enum(animal_ids))
        )

    lf_filtered = (
        lf
        .select(['datetime', 'animal_id', 'position'])
        .filter(
            pl.col('position') != pl.col('position').shift(-1).over('animal_id')
        )
    ).sort(['animal_id', 'datetime'])

    time_step = f'{1000//precision}ms'

    time_range = pl.datetime_range(
        pl.col('datetime').min(),
        pl.col('datetime').max(), 
        time_step,
    ).alias('datetime')

    grid_lf = animals_lf.join(lf.select(time_range), how='cross').sort(['animal_id', 'datetime'])

    binary_lf = grid_lf.join_asof(
        lf_filtered,
        on='datetime',
        by='animal_id',
        strategy='forward',

    ).fill_null('forward')

    binary_lf = binary_lf.with_columns(
        [(pl.col('position')== x).alias(x) for x in positions]
        ).drop('position')

    binary_df = binary_lf.collect()

    if save_data:
        binary_df.write_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    if return_df:
        return binary_df