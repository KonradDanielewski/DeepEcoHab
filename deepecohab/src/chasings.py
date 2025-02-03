import pickle
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import toml

from openskill.models import PlackettLuce

from deepecohab.plots.plotting import _plot_chasings_matrix
from deepecohab.utils.auxfun import read_config

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

    return ranking, ranking_in_time, datetimes

def calculate_chasings(
    cfp: str, 
    df: pd.DataFrame, 
    plot: bool = True, 
    save_plot: bool = True,
    show_plot: bool = True,
    ranking: dict | None = None,
) -> tuple[pd.DataFrame, dict, pd.Series, pd.DataFrame, pd.Series]:
    """Calculates chasing events per pair of mice

    Args:
        cfp: path to project config file
        df: EcoHab data structure
        plot: toogle whether to plot results as a heatmap
        save_plot: toggle whether to save the plot in the project
        ranking: users can provide the inintal ranking - can be useful for instance if second recording of same animals is being done, 
                 or animals from different cohorts have been mixed. NOTE: needs a function to combine rankings between recordings.

    Returns:
        Matrix of pairwise chasings as a pd.DataFrame and a DataFrame with a ranking calculated using TrueSkill with each chasing event being a separate match
    """
    cfg = read_config(cfp)
    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]
    antenna_combinations = list(cfg["antenna_combinations"])
    tunnel_combinations = [comb for comb in antenna_combinations if "cage" not in comb]
    cage_combinations = [comb for comb in antenna_combinations if "cage" in comb]

    data_path = project_location / "data" / f"{experiment_name}_data.h5"

    chasings = pd.DataFrame(np.nan, columns=df.animal_id.unique(), index=df.animal_id.unique())

    animals = sorted(cfg["animal_ids"])
    mouse_pairs = list(combinations(animals, 2))
    matches = []

    for mouse1, mouse2 in mouse_pairs:
        # Calculates time spent in the tube together
        temp = df.query("(animal_id == @mouse1 or animal_id == @mouse2)").sort_values("datetime").reset_index(drop=True)

        condition1 = np.sort(np.concatenate([temp.loc[temp.position_keys.diff() == 0].index, 
                                             temp.loc[temp.position_keys.diff() == 0].index - 1]))
        temp2 = temp.loc[condition1]
        condition2 = np.sort(np.concatenate([temp2.loc[temp2.position.isin(tunnel_combinations)].index, 
                                             temp2.loc[temp2.position.isin(tunnel_combinations)].index[::2] - 1]))  
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

        chase_times1 = (chased_mouse.query("animal_id == @mouse1").datetime.reset_index(drop=True) - chasing_mouse.query("animal_id == @mouse2").datetime.reset_index(drop=True)).dt.total_seconds()
        chase_times2 = (chased_mouse.query("animal_id == @mouse2").datetime.reset_index(drop=True) - chasing_mouse.query("animal_id == @mouse1").datetime.reset_index(drop=True)).dt.total_seconds()
        
        chasings.loc[mouse1, mouse2] = len(chase_times1[(chase_times1 < 1) & (chase_times1 > 0.1)])
        chasings.loc[mouse2, mouse1] = len(chase_times2[(chase_times2 < 1) & (chase_times2 > 0.1)])

    # Get the ranking and calculate ranking ordinal
    ranking, ranking_in_time, datetimes = _rank_mice_openskill(matches, animals, ranking)
    ranking_ordinal = (
        pd.Series(
            {animal: ranking[animal].ordinal() for animal in ranking.keys()}, name="ordinal")
            .sort_values(ascending=False)
    )
    
    animal_order = ranking_ordinal.index
    # Reorder animals according to the ranking
    chasings = chasings.reindex(animal_order).reindex(animal_order, axis=1)
    
    data_save_path = project_location / "data" / (experiment_name + "_chase_rank.pickle")
    
    pickle_file = {
        "chasing_matrix": chasings,
        "ranking_raw": ranking,
        "ranking_ordinal": ranking_ordinal,
        "ranking_in_time": ranking_in_time,
        "datetimes": datetimes
    }
    
    with open(str(data_save_path), "wb") as outfile: 
        pickle.dump(pickle_file, outfile)

    # Remove from here eventually - should be called separately - data available in the dataset file
    if plot:
        _plot_chasings_matrix(chasings, project_location, save_plot, show_plot)

    chasings.to_hdf(data_path, key="chasings", format="table")
    ranking_ordinal.to_hdf(data_path, key="end_ranking", format="table")
    
    

    return chasings, ranking, ranking_ordinal, ranking_in_time, datetimes
