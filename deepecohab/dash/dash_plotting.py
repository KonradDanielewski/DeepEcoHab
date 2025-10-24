from typing import Literal

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from deepecohab.utils import auxfun_plots
from deepecohab.dash import plot_factory

def activity_line(
    store: pd.HDFStore,
    phase_range: list[int, int], 
    agg_switch: Literal['sum', 'mean'],
    animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a line plot of cage visits per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the activity (antenna reads) per hour. The aggregation can be either the sum or the mean.

    Args:
        store: The HDFStore object containing the data.
        phase_range: A list specifying the start and end of the phase range.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    df = store['padded_df']
    df = df[
        (df['day'] >= phase_range[0]) & 
        (df['day'] <= phase_range[-1])
    ]

    match agg_switch:
        case 'sum':
            return plot_factory.plot_sum_line_per_hour(df, animals, colors, 'activity')
        case 'mean':
            return plot_factory.plot_mean_line_per_hour(df, animals, colors, 'activity',)
        
def chasings_line(
    store: pd.HDFStore,
    phase_range: list[int, int],
    agg_switch: Literal['sum', 'mean'],
    animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a line plot of chasings per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the number of chasings per hour. The aggregation can be either the sum or the mean.

    Args:
        store: The HDFStore object containing the data.
        phase_range: A list specifying the start and end of the phase range.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    chasings_df = store['chasings'].loc[(slice(None), slice(phase_range[0], phase_range[1])), :]
    chasings_df.columns.name = 'chaser'

    match agg_switch:
        case 'sum':
            return plot_factory.plot_sum_line_per_hour(chasings_df, animals, colors, 'chasings')
        case 'mean':
            return plot_factory.plot_mean_line_per_hour(chasings_df, animals, colors, 'chasings')
        
def activity_bar( # TODO: Add choice to show tunnels or no
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice],
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a bar plot or box plot of activity.

    This function generates either a bar plot or a box plot of activity based on the specified data slice (phase type and range).
    For 'mean', a box plot is created showing the mean number of entries or mean time spent per position.
    For 'sum', a bar plot is created showing the sum of entries or time spent per position.

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.
        type_switch: Determines whether to plot visits or time.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the bar plot or box plot.
    """
    match type_switch:
        case 'visits':
            df = store['visits_per_position'].loc[data_slice]
        case 'time':
            df = store['time_per_position'].loc[data_slice]

    x = np.linspace(0, 1, len(df.index.get_level_values('position').unique()))
    colors = px.colors.sample_colorscale('Phase', x)

    match agg_switch:
        case 'sum':
            return plot_factory.plot_sum_bar_activity(df, colors, type_switch)
        case 'mean':
            return plot_factory.plot_mean_box_activity(df, colors, type_switch)

def ranking_distribution(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice], # TODO: For future use - requires rewrite of ranking calculation but we could show dsitribution change over time
    animals, colors
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a line plot of the ranking distribution.

    This function generates a line plot showing the distribution of rankings based on the specified data slice (phase type and range).

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    df = store['ranking']

    return plot_factory.plot_ranking_distribution(df, animals, colors)

def ranking_over_time(
    store: pd.HDFStore,
    animals, colors
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a line plot of the ranking distribution over time.

    This function generates a line plot showing ranking change over time per animal.

    Args:
        store: The HDFStore object containing the data.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    ranking_in_time = store['ranking_in_time']
    main_df = store['main_df']

    return plot_factory.plot_ranking_line(ranking_in_time, main_df, colors, animals)

def pairwise_sociability(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice],
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a plot with heatmaps corresponding to the number of cages.

    This function generates a plot with multiple heatmaps, each corresponding to a cage,
    showing pairwise sociability based on visits or time spent together.

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.
        type_switch: Determines whether to plot visits or time.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the heatmaps.
    """
    match type_switch:
        case 'visits':
            df = store['pairwise_encounters'].loc[data_slice]
        case 'time':
            df = store['time_together'].loc[data_slice]

    return plot_factory.plot_sociability_heatmap(df, type_switch, agg_switch)

def chasings(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice],
    agg_switch: Literal['sum', 'mean'],
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a heatmap of chasings.

    This function generates a heatmap showing the number of chasings based on the specified data slice.

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the heatmap.
    """   
    df = store['chasings'].loc[data_slice]
    df.columns.name = 'chaser'

    return plot_factory.plot_chasings_heatmap(df, agg_switch)

def metrics(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice],
    animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a polar plot of different social dominance related metrics.

    This function generates a polar plot showing a z-scored value correspondings to specific metrics,
    like chasings, being chased, activity etc. Each line represents a different animal

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the metrics.
    """   
    time_alone = store['time_alone']
    chasings_df = store['chasings'].loc[data_slice]
    chasings_df.columns.name = 'chaser'
    pairwise_encounters = store['time_together'].loc[data_slice]
    activity = store['visits_per_position'].loc[data_slice]

    return plot_factory.plot_metrics_polar(time_alone, chasings_df, pairwise_encounters, activity, animals, colors)

def within_cohort_sociability(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice],
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a heatmap of within-cohort sociability.

    This function generates a heatmap showing normalized pairwise sociability within a cohort based on the specified data slice.

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the heatmap.
    """
    df = store['incohort_sociability'].loc[data_slice]

    return plot_factory.plot_within_cohort_heatmap(df)

def network_graph(
    store: pd.HDFStore,
    mode: str,
    phase_range: list[int, int],
    animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    """Generates a network graph.

    This function generates a network graph where nodes are sized by ranking and edges are normalized
    based on chasings. It outputs a graph for the last ranking in the phase range and the sum of all chasings up to this phase.
    TODO: Done for dark_phase now, hardcoded. To be fixed.
    
    Args:
        store: The HDFStore object containing the data.
        mode: The mode to use for filtering data.
        phase_range: A list specifying the start and end of the phase range.

    Returns:
        A Plotly Figure object representing the network graph.
    """
    if mode == 'all': # TODO: ugly 🤢, better solution? 
        mode = slice(None)
    chasings_df = store['chasings'].loc[(mode)]
    chasings_df.columns.name = 'chaser'
    ranking_df = store['ranking_ordinal']

    return plot_factory.plot_network_graph(chasings_df, ranking_df, phase_range, animals, colors)

def time_per_cage(
        store: pd.HDFStore,
        phase_range: list[int, int],
        agg_switch: Literal['sum', 'mean'],
        animals, colors,
) -> tuple[go.Figure, pd.DataFrame]:
    
    df = store['cage_occupancy']
    df = df[
        (df['day'] >= phase_range[0]) & 
        (df['day'] <= phase_range[-1])
    ]

    return plot_factory.time_per_cage_line(df, agg_switch, animals, colors)

def get_single_plot(store, mode, plot_type, data_slice, phase_range, agg_switch, animals, colors):
    """Retrieves a single plot based on the specified parameters.

    This function acts as a factory to generate different types of plots based on the provided parameters.

    Args:
        store: The data store object containing the data.
        mode: The mode to use for filtering data.
        plot_type: The type of plot to generate.
        data_slice: A tuple specifying the data slice to use.
        phase_range: A list specifying the start and end of the phase range.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the requested plot or an empty dictionary if the plot type is not recognized.
    """
    match plot_type:
        case 'position_visits':
            return activity_bar(store, data_slice, 'visits', agg_switch)
        case 'position_time':
            return activity_bar(store, data_slice, 'time', agg_switch)
        case 'chasings_line':
            return chasings_line(store, phase_range, agg_switch, animals, colors)
        case 'activity_line':
            return activity_line(store, data_slice, agg_switch, animals, colors)
        case 'pairwise_encounters':
            return pairwise_sociability(store, data_slice, 'visits', agg_switch)
        case 'pairwise_time': 
            return pairwise_sociability(store, data_slice, 'time', agg_switch)
        case 'chasings':
            return chasings(store, data_slice, agg_switch)
        case 'sociability':
            return within_cohort_sociability(store, data_slice)
        case 'network':
            return network_graph(store, mode, phase_range, animals, colors)
        case 'ranking_distribution':
            return ranking_distribution(store, data_slice, animals, colors)
        case 'ranking_line':
            return ranking_over_time(store, animals, colors)
        case 'time_per_cage':
            return time_per_cage(store, phase_range, animals, colors)
        case _:
            return {}