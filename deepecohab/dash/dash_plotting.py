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
    agg_switch: Literal['sum', 'mean']
) -> go.Figure:
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
        (df['phase_count'] >= phase_range[0]) & 
        (df['phase_count'] <= phase_range[-1])
    ]
    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    match agg_switch:
        case 'sum':
            return plot_factory.plot_sum_line_per_hour(df, colors, 'activity')
        case 'mean':
            return plot_factory.plot_mean_line_per_hour(df, animals, colors, 'activity')
        
def chasings_line(
    store: pd.HDFStore,
    phase_range: list[int, int], 
    agg_switch: Literal['sum', 'mean']
) -> go.Figure:
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
    df = store['main_df']
    match_df = store['match_df']

    match_df = auxfun_plots.prep_match_df_line(df, match_df)

    match_df = match_df[
        (match_df['phase_count'] >= phase_range[0]) & 
        (match_df['phase_count'] <= phase_range[-1])
    ]

    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    match agg_switch:
        case 'sum':
            return plot_factory.plot_sum_line_per_hour(match_df, colors, 'chasings')
        case 'mean':
            return plot_factory.plot_mean_line_per_hour(match_df, animals, colors, 'chasings')
        
def activity_bar( # TODO: Add choice to show tunnels or no
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice[int, int]],
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
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
    data_slice: tuple[str | None, slice[int, int]], # TODO: For future use - requires rewrite of ranking calculation but we could show dsitribution change over time
) -> go.Figure:
    """Generates a line plot of the ranking distribution.

    This function generates a line plot showing the distribution of rankings based on the specified data slice (phase type and range).

    Args:
        store: The HDFStore object containing the data.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    df = store['ranking']

    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    return plot_factory.plot_ranking_distribution(df, colors)

def ranking_over_time(
    store: pd.HDFStore,
) -> go.Figure:
    """Generates a line plot of the ranking distribution over time.

    This function generates a line plot showing ranking change over time per animal.

    Args:
        store: The HDFStore object containing the data.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    ranking_in_time = store['ranking_in_time']
    main_df = store['main_df']

    animals = main_df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    return plot_factory.plot_ranking_line(ranking_in_time, main_df, colors, animals)

def pairwise_sociability(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice[int, int]],
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
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
    data_slice: tuple[str | None, slice[int, int]],
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
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

    return plot_factory.plot_chasings_heatmap(df, agg_switch)

def within_cohort_sociability(
    store: pd.HDFStore,
    data_slice: tuple[str | None, slice[int, int]],
) -> go.Figure:
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
) -> go.Figure:
    """Generates a network graph.

    This function generates a network graph where nodes are sized by ranking and edges are normalized
    based on chasings. It outputs a graph for the last ranking in the phase range and the sum of all chasings up to this phase.
    NOTE: Done for dark_phase now, hardcoded. To be fixed.
    
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
    ranking_df = store['ranking_ordinal']

    animals = chasings_df.columns
    colors = auxfun_plots.color_sampling(animals)

    return plot_factory.plot_network_graph(chasings_df, ranking_df, phase_range, colors)

def get_single_plot(store, mode, plot_type, data_slice, phase_range, agg_switch):
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
            return chasings_line(store, phase_range, agg_switch)
        case 'activity_line':
            return activity_line(store, data_slice, agg_switch)
        case 'pairwise_encounters':
            return pairwise_sociability(store, data_slice, 'visits', agg_switch)
        case 'pairwise_time': 
            return pairwise_sociability(store, data_slice, 'time', agg_switch)
        case 'chasings':
            return chasings(store, data_slice, agg_switch)
        case 'sociability':
            return within_cohort_sociability(store, data_slice)
        case 'network':
            return network_graph(store, mode, phase_range)
        case 'ranking_distribution':
            return ranking_distribution(store, data_slice)
        case 'ranking_line':
            return ranking_over_time(store)
        case _:
            return {}