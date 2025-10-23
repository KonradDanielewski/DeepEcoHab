from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from deepecohab.utils import auxfun
from deepecohab.utils import auxfun_plots

def plot_sum_line_per_hour(
    df: pd.DataFrame,
    animals: list[str], 
    colors: list[tuple[int, int, int]], 
    input_type: Literal['activity', 'chasings'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots line graph for activity or chasings."""
    
    match input_type:
        case 'activity':
            plot_df = auxfun_plots.prep_activity_overtime_sum(df)
            title = "<b>Activity over time</b>"
            y_axes_label = "Antenna detections"
        case 'chasings':
            plot_df = auxfun_plots.prep_chasing_overtime_sum(df)
            title = "<b>Chasing over time</b>"
            y_axes_label = "# of chasing events"

    fig = px.line(
        plot_df, 
        x="hour", 
        y="count", 
        color="animal_id", 
        color_discrete_map={animal: color for animal, color in zip(animals, colors)},
        category_orders={"animal_id": animals}, 
        line_shape='spline', 
        title=title, 
    )
    fig.update_yaxes(title=y_axes_label)
    fig.update_xaxes(title="<b>Hours</b>", range=[0, 23])
    
    return fig, plot_df

def plot_mean_line_per_hour(
    df: pd.DataFrame, 
    animals: list[str], 
    colors: list[str],
    input_type: Literal['activity', 'chasings'],    
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots line graph for activity or chasings with SEM shading."""

    match input_type:
        case 'activity':
            plot_df = auxfun_plots.prep_activity_overtime_mean(df)
            title = "<b>Activity over time</b>"
            y_axes_label = "Antenna detections"
        case 'chasings':
            plot_df = auxfun_plots.prep_chasing_overtime_mean(df)
            title = "<b>Chasing over time</b>"
            y_axes_label = "# of chasing events"

    fig = go.Figure()

    for animal, color in zip(animals, colors):
        animal_df = plot_df.query("animal_id == @animal")
        
        x = list(animal_df['hour'].values) 
        x_rev = x[::-1]
        y = list(animal_df["count"].values)
        y_upper = list(animal_df["upper"].values) 
        y_lower = list(animal_df["lower"].values)[::-1]

        shade_color = color.replace('rgb', 'rgba').replace(')', ', 0.2)') # shaded region is SEM
 
        fig.add_trace(go.Scatter(
            x=x+x_rev,
            y=y_upper+y_lower,
            fill='toself',
            fillcolor=shade_color,
            line_color='rgba(255,255,255,0)',
            showlegend=False,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

        fig.add_trace(go.Scatter(
            x=x, y=y,
            line_color=color,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

    fig.update_layout(
        title=title,
        legend=dict(
            title='animal_id',
            tracegroupgap=0,
            )
        )
    fig.update_yaxes(title=y_axes_label)
    fig.update_xaxes(title="<b>Hours</b>")

    return fig, plot_df

def plot_sum_bar_activity(
    df: pd.DataFrame, 
    colors, 
    type_switch: Literal['visits', 'time'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots bar graph of sum of cage and tunnel visits or time spent."""
    match type_switch:
        case 'visits':
            position_title = f'<b>Visits to each position</u></b>'
            position_y_title = '<b>Number of visits</b>'   
        case 'time':
            position_title = f'<b>Time spent in each position</u></b>'
            position_y_title = '<b>Time spent [s]</b>'

    plot_df = auxfun_plots.prep_sum_per_position_df(df)

    fig = px.bar(
        plot_df,
        x='animal_id',
        y='y_val', # TODO: Maybe change the name to something that's more meaningful
        color='position',
        color_discrete_sequence=colors,
        barmode='group',
        title=position_title,
    )
    
    fig.update_xaxes(title_text='<b>Animal ID</b>')
    fig.update_yaxes(title_text=position_y_title)

    return fig, plot_df

def plot_mean_box_activity(
    df, 
    colors, 
    type_switch: Literal['visits', 'time'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots box graph of mean of cage and tunnel visits or time spent."""
    match type_switch:
        case 'visits':
            position_title = f'<b>Visits to each position</u></b>'
            position_y_title = '<b>Number of visits</b>'
        case 'time':
            position_title = f'<b>Time spent in each position</u></b>'
            position_y_title = '<b>Time spent [s]</b>'

    plot_df = auxfun_plots.prep_mean_per_position_df(df)

    fig = px.box(
        plot_df,
        x='animal_id',
        y='y_val',
        color='position',
        color_discrete_sequence=colors,
        points='all',
        title=position_title,
        hover_data=['position', 'day', 'y_val'],
        boxmode='group',
    )
    
    fig.update_xaxes(title_text='<b>Animal ID</b>')
    fig.update_yaxes(title_text=position_y_title)

    return fig, plot_df

def plot_ranking_distribution(
    df: pd.DataFrame,
    animals: list[str],
    colors: list[tuple[int, int, int, float]],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots line graph of ranking distribution with shaded area."""
    distribution_df = auxfun_plots.prep_ranking_distribution(df)
    
    fig = px.line(
        distribution_df,
        color_discrete_map={animal: color for animal, color in zip(animals, colors)},
    )
    fig.update_traces(fill='tozeroy')

    fig.update_layout(
        title='<b>Ranking probability distribution</b>',
        xaxis=dict(
            title='Ranking',
        ),
        yaxis=dict(
            title='Probability density',
        ),
        legend=dict(
            title='animal_id',
            tracegroupgap=0,
            )
    )

    return fig, distribution_df

def plot_ranking_line(
    ranking_in_time: pd.DataFrame, 
    main_df: pd.DataFrame,
    colors, 
    animals,
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots line graph of ranking over time."""   
    plot_df = auxfun_plots.prep_ranking_in_time_df(main_df, ranking_in_time, per_hour=True)

    fig = go.Figure()
    for i, animal in enumerate(animals):
        fig.add_trace(
            go.Scatter(
                x=plot_df.index, 
                y=plot_df[animal], 
                name=animal, 
                marker=dict(color=colors[i]),
            ),
        )

    fig.update_layout(
        title='<b>Social dominance ranking in time</b>',
        legend=dict(
            title='animal_id',
            tracegroupgap=0,
            ),
        xaxis=dict(
            # Breakes download from the dash - maybe a bug in dash? works outside. TODO: report it?
            # rangeslider=dict(visible=True, thickness=0.1), 
            title='Timeline'
        ),
        yaxis=dict(
            title='Ranking',
        ),
    )

    return fig, plot_df

def plot_sociability_heatmap(
    df: pd.DataFrame, 
    type_switch: Literal['visits', 'time'], 
    agg_switch: Literal['mean', 'sum'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots heatmaps for pairwise encounters or time spent together."""
    match type_switch:
        case 'visits':
            pairwise_title = f'<b>Number of pairwise encounters</b>'
            pairwise_z_label = 'Number: %{z}'   
        case 'time':
            pairwise_title = f'<b>Time spent together</b>'
            pairwise_z_label = 'Time [s]: %{z}'

    match agg_switch:
        case 'sum':
            plot_arr, animals = auxfun_plots.prep_pairwise_arr(df, agg_switch)
        case 'mean':
            plot_arr, animals = auxfun_plots.prep_pairwise_arr(df, agg_switch)
    
    fig = px.imshow(
        plot_arr,
        zmin=0,
        x=animals,
        y=animals,
        facet_col=0,
        facet_col_wrap=2,
        color_continuous_scale='Viridis',
        title=pairwise_title
    )

    for annotation in fig.layout.annotations:
        annotation['text'] = f'Cage {int(annotation['text'].split('=')[1]) + 1}'

    fig.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            pairwise_z_label,
        ])
    )

    return fig, plot_arr

def plot_chasings_heatmap(
    df: pd.DataFrame,
    agg_switch: Literal['mean', 'sum'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots heatmap for number of chasings."""
    plot_df = auxfun_plots.prep_chasings_plot_df(df, agg_switch)

    z_label = 'Number: %{z}'

    fig = px.imshow(
        plot_df,
        zmin=0, 
        color_continuous_scale="Viridis",
        title='<b>Number of chasings</b>',
    )

    fig.update_xaxes(title='Chasing', showspikes=True, spikemode='across')
    fig.update_yaxes(title='Chased', showspikes=True, spikemode='across')
    fig.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            z_label,
        ])
    )

    return fig, plot_df

def plot_within_cohort_heatmap(
    df: pd.DataFrame,
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots heatmap for within-cohort sociability."""
    plot_df = auxfun_plots.prep_within_cohort_plot_df(df)

    z_label = 'Sociability: %{z}'

    fig = px.imshow(
        plot_df,
        zmin=0, 
        color_continuous_scale="Viridis",
        title='<b>Within-cohort sociability</b>',
    )

    fig.update_xaxes(title=None, showspikes=True, spikemode='across')
    fig.update_yaxes(title=None, showspikes=True, spikemode='across')
    fig.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            z_label,
        ])
    )

    return fig, plot_df

def plot_network_graph(
    chasings_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    phase_range: list[int, int],
    animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    """Plots network graph of social structure."""
    chasings_df = auxfun_plots.prep_network_df(chasings_df)
    ranking_ser = auxfun_plots.prep_ranking(ranking_df, phase_range)
    
    G = nx.from_pandas_edgelist(chasings_df, create_using=nx.DiGraph, edge_attr='chasings')
    pos = nx.spring_layout(G, k=None, iterations=300, seed=42, weight='chasings', method='energy')
    node_trace = auxfun_plots.create_node_trace(G, pos, ranking_ser, colors, animals)
    edge_trace = auxfun_plots.create_edges_trace(G, pos)
    
    fig = go.Figure(
            data=edge_trace + [node_trace],
            layout=go.Layout(
                showlegend=False,
                hovermode='closest',
                title=dict(text=f'<b>Social structure network graph</u></b>', x=0.01, y=0.95),
            )
        )

    fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=False,)
    fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False,)
    
    return fig, chasings_df

def time_per_cage_line(
    cage_occupancy: pd.DataFrame,
    agg_switch: Literal['sum', 'mean'], 
    animals, colors, 
) -> tuple[go.Figure, pd.DataFrame]:
    
    plot_df = auxfun_plots.prep_time_per_cage(cage_occupancy)
    cages = sorted(plot_df['cage'].unique())

    fig = make_subplots(
        rows=2, cols=int(np.ceil(len(cages)/2)),
        subplot_titles=[f'{" ".join([cage.split("_")[0].capitalize(), cage.split("_")[1]])}' for cage in cages],
        shared_yaxes='all', shared_xaxes='all',
        horizontal_spacing = 0.05,
        vertical_spacing = 0.12,
        x_title='<b>Hours</b>',
        y_title='<b>Time (seconds)</b>'
    )

    location = list(product(range(1, len(cages)//2+1), 
                            range(1, len(cages)//2+1)))

    for cage, loc in zip(cages, location):
        row, col = loc
        for animal, color in zip(animals, colors):
            animal_df = plot_df.query("animal_id == @animal and cage == @cage")

            if animal_df.empty:
                continue
            
            x = list(animal_df["hours"].values)
            x_rev = x[::-1]
            
            match agg_switch:
                case 'mean':
                    y = list(animal_df["time_mean"].values)
                    y_upper = list(animal_df["upper"].values)
                    y_lower = list(animal_df["lower"].values)

                    shade_color = color.replace('rgb', 'rgba').replace(')', ', 0.2)')

                    fig.add_trace(
                        go.Scatter(
                            x=x + x_rev,
                            y=y_upper + y_lower[::-1],
                            fill='toself',
                            fillcolor=shade_color,
                            line_color='rgba(255,255,255,0)',
                            line=dict(shape='spline'),
                            showlegend=False,
                            hoverinfo='skip',
                            name=f"{animal} SEM",
                            legendgroup=animal
                        ),
                        row=row, col=col
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=x,
                            y=y,
                            line_color=color,
                            name=animal,
                            legendgroup=animal,
                            line=dict(shape='spline'),
                            showlegend=(row == 1 and col == 1) 
                        ),
                        row=row, col=col
                    )
                case 'sum':
                    y = list(animal_df["time_sum"].values)
                    fig.add_trace(
                        go.Scatter(
                            x=x,
                            y=y,
                            line_color=color,
                            name=animal,
                            legendgroup=animal,
                            line=dict(shape='spline'),
                            showlegend=(row == 1 and col == 1) 
                        ),
                        row=row, col=col
                    )

    fig.update_layout(
        title="<b>Time Spent per Cage</b>",
        legend=dict(
            title='Animal ID',
            tracegroupgap=0
        ),
    )
    
    return fig, plot_df

def plot_metrics_polar(
    time_alone: pd.DataFrame,
    chasings_df: pd.DataFrame,
    pairwise_encounters: pd.DataFrame,
    activity: pd.DataFrame,
    animals, colors, 
    ) -> tuple[go.Figure, pd.DataFrame]:
    plot_df = auxfun_plots.prep_polar_df(time_alone, chasings_df, pairwise_encounters, activity, animals)

    fig = px.line_polar(
        plot_df, 
        r='value', 
        theta='metric', 
        color='animal_id', 
        line_close=True,
        line_shape='spline', 
        color_discrete_map={animal: color for animal, color in zip(animals, colors)},
        title='<b>Social dominance metrics</b>'
    )

    fig.update_polars(bgcolor="rgba(0,0,0,0)")
    fig.update_layout(title_y=0.95, title_x=0.45)

    return fig, plot_df
    


