from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from plotly.subplots import make_subplots

from deepecohab.utils import auxfun
from deepecohab.utils import auxfun_plots

def social_dominance_evaluation(
    cfp: str,
    chasings: pd.DataFrame,
    ranking_ordinal: pd.Series,
    save_plot: bool = True,
    show_plot: bool = True,
    ) -> go.Figure:
    """TODO: data should be read from file

    Args:
        cfp: path to project config file
        chasings: chasings matrix created with calculate_chasings
        ranking_ordinal: ranking created during chasings calculation
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to show the plot. Defaults to True.
    """    
    cfg = auxfun.read_config(cfp)
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
    """TODO: Make it better, x axis showing time, add loading from file

    Args:
        cfp: path to project config file
        ranking_in_time: DataFrame of ranking changes througout the experiment
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to show the plot. Defaults to True.
    """    
    cfg = auxfun.read_config(cfp)
    
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
    chasing_data: pd.DataFrame,
    ranking_ordinal: pd.Series,
    title: str = "Title",
    node_size_multiplier: int | float = 0.05,
    edge_width_multiplier: int | float = 0.05,
    cmap: str = "bluered",
    save_plot: bool = True,
):
    """
    Plot network graph of social interactions with interactive node highlighting.

    Args:
        cfp: Path to project config file.
        chasing_data: Pandas DataFrame with graph_data calculated by calculate_chasings function.
        ranking_ordinal: Pandas Series with ordinal ranking.
        title: Title of the graph. Defaults to "Title".
        node_size_multiplier: Node size multiplier. Defaults to 1.
        edge_width_multiplier: Edge width multiplier. Defaults to 1.
        cmap: Color map for nodes. Defaults to "inferno".
        save_plot: Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])

    # Create graph and layout
    data = auxfun_plots.prep_network_df(chasing_data)
    phases = data["phase_count"].unique()
    for phase in phases:
        data_phase = data[data["phase_count"] == phase]
        G = nx.from_pandas_edgelist(data_phase, create_using=nx.DiGraph, edge_attr="weight")
        pos = nx.spring_layout(G, k=None, iterations=500, seed=42)

        # Create edge traces
        edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_width_multiplier, node_size_multiplier)

        # Create node traces
        node_trace = auxfun_plots.create_node_trace(G, pos, cmap, ranking_ordinal, node_size_multiplier)

        # Create figure
        fig = go.Figure(
            data=edge_trace + [node_trace],
            layout=go.Layout(
                title=f"{title}_phase_{phase}",
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
            fig.write_html(project_location / "plots" / f"network_graph_phase_{phase}.html")

        # Show plot
        fig.show()

def plot_cage_position_time(cfp: str, time_per_position: pd.DataFrame, save_plot: bool = True):
    """Plot simplebar plot of time spent in each cage.

    Args:
        cfp (str): Path to project config file.
        time_per_position (pd.DataFrame): dataframe generated by deepecohab.calculate_time_spent_per_position.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
     # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_time_per_position_df(time_per_position)
    phases = plot_data['phase_count'].unique()
    
    for phase in phases:
        plot_df = plot_data[plot_data['phase_count']==phase]
        fig = px.bar(
            plot_df[plot_df['phase_count']==phase],
            x="animal_id",
            color="position",
            y="time",
            title=f"Time spent per position in dark phase {phase}",
            )
        if save_plot:
            fig.write_html(project_location / "plots" / f"time_spent_per_position_dark_{phase}.html")

        # Show plot
        fig.show()
        
def plot_cage_position_visits(cfp: str, visits_per_position: pd.DataFrame, save_plot: bool = True):
    """Plot simplebar plot of visits spent in each cage.

    Args:
        cfp (str): Path to project config file.
        visits_per_position (pd.DataFrame): dataframe generated by deepecohab.calculate_visits_spent_per_position.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
     # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_visits_per_position_df(visits_per_position)
    phases = plot_data['phase_count'].unique()
    
    for phase in phases:
        plot_df = plot_data[plot_data['phase_count']==phase]
        fig = px.bar(
            plot_df[plot_df['phase_count']==phase],
            x="animal_id",
            color="position",
            y="visits",
            title=f"Visits per position in dark phase {phase}",
            )
        if save_plot:
            fig.write_html(project_location / "plots" / f"visits_per_position_dark_{phase}.html")

        # Show plot
        fig.show()

def plot_time_together(cfp: str, time_together: pd.DataFrame, save_plot: bool = True):
    """Plot simplebar plot of time spent together.

    Args:
        cfp (str): Path to project config file.
        time_together (pd.DataFrame): dataframe generated by deepecohab.calculate_time_together.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_time_together_df(time_together)
    
    phases = plot_data['phase_count'].unique()
    
    for phase in phases:
        plot_df = plot_data[plot_data['phase_count']==phase]
        data = plot_df.pivot_table(values='time_together', index='animal_ids', columns='animal_2_ids', aggfunc='first')

        fig = px.imshow(data.values,
                        labels=dict(x="animal_1", y="animal_2", color="time spent together"),
                    y=data.index,
                    x=data.columns
                    )
        fig.update_xaxes(side="top")

        if save_plot:
            fig.write_html(project_location / "plots" / f"time_together_dark_{phase}.html")

        # Show plot
        fig.show()
        
def plot_incohort_soc(cfp: str, time_together: pd.DataFrame, save_plot: bool = True):
    """Plot simplebar plot of time spent together.

    Args:
        cfp (str): Path to project config file.
        time_together (pd.DataFrame): dataframe generated by deepecohab.calculate_time_together.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_incohort_soc_df(time_together)
    
    phases = plot_data['phase_count'].unique()
    
    for phase in phases:
        plot_df = plot_data[plot_data['phase_count']==phase]
        data = plot_df.pivot_table(values='incohort_soc', index='animal_ids', columns='animal_2_ids', aggfunc='first')

        fig = px.imshow(data.values,
                        labels=dict(x="animal_1", y="animal_2", color="time spent together"),
                    y=data.index,
                    x=data.columns
                    )
        fig.update_xaxes(side="top")

        if save_plot:
            fig.write_html(project_location / "plots" / f"time_together_dark_{phase}.html")

        # Show plot
        fig.show()