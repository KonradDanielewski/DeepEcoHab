import math
from typing import Literal

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from scipy.stats import norm

from deepecohab.dash import plot_factory


def ranking_over_time(
    store: dict,
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of the ranking distribution over time.

    This function generates a line plot showing ranking change over time per animal.

    Args:
        store: Dictionary containing all the DataFrames.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    lf = store['ranking'].lazy()

    df = (
        lf
        .sort('datetime')
        .group_by('day', 'hour', 'animal_id', 'datetime', maintain_order=True)
        .agg(
            pl.when(pl.first('day') == 1)
            .then(pl.first('ordinal'))
            .otherwise(pl.last('ordinal'))
        )
    ).collect()

    return plot_factory.plot_ranking_line(df, colors, animals)


def polar_metrics(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a polar plot of different social dominance related metrics.

    This function generates a polar plot showing a z-scored value correspondings to specific metrics,
    like chasings, being chased, activity etc. Each line represents a different animal

    Args:
        store: Dictionary containing all the DataFrames.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the metrics.
    """

    return plot_factory.plot_metrics_polar(
        store, days_range, phase_type, animals, colors
    )


def ranking_distribution(
    store: dict,
    days_range: list[int, int],
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of the ranking distribution.

    This function generates a line plot showing the probability distribution for the ranking of each aniaml based for the last day in range.

    Args:
        store: Dictionary containing all the DataFrames.
        days_range: Range of days - only last day used
        animals: List of animal IDs
        colors: list of colors sampled from the colormap

    Returns:
        A Plotly Figure object representing the line plot.
    """
    data_dict = {}
    x_axis = np.arange(-10, 50, 0.1)
    for animal in animals:
        intermediate = store['ranking'].filter(
            pl.col('day') == days_range[-1],
            pl.col('animal_id') == animal,
        ).select(['animal_id', 'mu', 'sigma']).to_numpy()[0]

        data_dict[animal] = norm.pdf(x_axis, intermediate[1], intermediate[2])

    df = pl.DataFrame(data_dict)

    return plot_factory.plot_ranking_distribution(df, animals, colors)
    

def network_graph(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a network graph.

    This function generates a network graph where nodes are sized by ranking and edges are normalized
    based on chasings. It outputs a graph for the last ranking in the phase range and the sum of all chasings up to this phase.

    Args:
        store: Dictionary containing all the DataFrames.
        pl.Dataphase_type: names of phases used for grouping.Frame
        days_range: range of days used for grouping.

    Returns:
        A Plotly Figure object representing the network graph.
    """
    connections = (
        store['chasings_df'].lazy()
        .filter(
            pl.col('day').is_between(days_range[0], days_range[-1]),
            pl.col('phase').is_in(phase_type)
        )
        .group_by('chased', 'chaser')
        .agg(pl.sum('chasings'))
        .rename({'chaser': 'source', 'chased': 'target'})
        .sort('target', 'source') # Order is necesarry for deterministic result of node position
    ).collect()
    
    nodes = (
        store['ranking']
        .filter(
            pl.col('day') == days_range[-1],
            pl.col('phase').is_in(phase_type)
        )
        .group_by('animal_id')
        .agg(pl.last('ordinal'))
    )

    return plot_factory.plot_network_graph(
        connections, nodes, animals, colors
    )
    
    
def chasings_heatmap(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    agg_switch: Literal["sum", "mean"],
    animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a heatmap of chasings.

    This function generates a heatmap showing the number of chasings based on the specified data slice.

    Args:
        store: Dictionary containing all the DataFrames.
        data_slice: A tuple specifying the data slice to use.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the heatmap.
    """
    lf = store['chasings_df'].lazy()
    
    match agg_switch:
        case 'sum':
            agg_func = pl.when(pl.len()>0).then(pl.sum('chasings')).alias('sum')
        case 'mean':
            agg_func = pl.mean('chasings').alias('mean')

    img = (
        lf
        .sort('chased', 'chaser')
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by(['chaser', 'chased'], maintain_order=True)
        .agg(
            agg_func
        ).collect()
        .pivot(
            on='chaser',
            index='chased',
            values=agg_switch,
        )
        .drop('chased')
        .select(animals)
    ).to_numpy()

    return plot_factory.plot_chasings_heatmap(img, animals)


def chasings_line(
    store: dict,
    days_range: list[int, int],
    agg_switch: Literal["sum", "mean"],
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of chasings per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the number of chasings per hour. The aggregation can be either the sum or the mean.

    Args:
        store: Dictionary containing all the DataFrames.
        days_range: range of days used for grouping.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    n_days = len(range(days_range[0], days_range[-1])) + 1
    lf = store['chasings_df'].lazy()
    df = (
        lf
        .filter(pl.col('day').is_between(days_range[0], days_range[-1]))
        .group_by(["hour", "chaser"])
        .agg(
            pl.sum("chasings").alias("total_chasings"),
            (pl.sum("chasings") / n_days).alias("mean_chasings"),
            (pl.std("chasings") / math.sqrt(n_days)).fill_null(0).alias("sem")
        )
        .with_columns(
            (pl.col('mean_chasings') - pl.col('sem')).alias('lower'),
            (pl.col('mean_chasings') + pl.col('sem')).alias('upper')
        )
        .sort(['hour', "chaser"])
    ).collect()

    match agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, animals, colors, "chasings"
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df, animals, colors, "chasings"
            )


def activity(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    type_switch: Literal["visits", "time"],
    agg_switch: Literal["sum", "mean"],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a bar plot or box plot of activity.

    This function generates either a bar plot or a box plot of activity based on the specified data slice (phase type and range).
    For 'mean', a box plot is created showing the mean number of entries or mean time spent per position.
    For 'sum', a bar plot is created showing the sum of entries or time spent per position.

    Args:
        store: Dictionary containing all the DataFrames.
        days_range: range of days used for grouping.
        phase_type: names of phases used for grouping.
        type_switch: Determines whether to plot visits or time.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the bar plot or box plot.
    """
    
    lf = store['activity_df'].lazy()
    df = (
        lf
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1])
        )
        .group_by(['day', 'animal_id', 'position'])
        .agg(
            pl.sum('visits_to_position').alias('visits'),
            pl.sum('time_in_position').alias('time'),
        )
        .sort(['position'])
    ).collect()

    x = np.linspace(0, 1, len(df.select("position").unique()))
    colors = px.colors.sample_colorscale("Phase", x)

    return plot_factory.plot_activity(df, colors, type_switch, agg_switch)


def activity_line(
    store: dict,
    days_range: list[int, int],
    agg_switch: Literal["sum", "mean"],
    animals: list[str],
    colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of cage visits per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the activity (antenna reads) per hour. The aggregation can be either the sum or the mean.

    Args:
        store: Dictionary containing all the DataFrames.
        days_range: range of days used for grouping.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    n_days = len(range(days_range[0], days_range[-1])) + 1
    lf = store['padded_df'].lazy()
    df = (
        lf
        .filter(pl.col('day').is_between(days_range[0],days_range[-1]))
        .group_by(['day', "hour", "animal_id"])
        .len('detections')
        .group_by(["hour", 'animal_id'])
        .agg(
            pl.sum("detections").alias("total_detections"),
            (pl.sum("detections") / n_days).alias("mean_detections"),
            (pl.std("detections") / math.sqrt(n_days)).alias("sem")
        )
        .with_columns(
            (pl.col('mean_detections') - pl.col('sem')).alias('lower'),
            (pl.col('mean_detections') + pl.col('sem')).alias('upper')
        )
        .sort(['hour', 'animal_id'])
    ).collect()

    match agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, 
                animals, 
                colors, 
                "activity",
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df,
                animals,
                colors,
                "activity",
            )


def time_per_cage(
    store: dict,
    days_range: list[int, int],
    agg_switch: Literal["sum", "mean"],
    animals: list[str],
    cages: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """placeholder"""
    lf = store["cage_occupancy"].lazy()
    
    match agg_switch:
        case 'sum':
            agg = pl.sum('time_spent'),
        case 'mean':
            agg = pl.mean('time_spent'),
    
    img = (
        lf
        .filter(pl.col('day').is_between(days_range[0], days_range[-1]))
        .sort('day', 'hour')
        .group_by(['cage', 'animal_id', 'hour'], maintain_order=True)
        .agg(
            agg  
        ).collect()
        .pivot(
            on='hour',
            index=['cage', 'animal_id'],
            values='time_spent',
        )
        .drop('cage', 'animal_id')
    ).to_numpy().reshape(len(cages), len(animals), 24)

    return plot_factory.time_spent_per_cage(img, animals)


def pairwise_sociability(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    type_switch: Literal["pairwise_encounters", "time_together"],
    agg_switch: Literal["sum", "mean"],
    animals: list[str],
    cages: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a plot with heatmaps corresponding to the number of cages.

    This function generates a plot with multiple heatmaps, each corresponding to a cage,
    showing pairwise sociability based on visits or time spent together.

    Args:
        store: Dictionary containing all the DataFrames.
        data_slice: A tuple specifying the data slice to use.
        type_switch: Determines whether to plot visits or time.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the heatmaps.
    """
    lf = store['pairwise_meetings'].lazy()
    img = (
        lf
        .with_columns(pl.col(type_switch).round(2))
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1]),
        )
        .group_by(['animal_id', 'animal_id_2', 'position'], maintain_order=True)
        .agg(
            pl.when(pl.len()>0).then(pl.sum(type_switch)).alias('sum'),
            pl.mean(type_switch).alias('mean')
            
        ).collect()
        .pivot(
            on='animal_id_2',
            index=['position', 'animal_id'],
            values=agg_switch,
        )
        .drop('position', 'animal_id')
    ).to_numpy().reshape(len(cages), len(animals)-1, len(animals)-1)

    return plot_factory.plot_sociability_heatmap(img, type_switch, animals)

def time_alone(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    cages: list[str],
) -> tuple[go.Figure, pl.DataFrame]:

    df = (
        store['time_alone']
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1]),
        )
    )
    
    return plot_factory.plot_time_alone(df, cages)

