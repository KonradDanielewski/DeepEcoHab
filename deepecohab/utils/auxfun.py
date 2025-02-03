import os
from glob import glob
from pathlib import Path

import pandas as pd
import toml
import networkx as nx
import plotly.graph_objects as go
import numpy as np


def get_data_paths(data_path: str) -> list:
    """Auxfun to load all raw data paths
    """    
    data_files = glob(os.path.join(data_path, "COM*.txt"))
    if len(data_files) == 0:
        data_files = glob(os.path.join(data_path, "20*.txt"))
    return data_files

def load_ecohab_data(cfp: str, structure_type: str) -> pd.DataFrame:
    """Loads already analyzed data structure

    Args:
        cfp: config file path
        structure_type: accepts either 'chasings' to load the chasings matrix or 'ecohab' to load the general data structure

    Raises:
        ValueError: raised if unexpected value provided in structure_type
        FileNotFoundError: raised if the data file not found.

    Returns:
        returns desired data structure loaded from the file.
    """    
    cfg = read_config(cfp)
    project_location = Path(cfg["project_location"])
    experiment_name = cfg["experiment_name"]
    
    if structure_type == "chasings":
        suffix = "_chasings.h5"
    elif structure_type == "ecohab":
        suffix = "_data.h5"
    else:
        raise ValueError(f"'chasings' or 'ecohab' supported but {structure_type} provided! Please use one of the available structure types")
    
    data_path = project_location / "data" / (experiment_name + suffix)
    
    if data_path.is_file():
        df = pd.read_hdf(data_path)
    else:
        raise FileNotFoundError(f"{structure_type.capitalize()} data file not found in the specified location: {data_path}. Perhaps not analyzed yet!")
    
    return df

def read_config(cfp: str | Path) -> dict:
    """Auxfun reads the config and returns it as a dictionary
    """
    if isinstance(cfp, (str, Path)):
        cfg = toml.load(cfp)
    else:
        raise ValueError(f"Config path should be a str or a Path object. Type {type(cfp)} provided!")
    
    return cfg

def create_edges_trace(G: nx.Graph, pos: dict, width_multiplier: float) -> go.Scatter:
    """Auxfun to create edges trace 
    """
    # Note need to add curved lines and arrowheads
    edge_trace = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_width = G.edges[edge]['weight'] * width_multiplier
        edge_trace.append(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            line=dict(
                width=edge_width,
                color='#888',
            ),
            hoverinfo='none',
            mode="lines+markers",
            marker= dict(size=edge_width * 2, symbol= "arrow", angleref="previous"),
            opacity=0.5 
        ))
    return edge_trace

def create_node_trace(cmap: str, graph, pos, ranking_ordinal, node_size_multiplier) -> go.Scatter:
    """Auxfun to create node trace
    """
    node_trace = go.Scatter(
        x=[],
        y=[],
        text=[],
        hovertext=[],
        hoverinfo='text',
        mode='markers',
        marker=dict(
            showscale=True,
            colorscale=cmap,
            size=[], color=[],
            colorbar=dict(
                thickness=15,
                title='Ranking',
                xanchor='left',
                titleside='right'
            )
        )
    )
    
    # Add positions and text to node_trace
    for node in graph.nodes(): # should we add this part to the create_node_trace function?
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['hovertext'] += (
            f"Mouse ID: {node}<br>Ranking: {round(ranking_ordinal[node], 3)}",
            )
        
    # Scale node size and color
    node_trace['marker']['color'] = list(ranking_ordinal)
    node_trace['marker']['size'] = list(ranking_ordinal * node_size_multiplier)
    return node_trace
