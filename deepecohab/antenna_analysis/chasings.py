from itertools import (
    combinations,
    product,
)
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import polars.selectors as cs

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

def _combine_matches(cfg: dict) -> tuple[list, pl.Series]:
    """Auxfun to combine all the chasing events into one data structure
    """    
    match_lf = auxfun.load_ecohab_data(cfg, 'match_df', verbose=False)
    match_df = match_lf.collect()

    datetimes = match_df['datetime']

    match_df  = match_df.drop('datetime')

    matches = [tuple(row) for row in match_df.iter_rows()]

    return matches, datetimes

def _rank_mice_openskill(
    cfg: dict,
    animal_ids: list[str], 
    ranking: dict | None = None,
    ) -> tuple[dict, pl.DataFrame]:
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
    
    ranking_in_time = pl.LazyFrame(ranking_update)

    ranking_in_time = ranking_in_time.with_columns(
        datetimes.alias('datetime')
    )

    return ranking, ranking_in_time

def calculate_chasings(
    cfp: str | Path | dict, 
    overwrite: bool = False,
    save_data: bool = True,
    ) -> pl.LazyFrame:
    """Calculates chasing events per pair of mice for each phase

    Args:
        cfp: path to project config file.
        save_data: toogles whether to save data.
        overwrite: toggles whether to overwrite the data.
    
    Returns:
        MultiIndex DataFrame of chasings per phase every animal vs every animal. Column chases the row
    """
    cfg = auxfun.read_config(cfp)
    results_path = Path(cfg['project_location']) / 'results'
    key='chasings'
    
    chasings = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(chasings, pl.LazyFrame):
        return chasings
    
    df = auxfun.load_ecohab_data(cfg, key='main_df')
    
    cages = cfg['cages']
    tunnels = cfg['tunnels']

    lf_filtered = (
        df
        .select(['datetime', 'animal_id', 'position', 'phase', 'day', 'hour', 'phase_count'])
        .filter(
            (pl.col('position') != pl.col('position').shift(1).over('animal_id'))
        )
    ).sort(['animal_id', 'datetime'])

    chased = lf_filtered.filter(
        pl.col('position').is_in(tunnels),
    )

    chasing = lf_filtered.with_columns(
        pl.col('datetime').shift(-1).over('animal_id').alias('exit'),
        pl.col('position').shift(-1).over('animal_id').alias('next_position'),
    ).drop(
        ['phase', 'day', 'hour', 'phase_count']
    ).with_columns(
        pl.all().name.suffix("_chasing")
    ).drop(
        ~cs.contains("_chasing")
    )

    chasing = chasing.with_columns(
        (pl.col('datetime_chasing') + pl.duration(seconds=1, milliseconds=200)).alias('dt_upper'),
        (pl.col('datetime_chasing') + pl.duration(milliseconds=100)).alias('dt_lower')
    ).filter(
        pl.col('position_chasing').is_in(cages)
    ).drop(
        'position_chasing'
    )

    chasings_list = chased.join_where(
        chasing,
        (pl.col('position') == pl.col("next_position_chasing")),
        (pl.col("animal_id") != pl.col("animal_id_chasing")),
        (pl.col("datetime") > pl.col("datetime_chasing")),
        (pl.col("datetime") < (pl.col("dt_upper"))),
        (pl.col("datetime") > (pl.col("dt_lower"))),
        (pl.col('exit_chasing') > pl.col('datetime'))
    ).drop(
        ['dt_upper', 'dt_lower', 'next_position_chasing', 'exit_chasing']
    ).sort(
        'datetime'
    ).unique(
        subset = 'datetime',
        keep = 'first'
    )

    matches = chasings_list.select(
        'animal_id', 'animal_id_chasing', 'datetime_chasing'
    ).rename(
        {
            'animal_id' : 'loser', 
            'animal_id_chasing' : 'winner', 
            'datetime_chasing' : 'datetime'
        }
    )

    chasings = chasings_list.group_by(
        ['phase', 'day', 'phase_count', 'hour', 'animal_id_chasing', 'animal_id']
    ).len(
        name='chasings'
    ).rename(
        {
            'animal_id' : 'chased',
            'animal_id_chasing' : 'chaser'
        }
    )
   
    
    if save_data:
        chasings.sink_parquet(results_path / f'{key}.parquet', compression='lz4')
        matches.sink_parquet(results_path / 'match_df.parquet', compression='lz4')


    return chasings

def calculate_ranking(
    cfp: str | Path | dict, 
    overwrite: bool = False, 
    save_data: bool = True,
    ranking: dict | None = None,
    ) -> pl.LazyFrame:
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
    results_path = Path(cfg['project_location']) / 'results'
    key='ranking_ordinal'
    
    ranking_ordinal = None if overwrite else auxfun.load_ecohab_data(cfp, key, verbose=False)
    
    if isinstance(ranking_ordinal, pl.LazyFrame):
        return ranking_ordinal
    
    animals = cfg['animal_ids']
    df = auxfun.load_ecohab_data(cfp, 'main_df')
    phases = cfg['phase'].keys()
    # phase_count = df.phase_count.unique()
    # days = df.day.unique()
            
    # Get the ranking and calculate ranking ordinal
    ranking, ranking_in_time = _rank_mice_openskill(cfg, animals, ranking)

    ranking_df = pl.LazyFrame(
        {
            'animal_id': list(ranking.keys()),
            'mu': [v.mu for v in ranking.values()],
            'sigma': [v.sigma for v in ranking.values()],
        }
    ).with_columns(pl.col('animal_id').cast(pl.Enum(animals)))
    
    ranking_in_time = (
        ranking_in_time
        .group_by('datetime', maintain_order=True)
        .tail(1)
    )

    phase_end_marks = (
        df
        .filter(pl.col('datetime').is_in(ranking_in_time.select('datetime')))
        .group_by(['phase', 'day', 'phase_count'])
        .agg(pl.col('datetime').max().alias('datetime'))
    )

    ranking_ordinal = (
        phase_end_marks.join(
            ranking_in_time, 
            on='datetime', 
            how='left'
        )
    )
    
    if save_data:
        ranking_ordinal.sink_parquet(results_path / 'ranking_ordinal.parquet', compression='lz4')
        ranking_in_time.sink_parquet(results_path / 'ranking_in_time.parquet', compression='lz4')
        ranking_df.sink_parquet(results_path / 'ranking.parquet', compression='lz4')

    
    return ranking_ordinal