from pathlib import Path

import numpy as np
import pandas as pd
import pytz
from tzlocal import get_localzone

from deepecohab.utils import auxfun

def load_data(cfp: str | Path, custom_layout: bool, sanitize_animal_ids: bool, min_antenna_crossings: int = 100) -> pd.DataFrame:
    """Auxfum to load and combine text files into a pandas dataframe
    """    
    cfg = auxfun.read_config(cfp)   
    data_path = Path(cfg['data_path'])
    
    data_files = auxfun.get_data_paths(data_path)

    dfs = []
    for file in data_files:
        df = pd.read_csv(file, sep='\t', names=['ind', 'date', 'time', 'antenna', 'time_under', 'animal_id'])
        comport = Path(file).name.split('_')[0]
        df['COM'] = comport
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).drop('ind', axis=1)
    
    if sanitize_animal_ids:
        df = auxfun._sanitize_animal_ids(cfp, df, min_antenna_crossings)
    
    if custom_layout:
        rename_dicts = cfg['antenna_rename_scheme']
        for com_name in rename_dicts.keys():
            df = _rename_antennas(df, com_name, rename_dicts)
    
    return df

def check_for_dst(df: pd.DataFrame) -> tuple[int, int]:
    zone_offset = df.datetime.dt.strftime('%z').map(lambda x: x[1:3]).astype(int)
    time_change_happened = len(np.where((zone_offset != zone_offset[0]))[0]) > 0
    if time_change_happened:
        time_change_ind = np.where((zone_offset != zone_offset[0]))[0][0]
        time_change = zone_offset[time_change_ind] - zone_offset[time_change_ind-1]
        return int(time_change), int(time_change_ind)
    else:
        return None, None

def correct_phases_dst(cfg: dict, df: pd.DataFrame, time_change: int, time_change_index: int) -> pd.DataFrame:
    """Auxfun to correct phase start and end when daylight saving happens during the recording
    """    
    start_time, end_time = cfg['phase'].values()

    start_time = (':').join(
        (str(int(start_time.split(':')[0]) + time_change), 
            start_time.split(':')[1], 
            start_time.split(':')[2])
    )
    end_time = (':').join(
        (str(int(end_time.split(':')[0]) + time_change), 
            end_time.split(':')[1], 
            end_time.split(':')[2])
    )

    temp_df = df.loc[time_change_index:].copy()

    index = pd.DatetimeIndex(temp_df['datetime'])
    temp_df.loc[index.indexer_between_time(start_time, end_time) + time_change_index, 'phase'] = 'light_phase'
    temp_df['phase'] = temp_df.phase.fillna('dark_phase')

    df.loc[time_change_index:, 'phase'] = temp_df['phase'].values

    return df

