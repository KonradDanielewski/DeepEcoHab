from itertools import (
    combinations,
    product,
)
from pathlib import Path

import numpy as np
import pandas as pd
from openskill.models import PlackettLuce
from tqdm import tqdm

from deepecohab.utils import auxfun

def _get_chasing_matches(chasing_mouse: pd.DataFrame, chased_mouse: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to get each chasing event as a match
    """    
    matches = pd.DataFrame({
        'loser': chased_mouse.animal_id, 
        'winner': chasing_mouse.animal_id,
        'datetime': chasing_mouse.datetime,
    })
    return matches

def _combine_matches(cfg: dict) -> tuple[list, pd.Series]:
    """Auxfun to combine all the chasing events into one data structure
    """    
    match_df = auxfun.load_ecohab_data(cfg, 'match_df', verbose=False)
    datetimes = match_df.datetime

    matches = list(match_df.drop('datetime', axis=1).itertuples(index=False, name=None))
    return matches, datetimes

def _rank_mice_openskill(
    cfg: dict,
    animal_ids: list[str], 
    ranking: dict | None = None,
    ) -> tuple[dict, pd.DataFrame, pd.Series]:
    """Rank mice using PlackettLuce algorithm from openskill. More info: https://arxiv.org/pdf/2401.05451

    Args:
        cfg: config dict
        matches: list of all matches structured
        animal_ids: list of animal IDs
        ranking: dictionary that contains ranking of animals - if provided the ranking will start from this state. Defaults to None.

    Returns:
        ranking: dictionary of the ranking per animal
        ranking_in_time: pd.DataFrame of the ranking where each row is another match, sorted in time
        datetimes: pd.Series of all matches datetimes for sorting or axis setting purposes
    """    
    model = PlackettLuce(limit_sigma=True, balance=True)
    match_list, datetimes = _combine_matches(cfg)
    
    if not isinstance(ranking, dict):
        ranking = {}

    for player in animal_ids:
        ranking[player] = model.rating()
    
    ranking_update = []
    for loser_name, winner_name in match_list:
        new_ratings = model.rate([[ranking[loser_name]], [ranking[winner_name]]], ranks=[1,0])
        
        ranking[loser_name] = new_ratings[0][0]
        ranking[winner_name] = new_ratings[1][0]
        
        temp = {key: round(ranking[key].ordinal(), 3) for key in ranking.keys()} # alpha=200/ranking[key].sigma, target=1000 for ordinal if ELO like values
        ranking_update.append(temp)

    ranking_in_time = pd.concat([pd.Series(match) for match in ranking_update], axis=1)
    ranking_in_time = ranking_in_time.T
    ranking_in_time.index = datetimes

    return ranking, ranking_in_time

def calculate_chasings(
    cfp: str | Path | dict, 
    overwrite: bool = False,
    save_data: bool = True,
    ) -> pd.DataFrame:
    """Calculates chasing events per pair of mice for each phase

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
    
    Returns:
        MultiIndex DataFrame of chasings per phase every animal vs every animal. Column chases the row
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='chasings'
    
    chasings = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(chasings, pd.DataFrame):
        return chasings
    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    
    cages = [val for val in set(cfg['antenna_combinations'].values()) if 'cage' in val]
    tunnels = [val for val in set(cfg['antenna_combinations'].values()) if 'cage' not in val]
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    animals = cfg['animal_ids']

    mouse_pairs = list(combinations(animals, 2))
    matches = []
    dfs = []
    
    print('Calculating chasings...')
    for animal1, animal2 in tqdm(mouse_pairs):
        animal_pair_df = df[df.animal_id.isin([animal1, animal2])].reset_index(drop=True)
        chasing_position = animal_pair_df[
            (animal_pair_df.position == animal_pair_df.position.shift(1)) 
            & animal_pair_df.position.isin(tunnels)
        ]
        
        chased = animal_pair_df.loc[chasing_position.index - 1].reset_index(drop=True)
        chasing = animal_pair_df.loc[chasing_position.index - 2].reset_index(drop=True)
        
        # Chaser comes from cage, chased leaves the tunnel
        pos_condition = chasing.position.isin(cages) & chased.position.isin(tunnels)
        chasing_pos_filt = chasing[pos_condition].reset_index(drop=True)
        chased_pos_filt = chased[pos_condition].reset_index(drop=True)

        # Ensures that the chased one was the first to exit the tube
        chased_mouse = chased_pos_filt.loc[chased_pos_filt.animal_id != chasing_pos_filt.animal_id]
        chasing_mouse = chasing_pos_filt.loc[chasing_pos_filt.animal_id != chased_pos_filt.animal_id]

        # Add filtering by duration of the event
        chasing_len = (chased_mouse.datetime - chasing_mouse.datetime).dt.total_seconds()
        chasing_len_condition = (chasing_len < 1.2) & (chasing_len > 0.1)
        
        filtered_chased = chased_mouse[chasing_len_condition].copy()
        filtered_chasing = chasing_mouse[chasing_len_condition].copy()
        
        matches.append(_get_chasing_matches(filtered_chasing, filtered_chased))
        
        filtered_chasing['chased'] = filtered_chased.loc[:, 'animal_id'].values

        dfs.append(filtered_chasing)
        
    chasings = (
        pd.concat(dfs)
        .groupby(by=['phase', 'day', 'phase_count', 'hour', 'chased', 'animal_id'], observed=False)['animal_id']
        .size()
        .unstack('animal_id')
    )
    chasings.columns.rename('chaser', inplace=True)
    chasings = chasings.apply(lambda col: col.mask(
        (col.name == col.index.get_level_values('chased')), np.nan
    ))
    
    if save_data:
        chasings.to_hdf(results_path, key='chasings', mode='a', format='table')
        
        matches_df = (
            pd.concat(matches).
                sort_values(by='datetime').
                reset_index(drop=True)
            )
        
        matches_df.to_hdf(results_path, key='match_df', mode='a', format='table')

    return chasings

def calculate_ranking(
    cfp: str | Path | dict, 
    overwrite: bool = False, 
    save_data: bool = True,
    ranking: dict | None = None,
    ) -> tuple[pd.DataFrame, dict]:
    """Calculate ranking using Plackett Luce algortihm. Each chasing event is a match
        TODO: handling of previous rankings
    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
        ranking: optionally, user can pass a dictionary from a different recording of same animals
                 to start ranking from a certain point instead of 0

    Returns:
        Series with ordinal of the rank calculated for each animal
    """    
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results' / 'results.h5'
    key='ranking_ordinal'
    
    ranking_ordinal = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(ranking_ordinal, pd.DataFrame):
        return ranking_ordinal
    
    animals = cfg['animal_ids']
    df = auxfun.load_ecohab_data(cfp, 'main_df')
    phases = cfg['phase'].keys()
    phase_count = df.phase_count.unique()
    days = df.day.unique()
            
    # Get the ranking and calculate ranking ordinal
    ranking, ranking_in_time = _rank_mice_openskill(cfg, animals, ranking)

    ranking_df = pd.DataFrame([(key, val.mu, val.sigma) for key, val in ranking.items()])
    ranking_df.columns = ['animal_id', 'mu', 'sigma']
    ranking_df['animal_id'] = ranking_df['animal_id'].astype('category')
    
    # Calculate ranking at the end of each phase
    phase_end_marks = df[df.datetime.isin(ranking_in_time.index)].sort_values('datetime')
    phase_end_marks = (
        phase_end_marks
        .loc[:, ['datetime', 'phase', 'day', 'phase_count']]
        .groupby(['phase', 'day', 'phase_count'], observed=True)
        .max()
        .dropna()
    )

    ranking_in_time = ranking_in_time[~ranking_in_time.index.duplicated(keep='last')] # handle possible duplicate indices
    ranking_ordinal = pd.DataFrame(index=phase_end_marks.index, columns=ranking_in_time.columns, dtype=float)

    for phase, day, count in product(phases, days, phase_count):
        try:
            datetime = phase_end_marks.loc[(phase, day, count)].iloc[0]
            ranking_ordinal.loc[(phase, day, count), :] = ranking_in_time.loc[datetime, :]
        except KeyError: # Account for one phase happening less times
            pass
    
    if save_data:
        ranking_ordinal.to_hdf(results_path, key='ranking_ordinal', mode='a', format='table')
        ranking_in_time.to_hdf(results_path, key='ranking_in_time', mode='a', format='table')
        ranking_df.to_hdf(results_path, key='ranking', mode='a', format='table')
    
    return ranking_ordinal