from pathlib import Path

import pandas as pd
import polars as pl
import polars.selectors as cs

from datetime import datetime

from deepecohab.utils import auxfun
from deepecohab.core import create_data_structure

def _split_datetime(phase_start: str) -> datetime:
    """Auxfun to split datetime string.
    """    
    return datetime.strptime(phase_start, "%H:%M:%S")


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

def create_padded_df(
    cfp: Path | str | dict,
    df: pl.LazyFrame,
    save_data: bool = True, 
    overwrite: bool = False,
    ) ->  pl.LazyFrame:
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
    results_path = Path(cfg['project_location']) / 'results'
    key='padded_df'
    
    padded_df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(padded_df, pl.LazyFrame):
        return padded_df
    
    dark_start = _split_datetime(cfg['phase']['dark_phase'])
    light_start = _split_datetime(cfg['phase']['light_phase'])

    dark_offset = pl.duration(
        hours=dark_start.hour,
        minutes=dark_start.minute,
        seconds=dark_start.second,
        microseconds=-1,
    )

    light_offset = pl.duration(
        hours=24 if light_start.hour == 0 else light_start.hour,
        minutes=light_start.minute,
        seconds=light_start.second,
        microseconds=-1,
    )

    tz = df.collect_schema()["datetime"].time_zone
    base_midnight = pl.col("datetime").dt.date().cast(pl.Datetime("us")).dt.replace_time_zone(tz)


    df = df.with_columns(
        (pl.col('phase') != pl.col('phase').shift(-1).over('animal_id')).alias('mask')
    )

    extension_df = df.filter(pl.col('mask')).with_columns(
        pl.when(pl.col('phase') == 'light_phase').then(
            base_midnight + dark_offset
        ).otherwise(
            base_midnight + light_offset
        ).alias("datetime")
    )

    padded_lf = pl.concat([
        df,
        extension_df    
    ]).sort(['datetime'])

    padded_lf = padded_lf.with_columns(
        pl.when(
            pl.col('mask')
        ).then(
            auxfun.get_timedelta_expression(alias = None)
        ).otherwise(
            pl.when(
                pl.col('mask').shift(1).over('animal_id')
            ).then(
                auxfun.get_timedelta_expression(alias = None)
            ).otherwise(
                pl.col('timedelta')
            )
        ).alias('timedelta'),
        pl.when(pl.col('mask')).then(
            pl.col('position').shift(-1).over('animal_id')
        ).otherwise(pl.col('position')).alias('position')
    ).drop('mask')

    if save_data:
        padded_lf.sink_parquet(results_path / f"{key}.parquet", compression='lz4')
    
    return padded_lf

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

    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_lf = create_padded_df(cfp, df, overwrite=overwrite)

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

    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    padded_lf = create_padded_df(cfp, df)
    
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