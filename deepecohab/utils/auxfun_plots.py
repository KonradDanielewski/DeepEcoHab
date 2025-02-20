import pandas as pd
import networkx as nx
import numpy as np
import plotly.graph_objects as go
from typing import Literal
from plotly.express.colors import sample_colorscale


def create_edges_trace(G: nx.Graph, pos: dict, width_multiplier: float | int, node_size_multiplier: float | int, cmap: str = "bluered") -> list:
    """Auxfun to create edges trace with color mapping based on edge width."""
    edge_trace = []
    
    # Get all edge widths to create a color scale
    edge_widths = [G.edges[edge]['chasings'] * width_multiplier for edge in G.edges()]
    
    # Normalize edge widths to the range [0, 1] for color mapping
    max_width = max(edge_widths)
    min_width = min(edge_widths)
    if max_width == 0 and min_width == 0:
        normalized_widths = [0 for _ in edge_widths]
    else:
        normalized_widths = [(width - min_width) / (max_width - min_width) for width in edge_widths]
    colorscale = sample_colorscale(cmap, normalized_widths)
    for i, edge in enumerate(G.edges()):
        source_x, source_y = pos[edge[0]]  # Start point (source node)
        target_x, target_y = pos[edge[1]]  # End point (target node)
        edge_width = edge_widths[i]
        
        # Calculate the direction vector from (source_x, source_y) to (target_x, target_y)
        dx = target_x - source_x
        dy = target_y - source_y
        
        # Calculate the length of the edge
        length = (dx**2 + dy**2)**0.5
        
        # Calculate the offset to shorten the line (e.g., by 10% of the node size)
        offset = 0.02 * node_size_multiplier  
        
        # Calculate new end point (target_x_new, target_y_new) by moving back along the line
        if length > 0:  # Avoid division by zero
            target_x_new = target_x - (dx / length) * offset
            target_y_new = target_y - (dy / length) * offset
        else:
            target_x_new, target_y_new = target_x, target_y
        
        # Map the normalized width to a color in the color scale
        # color_index = int(normalized_widths[i] * (len(color_scale) - 1))
        # line_color = color_scale[i]
        
        edge_trace.append(go.Scatter(
            x=[source_x, target_x_new, None],  
            y=[source_y, target_y_new, None],
            line=dict(
                width=edge_width,
                color=colorscale[i],
            ),
            hoverinfo='none',
            mode="lines+markers",
            marker=dict(size=edge_width * 4, symbol="arrow", angleref="previous"),
            opacity=0.5,
            showlegend=False,
        ))
    
    return edge_trace

def create_node_trace(G: nx.DiGraph, pos: dict, ranking_ordinal: pd.Series, node_size_multiplier: float | int, cmap: str = "Bluered") -> go.Scatter:
    """Auxfun to create node trace
    """
    node_trace = go.Scatter(
        x=[],
        y=[],
        text=[],
        hovertext=[],
        hoverinfo='text',
        mode='markers+text',
        textposition='top center',
        showlegend=False,
        marker=dict(
            showscale=True,
            colorscale=cmap,
            size=[], color=[],
            colorbar=dict(
                thickness=15,
                title='Ranking',
                xanchor='left',
                titleside='right',
            )
        )
    )
    
    # Add positions and text to node_trace
    ranking_score_list = []
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['text'] += ('<b>' + node + '</b>',)
        ranking_score = round(ranking_ordinal[node], 3) if ranking_ordinal[node] > 0 else 0.1
        ranking_score_list.append(ranking_score)
        node_trace['hovertext'] += (
            f"Mouse ID: {node}<br>Ranking: {ranking_score}",
            )
        
    # Scale node size and color
    node_trace['marker']['color'] = ranking_score_list
    node_trace['marker']['size'] = [rank * node_size_multiplier for rank in ranking_score_list]
    return node_trace

def prep_network_df(chasing_data: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare network data for plotting
    """
    graph_data = (
        chasing_data
        .melt(ignore_index=False, value_name="chasings", var_name="source")
        .dropna()
        .reset_index()
        .rename(columns={"animal_ids": "target"})
    )
    return graph_data

def prep_per_position_df(visits_per_position: pd.DataFrame, type: Literal["visits", "time"]) -> pd.DataFrame:
    """Auxfun to prepare visits_per_position data for plotting
    """
    if type == "visits":
        val_name = "Visits[#]"
    elif type == "time":
        val_name = "Time[s]"
    else:
        raise ValueError("Invalid type. Choose between 'visits' and 'time'.")
        
    visits_per_position_df = visits_per_position.melt(ignore_index=False, value_name=val_name, var_name="animal_id").reset_index()
    return visits_per_position_df

def prep_ranking(ranking_df: pd.DataFrame) -> pd.Series:
    """Auxfun to prepare ranking data for plotting
    """
    ranking = (
        ranking_df
        .melt(ignore_index=False, var_name="mouse_id", value_name="ranking")
        .reset_index()
        )
    return ranking