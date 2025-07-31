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
    """Outputs a lineplot of cage visits per hour to the dashboard
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
    """Outputs a lineplot of chasings per hour to the dashboard
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
    data_slice,
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
    """Outputs a bar plot or box plot of activity to the dashboard.
    For 'mean' boxplot is created showing mean number of entries or mean time spent per position.
    For 'sum' a barplot is created showing sum of entries or time spent per position.
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
    data_slice, # TODO: For future use - requires rewrite of ranking calculation but we could show dsitribution change over time
) -> go.Figure:
    """Outputs a line plot of the ranking distribution to the dashboard.
    """ 

    df = store['ranking']

    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    return plot_factory.plot_ranking_distribution(df, colors)

def ranking_over_time(
    store: pd.HDFStore,
) -> go.Figure:
    """Outputs a line plot of the ranking distribution to the dashboard.
    """ 

    ranking_in_time = store['ranking_in_time']
    main_df = store['main_df']

    animals = main_df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    plot_df = auxfun_plots.prep_ranking_in_time_df(main_df, ranking_in_time, per_hour=True)

    return plot_factory.plot_ranking_line(plot_df, colors, animals)

def pairwise_sociability(
    store: pd.HDFStore,
    data_slice,
    type_switch: Literal['visits', 'time'],
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
    
    match type_switch:
        case 'visits':
            df = store['pairwise_encounters'].loc[data_slice]
        case 'time':
            df = store['time_together'].loc[data_slice]

    return plot_factory.plot_sociability_heatmap(df, type_switch, agg_switch)

def chasings(
    store: pd.HDFStore,
    data_slice,
    agg_switch: Literal['sum', 'mean'],
) -> go.Figure:
    
    df = store['chasings'].loc[data_slice]

    return plot_factory.plot_chasings_heatmap(df, agg_switch)

def within_cohort_sociability(
    store: pd.HDFStore,
    data_slice,
) -> go.Figure:
    
    df = store['incohort_sociability'].loc[data_slice]

    return plot_factory.plot_within_cohort_heatmap(df)

def network_graph(
    store: pd.HDFStore,
    mode,
    data_slice,
    phase_range,
) -> go.Figure:
    if mode == 'all': # TODO: ugly 🤢, better solution? 
        mode = slice(None)
    chasings_df = store['chasings'].loc[(mode)]
    ranking_df = store['ranking_ordinal']

    animals = chasings_df.columns
    colors = auxfun_plots.color_sampling(animals)

    return plot_factory.plot_network_graph(chasings_df, ranking_df, phase_range, colors)

def get_single_plot(store, plot_type, data_slice, phase_range, agg_switch):
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
            return network_graph(store, data_slice, phase_range)
        case 'ranking_distribution':
            return ranking_distribution(store, data_slice)
        case 'ranking_line':
            return ranking_over_time(store)
        case _:
            return {}