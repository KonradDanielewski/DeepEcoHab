from pathlib import Path
from typing import Literal

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

from plotly.subplots import make_subplots

from deepecohab.utils import auxfun
from deepecohab.utils import auxfun_plots

def _super_plot_per_position(
    project_location: Path,
    df: pd.DataFrame, 
    plot_type: Literal["time", "visits"], 
    cmap: str,
    save_plot: bool,
    ):
    """Auxfun does the plotting for barplots per position
    """
    
    plot_data = auxfun_plots.prep_per_position_df(df, plot_type)
    for phase in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase else "light"
        data = plot_data[plot_data['phase']==phase].drop("phase", axis=1).sort_values(["phase_count", "animal_id"])
        
        if plot_type == "time":
            title = f"<b>Time spent in each position: <u>{phase_type_name} phase</u></b>"
            y_title = "<b>Time spent [s]</b>"
            y = "Time[s]"
            y_range_add = 1000
            
        elif plot_type == "visits":
            title = f"<b>Visits to each position: <u>{phase_type_name} phase</u></b>"
            y_title = "<b>Number of visits</b>"
            y = "Visits[#]"
            y_range_add = 50
        
        max_y = data[y].max() + y_range_add
        
        fig = px.bar(
            data,
            x="animal_id",
            y=y,
            color="position",
            color_discrete_sequence=px.colors.qualitative.__dict__[cmap],
            animation_frame='phase_count',
            barmode='group',
            title=title,
            range_y=[0, max_y],
            width=800,
            height=500,
        )
        fig["layout"].pop("updatemenus")

        fig.update_layout(sliders=[{"currentvalue": {"prefix": "Phase="}}])
        
        fig.update_xaxes(title_text="<b>Animal ID</b>")
        fig.update_yaxes(title_text=y_title)
        
        if save_plot:
            fig.write_html(project_location / "plots" / f"{plot_type}_per_position_{phase_type_name}.html")
        fig.show()
        
def _super_plot_together(
    project_location: Path, 
    animal_ids: list,
    df: pd.DataFrame,
    plot_type: Literal["time_together", "pairwise_encounters"],
    cmap: str,
    show_cell_vals: bool,
    save_plot: bool,
    ):
    """Auxfun does the plotting for per cage heatmaps
    """    
    plot_data = df.reset_index()
    
    for phase_type in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
            
        if plot_type == "time_together":
            title = f"<b>Time spent in each position: <u>{phase_type_name} phase</u></b>"
            z_label = "Time [s]: %{z}"
        
        elif plot_type == "pairwise_encounters":
            title = f"<b>Number of pairwise encounters: <u>{phase_type_name} phase</u></b>"
            z_label = "Number: %{z}"
        
        _data = plot_data[plot_data['phase']==phase_type].copy()

        n_phases = len(_data['phase_count'].unique())
        n_cages = len(_data['cages'].unique())
        
        heatmap_data = (
            _data
            .drop(columns=["phase", "phase_count", "animal_ids", "cages"])
            .values
            .reshape(n_phases, n_cages, len(animal_ids), len(animal_ids))
        )

        fig = px.imshow(
            heatmap_data,
            animation_frame=0,
            x=animal_ids,
            y=animal_ids,
            color_continuous_scale=cmap,  
            text_auto=show_cell_vals,
            facet_col=1,
            facet_col_wrap=2,
            )
        
        fig["layout"].pop("updatemenus")
        fig = fig.update_layout(
                            sliders=[{"currentvalue": {"prefix": "Phase="}}],
                            height=800,
                            width=800,
                            plot_bgcolor='white',
                            title=dict(text=title),
                        )
        for i in range(n_cages):
            facet_col_n = int(fig.layout.annotations[i]['text'][-1])
            fig.layout.annotations[i]['text'] = f"Cage {facet_col_n+1}"
            
        fig.update_xaxes(showspikes=True, spikemode="across")
        fig.update_yaxes(showspikes=True, spikemode="across")
        fig.update_traces(
            hovertemplate="<br>".join([
                "X: %{x}",
                "Y: %{y}",
                z_label,
            ])
        )
        if save_plot:
            fig.write_html(project_location / "plots" / f"{plot_type}_{phase_type_name}.html")
        fig.show()

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
    node_size_multiplier: int | float = 0.05,
    edge_width_multiplier: int | float = 0.05,
    node_cmap: str = "bluered",
    edge_cmap: str = "bluered",
    save_plot: bool = True,
):
    """
    Plot network graph of social interactions with interactive node highlighting.

    Args:
        cfp: Path to project config file.
        chasing_data: Pandas DataFrame with graph_data calculated by calculate_chasings function.
        ranking_ordinal: Pandas Series with ordinal ranking.
        node_size_multiplier: Node size multiplier. Defaults to 1.
        edge_width_multiplier: Edge width multiplier. Defaults to 1.
        node_cmap: Color map for nodes. Defaults to "bluered".
        edge_cmap: Color map for edges. Defaults to "bluered".
        save_plot: Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])

    # Prepare data
    chasing_data = auxfun_plots.prep_network_df(chasing_data)
    ranking_data = auxfun_plots.prep_ranking(ranking_ordinal)

    # Create phase aware network graph
    for phase_type in chasing_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
        _data = chasing_data[chasing_data['phase'] == phase_type]
        _ranking = ranking_data[ranking_data['phase'] == phase_type]
        frames = []
        for phase in _data['phase_count'].unique():        
            __data = _data[_data['phase_count'] == phase].drop(columns=['phase', 'phase_count'])
            G = nx.from_pandas_edgelist(__data, create_using=nx.DiGraph, edge_attr="chasings")
            pos = nx.spring_layout(G, k=None, iterations=500, seed=42, weight="chasings")
            __ranking = _ranking[_ranking['phase_count'] == phase].drop(columns=['phase', 'phase_count']).set_index('mouse_id')['ranking']
            if len(__ranking) == 0:
                continue
            node_trace = auxfun_plots.create_node_trace(G, pos, __ranking, node_size_multiplier, node_cmap)
            edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_width_multiplier, node_size_multiplier, edge_cmap)
            
            plot = go.Figure(
                    data=edge_trace + [node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=0, l=0, r=0, t=40),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    )
                )
            frame = go.Frame(
                    data=plot.data,
                    name=f"Phase {phase}",
                )
            frames.append(frame)
            
        fig = go.Figure(data=frames[0].data, frames=frames).update_layout(
                    sliders=[{"steps": [{"args": [[f.name],{"frame": {"duration": 0, "redraw": True},
                                                            "mode": "immediate",},],
                                        "label": f.name, "method": "animate",}
                                        for f in frames],}],
                    height=800,
                    width=800,
                    plot_bgcolor='white',
                    title=dict(text=f"<b>Social structure network graph: <u>{phase_type_name} phase</u></b>", x=0.01, y=0.95),
                )
        fig.update_xaxes(showticklabels=False)
        fig.update_yaxes(showticklabels=False)
        if save_plot:
            fig.write_html(project_location / "plots" / f"time_per_position_{phase_type_name}.html")
        fig.show()

def plot_cage_position_time(
        cfp: str, 
        time_per_position: pd.DataFrame, 
        cmap: str = "Set1", 
        save_plot: bool = True,
    ):
    """Plot simple bar plot of time spent in each cage.

    Args:
        cfp: Path to project config file.
        cmap: Color map for bar plot. Defaults to "Set1".
        time_per_position: dataframe generated by deepecohab.calculate_time_spent_per_position.
        save_plot: Save plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    _super_plot_per_position(
        project_location,
        time_per_position,
        "time",
        cmap,
        save_plot,
    )
            
