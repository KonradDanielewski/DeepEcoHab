from pathlib import Path

import numpy as np
import pandas as pd
import toml

from DeepEcoHab.deepecohab.plots.plotting import _plot_weighted_ranking


def _graph_distances(graph) -> pd.Series:
    """Auxfun to get distance from the center fro the network graph
    """    
    distances = [np.linalg.norm(graph[animal] - [0,0]) for animal in graph.keys()]
    inverted_distances = 1 - ((distances - np.min(distances)) / (np.max(distances) - np.min(distances)))
    
    scaled_distances = inverted_distances * (1 / np.max(inverted_distances))
    distances = pd.Series({key: val for key, val in zip(graph.keys(), scaled_distances)})

    return distances

def weigh_ranking(
    cfp: str, 
    graph: dict, 
    ranking_ordinal: pd.Series, 
    chasings: pd.DataFrame, 
    plot: bool = True, 
    save_plot: bool = True, 
    show_plot: bool = True,
) -> pd.Series:
    """Creates a weighted ranking based on multiple features of the social structure.

    Args:
        cfp: path to project config file
        graph: node location from the graph network
        ranking_ordinal: ranking created during chasings calculation
        chasings: chasings matrix created with calculate_chasings
        plot: toggle whether to create the plot. Defaults to True.
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to save the plot. Defaults to True.

    Returns:
        _description_
    """    
    cfg = toml.load(cfp)
    project_location = Path(cfg["project_location"])
    
    distances = _graph_distances(graph)

    normalized_ranking = ranking_ordinal.copy()
    normalized_ranking.loc[:] = (ranking_ordinal.values - ranking_ordinal.min()) / (ranking_ordinal.max() - ranking_ordinal.min())

    normalized_chasings = chasings.sum()
    normalized_chasings.loc[:] = (normalized_chasings - normalized_chasings.min()) / (normalized_chasings.max() - normalized_chasings.min())

    data_prep = pd.DataFrame({"distance": distances, "ranking": normalized_ranking, "chasings": normalized_chasings})
    data_prep["final_ranking"] = np.average(data_prep, axis=1, weights=[0.4, 0.4, 0.2])
    data_prep = data_prep.sort_values("final_ranking", ascending=False)
    

    # NOTE: Move this part to the summary plot. In workflow summary plot should be the last one, after ranking in time and network
    if plot:
        _plot_weighted_ranking(data_prep, project_location, save_plot, show_plot)

    return data_prep.final_ranking
