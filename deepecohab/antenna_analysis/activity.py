from pathlib import Path

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
    )

    if save_data:
        cage_occupancy.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
        
    return cage_occupancy


def calculate_activity(
    cfp: str | Path | dict, 
    save_data: bool = True, 
    overwrite: bool = False,
    ) -> pl.LazyFrame:
    """Calculates time spent and visits to every possible position per phase for every mouse.

    Args:
        cfp: path to projects' config file or dict with the config.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.

    Returns:
        LazyFrame of time and visits
    """
    cfg = auxfun.read_config(cfp)
    
    results_path = Path(cfg['project_location']) / 'results'
    key='time_per_position'
    
    time_per_position_lf = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(time_per_position_lf, pl.LazyFrame):
        return time_per_position_lf

    padded_lf = auxfun.load_ecohab_data(cfg, key='padded_df')

    padded_lf = auxfun.remove_tunnel_directionality(padded_lf, cfg)

    per_position_lf = (
        padded_lf
        .group_by(["phase", "day", "phase_count", "position", 'animal_id'])
        .agg(
            pl.sum('timedelta').alias('time_in_position'),
            pl.len().alias('visits_to_position'),
        )
    )

    if save_data:
        per_position_lf.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    return per_position_lf

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