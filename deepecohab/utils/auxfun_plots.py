import json
import webbrowser
from dataclasses import dataclass, field
from typing import (
    Any, 
    Callable, 
    Dict, 
    Literal,
)

import networkx as nx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import polars as pl


@dataclass(frozen=True)
class PlotConfig:
    store: dict
    days_range: list[int]
    phase_type: list[str]
    agg_switch: Literal['sum', 'mean']
    position_switch: Literal['visits', 'time']
    pairwise_switch: Literal['time_together', 'pairwise_encounters']
    animals: list[str]
    colors: list[str]
    cages: list[str]

class PlotRegistry:
    def __init__(self):
        self._registry: Dict[str, Callable[[PlotConfig], Any]] = {}

    def register(self, name: str):
        """Decorator to register a new plot type."""
        def wrapper(func: Callable[[PlotConfig], Any]):
            self._registry[name] = func
            return func
        return wrapper

    def get_plot(self, name: str, config: PlotConfig):
        plotter = self._registry.get(name)
        if not plotter:
            return {}
        return plotter(config)

def create_edges_trace(G: nx.Graph, pos: dict, cmap: str = "Viridis") -> list:
    """Auxfun to create edges trace with color mapping based on edge width"""
    edge_trace = []

    edge_widths = [G.edges[edge]["chasings"] if G.edges[edge]["chasings"] is not None else 0 for edge in G.edges()]
    # Normalize edge widths to the range [0, 1] for color mapping
    max_width = max(edge_widths)
    min_width = min(edge_widths)
    if max_width == 0 and min_width == 0:
        normalized_widths = [0 for _ in edge_widths]
    else:
        normalized_widths = [
            (width - min_width) / (max_width - min_width) for width in edge_widths
        ]

    colorscale = px.colors.sample_colorscale(cmap, normalized_widths)

    for i, edge in enumerate(G.edges()):
        source_x, source_y = pos[edge[0]]
        target_x, target_y = pos[edge[1]]
        edge_width = (
            normalized_widths[i] * 10 # connection width scaler for visivbility
        )  

        edge_trace.append(
            go.Scatter(
                x=[source_x, target_x, None],
                y=[source_y, target_y, None],
                line=dict(
                    width=edge_width,
                    color=colorscale[i],
                ),
                hoverinfo="none",
                mode="lines+markers",
                marker=dict(size=edge_width, symbol="arrow", angleref="previous"),
                opacity=0.5,
                showlegend=False,
            )
        )

    return edge_trace


def create_node_trace(
    pos: dict,
    colors: list,
    animals: list[str],
) -> go.Scatter:
    """Auxfun to create node trace"""
    node_trace = go.Scatter(
        x=[],
        y=[],
        text=[],
        hovertext=[],
        hoverinfo="text",
        mode="markers+text",
        textposition="top center",
        showlegend=False,
        marker=dict(
            showscale=False,
            colorscale=colors,
            size=[],
            color=[],
        ),
    )

    ranking_score_list = []
    for node in animals:
        x, y, score = pos[node]
        node_trace["x"] += (x,)
        node_trace["y"] += (y,)
        node_trace["text"] += ("<b>" + node + "</b>",)
        ranking_score = (
            score if score > 0 else 0.1
        )
        ranking_score_list.append(ranking_score)
        node_trace["hovertext"] += (f"Mouse ID: {node}<br>Ranking: {ranking_score}",)

    node_trace["marker"]["color"] = colors
    node_trace["marker"]["size"] = [rank for rank in ranking_score_list]
    return node_trace


def color_sampling(values: list[str], cmap: str = "Phase") -> list[str]:
    """Samples colors from a colormap for given values."""
    x = np.linspace(0, 1, len(values))
    colors = px.colors.sample_colorscale(cmap, x)

    return colors

def prep_polar_df(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
) -> pl.DataFrame:
    columns = ['time_alone', 'n_chasing', 'n_chased', 'activity', 'time_together', 'pairwise_encounters']

    time_alone = (
        store['time_alone'].lazy()
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by('animal_id')
        .agg(
            pl.sum('time_alone'), 
        )
    )

    n_chasing = (
        store['chasings_df'].lazy()
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by('chaser')
        .agg(
            pl.sum('chasings').alias('n_chasing'), 
        )
        .rename({'chaser': 'animal_id'})
    )

    n_chased = (
        store['chasings_df'].lazy()
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by('chased')
        .agg(
            pl.sum('chasings').alias('n_chased'), 
        )
        .rename({'chased': 'animal_id'})
    )

    activity = (
        store['activity_df'].lazy()
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by('animal_id')
        .agg(
            pl.sum('visits_to_position').alias('activity'), 
        )
    )

    pairwise_meetings = (
        pl.concat(
            [
                store['pairwise_meetings'].lazy()
                .filter(
                    pl.col('phase').is_in(phase_type),
                    pl.col('day').is_between(days_range[0], days_range[-1])
                )
                .select('animal_id', 'time_together', 'pairwise_encounters'),
                store['pairwise_meetings'].lazy()
                .filter(
                    pl.col('phase').is_in(phase_type),
                    pl.col('day').is_between(days_range[0], days_range[-1])
                )
                .select(pl.col('animal_id_2').alias('animal_id'), 'time_together', 'pairwise_encounters'),
            ], how='align',
        ).group_by('animal_id')
        .agg(
            pl.sum('time_together'),
            pl.sum('pairwise_encounters'),
        )
        .sort('animal_id')
    )

    df = pl.concat([time_alone, n_chasing, n_chased, activity, pairwise_meetings], how='align')

    df = (
        df.with_columns(
            (pl.col(columns) - pl.col(columns).mean()) / pl.col(columns).std()
        )
    ).unpivot(index='animal_id', variable_name='metric').collect()

    return df


def set_default_theme():
    """Sets default plotly theme. TODO: to be updated as we go."""
    dark_dash_template = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e6f0"),
            xaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
            yaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
    )

    # register & set as default
    pio.templates["dash_dark"] = dark_dash_template
    pio.templates.default = "dash_dark"


def open_browser():
    """Opens browser with dashboard."""
    webbrowser.open_new("http://127.0.0.1:8050/")


def to_store_json(df: pl.DataFrame | None) -> dict | None:
    if not isinstance(df, pl.DataFrame):
        return None
    return json.dumps(df.to_dict(as_series=False), default=str)
