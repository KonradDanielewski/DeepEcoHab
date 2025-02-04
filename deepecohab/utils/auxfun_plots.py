import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import plotly.express as px


def create_edges_trace(G: nx.Graph, pos: dict, width_multiplier: float | int, node_size_multiplier: float | int) -> list:
    """Auxfun to create edges trace with color mapping based on edge width."""
    edge_trace = []
    
    # Get all edge widths to create a color scale
    edge_widths = [G.edges[edge]['weight'] * width_multiplier for edge in G.edges()]
    
    # Create a color scale based on edge widths
    color_scale = px.colors.sequential.Bluered
    
    # Normalize edge widths to the range [0, 1] for color mapping
    max_width = max(edge_widths)
    min_width = min(edge_widths)
    normalized_widths = [(width - min_width) / (max_width - min_width) for width in edge_widths]
    
    for i, edge in enumerate(G.edges()):
        x0, y0 = pos[edge[0]]  # Start point (source node)
        x1, y1 = pos[edge[1]]  # End point (target node)
        edge_width = edge_widths[i]
        
        # Calculate the direction vector from (x0, y0) to (x1, y1)
        dx = x1 - x0
        dy = y1 - y0
        
        # Calculate the length of the edge
        length = (dx**2 + dy**2)**0.5
        
        # Calculate the offset to shorten the line (e.g., by 10% of the node size)
        offset = 0.08 * node_size_multiplier  
        
        # Calculate new end point (x1_new, y1_new) by moving back along the line
        if length > 0:  # Avoid division by zero
            x1_new = x1 - (dx / length) * offset
            y1_new = y1 - (dy / length) * offset
        else:
            x1_new, y1_new = x1, y1
        
        # Map the normalized width to a color in the color scale
        color_index = int(normalized_widths[i] * (len(color_scale) - 1))
        line_color = color_scale[color_index]
        
        edge_trace.append(go.Scatter(
            x=[x0, x1_new, None],  
            y=[y0, y1_new, None],
            line=dict(
                width=edge_width,
                color=line_color,
            ),
            hoverinfo='none',
            mode="lines+markers",
            marker=dict(size=edge_width * 4, symbol="arrow", angleref="previous"),
            opacity=0.5
        ))
    
    return edge_trace

def create_node_trace(G: nx.DiGraph, pos: dict, cmap: str,  ranking_ordinal: pd.Series, node_size_multiplier: float | int) -> go.Scatter:
    """Auxfun to create node trace
    """
    node_trace = go.Scatter(
        x=[],
        y=[],
        text=[],
        hovertext=[],
        hoverinfo='text',
        mode='markers+text',
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
    ranking_score_list = []
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['text'] += (node,)
        ranking_score = round(ranking_ordinal[node], 3)
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
    graph_data = chasing_data.reset_index()\
        .melt(id_vars="index", value_name="weight")\
        .dropna()\
        .rename(columns={"index": "source", "variable": "target"})
    return graph_data