def plot_cage_position_visits(
        cfp: str, 
        visits_per_position: pd.DataFrame, 
        cmap: str = "Set1", 
        save_plot: bool = True,
    ):
    """Plot simple bar plot of visits spent in each cage.

    Args:
        cfp: Path to project config file.
        visits_per_position: dataframe generated by deepecohab.calculate_visits_spent_per_position.
        cmap: Color map for bar plot. Defaults to "Set1".
        save_plot: Save plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    _super_plot_per_position(
        project_location, 
        visits_per_position, 
        "visits", 
        cmap, 
        save_plot,
    )

def plot_time_together(
        cfp: str, 
        time_together: pd.DataFrame, 
        cmap: str = "OrRd",
        show_cell_vals: bool = False,  
        save_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        time_together: dataframe generated by deepecohab.calculate_time_together.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: Save plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    _super_plot_together(
        project_location,
        animal_ids,
        time_together,
        "time_together",
        cmap,
        show_cell_vals,
        save_plot,
    )
    
def plot_pairwise_encounters(
        cfp: str, 
        pairwise_encounters: pd.DataFrame, 
        cmap: str = "OrRd",
        show_cell_vals: bool = False,  
        save_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        pairwise_encounters: dataframe generated by deepecohab.pairwise_encounters.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: Save plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    _super_plot_together(
        project_location,
        animal_ids,
        pairwise_encounters,
        "pairwise_encounters",
        cmap,
        show_cell_vals,
        save_plot,
    )
        
def plot_incohort_sociability(
        cfp: str, 
        incohort_soc: pd.DataFrame, 
        cmap: str="OrRd", 
        show_cell_vals: bool = False,  
        save_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        incohort_soc: dataframe generated by deepecohab.calculate_in_cohort_sociability.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = incohort_soc.reset_index()
    
    for phase_type in plot_data['phase'].unique():
        
        phase_type_name = "dark" if "dark" in phase_type else "light"
        
        _data = plot_data[plot_data['phase']==phase_type].copy()
        
        animals_ids = _data['animal_ids'].unique() 
        n_phases = len(_data['phase_count'].unique())
        
        heatmap_data = (
            _data
            .drop(columns=["phase", "phase_count", "animal_ids"])
            .values
            .reshape(n_phases, len(animals_ids), len(animals_ids))
            .round(3)
        )

        fig = px.imshow(
            heatmap_data,
            animation_frame=0,
            x=animals_ids,
            y=animals_ids,
            color_continuous_scale=cmap,  
            text_auto=show_cell_vals,
        )
        
        fig["layout"].pop("updatemenus")
        fig = fig.update_layout(
                            sliders=[{"currentvalue": {"prefix": "Phase="}}],
                            height=800,
                            width=800,
                            plot_bgcolor='white',
                            title=dict(text=f"<b>In-cohort sociability: <u>{phase_type_name} phase</u></b>"),
                        )
            
        fig.update_xaxes(showspikes=True, spikemode="across")
        fig.update_yaxes(showspikes=True, spikemode="across")
        fig.update_traces(
            hovertemplate="<br>".join([
                "X: %{x}",
                "Y: %{y}",
                "In-cohort sociability: %{z}",
            ])
        )
        if save_plot:
            fig.write_html(project_location / "plots" / f"in_cohort_sociablity_{phase_type_name}.html")
        fig.show()
    