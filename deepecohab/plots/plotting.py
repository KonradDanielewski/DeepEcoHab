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
        node_size_multiplier: Node size multiplier. Defaults to 1.
        edge_width_multiplier: Edge width multiplier. Defaults to 1.
        cmap: Color map for nodes. Defaults to "inferno".
        save_plot: Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])

    # Prepare data
    data = auxfun_plots.prep_network_df(chasing_data)
    ranking_data = auxfun_plots.prep_ranking(ranking_ordinal)
    
    # Create phase aware network graph
    for phase_type in data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
        _data = data[data['phase'] == phase_type]
        _ranking = ranking_data[ranking_data['phase'] == phase_type]
        frames = []
        for phase in _data['phase_count'].unique():        
            __data = _data[_data['phase_count'] == phase].drop(columns=['phase', 'phase_count'])
            G = nx.from_pandas_edgelist(__data, create_using=nx.DiGraph, edge_attr="chasings")
            pos = nx.spring_layout(G, k=None, iterations=500, seed=42)
            edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_width_multiplier, node_size_multiplier, cmap)
            __ranking = _ranking[_ranking['phase_count'] == phase].drop(columns=['phase', 'phase_count']).set_index('mouse_id')['ranking']
            if len(__ranking) == 0:
                continue
            node_trace = auxfun_plots.create_node_trace(G, pos, __ranking, node_size_multiplier, cmap)
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
                    title=dict(text=f"<b>Time spent together [s] during {phase_type_name} phase</b>", x=0.01, y=0.95)
                )
        fig.update_xaxes(showticklabels=False)
        fig.update_yaxes(showticklabels=False)
        if save_plot:
            fig.write_html(project_location / "plots" / f"time_per_position_{phase_type_name}.html")
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
    for phase in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase else "light"
        data = plot_data[plot_data['phase']==phase].drop("phase", axis=1).sort_values(["phase_count", "animal_id"])
        max_y = data["Time[s]"].max() + 1000
        
        fig = px.bar(
            data,
            x="animal_id",
            y="Time[s]",
            color="position",
            animation_frame='phase_count',
            barmode='group',
            title=f"<b>Time[s] spent in each position during {phase_type_name} phase</b>",
            range_y=[0, max_y],
            width=800,
            height=500,
        )
        fig["layout"].pop("updatemenus")
    
        fig.update_layout(sliders=[{"currentvalue": {"prefix": "Phase="}}])
        
        fig.update_xaxes(title_text="<b>Animal ID</b>")
        fig.update_yaxes(title_text="<b>Time spent [s]</b>")
        
        if save_plot:
            fig.write_html(project_location / "plots" / f"time_per_position_{phase_type_name}.html")
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
    for phase in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase else "light"
        data = plot_data[plot_data['phase']==phase].drop("phase", axis=1).sort_values(["phase_count", "animal_id"])
        max_y = data["Visits[n]"].max() + 100
        
        fig = px.bar(
            data,
            x="animal_id",
            y="Visits[n]",
            color="position",
            animation_frame='phase_count',
            barmode='group',
            title=f"<b>Visits[n] spent in each position during {phase_type_name} phase</b>",
            range_y=[0, max_y],
            width=800,
            height=500,
        )
        fig["layout"].pop("updatemenus")
    
        fig.update_layout(sliders=[{"currentvalue": {"prefix": "Phase="}}])
        
        fig.update_xaxes(title_text="<b>Animal ID</b>")
        fig.update_yaxes(title_text="<b>Visits to compartmens [n]</b>")
        
        if save_plot:
            fig.write_html(project_location / "plots" / f"visits_per_position_{phase_type_name}.html")
        fig.show()

def plot_time_together(cfp: str, time_together: pd.DataFrame, save_plot: bool = True):
    """Plot heatmap of time spent together.

    Args:
        cfp (str): Path to project config file.
        time_together (pd.DataFrame): dataframe generated by deepecohab.calculate_time_together.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_time_together_df(time_together)
    
    for phase_type in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
        _data = plot_data[plot_data['phase']==phase_type].drop(columns=["phase"])
        min_val = 0
        max = int(_data.iloc[:,2:].max().max() * 1.1)

        frames = []
        for phase in _data["phase_count"].unique():
            heatmap_data = _data[_data["phase_count"] == phase].drop(columns=["phase_count"]).set_index("animal_ids")
            heatmap = go.Heatmap(
                    z=heatmap_data.values,
                    x=heatmap_data.columns,
                    y=heatmap_data.index,
                    text=heatmap_data.round(2).fillna("").values,
                    texttemplate="%{text}",
                    hoverinfo="skip",
                    zmin=min_val,
                    zmax=max,            
                )
            frame = go.Frame(
                data=heatmap,
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
            yaxis={"title": 'Animal ID', "tickangle": 0, 'side': 'left'},
            xaxis={"title": 'Animal ID', "tickangle": 20, 'side': 'top'},
            title_x=0.5,
        )
        fig.update_layout(title=dict(text=f"Time spent together [s] during {phase_type_name} phase", x=0.01, y=0.99))
        if save_plot:
            fig.write_html(project_location / "plots" / f"time_together_{phase_type_name}.html")
        fig.show()
        
def plot_incohort_soc(cfp: str, time_together: pd.DataFrame, save_plot: bool = True):
    """Plot heatmap of time spent together.

    Args:
        cfp (str): Path to project config file.
        time_together (pd.DataFrame): dataframe generated by deepecohab.calculate_time_together.
        save_plot (bool, optional): Save plot. Defaults to True.
    """
    # Read config file
    cfg = auxfun.read_config(cfp)
    project_location = Path(cfg["project_location"])
    
    plot_data = auxfun_plots.prep_incohort_soc_df(time_together)
    
    for phase_type in plot_data['phase'].unique():
        phase_type_name = "dark" if "dark" in phase_type else "light"
        _data = plot_data[plot_data['phase']==phase_type].drop(columns=["phase"])
        min_val = _data.iloc[:,2:].min().min() - 0.01
        max = _data.iloc[:,2:].max().max() + 0.01

        frames = []
        for phase in _data["phase_count"].unique():
            heatmap_data = _data[_data["phase_count"] == phase].drop(columns=["phase_count"]).set_index("animal_ids")
            heatmap = go.Heatmap(
                    z=heatmap_data.values,
                    x=heatmap_data.columns,
                    y=heatmap_data.index,
                    text=heatmap_data.round(2).fillna("").values,
                    texttemplate="%{text}",
                    hoverinfo="skip",
                    zmin=min_val,
                    zmax=max,            
                )
            frame = go.Frame(
                data=heatmap,
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
            yaxis={"title": 'Animal ID', "tickangle": 0, 'side': 'left'},
            xaxis={"title": 'Animal ID', "tickangle": 20, 'side': 'top'},
            title_x=0.5,
        )
        fig.update_layout(title=dict(text=f"In-cohort sociability {phase_type_name} phase", x=0.01, y=0.99))
        if save_plot:
            fig.write_html(project_location / "plots" / f"in_cohort_sociability_{phase_type_name}.html")
        fig.show()