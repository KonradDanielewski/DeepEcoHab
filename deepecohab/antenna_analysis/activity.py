from pathlib import Path

import pandas as pd
import polars as pl
import polars.selectors as cs

from deepecohab.utils import auxfun


def calculate_cage_occupancy(
    cfp: str | Path | dict, 
    save_data: bool = True,
    overwrite: bool = False, 
) -> pl.LazyFrame:
    cfg = auxfun.read_config(cfp)
    
    results_path = Path(cfg['project_location']) / 'results'
    key = 'cage_occupancy'
    
    cage_occupancy = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(cage_occupancy, pl.LazyFrame):
        return cage_occupancy
    
    binary_lf = create_binary_df(cfp, save_data, overwrite, return_df=True)
    
    binary_lf = binary_lf.group_by(['day', 'hour', 'animal_id']).agg(
        cs.boolean().sum()
    )

    cage_occupancy = (
        binary_lf.unpivot(
            cs.contains('cage'),
            index = ['day', 'hour', 'animal_id'],
            variable_name='cage',
            value_name='time_sum',
        )
        .sort(['day', 'hour', 'cage', 'animal_id'])  # drop if you don't need sorted
    )

    if save_data:
        cage_occupancy.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
        
    return cage_occupancy


def calculate_time_spent_per_position(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pl.LazyFrame:
    """Calculates time spent in each possible position per phase for every mouse.

    Args:
        cfp: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        Multiindex DataFrame of time spent per position in seconds.
    """
    cfg = auxfun.read_config(cfp)
    
    results_path = Path(cfg['project_location']) / 'results'
    key='time_per_position'
    
    time_per_position_lf = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(time_per_position_lf, pl.LazyFrame):
        return time_per_position_lf
    
    animal_ids = list(cfg['animal_ids'])

    padded_lf = auxfun.load_ecohab_data(cfg, key='padded_df')

    # Map directional tunnel position to non-directional and calculate time spent per position per phase
    padded_lf = auxfun.remove_tunnel_directionality(padded_lf, cfg)

    group_cols = ["phase", "day", "phase_count", "position"]

    time_per_position_lf = padded_lf.group_by(
            group_cols
        ).agg(
            auxfun.get_agg_expression(
                value_col="timedelta",
                animal_ids=animal_ids,
                agg_fn=lambda e: e.sum(),
            )
        ).sort(group_cols)

    if save_data:
        time_per_position_lf.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    return time_per_position_lf

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
    results_path = Path(cfg['project_location']) / 'results'
    key='visits_per_position'
    
    visits_per_position = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(visits_per_position, pd.DataFrame):
        return visits_per_position
    
    animal_ids = list(cfg['animal_ids'])

    padded_lf = auxfun.load_ecohab_data(cfg, key='padded_df')    
    padded_lf = auxfun.remove_tunnel_directionality(padded_lf, cfg)

    group_cols = ['phase', 'day', 'phase_count', 'hour', 'position']
    
    # Calculate visits to each position
    visits_per_position = (
        padded_lf.group_by(
            group_cols
        ).agg(
            auxfun.get_agg_expression(
                value_col="timedelta",
                animal_ids=animal_ids,
                agg_fn=lambda e: e.count(),
            )
        ).sort(group_cols).fill_null(0)
    )
    
    if save_data:
        visits_per_position.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    return visits_per_position

def create_binary_df(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    return_df: bool = False,
    precision: int = 1,
    ) -> pl.LazyFrame:
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

    positions = cfg['cages']
    animal_ids = list(cfg['animal_ids'])

    lf = auxfun.load_ecohab_data(cfg, key='main_df')

    animals_lf = pl.DataFrame({'animal_id': animal_ids}).lazy().with_columns(
        pl.col('animal_id').cast(pl.Enum(animal_ids))
        )

    lf_filtered = (
        lf
        .select(['phase', 'day', 'hour', 'phase_count', 'datetime', 'animal_id', 'position'])
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

    ).fill_null(strategy='forward')

    binary_lf = binary_lf.with_columns(
        [(pl.col('position')== x).alias(x) for x in positions]
        ).drop('position')

    if save_data:
        binary_lf.sink_parquet(results_path / f"{key}.parquet", compression='lz4')

    if return_df:
        return binary_lf