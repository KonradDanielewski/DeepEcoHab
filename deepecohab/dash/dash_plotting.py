import plotly.graph_objects as go
import polars as pl

from deepecohab.dash import plot_factory
from deepecohab.utils import auxfun_plots
from deepecohab.utils.auxfun_plots import PlotConfig, PlotRegistry

plot_registry = PlotRegistry()


@plot_registry.register(
	"ranking-line",
	dependencies=["store", "animals", "animal_colors", "ranking_switch"],
)
def ranking_over_time(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates ranking plots either over time or as day-to-day stability."""
	
	if cfg.ranking_switch == "intime":
		df = auxfun_plots.prep_ranking_over_time(cfg.store)
		fig = plot_factory.plot_ranking_line(
			df, cfg.animal_colors, cfg.animals
		)

	elif cfg.ranking_switch == "stability":
		df = auxfun_plots.prep_ranking_day_stability(cfg.store)
		fig = plot_factory.plot_ranking_stability(
			df, cfg.animal_colors, cfg.animals
		)

	else:
		raise ValueError(f"Unknown ranking_switch: {cfg.ranking_switch}")

	return fig, df

@plot_registry.register(
	"metrics-polar-line",
	dependencies=["store", "days_range", "phase_type", "animals", "animal_colors"],
)
def polar_metrics(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a polar (radar) plot comparing various social dominance metrics.

	Visualizes z-scored values for chasing behavior, activity levels, and social
	proximity (time alone vs. together) for each animal on a unified circular scale.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_polar_df(cfg.store, cfg.days_range, cfg.phase_type)

	return plot_factory.plot_metrics_polar(df, cfg.animals, cfg.animal_colors)


@plot_registry.register(
	"ranking-distribution-line",
	dependencies=["store", "days_range", "animals", "animal_colors"],
)
def ranking_distribution(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a line plot of the ranking probability distributions.

	Fits and displays the probability density functions (PDF) for each animal's
	ranking based on Mu and Sigma values for the final day in the selected range.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_ranking_distribution(cfg.store, cfg.days_range)

	return plot_factory.plot_ranking_distribution(df, cfg.animals, cfg.animal_colors)


@plot_registry.register(
	"network-dominance",
	dependencies=["store", "animals", "days_range", "animal_colors"],
)
def network_dominance(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a social dominance network graph of animal interactions.

	Visualizes hierarchy and aggression where node size represents ranking
	and edges represent the sum of chasing events in a directional fashion.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	connections, nodes = auxfun_plots.prep_network_dominance(cfg.store, cfg.animals, cfg.days_range)

	return plot_factory.plot_network_graph(
		connections, nodes, cfg.animals, cfg.animal_colors, "chasings"
	)


@plot_registry.register(
	"chasings-heatmap",
	dependencies=["store", "animals", "days_range", "phase_type", "agg_switch"],
)
def chasings_heatmap(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a chaser-vs-chased interaction heatmap.

	Displays a matrix of agonistic interactions, where rows and columns represent
	individual animals and cells show the sum or mean of chasing events. Columns
	represent Chasers and rows represent Chased.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	img = auxfun_plots.prep_chasings_heatmap(
		cfg.store, cfg.animals, cfg.days_range, cfg.phase_type, cfg.agg_switch
	)

	return plot_factory.plot_chasings_heatmap(img, cfg.animals)


@plot_registry.register(
	"chasings-line",
	dependencies=["store", "animals", "days_range", "animal_colors", "agg_switch"],
)
def chasings_line(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a line plot of chasing frequency per hour.

	Shows the diurnal rhythm of aggression. For mean includes a shaded area representing
	the Standard Error of the Mean (SEM) across the selected days.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_chasings_line(cfg.store, cfg.animals, cfg.days_range)

	match cfg.agg_switch:
		case "sum":
			return plot_factory.plot_sum_line_per_hour(
				df, cfg.animals, cfg.animal_colors, "chasings"
			)
		case "mean":
			return plot_factory.plot_mean_line_per_hour(
				df, cfg.animals, cfg.animal_colors, "chasings"
			)


@plot_registry.register(
	"activity-bar",
	dependencies=[
		"store",
		"animals",
		"days_range",
		"animal_colors",
		"phase_type",
		"positions",
		"position_colors",
		"position_switch",
		"agg_switch",
	],
)
def activity(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a bar or box plot of animal activity levels by position.

	Quantifies behavior either by the number of visits to specific locations
	or the total time spent in those locations.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_activity(
		cfg.store, cfg.days_range, cfg.phase_type, cfg.animals, cfg.positions
	)

	return plot_factory.plot_activity(df, cfg.position_colors, cfg.position_switch, cfg.agg_switch)


@plot_registry.register(
	"activity-line",
	dependencies=["store", "animals", "days_range", "animal_colors", "agg_switch"],
)
def activity_line(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a line plot of diurnal activity based on antenna crossings.

	Plots the number of antenna detections per hour, allowing for
	comparison of circadian rhythms between animals. For mean includes a shaded area
	representing the Standard Error of the Mean (SEM) across the selected days.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_activity_line(cfg.store, cfg.animals, cfg.days_range)

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


@plot_registry.register(
	"time-per-cage-heatmap",
	dependencies=["store", "animals", "days_range", "cages", "agg_switch"],
)
def time_per_cage(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a grid of heatmaps showing cage occupancy over 24 hours.

	Creates a subplot for each cage, visualizing when and for how long specific animals
	occupy that space throughout the day.

	Args:
	    cfg: Configuration object with 'cage_occupancy' data and 'agg_switch'.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	img = auxfun_plots.prep_time_per_cage(
		cfg.store, cfg.animals, cfg.days_range, cfg.agg_switch, cfg.cages
	)

	return plot_factory.time_spent_per_cage(img, cfg.animals)


@plot_registry.register(
	"sociability-heatmap",
	dependencies=[
		"store",
		"animals",
		"phase_type",
		"days_range",
		"cages",
		"agg_switch",
		"pairwise_switch",
	],
)
def pairwise_sociability(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates heatmaps of pairwise sociability per cage.

	Visualizes how often pairs of animals meet or spend time together,
	broken down by physical location (cages).

	Args:
	    cfg: Configuration object defining 'pairwise_switch' (visits vs. time).

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	img = auxfun_plots.prep_pairwise_sociability(
		cfg.store,
		cfg.phase_type,
		cfg.animals,
		cfg.days_range,
		cfg.agg_switch,
		cfg.pairwise_switch,
		cfg.cages,
	)

	return plot_factory.plot_sociability_heatmap(img, cfg.pairwise_switch, cfg.animals)


@plot_registry.register(
	"cohort-heatmap", dependencies=["store", "animals", "phase_type", "days_range"]
)
def within_cohort_sociability(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a normalized heatmap of sociability within the entire cohort.

	Provides a high-level view of social bonds by calculating the mean
	sociability index between all animal pairs across the specified range.

	Args:
	    cfg: Configuration object containing 'incohort_sociability' data.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	img = auxfun_plots.prep_within_cohort_sociability(
		cfg.store, cfg.phase_type, cfg.animals, cfg.days_range
	)

	return plot_factory.plot_within_cohort_heatmap(img, cfg.animals)


@plot_registry.register(
	"time-alone-bar",
	dependencies=["store", "phase_type", "days_range", "agg_switch", "position_colors"],
)
def time_alone(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a stacked bar plot of time spent alone.

	Shows the duration each animal spent without any other animals present,
	segmented by the specific cages where this behavior occurred.

	Args:
	    cfg: Configuration object with 'time_alone' data and color preferences.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	df = auxfun_plots.prep_time_alone(cfg.store, cfg.phase_type, cfg.days_range)

	return plot_factory.plot_time_alone(df, cfg.position_colors, cfg.agg_switch)


@plot_registry.register(
	"network-sociability",
	dependencies=["store", "animals", "animal_colors", "days_range"],
)
def network_sociability(cfg: PlotConfig) -> tuple[go.Figure, pl.DataFrame]:
	"""Generates a social dominance network graph of animal interactions.

	Visualizes hierarchy and aggression where node size represents ranking
	and edges represent the sum of chasing events in a directional fashion.

	Returns:
	    A tuple containing the Plotly Figure and the processed Polars DataFrame.
	"""
	connections = auxfun_plots.prep_network_sociability(cfg.store, cfg.animals, cfg.days_range)

	return plot_factory.plot_network_graph(
		connections, None, cfg.animals, cfg.animal_colors, "sociability"
	)
