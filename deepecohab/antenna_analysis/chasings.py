import pickle
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
        "loser": chased_mouse.animal_id, 
        "winner": chasing_mouse.animal_id,
        "datetime": chasing_mouse.datetime,
    })
    return matches

def _combine_matches(matches: list[pd.DataFrame]) -> tuple[list, pd.Series]:
    """Auxfun to combine all the chasing events into one data structure
    """    
    matches_df = (
        pd.concat(matches).
            sort_values(by="datetime").
            reset_index(drop=True)
        )
    datetimes = matches_df.datetime

    matches = list(matches_df.drop("datetime", axis=1).itertuples(index=False, name=None))
    return matches, datetimes

def _rank_mice_openskill(
    matches: list[pd.DataFrame], 
    animal_ids: list[str], 
    ranking: dict | None = None,
    ) -> tuple[dict, pd.DataFrame, pd.Series]:
    """Rank mice using PlackettLuce algorithm from openskill. More info: https://arxiv.org/pdf/2401.05451

    Args:
        matches: list of all matches structured
        animal_ids: list of animal IDs
        ranking: dictionary that contains ranking of animals - if provided the ranking will start from this state. Defaults to None.

    Returns:
        ranking: dictionary of the ranking per animal
        ranking_in_time: pd.DataFrame of the ranking where each row is another match, sorted in time
        datetimes: pd.Series of all matches datetimes for sorting or axis setting purposes
    """    
    model = PlackettLuce(limit_sigma=True, balance=True)
    match_list, datetimes = _combine_matches(matches)
    
    ranking = {}
    
    for player in animal_ids:
        ranking[player] = model.rating()
    
    ranking_update = []
    for loser_name, winner_name in match_list:
        new_ratings = model.rate([[ranking[loser_name]], [ranking[winner_name]]], ranks=[1,0])
        
        ranking[loser_name] = new_ratings[0][0]
        ranking[winner_name] = new_ratings[1][0]
        
        temp = {key: round(ranking[key].ordinal(), 3) for key in ranking.keys()}
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
    cfg = auxfun.check_cfp_validity(cfp)
    data_path = Path(cfg["results_path"])
    key="chasings"
    
    chasings = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(chasings, pd.DataFrame):
        return chasings
    
    df = auxfun.load_ecohab_data(cfg, key="main_df")
    
    experiment_name = cfg["experiment_name"]
    positions = list(set(cfg["antenna_combinations"].values()))
    tunnel_combinations = [comb for comb in positions if "cage" not in comb]
    cage_combinations = [comb for comb in positions if "cage" in comb]
    data_path = Path(cfg["results_path"])
    phases = list(cfg["phase"].keys())
    phase_N = df.phase_count.unique()
    animals = cfg["animal_ids"]

    idx = auxfun._create_phase_multiindex(cfg, animals=True)

    chasings = pd.DataFrame(columns=animals, index=idx, dtype=float).sort_index()

    mouse_pairs = list(combinations(animals, 2))
    matches = []
    iterator = list(product(phases, phase_N, mouse_pairs))
    
    print("Calculating chasings...")
    for phase, N, (mouse1, mouse2) in tqdm(iterator): # TODO: Think about parallelization - output a df then concat a list of dfs
        # Calculates time spent in the tube together
        temp = df.query("phase == @phase and phase_count == @N and (animal_id == @mouse1 or animal_id == @mouse2)").sort_values("datetime").reset_index(drop=True)

        condition1 = np.sort(np.concatenate([temp.loc[temp.position_keys.diff() == 0].index, 
                                            temp.loc[temp.position_keys.diff() == 0].index - 1]))
        temp2 = temp.loc[condition1]
        condition2 = np.sort(np.concatenate([temp2.loc[temp2.position.isin(tunnel_combinations)].index, 
                                            temp2.loc[temp2.position.isin(tunnel_combinations)].index[::2] - 1]))
        # Ensure no negative indices
        condition2 = condition2[condition2 >= 0]  
        temp2 = temp.loc[condition2].reset_index(drop=True)

        chasing = temp2[::3].reset_index(drop=True)
        chased = temp2[1::3].reset_index(drop=True)
        
        # Chasing one has to be in the tunnel
        if len(chasing.loc[chasing.position.isin(tunnel_combinations)]) > 0:
            indices_to_drop = chasing.loc[chasing.position.isin(tunnel_combinations)].index
            chasing = chasing.drop(indices_to_drop).reset_index(drop=True)
            chased = chased.drop(indices_to_drop).reset_index(drop=True)
        # Chased one has to be in the cage
        if len(chased.loc[chased.position.isin(cage_combinations)]) > 0:
            indices_to_drop = chasing.loc[chasing.position.isin(cage_combinations)].index
            chasing = chasing.drop(indices_to_drop).reset_index(drop=True)
            chased = chased.drop(indices_to_drop).reset_index(drop=True)

        # Ensures that the chased one was the first to exit the tube
        chased_mouse = chased.loc[chased.animal_id != chasing.animal_id]
        chasing_mouse = chasing.loc[chasing.animal_id != chased.animal_id]

        matches.append(_get_chasing_matches(chasing_mouse, chased_mouse))

        chase_times1 = (
            chased_mouse.query("animal_id == @mouse1").datetime.reset_index(drop=True) - 
            chasing_mouse.query("animal_id == @mouse2").datetime.reset_index(drop=True)).dt.total_seconds()
        chase_times2 = (
            chased_mouse.query("animal_id == @mouse2").datetime.reset_index(drop=True) - 
            chasing_mouse.query("animal_id == @mouse1").datetime.reset_index(drop=True)).dt.total_seconds()
        
        chasings.loc[(phase, N, mouse1), mouse2] = len(chase_times1[(chase_times1 < 1) & (chase_times1 > 0.1)])
        chasings.loc[(phase, N, mouse2), mouse1] = len(chase_times2[(chase_times2 < 1) & (chase_times2 > 0.1)])
    
    # reindex most chasing to least
    new_index = chasings.sum(axis=0).sort_values(ascending=False).index
    chasings = chasings.reindex(new_index, axis=1).reindex(new_index, level=2, axis=0)
    
    chasings = auxfun._drop_empty_slices(chasings)
    
    if save_data:
        chasings.to_hdf(data_path, key="chasings", mode="a", format="table")
        
        ranking_data = Path(cfg["project_location"]) / "results" / (experiment_name + "_match_data.pickle")
        with open(str(ranking_data), "wb") as outfile: 
            pickle.dump(matches, outfile)

    return chasings

