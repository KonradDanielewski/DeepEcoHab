from typing import Literal

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from deepecohab.utils import auxfun_plots

def plot_sum_line_per_hour(
    df: pd.DataFrame, 
    colors: list[tuple[int, int, int]], 
    input_type: Literal['activity', 'chasings'],
) -> go.Figure:
    """Create a line plot showing per hour activity grouped by phase_count - sum of phase_counts. 
    Activity is defined as every antenna detection.

    Args:
        df: main_df of the dataset
        colors: list of colors to be used for animals

    Returns:
        Line plot of sum of all antenna detections across selected phases
    """
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
        color_discrete_sequence=colors, 
        line_shape='spline', 
        title=title, 
    )
    fig.update_yaxes(title=y_axes_label)
    fig.update_xaxes(title="<b>Hours</b>")
    
    return fig

def plot_mean_line_per_hour(
    df: pd.DataFrame, 
    animals: list[str], 
    colors: list[str],
    input_type: Literal['activity', 'chasings'],
) -> go.Figure:
    """Create a line plot showing per hour activity grouped by phase_count - mean per phase_count. 
    Activity is defined as every antenna detection.

    Args:
        df: mean_df of antenna detections per hour
        animals: animal_ids
        colors: list of colors to be used for animals

    Returns:
        Line plot of mean N detections in phase_counts with shaded region for SEM
    """
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

    x = list(range(24)) # N hours in a day
    x_rev = x[::-1]

    for animal, color in zip(animals, colors):
        animal_df = plot_df.query("animal_id == @animal")
        
        y = list(animal_df["count"].values)
        y_upper = list(animal_df["higher"].values) 
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

    fig.update_layout(title=title)
    fig.update_yaxes(title=y_axes_label)
    fig.update_xaxes(title="<b>Hours</b>")

    return fig

def plot_sum_bar_activity(
    df: pd.DataFrame, 
    colors, 
    type_switch: Literal['visits', 'time'],
) -> go.Figure:
    match type_switch:
        case 'visits':
            position_title = f'<b>Visits to each position</u></b>'
            position_y_title = '<b>Number of visits</b>'
            position_y = 'Visits[#]'     
        case 'time':
            position_title = f'<b>Time spent in each position</u></b>'
            position_y_title = '<b>Time spent [s]</b>'
            position_y = 'Time[s]'

    plot_df = auxfun_plots.prep_sum_per_position_df(df)

    fig = px.bar(
        plot_df,
        x='animal_id',
        y='y_val',
        color='position',
        color_discrete_sequence=colors,
        barmode='group',
        title=position_title,
    )
    
    fig.update_xaxes(title_text='<b>Animal ID</b>')
    fig.update_yaxes(title_text=position_y_title)

    return fig

def plot_mean_box_activity(
    df, 
    colors, 
    type_switch: Literal['visits', 'time'],
) -> go.Figure:
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
        hover_data=['position', 'phase_count', 'y_val']
    )
    
    fig.update_xaxes(title_text='<b>Animal ID</b>')
    fig.update_yaxes(title_text=position_y_title)

    return fig

def plot_ranking_distribution(
    df: pd.DataFrame, 
    colors: list[tuple[int, int, int, float]],
) -> go.Figure:
    
    distribution_df = auxfun_plots.prep_ranking_distribution(df)
    
    fig = px.line(
        distribution_df,
        color_discrete_sequence=colors,
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
    )

    return fig

def plot_ranking_line(
    df: pd.DataFrame, 
    colors, 
    animals,
) -> go.Figure:
    fig = go.Figure()
    for i, animal in enumerate(animals):
        fig.add_trace(
            go.Scatter(
                x=df.index, 
                y=df[animal], 
                name=animal, 
                marker=dict(color=colors[i]),
            ),
        )

    fig.update_layout(
        title='<b>Social dominance ranking in time</b>',
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.1),
            title='Timeline'
        ),
        yaxis=dict(
            title='Ranking',
        ),
    )

    return fig

def plot_sociability_heatmap(
    df: pd.DataFrame, 
    type_switch: Literal['visits', 'time'], 
    agg_switch: Literal['mean', 'sum'],
) -> go.Figure:
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

    return fig

def plot_chasings_heatmap(
    df: pd.DataFrame,
    agg_switch: Literal['mean', 'sum'],
) -> go.Figure:
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

    return fig

def plot_within_cohort_heatmap(
    df: pd.DataFrame,
) -> go.Figure:
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

    return fig

def plot_network_graph(
    chasings_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    phase_range: list[int, int],
    colors,
) -> go.Figure:
    """Auxfun to plot network graph
    """
    chasings_df = auxfun_plots.prep_network_df(chasings_df)
    ranking_ser = auxfun_plots.prep_ranking(ranking_df, phase_range)

    animals = ranking_ser.index
    colors = auxfun_plots.color_sampling(animals)
    
    G = nx.from_pandas_edgelist(chasings_df, create_using=nx.DiGraph, edge_attr='chasings')
    pos = nx.spring_layout(G, k=None, iterations=300, seed=42, weight='chasings', method='energy')
    node_trace = auxfun_plots.create_node_trace(G, pos, ranking_ser, colors)
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
    
    return fig
    


