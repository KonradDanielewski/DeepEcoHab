from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from plotly.subplots import make_subplots

from deepecohab.utils.auxfun import read_config, create_edges_trace, create_node_trace



def _plot_chasings_matrix(chasings: pd.DataFrame, project_location: Path, save_plot: bool, show_plot: bool):
    """Auxfun for plotting the chasings matrix
    """            
    fig = px.imshow(chasings, text_auto=True, width=700, height=700)
    fig.update_xaxes(side="top")
    
    if save_plot:
        save_path = project_location / "plots"
        fig.write_html(save_path / "chasings_matrix.html")
        # fig.write_image(save_path / "chasings_matrix.svg")
    if show_plot:
        fig.show()

def _plot_weighted_ranking(data_prep: pd.DataFrame, project_location: Path, save_plot: bool, show_plot: bool):
    """Auxfun to plot a barplot with weighted ranking
    """            
    fig = px.bar(data_prep["final_ranking"], width=800, height=500)
    fig.update_yaxes(title="Weighted rank")
    
    if save_plot:
        plot_location = project_location / "plots"
        fig.write_html(plot_location / r"weighted_ranking.html")
         # fig.write_image(save_path / "weighted_ranking.svg")
    if show_plot:
        fig.show()

def social_dominance_evaluation(
    cfp: str,
    chasings: pd.DataFrame,
    ranking_ordinal: pd.Series,
    save_plot: bool = True,
    show_plot: bool = True,
    ) -> go.Figure:
    """NOTE: Add the weighted ranking here?

    Args:
        cfp: path to project config file
        chasings: chasings matrix created with calculate_chasings
        ranking_ordinal: ranking created during chasings calculation
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to show the plot. Defaults to True.
    """    
    cfg = read_config(cfp)
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"type": "bar"}, {"type": "bar"}],
               [{"type": "bar"}, {"type": "bar"}]],
        subplot_titles=["Ranking", "Number of chasings", "Win/Loss-Rate", "Number of times being chased"],
    )

    chases = chasings.sum()
    chased = chasings.sum(axis=1)
    proportion = ((chases - chased) / chases) * 100


    fig.add_trace(go.Bar(x=ranking_ordinal.index.to_list(), y=ranking_ordinal.values, name="Ranking"),
                row=1, col=1,
                )
    fig.add_trace(go.Bar(x=chases.index.to_list(), y=chases.values, name="Number of chasings"),
                row=1, col=2,
                )
    fig.add_trace(go.Bar(x=chased.index.to_list(), y=chased.values, name="Number of times being chased"),
                row=2, col=2,
                )
    fig.add_trace(go.Bar(x=proportion.index.to_list(), y=proportion.values, name="Proportion chases vs being chased"),
                row=2, col=1,
                )

    fig.update_layout(
        width=1000, 
        height=600, 
        title_text="Social dominance evaluation", 
        showlegend=False,
    )
    if save_plot:
        save_path = Path(cfg["project_location"]) / "plots"
        fig.write_html(save_path / "social_dominance_evaluation.html")
        # fig.write_image(save_path / "social_dominance_evaluation.svg")
    if show_plot:
        fig.show()
    
    return fig

def plot_ranking_in_time(
    cfp: str,
    ranking_in_time: pd.DataFrame,
    save_plot: bool = True,
    show_plot: bool = True,
    ) -> go.Figure:
    """_summary_

    Args:
        cfp: path to project config file
        ranking_in_time: DataFrame of ranking changes througout the experiment
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to show the plot. Defaults to True.
    """    
    cfg = read_config(cfp)
    
    fig = px.line(
        ranking_in_time,
        width=1000,
        height=600,
        color_discrete_sequence=px.colors.qualitative.Dark24, 
        title="Social dominance ranking in time",
    )
    
    fig.update_layout(
        yaxis_title="Ordinal",
        xaxis_title="Chasing events",
    )
    
    if save_plot:
        save_path = Path(cfg["project_location"]) / "plots"
        fig.write_html(save_path / "Ranking_change_in_time.html")
        # fig.write_image(save_path / "Ranking_change_in_time.svg")
    if show_plot:
        fig.show()
    
    return fig

def plot_network_graph(
    cfp: str,
    data: pd.DataFrame,
    ranking_ordinal: pd.Series,
    title: str = "Title",
    node_size_multiplier: int | float = 0.05,
    edge_width_multiplier: int | float = 0.05,
    cmap: str = "viridis_r",
    save_plot: bool = True,
) -> nx.DiGraph:
    """
    Plot network graph of social interactions with interactive node highlighting.

    Args:
        cfp: Path to project config file.
        data: Pandas DataFrame with graph_data calculated by calculate_chasings function.
        ranking_ordinal: Pandas Series with ordinal ranking.
        title: Title of the graph. Defaults to "Title".
        node_size_multiplier: Node size multiplier. Defaults to 1.
        edge_width_multiplier: Edge width multiplier. Defaults to 1.
        cmap: Color map for nodes. Defaults to "inferno".
        save_plot: Save plot. Defaults to True.

    Returns:
        Dictionary containing the graph, figure, and traces.
    """
    # Read config file
    cfg = read_config(cfp)
    project_location = Path(cfg["project_location"])

    # Create graph and layout
    G = nx.from_pandas_edgelist(data, create_using=nx.DiGraph, edge_attr="weight")
    pos = nx.spring_layout(G, k=None, iterations=500, seed=42)

    # Create edge traces
    edge_trace = create_edges_trace(G, pos, edge_width_multiplier)

    # Create node traces
    node_trace = create_node_trace(cmap)

    # Add positions and text to node_trace
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['hovertext'] += (
            f"Mouse ID: {node}<br>Ranking: {round(ranking_ordinal[node], 3)}",
            )

    # Scale node size and color
    node_trace['marker']['color'] = list(ranking_ordinal)
    node_trace['marker']['size'] = list(ranking_ordinal * node_size_multiplier)

    # Create figure
    fig = go.Figure(
        data=edge_trace + [node_trace],
        layout=go.Layout(
            title=title,
            showlegend=False,
            hovermode='closest',
            margin=dict(b=0, l=0, r=0, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            width=800,
            height=600,
            plot_bgcolor='white',
        )
    )

    # Save plot if required
    if save_plot:
        fig.write_html(project_location / "plots" / "network_graph.html")

    # Show plot
    fig.show()

    return G