def within_cohort_sociability(
    store: dict,
    days_range: list[int, int],
    phase_type: list[str],
    animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a heatmap of within-cohort sociability.

    This function generates a heatmap showing normalized pairwise sociability within a cohort based on the specified data slice.

    Args:
        store: Dictionary containing all the DataFrames.
        data_slice: A tuple specifying the data slice to use.

    Returns:
        A Plotly Figure object representing the heatmap.
    """
    lf = store['incohort_sociability'].lazy()
    img = (
        lf
        .with_columns(pl.col('sociability').round(3))
        .filter(
            pl.col('phase').is_in(phase_type),
            pl.col('day').is_between(days_range[0], days_range[-1]),
        )
        .group_by(['animal_id', 'animal_id_2'], maintain_order=True)
        .agg(
            pl.mean('sociability').alias('mean')
        ).collect()
        .pivot(
            on='animal_id_2',
            index='animal_id',
            values='mean',
        )
        .drop('animal_id')
    ).to_numpy().reshape(len(animals)-1, len(animals)-1)

    return plot_factory.plot_within_cohort_heatmap(img, animals)


def get_single_plot(
    store: dict, 
    days_range: list[int, int],
    phase_type: list[str], 
    plot_type: str, 
    agg_switch: Literal['sum', 'mean'], 
    animals: list[str],
    colors: list[str], 
    cages: list[str],
):
    """Retrieves a single plot based on the specified parameters.

    This function acts as a factory to generate different types of plots based on the provided parameters.

    Args:
        store: The data store object containing the data.
        pl.Dataphase_type: names of phases used for grouping.Frame
        plot_type: The type of plot to generate.
        data_slice: A tuple specifying the data slice to use.
        days_range: range of days used for grouping.
        agg_switch: Determines whether to aggregate data by sum or mean.

    Returns:
        A Plotly Figure object representing the requested plot or an empty dictionary if the plot type is not recognized.
    """
    match plot_type:
        case "position_visits":
            return activity(store, days_range, phase_type, "visits", str(agg_switch))
        case "position_time":
            return activity(store, days_range, phase_type, "time", str(agg_switch))
        case "chasings_line":
            return chasings_line(store, days_range, str(agg_switch), animals, colors)
        case "activity_line":
            return activity_line(store, days_range, phase_type, str(agg_switch), animals, colors)
        case "pairwise_encounters":
            return pairwise_sociability(store, days_range, phase_type, "visits", str(agg_switch), animals, cages)
        case "pairwise_time":
            return pairwise_sociability(store, days_range, phase_type, "visits", str(agg_switch), animals, cages)
        case "chasings":
            return chasings_heatmap(store, days_range, phase_type, str(agg_switch), animals)
        case "sociability":
            return within_cohort_sociability(store, days_range, phase_type, animals)
        case "network":
            return network_graph(store, days_range, phase_type, animals, colors)
        case "ranking_distribution":
            return ranking_distribution(store, days_range, phase_type, animals, colors)
        case "ranking_line":
            return ranking_over_time(store, animals, colors)
        case "time_per_cage":
            return time_per_cage(store, days_range, str(agg_switch), animals, colors, cages)
        case _:
            return {}
