import math
from itertools import product

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from scipy.stats import norm

from deepecohab.dash import plot_factory
from deepecohab.utils import auxfun_plots
from deepecohab.utils.auxfun_plots import PlotConfig, PlotRegistry

plot_registry = PlotRegistry()

@plot_registry.register("ranking-line")
def ranking_over_time(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot showing the evolution of animal rankings over time.

        Tracks the ordinal rank of each animal across days and hours to visualize 
        changes in social hierarchy.

        Args:
            cfg: Configuration object containing 'ranking' data, animal IDs, and colors.

        Returns:
            A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store['ranking'].lazy()

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

    return plot_factory.plot_ranking_line(df, cfg.animal_colors, cfg.animals)


@plot_registry.register("metrics-polar-line")
def polar_metrics(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a polar (radar) plot comparing various social dominance metrics.

    Visualizes z-scored values for chasing behavior, activity levels, and social 
    proximity (time alone vs. together) for each animal on a unified circular scale.

    Args:
        cfg: Configuration object with 'days_range', 'phase_type', and color mappings.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    df = auxfun_plots.prep_polar_df(cfg.store, cfg.days_range, cfg.phase_type)
    
    return plot_factory.plot_metrics_polar(
        df, cfg.animals, cfg.animal_colors
    )


@plot_registry.register("ranking-distribution-line")
def ranking_distribution(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of the ranking probability distributions.

    Fits and displays the probability density functions (PDF) for each animal's 
    ranking based on Mu and Sigma values for the final day in the selected range.

    Args:
        cfg: Configuration object containing Gaussian parameters (mu, sigma) in 'ranking'.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    data_dict = {}
    x_axis = np.arange(-10, 50, 0.1)
    for animal in cfg.animals:
        intermediate = cfg.store['ranking'].filter(
            pl.col('day') == cfg.days_range[-1],
            pl.col('animal_id') == animal,
        ).select(['animal_id', 'mu', 'sigma']).to_numpy()[0]

        data_dict[animal] = norm.pdf(x_axis, intermediate[1], intermediate[2])

    df = (
        pl.DataFrame(data_dict)
        .with_columns(ranking=x_axis)
        .unpivot(variable_name='animal_id', value_name='probability_density', index='ranking')
    )

    return plot_factory.plot_ranking_distribution(df, cfg.animals, cfg.animal_colors)
   
    
@plot_registry.register("network-graph")
def network_graph(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a social network graph of animal interactions.

    Visualizes hierarchy and aggression where node size represents ranking 
    and edges represent the sum of chasing events in a directional fashion.

    Args:
        cfg: Configuration object containing interaction data and ranking ordinal.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    join_df = pl.LazyFrame(
        (product(
            cfg.animals,
            cfg.animals,
            )
        ), 
        schema=[
            ('chased', pl.Enum(cfg.animals)),
            ('chaser', pl.Enum(cfg.animals)),
        ]
    )
    
    connections = (
        cfg.store['chasings_df'].lazy()
        .filter(
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]),
        )
        .group_by('chased', 'chaser')
        .agg(pl.sum('chasings'))
        .join(
            join_df,
            on=['chaser', 'chased'],
            how='full',
        )
        .drop('chaser', 'chased')
        .rename({'chaser_right': 'source', 'chased_right': 'target'})
        .sort('target', 'source') # Order is necesarry for deterministic result of node position
    ).collect()
    
    nodes = (
        cfg.store['ranking']
        .filter(
            pl.col('day') == cfg.days_range[-1],
        )
        .group_by('animal_id')
        .agg(pl.last('ordinal'))
    )

    return plot_factory.plot_network_graph(
        connections, nodes, cfg.animals, cfg.animal_colors
    )
    

@plot_registry.register("chasings-heatmap")    
def chasings_heatmap(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a chaser-vs-chased interaction heatmap.

    Displays a matrix of agonistic interactions, where rows and columns represent 
    individual animals and cells show the sum or mean of chasing events. Columns 
    represent Chasers and rows represent Chased.

    Args:
        cfg: Configuration object defining the 'agg_switch' (sum/mean) and time filters.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store['chasings_df'].lazy()
    
    join_df = pl.LazyFrame(
        (product(
            cfg.animals,
            cfg.animals,
            )
        ), 
        schema=[
            ('chased', pl.Enum(cfg.animals)),
            ('chaser', pl.Enum(cfg.animals)),
        ]
    )
    
    match cfg.agg_switch:
        case 'sum':
            agg_func = pl.when(pl.len()>0).then(pl.sum('chasings')).alias('sum')
        case 'mean':
            agg_func = pl.mean('chasings').alias('mean')

    img = (
        lf
        .sort('chased', 'chaser')
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1])
        )
        .group_by(['chaser', 'chased'], maintain_order=True)
        .agg(
            agg_func
        )
        .join(
            join_df,
            on=['chaser', 'chased'],
            how='full',
        )
        .drop('chaser', 'chased').collect()
        .pivot(
            on='chaser_right',
            index='chased_right',
            values=cfg.agg_switch,
        )
        .drop('chased_right')
        .select(cfg.animals)
    )

    return plot_factory.plot_chasings_heatmap(img, cfg.animals)


