from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import toml


def graph_distances(graph):
    """Auxfun to get distance from the center fro the network graph
    """    
    distances = [np.linalg.norm(graph[animal] - [0,0]) for animal in graph.keys()]
    d_min = np.min(distances)
    d_max = np.max(distances)
    normalized_distances = (distances - d_min) / (d_max - d_min)
    inverted_distances = 1 - normalized_distances
    scaled_distances = inverted_distances * (1 / np.max(inverted_distances))
    distances = pd.Series({key: val for key, val in zip(graph.keys(), scaled_distances)})

    return distances

def weigh_ranking(cfp: str, graph: dict, ranking_ordinal: pd.Series, chasings: pd.DataFrame, plot: bool = True, save_plot: bool = False) -> pd.Series:
    """_summary_

    Args:
        cfp: _description_
        graph: _description_
        ranking: _description_
        chasings: _description_
        plot: _description_. Defaults to True.
        save_plot: _description_. Defaults to False.

    Returns:
        _description_
    """    
    cfg = toml.load(cfp)
    plot_location = Path(cfg["project_location"]) / "plots"
    
    distances = graph_distances(graph)

    normalized_ranking = ranking_ordinal.copy()
    normalized_ranking.loc[:] = (ranking_ordinal.values - ranking_ordinal.min()) / (ranking_ordinal.max() - ranking_ordinal.min())

    normalized_chasings = chasings.sum()
    normalized_chasings.loc[:] = (normalized_chasings - normalized_chasings.min()) / (normalized_chasings.max() - normalized_chasings.min())

    data_prep = pd.DataFrame({"distance": distances, "ranking": normalized_ranking, "chasings": normalized_chasings})
    data_prep["final_ranking"] = np.average(data_prep, axis=1, weights=[0.4, 0.4, 0.2])
    data_prep = data_prep.sort_values("final_ranking", ascending=False)
    

    # NOTE: Move this part to the summary plot. In workflow summary plot should be the last one, after ranking in time and network
    if plot:
        fig = px.bar(data_prep["final_ranking"], width=800, height=500, showlegend=False)
        fig.update_yaxes(title="Weighted rank")
        if save_plot:
            fig.write_html(plot_location / r"weighted_ranking.html")
        fig.show()

    return data_prep.final_ranking