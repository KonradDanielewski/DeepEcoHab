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
    show_plot: bool,
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
            fig.write_json(project_location / "plots" / "fig_source" / f"{plot_type}_per_position_{phase_type_name}.json")
        if show_plot:
            fig.show()
        
def _super_plot_together(
    project_location: Path, 
    animal_ids: list,
    df: pd.DataFrame,
    plot_type: Literal["time_together", "pairwise_encounters"],
    cmap: str,
    show_cell_vals: bool,
    save_plot: bool,
    show_plot: bool,
    ):
    """Auxfun does the plotting for per cage heatmaps
    """    
    plot_data = df.reset_index()
    
    for phase_type in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
            
        if plot_type == "time_together":
            title = f"<b>Time spent together: <u>{phase_type_name} phase</u></b>"
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
            fig.layout.annotations[i]['text'] = f"<u><b>Cage {facet_col_n+1}</u></b>"
            
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
            fig.write_json(project_location / "plots" / "fig_source" / f"{plot_type}_{phase_type_name}.json")
        if show_plot:
            fig.show()

def plot_ranking_in_time(
    cfp: str,
    cmap: str = "Pastel",
    save_plot: bool = True,
    show_plot: bool = True,
    ) -> go.Figure:
    """

    Args:
        cfp: path to project config file
        cmap: Color map for line plot. Defaults to "Pastel".
        save_plot: toggle whether to save the plot. Defaults to True.
        show_plot: toggle whether to show the plot. Defaults to True.
    """    
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animals = cfg["animal_ids"]
    colors = px.colors.qualitative.__dict__[cmap]

    ranking_in_time = auxfun.load_ecohab_data(cfp, "ranking_in_time")
    main_df = auxfun.load_ecohab_data(cfp, "main_df")

    plot_df = auxfun_plots.prep_ranking_in_time_df(main_df, ranking_in_time)

    # Make fig
    fig = go.Figure()

    for i, animal in enumerate(animals):
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df[animal], name=animal, marker=dict(color=colors[i]))
        )

    fig.update_layout(
        title="<b>Social dominance ranking in time</b>",
        xaxis=dict(
            rangeslider=dict(visible=True),
            type="date",
            title="<b>Time</b>"
        ),
        yaxis=dict(title="<b>Ranking</b>"),
        legend=dict(title="<b>Animal IDs</b>"),
        width=1000,
        height=600,
    )
    
    if save_plot:
        fig.write_html(project_location / "plots" / "Ranking_change_in_time.html")
        fig.write_json(project_location / "plots" / "fig_source" / "Ranking_change_in_time.json")
    if show_plot:
        fig.show()