@plot_registry.register("chasings-line")   
def chasings_line(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of chasing frequency per hour.

    Shows the diurnal rhythm of aggression. For mean includes a shaded area representing 
    the Standard Error of the Mean (SEM) across the selected days.

    Args:
        cfg: Configuration object containing 'chasings_df' and the aggregation toggle.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    n_days = len(range(cfg.days_range[0], cfg.days_range[-1])) + 1

    join_df = pl.LazyFrame(
        (product(
            cfg.animals,
            cfg.animals,
            list(range(24)),
            list(range(cfg.days_range[0], cfg.days_range[-1] + 1)),
            )
        ), 
        schema=[
            ('chased', pl.Enum(cfg.animals)),
            ('chaser', pl.Enum(cfg.animals)),
            ('hour', pl.Int8()),
            ('day', pl.Int16()),
        ]
    )

    lf = cfg.store['chasings_df'].lazy()
    df = (
        lf
        .filter(pl.col('day').is_between(cfg.days_range[0], cfg.days_range[1]))
        .join(
            join_df,
            on=['chaser', 'chased', 'hour', 'day'],
            how='full',
        )
        .drop(["hour", "chaser", "chased", "day"])
        .rename({"hour_right": "hour", "chaser_right": "chaser", "chased_right": "chased", "day_right": "day"})
        .group_by('day', 'hour', 'chaser')
        .agg(
            pl.sum('chasings')
        )
        .group_by('hour', 'chaser')
        .agg(
            pl.sum('chasings').alias('total'),
            pl.mean('chasings').alias('mean'),
            (pl.std('chasings') / math.sqrt(n_days)).alias('sem'),
        )
        .with_columns(
            (pl.col('mean') - pl.col('sem')).alias('lower'),
            (pl.col('mean') + pl.col('sem')).alias('upper')
        )
        .sort('chaser', 'hour')
    ).collect()

    match cfg.agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, cfg.animals, cfg.animal_colors, "chasings"
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df, cfg.animals, cfg.animal_colors, "chasings"
            )


@plot_registry.register("activity-bar")   
def activity(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a bar or box plot of animal activity levels by position.

    Quantifies behavior either by the number of visits to specific locations 
    or the total time spent in those locations.

    Args:
        cfg: Configuration object containing 'position_switch' (visits/time) 
            and 'agg_switch'.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store['activity_df'].lazy()
    df = (
        lf
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1])
        )
        .group_by(['day', 'animal_id', 'position'])
        .agg(
            pl.sum('visits_to_position').alias('visits'),
            pl.sum('time_in_position').alias('time'),
        )
        .sort(['position'])
    ).collect()

    return plot_factory.plot_activity(df, cfg.position_colors, cfg.position_switch, cfg.agg_switch)


@plot_registry.register("activity-line")   
def activity_line(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of diurnal activity based on antenna crossings.

    Plots the number of antenna detections per hour, allowing for 
    comparison of circadian rhythms between animals. For mean includes a shaded area 
    representing the Standard Error of the Mean (SEM) across the selected days.

    Args:
        cfg: Configuration object containing 'padded_df' for sensor detections.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    n_days = len(range(cfg.days_range[0], cfg.days_range[-1])) + 1
    
    join_df = pl.LazyFrame(
        (product(
            cfg.animals,
            list(range(cfg.days_range[0], cfg.days_range[1] + 1)),
            list(range(24)),
            )
        ), 
        schema=[
            ('animal_id', pl.Enum(cfg.animals)),
            ('day', pl.Int16()),
            ('hour', pl.Int8()),
        ]
    )

    df = (
        cfg.store['padded_df'].lazy()
        .filter(pl.col('day').is_between(cfg.days_range[0], cfg.days_range[1]))
        .join(
            join_df,
            on=['animal_id', 'hour', 'day'],
            how='full',
        )
        .drop(["hour", "animal_id", "day"])
        .rename({"hour_right": "hour", "animal_id_right": "animal_id", "day_right": "day"})
        .group_by("day", "hour", "animal_id")
        .agg(
            pl.len().alias('n_detections'),
        )
        .group_by('hour', 'animal_id')
        .agg(
            pl.sum('n_detections').alias('total'),
            pl.mean('n_detections').alias('mean'),
            (pl.std("n_detections") / math.sqrt(n_days)).alias('sem'),
            
        )
        .with_columns(
            (pl.col('mean') - pl.col('sem')).alias('lower'),
            (pl.col('mean') + pl.col('sem')).alias('upper')
        )
        .sort('animal_id', 'hour')
    ).collect()

    match cfg.agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, 
                cfg.animals, 
                cfg.animal_colors, 
                "activity",
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df,
                cfg.animals,
                cfg.animal_colors,
                "activity",
            )