def calculate_ranking(
    cfp: str | Path | dict, 
    overwrite: bool = False, 
    save_data: bool = True,
    ranking: dict | None = None,
    ) -> pd.Series:
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
    cfg = auxfun.check_cfp_validity(cfp)
    data_path = Path(cfg["results_path"])
    key="ranking_ordinal"
    
    ranking_ordinal = None if overwrite else auxfun.check_save_data(data_path, key)
    
    if isinstance(ranking_ordinal, pd.DataFrame):
        return ranking_ordinal
    
    experiment_name = cfg["experiment_name"]
    animals = cfg["animal_ids"]
    df = auxfun.load_ecohab_data(cfp, "main_df")
    phases = cfg["phase"].keys()
    phase_count = df.phase_count.unique()
    
    match_data = Path(cfg["project_location"]) / "results" / (experiment_name + "_match_data.pickle")
    matches = pd.read_pickle(match_data)
            
    # Get the ranking and calculate ranking ordinal
    ranking, ranking_in_time = _rank_mice_openskill(matches, animals, ranking)
    
    # Calculate ranking at the end of each phase
    phase_end_marks = df[df.datetime.isin(ranking_in_time.index)].sort_values("datetime")
    phase_end_marks = (
        phase_end_marks
        .loc[:, ["datetime", "phase", "phase_count"]]
        .groupby(["phase", "phase_count"], observed=False)
        .max()
    ).dropna()

    ranking_ordinal = pd.DataFrame(index=phase_end_marks.index, columns=ranking_in_time.columns, dtype=float)

    for phase, count in product(phases, phase_count):
        try:
            datetime = phase_end_marks.loc[(phase,  count)].iloc[0]
            ranking_ordinal.loc[(phase, count), :] = ranking_in_time.loc[datetime, :]
        except KeyError: # Account for one phase happening less times
            pass
    
    if save_data:
        ranking_data = Path(cfg["project_location"]) / "results" / (experiment_name + "_ranking_data.pickle")
        pickle_file = {"ranking": ranking}
        with open(str(ranking_data), "wb") as outfile: 
            pickle.dump(pickle_file, outfile)
            
        ranking_ordinal.to_hdf(data_path, key="ranking_ordinal", mode="a", format="table")
        ranking_in_time.to_hdf(data_path, key="ranking_in_time", mode="a", format="table")
    
    return ranking_ordinal