def plot_network_graph(
    cfp: str,
    node_size_multiplier: int | float = 0.05,
    edge_width_multiplier: int | float = 0.05,
    cmap: str = "bluered",
    save_plot: bool = True,
    show_plot: bool = True,
):
    """
    Plot network graph of social interactions with interactive node highlighting.

    Args:
        cfp: Path to project config file.
        node_size_multiplier: Node size multiplier. Defaults to 0.05.
        edge_width_multiplier: Edge width multiplier. Defaults to 0.05.
        cmap: Color map for nodes and edges. Defaults to "bluered". The colorbar corresponds to node values.
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    chasing_data = auxfun.load_ecohab_data(cfp, "chasings")
    ranking_ordinal = auxfun.load_ecohab_data(cfp, "ranking_ordinal")

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
            node_trace = auxfun_plots.create_node_trace(G, pos, __ranking, node_size_multiplier, cmap)
            edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_width_multiplier, node_size_multiplier, cmap)
            
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
            fig.write_json(project_location / "plots" / "fig_source" / f"time_per_position_{phase_type_name}.json")
        if show_plot:
            fig.show()

def plot_cage_position_time(
        cfp: str, 
        cmap: str = "Pastel", 
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot simple bar plot of time spent in each cage.

    Args:
        cfp: Path to project config file.
        cmap: Color map for bar plot. Defaults to "Pastel".
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    time_per_position = auxfun.load_ecohab_data(cfp, "time_per_position")
    
    _super_plot_per_position(
        project_location,
        time_per_position,
        "time",
        cmap,
        save_plot,
        show_plot,
    )
            
def plot_cage_position_visits(
        cfp: str,
        cmap: str = "Pastel", 
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot simple bar plot of visits spent in each cage.

    Args:
        cfp: Path to project config file.
        cmap: Color map for bar plot. Defaults to "Pastel".
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    visits_per_position = auxfun.load_ecohab_data(cfp, "visits_per_position")
    
    _super_plot_per_position(
        project_location, 
        visits_per_position, 
        "visits", 
        cmap, 
        save_plot,
        show_plot,
    )

def plot_time_together(
        cfp: str, 
        cmap: str = "OrRd",
        show_cell_vals: bool = False,  
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    time_together = auxfun.load_ecohab_data(cfp, "time_together")
    
    _super_plot_together(
        project_location,
        animal_ids,
        time_together,
        "time_together",
        cmap,
        show_cell_vals,
        save_plot,
        show_plot,
    )
    
def plot_pairwise_encounters(
        cfp: str, 
        cmap: str = "OrRd",
        show_cell_vals: bool = False,  
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    pairwise_encounters = auxfun.load_ecohab_data(cfp, "pairwise_encounters")
    
    _super_plot_together(
        project_location,
        animal_ids,
        pairwise_encounters,
        "pairwise_encounters",
        cmap,
        show_cell_vals,
        save_plot,
        show_plot
    )
    
def _super_plot_heatmap(
    project_location: str | Path, 
    animal_ids: list[str], 
    df: pd.DataFrame, 
    plot_type: str, 
    cmap: str, 
    show_cell_vals: bool,
    save_plot: bool,
    show_plot: bool,
    ):
    """Auxfun plots chasings and incohort sociablity heatmaps
    """ 
    plot_data = df.reset_index()
    
    for phase_type in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
        
        if plot_type == "incohort_sociability":
            title = f"<b>In-cohort sociability: <u>{phase_type_name} phase</u></b>"
            min_range = df.min().min()
            max_range = df.max().max()
            z_label = "%{z}"
        
        elif plot_type == "chasings":
            title = f"<b>Number of chasings: <u>{phase_type_name} phase</u></b>"
            min_range = int(df.min().min())
            max_range = int(df.max().max())
            z_label = "Number: %{z}"
        
        _data = plot_data[plot_data['phase']==phase_type].copy()
        n_phases = len(_data['phase_count'].unique())
        
        heatmap_data = (
            _data
            .drop(columns=["phase", "phase_count", "animal_ids"])
            .values
            .reshape(n_phases, len(animal_ids), len(animal_ids))
            .round(3)
        )

        fig = px.imshow(
            heatmap_data,
            animation_frame=0,
            x=animal_ids,
            y=animal_ids,
            color_continuous_scale=cmap,  
            text_auto=show_cell_vals,
            range_color=[min_range, max_range]
        )
        
        fig["layout"].pop("updatemenus")
        fig = fig.update_layout(
                            sliders=[{"currentvalue": {"prefix": "Phase="}}],
                            height=800,
                            width=800,
                            plot_bgcolor='white',
                            title=dict(text=title),
                        )
            
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
            fig.write_json(project_location / "plots" / "fig_source" / f"{plot_type}_{phase_type_name}.json")
        if show_plot:
            fig.show()
        
def plot_incohort_sociability(
        cfp: str, 
        cmap: str="OrRd", 
        show_cell_vals: bool = False,  
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    incohort_sociability = auxfun.load_ecohab_data(cfp, "incohort_sociability")
    
    _super_plot_heatmap(
        project_location, 
        animal_ids, 
        incohort_sociability, 
        "incohort_sociability",
        cmap,
        show_cell_vals,
        save_plot,
        show_plot,
    )
            
def plot_chasings(
        cfp: str, 
        cmap: str="OrRd", 
        show_cell_vals: bool = False,  
        save_plot: bool = True,
        show_plot: bool = True,
    ):
    """Plot heatmap of time spent together.

    Args:
        cfp: Path to project config file.
        cmap: Color map for heatmap. Defaults to "OrRd".
        show_cell_vals: toggles whether to show value text in the heatmap cell. Defaults to False.
        save_plot: toggles whether to save the plot. Defaults to True.
        show_plot: toggles whether to show the plot. Defaults to True.
    """
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    animal_ids = cfg["animal_ids"]
    
    chasings = auxfun.load_ecohab_data(cfp, "chasings")
    
    _super_plot_heatmap(
        project_location, 
        animal_ids, 
        chasings, 
        "chasings",
        cmap,
        show_cell_vals,
        save_plot,
        show_plot,
    )
            
# TODO: consider relevance of this plot, should we keep it, and if so in what form (per phase> full summary?)
#
# def social_dominance_evaluation(
#     cfp: str,
#     chasings: pd.DataFrame,
#     ranking_ordinal: pd.Series,
#     save_plot: bool = True,
#     show_plot: bool = True,
#     ):
#     """
#     Args:
#         cfp: path to project config file
#         chasings: chasings matrix created with calculate_chasings
#         ranking_ordinal: ranking created during chasings calculation
#         save_plot: toggle whether to save the plot. Defaults to True.
#         show_plot: toggle whether to show the plot. Defaults to True.
#     """    
#     cfg = auxfun.read_config(cfp)
#     fig = make_subplots(
#         rows=2, cols=2,
#         specs=[[{"type": "bar"}, {"type": "bar"}],
#                [{"type": "bar"}, {"type": "bar"}]],
#         subplot_titles=["Ranking", "Number of chasings", "Win/Loss-Rate", "Number of times being chased"],
#     )

#     chases = chasings.sum()
#     chased = chasings.sum(axis=1)
#     proportion = ((chases - chased) / chases) * 100


#     fig.add_trace(go.Bar(x=ranking_ordinal.index.to_list(), y=ranking_ordinal.values, name="Ranking"),
#                 row=1, col=1,
#                 )
#     fig.add_trace(go.Bar(x=chases.index.to_list(), y=chases.values, name="Number of chasings"),
#                 row=1, col=2,
#                 )
#     fig.add_trace(go.Bar(x=chased.index.to_list(), y=chased.values, name="Number of times being chased"),
#                 row=2, col=2,
#                 )
#     fig.add_trace(go.Bar(x=proportion.index.to_list(), y=proportion.values, name="Proportion chases vs being chased"),
#                 row=2, col=1,
#                 )

#     fig.update_layout(
#         width=1000, 
#         height=600, 
#         title_text="Social dominance evaluation", 
#         showlegend=False,
#     )
#     if save_plot:
#         save_path = Path(cfg["project_location"]) / "plots"
#         fig.write_html(save_path / "social_dominance_evaluation.html")
#         # fig.write_image(save_path / "social_dominance_evaluation.svg")
#     if show_plot:
#         fig.show()
    