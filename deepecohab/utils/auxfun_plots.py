import pandas as pd
import networkx as nx
import plotly.graph_objects as go


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

def create_node_trace(cmap: str, graph: nx.DiGraph, pos: dict, ranking_ordinal: pd.Series, node_size_multiplier: float | int) -> go.Scatter:
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
