from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import colormaps
import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import toml

from plotly.subplots import make_subplots

# NOTE: Modify the internally created plots so that they all return the Figure object when run on their own (no longer internal use only) - perhaps a toogle switch?

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
    cfg = toml.load(cfp)
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
    cfg = toml.load(cfp)
    
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
    node_size_multiplier: int = 5,
    edge_width_multiplier: int = 5,
    cmap="inferno",
    save_plot=False,
    ) -> dict:
    """NOTE: The only plot not in plotly... Should be changed to lose matplotlib dependecy but it seems complicated to get similar quality and readability - for now a functional placeholder

    Args:
        cfp: path to project config file
        data: _description_
        ranking: _description_
        title: _description_. Defaults to "Title".
        node_size_multiplier: _description_. Defaults to 5.
        edge_width_multiplier: _description_. Defaults to 5.
        cmap: _description_. Defaults to "inferno".
        save_plot: _description_. Defaults to False.

    Returns:
        _description_
    """    
    cfg = toml.load(cfp)
    project_location = Path(cfg["project_location"])
    
    # Create graph
    G = nx.DiGraph()
    mice = ranking_ordinal.index  # Assuming first two columns are non-node identifiers
    G.add_nodes_from(mice)
    # Make edges
    mice_product = [(i, j) for i, j in list(product(mice, mice)) if i != j]

    for m1, m2 in mice_product:
        weight = data.loc[m1, m2]
        G.add_edge(m2, m1, weight=weight)

    # Edge specification
    edge_colors = [G[u][v]['weight'] for u, v in G.edges()]
    weights = edge_colors

    # Node specification
    pos = nx.spring_layout(G, k=None, iterations=500, seed=42)
    node_sizes = list(ranking_ordinal * node_size_multiplier) 
    node_colors = colormaps[cmap].resampled(len(mice)).colors
   
    # Draw network
    fig, ax = plt.subplots(figsize=(10, 10))
    nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=node_colors, edgecolors='black', ax=ax)
    edges = nx.draw_networkx_edges(G, pos, edgelist=G.edges(), width=[weight / max(weights) * edge_width_multiplier for weight in weights], edge_color=edge_colors, edge_cmap=plt.cm.viridis, alpha=0.7, ax=ax)
    nx.draw_networkx_labels(G, pos, font_size=10, font_color='black', font_weight='bold', ax=ax)
    
    # Create colorbar for edge weights using Coolwarm colormap
    viridis = plt.cm.ScalarMappable(cmap=plt.cm.viridis, norm=plt.Normalize(vmin=min(edge_colors), vmax=max(edge_colors)))
    viridis.set_array([])
    cbar_coolwarm = plt.colorbar(viridis, ax=ax, orientation='vertical', fraction=0.036, pad=0.04)
    cbar_coolwarm.set_label('Interaction Weight')


    plt.title(title, fontsize=16, fontweight='bold')
    plt.axis('off')
    plt.show()
    if save_plot:
        filename = project_location / "plots" / "network_plot.svg"
        fig.savefig(filename, dpi=300)

    return pos