@plot_registry.register("time-per-cage-heatmap")   
def time_per_cage(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a grid of heatmaps showing cage occupancy over 24 hours.

    Creates a subplot for each cage, visualizing when and for how long specific animals 
    occupy that space throughout the day.

    Args:
        cfg: Configuration object with 'cage_occupancy' data and 'agg_switch'.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store["cage_occupancy"].lazy()
    
    join_df = pl.LazyFrame(
        (product(
            list(range(24)),
            cfg.cages,
            cfg.animals,
            )
        ), 
        schema=[
            ('hour', pl.Int8()),
            ('cage', pl.Categorical()),
            ('animal_id', pl.Enum(cfg.animals)),
        ]
    )
    
    match cfg.agg_switch:
        case 'sum':
            agg = pl.sum('time_spent'),
        case 'mean':
            agg = pl.mean('time_spent'),
    
    img = (
        lf
        .filter(pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]))
        .sort('day', 'hour')
        .group_by(['cage', 'animal_id', 'hour'], maintain_order=True)
        .agg(
            agg  
        )
        .join(
            join_df,
            on=['hour', 'cage', 'animal_id'],
            how='full',
        )
        .drop('hour', 'cage', 'animal_id')
        .collect()
        .pivot(
            on='hour_right',
            index=['cage_right', 'animal_id_right'],
            values='time_spent',
        )
        .drop('cage_right', 'animal_id_right')
    )

    return plot_factory.time_spent_per_cage(img, cfg.animals, cfg.cages)


@plot_registry.register("sociability-heatmap")   
def pairwise_sociability(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates heatmaps of pairwise sociability per cage.

    Visualizes how often pairs of animals meet or spend time together, 
    broken down by physical location (cages).

    Args:
        cfg: Configuration object defining 'pairwise_switch' (visits vs. time).

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store['pairwise_meetings'].lazy()
    join_df = pl.LazyFrame(
        (product(
            cfg.cages, 
            cfg.animals,
            cfg.animals,
            )
        ), 
        schema=[
            ('position', pl.Categorical()), 
            ('animal_id', pl.Enum(cfg.animals)),
            ('animal_id_2', pl.Enum(cfg.animals)),
        ]
    )

    img = (
        lf
        .with_columns(pl.col(cfg.pairwise_switch).round(2))
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]),
        )
        .group_by(['animal_id', 'animal_id_2', 'position'], maintain_order=True)
        .agg(
            pl.when(pl.len()>0).then(pl.sum(cfg.pairwise_switch)).alias('sum'),
            pl.mean(cfg.pairwise_switch).alias('mean'),
        )
        .join(
            join_df,
            on=['position', 'animal_id', 'animal_id_2'],
            how='full',
        )
        .drop('position', 'animal_id', 'animal_id_2')
        .collect()
        .pivot(
            on='animal_id_2_right',
            index=['position_right', 'animal_id_right'],
            values=cfg.agg_switch,
        )
        .drop('position_right', 'animal_id_right')
    )

    return plot_factory.plot_sociability_heatmap(img, cfg.pairwise_switch, cfg.animals, cfg.cages)


@plot_registry.register("cohort-heatmap")   
def within_cohort_sociability(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a normalized heatmap of sociability within the entire cohort.

    Provides a high-level view of social bonds by calculating the mean 
    sociability index between all animal pairs across the specified range.

    Args:
        cfg: Configuration object containing 'incohort_sociability' data.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    lf = cfg.store['incohort_sociability'].lazy()

    join_df = pl.LazyFrame(
        (product(
            cfg.animals,
            cfg.animals,
            )
        ), 
        schema=[
            ('animal_id', pl.Enum(cfg.animals)),
            ('animal_id_2', pl.Enum(cfg.animals)),
        ]
    )
    img = (
        lf
        .with_columns(pl.col('sociability').round(3))
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]),
        )
        .group_by(['animal_id', 'animal_id_2'], maintain_order=True)
        .agg(
            pl.mean('sociability').alias('mean')
        )
        .join(
            join_df,
            on=['animal_id', 'animal_id_2'],
            how='full',
        )
        .drop('animal_id', 'animal_id_2').collect()
        .pivot(
            on='animal_id_2_right',
            index='animal_id_right',
            values='mean',
        )
        .drop('animal_id_right')
    )

    return plot_factory.plot_within_cohort_heatmap(img, cfg.animals)


@plot_registry.register("time-alone-bar")   
def time_alone(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a stacked bar plot of time spent alone.

    Shows the duration each animal spent without any other animals present, 
    segmented by the specific cages where this behavior occurred.

    Args:
        cfg: Configuration object with 'time_alone' data and color preferences.

    Returns:
        A tuple containing the Plotly Figure and the processed Polars DataFrame.
    """
    df = (
        cfg.store['time_alone']
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]),
        )
    )
    
    return plot_factory.plot_time_alone(df, cfg.position_colors)
