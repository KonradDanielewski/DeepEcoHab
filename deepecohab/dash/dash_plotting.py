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
    """Generates a line plot of the ranking distribution over time.

    Returns:
        A Plotly Figure object representing the line plot.
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

    return plot_factory.plot_ranking_line(df, cfg.colors, cfg.animals)


@plot_registry.register("metrics-polar-line")
def polar_metrics(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a polar plot of different social dominance related metrics.

    Shows a z-scored value correspondings to specific metrics, currently: 
    chasings, being chased, activity, time alone and time together. Each line represents a different animal

    Returns:
        A Plotly Figure object representing the metrics.
    """
    df = auxfun_plots.prep_polar_df(cfg.store, cfg.days_range, cfg.phase_type)
    
    return plot_factory.plot_metrics_polar(
        df, cfg.animals, cfg.colors
    )


@plot_registry.register("ranking-distribution-line")
def ranking_distribution(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of the ranking distribution.

    Shows the probability distribution for the ranking of each animal for the last day in range.

    Returns:
        A Plotly Figure object representing the line plot.
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

    return plot_factory.plot_ranking_distribution(df, cfg.animals, cfg.colors)
   
    
@plot_registry.register("network-graph")
def network_graph(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a network graph.

    Nodes are sized by ranking and edges are normalized based on chasings. 
    It outputs a graph for the last ranking in the day range and the sum of all chasings up to this day.

    Returns:
        A Plotly Figure object representing the network graph.
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
        connections, nodes, cfg.animals, cfg.colors
    )
    

@plot_registry.register("chasings-heatmap")    
def chasings_heatmap(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a heatmap of chasings.

    Shows the number of chasings based on the specified data slice.

    Returns:
        A Plotly Figure object representing the heatmap.
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
    """Generates a line plot of chasings per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the number of chasings per hour. The aggregation can be either the sum or the mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    n_days = len(range(cfg.days_range[0], cfg.days_range[-1])) + 1
    lf = cfg.store['chasings_df'].lazy()
    df = (
        lf
        .filter(pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]))
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

    match cfg.agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, cfg.animals, cfg.colors, "chasings"
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df, cfg.animals, cfg.colors, "chasings"
            )


@plot_registry.register("activity-bar")   
def activity(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a bar plot or box plot of activity.

    This function generates either a bar plot or a box plot of activity based on the specified data slice (phase type and range).
    For 'mean', a box plot is created showing the mean number of entries or mean time spent per position.
    For 'sum', a bar plot is created showing the sum of entries or time spent per position.

    Returns:
        A Plotly Figure object representing the bar plot or box plot.
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

    x = np.linspace(0, 1, len(df.select("position").unique()))
    colors = px.colors.sample_colorscale("Phase", x)

    return plot_factory.plot_activity(df, colors, cfg.position_switch, cfg.agg_switch)


@plot_registry.register("activity-line")   
def activity_line(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """Generates a line plot of cage visits per hour.

    This function filters data based on the specified phase range and generates a line plot
    showing the activity (antenna reads) per hour. The aggregation can be either the sum or the mean.

    Returns:
        A Plotly Figure object representing the line plot.
    """
    n_days = len(range(cfg.days_range[0], cfg.days_range[-1])) + 1
    lf = cfg.store['padded_df'].lazy()
    df = (
        lf
        .filter(pl.col('day').is_between(cfg.days_range[0],cfg.days_range[-1]))
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

    match cfg.agg_switch:
        case "sum":
            return plot_factory.plot_sum_line_per_hour(
                df, 
                cfg.animals, 
                cfg.colors, 
                "activity",
            )
        case "mean":
            return plot_factory.plot_mean_line_per_hour(
                df,
                cfg.animals,
                cfg.colors,
                "activity",
            )


@plot_registry.register("time-per-cage-heatmap")   
def time_per_cage(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
    """placeholder"""
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
    """Generates a plot with heatmaps corresponding to the number of cages.

    This function generates a plot with multiple heatmaps, each corresponding to a cage,
    showing pairwise sociability based on visits or time spent together.

    Returns:
        A Plotly Figure object representing the heatmaps.
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
    """Generates a heatmap of within-cohort sociability.

    This function generates a heatmap showing normalized pairwise sociability within a cohort based on the specified data slice.

    Returns:
        A Plotly Figure object representing the heatmap.
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

    df = (
        cfg.store['time_alone']
        .filter(
            pl.col('phase').is_in(cfg.phase_type),
            pl.col('day').is_between(cfg.days_range[0], cfg.days_range[-1]),
        )
    )
    
    return plot_factory.plot_time_alone(df, cfg.cages)