def calculate_timedelta(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to calculate timedelta between positions i.e. time spent in each state, rounded to 10s of miliseconds
    """    
    df.loc[:, 'timedelta'] = (
        df
        .loc[:, ['datetime', 'animal_id']]
        .groupby('animal_id', observed=False)
        .diff()
        .iloc[:, 0]
        .dt.total_seconds()
        .fillna(0)
        .round(2)
    )
    return df

def get_day(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the day
    """    
    df['day'] = ((df.datetime - df.datetime.iloc[0]) + pd.Timedelta(str(df.datetime.dt.time[0]))).dt.days + 1
    return df

def get_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the hour
    """    
    hour = (df.datetime - df.datetime[0]).dt.total_seconds()/3600
    hour[0] = 0.01
    df['hour'] = np.ceil(hour).astype(int)
    return df

def get_phase(cfg: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun for getting the phase
    """
    start_time, end_time = cfg['phase'].values()

    index = pd.DatetimeIndex(df['datetime'])
    df.loc[index.indexer_between_time(start_time, end_time), 'phase'] = 'light_phase'
    df['phase'] = df.phase.fillna('dark_phase')
    
    return df

def get_phase_count(cfg: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun used to count phases
    """   
    df['phase_count'] = None
    phases = list(cfg['phase'].keys())
    
    for phase in phases:
        phase_bool = df['phase'].eq(phase)
        shift = phase_bool.shift()
        indices = df.phase.loc[df.phase == phase].index
        df.loc[indices, 'phase_count'] = (phase_bool.ne(shift & phase_bool).cumsum()).loc[indices].values
    df.phase_count = df.phase_count.astype(int)
    return df

def map_antenna2position(antenna_column: pd.Series, positions: dict) -> pd.Series:
    """Auxfun to map antenna pairs to animal position
    """    
    arr1 = np.insert(antenna_column, 0, 0).astype(str)
    arr2 = np.insert(antenna_column, len(antenna_column), 0).astype(str)

    antenna_pairs = (pd.Series(arr1) + '_' + pd.Series(arr2))[:-1]
    antenna_pairs.index = antenna_column.index
    
    location = antenna_pairs.map(positions)

    return location

def get_animal_position(df: pd.DataFrame, positions: dict) -> pd.DataFrame:
    """Auxfun, groupby mapping of antenna pairs to position
    """    
    df.loc[:, 'position'] = (
        df
        .loc[:, ['animal_id', 'antenna']]
        .groupby('animal_id', observed=False)
        .apply(map_antenna2position, positions=positions, include_groups=False)
        .fillna('undefined')
        .droplevel(level=0, axis=0)
        .sort_index()
        .values
    )

    return df

def _rename_antennas(df: pd.DataFrame, com_name: str, rename_dicts: dict) -> pd.DataFrame:
    """Auxfun for antenna name mapping when custom layout is used
    """    
    mapping = {int(k):v for k,v in rename_dicts[com_name].items()}
    df.loc[df.COM == com_name, 'antenna'] = df.query('COM == @com_name')['antenna'].map(mapping)
    return df

def _prepare_columns(cfg: dict, df: pd.DataFrame, positions: list, timezone: str | None = None) -> pd.DataFrame:
    """Auxfun to prepare the df, adding new columns
    """    
    # Establish all possible categories for position
    positions.append('undefined')
    
    df['timedelta'] = np.nan
    df['day'] = np.nan
    
    df['position'] = pd.Series(dtype='category').cat.set_categories(positions)
    df['phase'] = pd.Series(dtype='category').cat.set_categories(cfg['phase'].keys())

    df['animal_id'] = df['animal_id'].astype('category').cat.set_categories(cfg['animal_ids'])
    df['datetime'] = df['date'] + ' ' + df['time']
    
    if not isinstance(timezone, str):
        df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(get_localzone().key, ambiguous='infer')
    else:
        df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(timezone, ambiguous='infer')

    df["hour"] = df.datetime.dt.hour.astype("category")
    df['antenna'] = df.antenna.astype(int)
    df = df.drop(['date', 'time'], axis=1)
    df = df.drop_duplicates(['datetime', 'animal_id'])
    
    return df

def get_ecohab_data_structure(
    cfp: str,
    sanitize_animal_ids: bool = True,
    min_antenna_crossings: int = 100,
    custom_layout: bool = False,
    overwrite: bool = False,
    timezone: str | None = None,
) -> pd.DataFrame:
    """Prepares EcoHab data for further analysis

    Args:
        cfp: path to project config file
        sanitize_animal_ids: toggle whether to remove animals. Removes animals that had less than 10 antenna crossings during the whole experiment.
        custom_layout: if multiple boards where added/antennas are in non-default location set to True
        overwrite: toggles whether to overwrite existing data file

    Returns:
        EcoHab data structure as a pd.DataFrame
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key = 'main_df'
    
    df = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(df, pd.DataFrame):
        return df
    
    remapping_dict = cfg['antenna_combinations']
    positions = list(set(remapping_dict.values()))
    
    df = load_data(
        cfp=cfp,
        custom_layout=custom_layout,
        sanitize_animal_ids=sanitize_animal_ids,
        min_antenna_crossings=min_antenna_crossings,
    )
    
    cfg = auxfun.read_config(cfp) # reload config potential animal_id changes due to sanitation
    df = _prepare_columns(cfg, df, positions, timezone)

    # Slice to start and end date
    try:
        start_date = cfg['experiment_timeline']['start_date']
        finish_date = cfg['experiment_timeline']['finish_date']
        if isinstance(start_date, str) & isinstance(finish_date, str): 
            start, finish = pd.to_datetime(start_date), pd.to_datetime(finish_date)
            timeframe = (
                (df.datetime >= pytz.timezone(timezone).localize(start)) & 
                (df.datetime <= pytz.timezone(timezone).localize(finish))
            )
            df = df.loc[timeframe, :].sort_values('datetime').reset_index(drop=True)
    except KeyError:
        print('Start and end dates not provided. Extracting from data...')
        auxfun._append_start_end_to_config(cfp, df)
    
    df = df.sort_values('datetime').reset_index(drop=True)
    
    df = calculate_timedelta(df)
    df = get_day(df)
    df = get_animal_position(df, remapping_dict)
    df = get_phase(cfg, df)

    time_change, time_change_ind = check_for_dst(df)
    if isinstance(time_change, int):
        print('Correcting for daylight savings...')
        df = correct_phases_dst(cfg, df, time_change, time_change_ind)

    df = get_phase_count(cfg, df)
    
    condition_map = {key: i+1 for i, key in enumerate(positions)}
    df['position_keys'] = df.position.map(condition_map).astype(int).fillna(0)

    df = df.sort_index(axis=1).reset_index(drop=True)

    df = df.drop('COM', axis=1)
    
    df.to_hdf(results_path, key=key, mode='a', format='table')
    
    phase_durations = auxfun.get_phase_durations(cfg, df)
    phase_durations.to_hdf(results_path, key='phase_durations', mode='a', format='table')

    return df
