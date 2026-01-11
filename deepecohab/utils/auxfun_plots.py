import math
from dataclasses import dataclass
from itertools import combinations, product
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


def set_default_theme() -> None:
	"""Sets default plotly theme. NOTE: to be updated as we go."""
	dark_dash_template = go.layout.Template(
		layout=go.Layout(
			paper_bgcolor="#161f34",
			plot_bgcolor="#161f34",
			font=dict(color="#e0e6f0"),
			xaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
			yaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
			legend=dict(bgcolor="rgba(0,0,0,0)"),
			colorscale=dict(
				sequential="Viridis",
				sequentialminus="Plasma",
				diverging="curl",
			),
		)
	)

	pio.templates["dash_dark"] = dark_dash_template
	pio.templates.default = "dash_dark"


def color_sampling(
	values: list[str], cmap: str = "Phase"
) -> list[str]:  # TODO: Expose the cmap choice to the dashboard
	"""Samples colors from a colormap for given values."""
	x = np.linspace(0, 1, len(values))
	colors: list[str] = px.colors.sample_colorscale(cmap, x)

	return colors


@dataclass(frozen=True)
class PlotConfig:
	"""
	Immutable container for dashboard state used to configure plot generation.

	This class aggregates UI selections and switch states into a single object
	passed to the plot factory. NOTE: Consider this as future BaseClass for group
	analysis.
	"""

	store: dict
	days_range: list[int]
	phase_type: list[str]
	agg_switch: Literal["sum", "mean"]
	position_switch: Literal["visits", "time"]
	pairwise_switch: Literal["time_together", "pairwise_encounters"]
	animals: list[str]
	animal_colors: list[str]
	cages: list[str]
	positions: list[str]
	position_colors: list[str]


class PlotRegistry:
	"""Registry for dashboard plots."""

	def __init__(self):
		self._registry: Dict[str, Callable[[PlotConfig], Any]] = {}
		self._plot_dependencies: Dict[str, list[str]] = {}

	def register(self, name: str, dependencies: list[str] = None):
		"""Decorator to register a new plot type."""

		def wrapper(func: Callable[[PlotConfig], Any]):
			self._registry[name] = func
			self._plot_dependencies[name] = dependencies
			return func

		return wrapper

	def get_dependencies(self, name: str) -> list[str]:
		"""Returns the list of PlotConfig attributes used by a specific plot."""
		return self._plot_dependencies.get(name, list())

	def get_plot(self, name: str, config: PlotConfig):
		plotter = self._registry.get(name)
		if not plotter:
			return {}
		return plotter(config)

	def list_available(self) -> list[str]:
		return list(self._registry.keys())


def create_edges_trace(
	G: nx.Graph,
	pos: dict,
	cmap: str = "Viridis",
	edge_weight: Literal["chasings", "time_together"] = "chasings",
) -> list:
	"""Auxfun to create edges trace with color mapping based on edge width"""
	edge_widths = np.array([G.edges[e][edge_weight] for e in G.edges()])

	min_w: float = edge_widths.min()
	max_w: float = edge_widths.max()

	if max_w == min_w:
		normalized_widths = np.zeros_like(edge_widths)
	else:
		normalized_widths = (edge_widths - min_w) / (max_w - min_w)
		colorscale: list[str] = px.colors.sample_colorscale(cmap, normalized_widths)

	edge_trace: list[go.Scatter] = []

	for i, edge in enumerate(G.edges()):
		if edge[0] == edge[1]:
			continue
		source_x, source_y = pos[edge[0]][:2]
		target_x, target_y = pos[edge[1]][:2]
		edge_width = normalized_widths[i] * 10  # connection width scaler for visivbility

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
	pos: dict[str, list[float]],
	colors: list[str],
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

	ranking_score_list: list[float] = []
	for node in animals:
		x, y, score = pos[node]
		node_trace["x"] += (x,)
		node_trace["y"] += (y,)
		node_trace["text"] += ("<b>" + node + "</b>",)
		ranking_score = score if score > 0 else 0.1
		ranking_score_list.append(ranking_score)
		node_trace["hovertext"] += (f"Mouse ID: {node}<br>Ranking: {ranking_score}",)

	node_trace["marker"]["color"] = colors
	node_trace["marker"]["size"] = [rank for rank in ranking_score_list]
	return node_trace


def prep_ranking_over_time(store: dict[str, pl.DataFrame]) -> pl.DataFrame:
	"""Aggregate animal ordinal rankings by day, hour, and datetime."""
	df = (
		store["ranking"]
		.lazy()
		.sort("datetime")
		.group_by("day", "hour", "animal_id", "datetime", maintain_order=True)
		.agg(pl.when(pl.first("day") == 1).then(pl.first("ordinal")).otherwise(pl.last("ordinal")))
	).collect(engine="in-memory")

	return df


def prep_polar_df(
	store: dict[str, pl.DataFrame],
	days_range: list[int, int],
	phase_type: list[str],
) -> pl.DataFrame:
	"""Prepare z-score normalized metrics for a polar/radar chart across multiple behavioral categories."""
	columns = [
		"time_alone",
		"n_chasing",
		"n_chased",
		"activity",
		"time_together",
		"pairwise_encounters",
	]

	time_alone = (
		store["time_alone"]
		.lazy()
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by("animal_id")
		.agg(
			pl.sum("time_alone"),
		)
	)

	n_chasing = (
		store["chasings_df"]
		.lazy()
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by("chaser")
		.agg(
			pl.sum("chasings").alias("n_chasing"),
		)
		.rename({"chaser": "animal_id"})
	)

	n_chased = (
		store["chasings_df"]
		.lazy()
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by("chased")
		.agg(
			pl.sum("chasings").alias("n_chased"),
		)
		.rename({"chased": "animal_id"})
	)

	activity = (
		store["activity_df"]
		.lazy()
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by("animal_id")
		.agg(
			pl.sum("visits_to_position").alias("activity"),
		)
	)

	pairwise_meetings = (
		pl.concat(
			[
				store["pairwise_meetings"]
				.lazy()
				.filter(
					pl.col("phase").is_in(phase_type),
					pl.col("day").is_between(*days_range),
				)
				.select("animal_id", "time_together", "pairwise_encounters"),
				store["pairwise_meetings"]
				.lazy()
				.filter(
					pl.col("phase").is_in(phase_type),
					pl.col("day").is_between(*days_range),
				)
				.select(
					pl.col("animal_id_2").alias("animal_id"),
					"time_together",
					"pairwise_encounters",
				),
			],
			how="align",
		)
		.group_by("animal_id")
		.agg(
			pl.sum("time_together"),
			pl.sum("pairwise_encounters"),
		)
		.sort("animal_id")
	)

	df = pl.concat([time_alone, n_chasing, n_chased, activity, pairwise_meetings], how="align")

	df = (
		df.with_columns((pl.col(columns) - pl.mean(columns)) / pl.std(columns))
		.unpivot(index="animal_id", variable_name="metric")
		.collect(engine="in-memory")
	)

	return df


def prep_ranking_distribution(
	store: dict[str, pl.DataFrame],
	days_range: list[int, int],
) -> pl.DataFrame:
	"""Calculate normal probability density functions for animal rankings on the latest available day."""
	x_df = pl.LazyFrame({"ranking": np.arange(-10, 50, 0.1)})

	diff = (pl.col("day") - days_range[-1]).abs()
	pdf_expression = (  # probability density function
		(1 / (pl.col("sigma") * math.sqrt(2 * math.pi)))
		* (-0.5 * ((pl.col("ranking") - pl.col("mu")) / pl.col("sigma")) ** 2).exp()
	)

	df = (
		store["ranking"]
		.lazy()
		.filter(diff == diff.min())
		.group_by("animal_id")
		.agg(pl.last("mu"), pl.last("sigma"))
		.join(x_df, how="cross")
		.with_columns(pdf_expression.alias("probability_density"))
		.select("animal_id", "ranking", "probability_density")
		.sort("animal_id")
	).collect(engine="in-memory")

	return df


def prep_network_dominance(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
) -> tuple[pl.DataFrame]:
	"""Return a tuple of (edges, nodes) dataframes representing chasing interactions and final rankings."""
	join_df = pl.LazyFrame(
		data=(product(animals, animals)),
		schema=[
			("target", pl.Enum(animals)),
			("source", pl.Enum(animals)),
		],
	)

	connections = (
		store["chasings_df"]
		.lazy()
		.filter(pl.col("day").is_between(*days_range))
		.group_by("chased", "chaser")
		.agg(pl.sum("chasings"))
		.join(
			join_df,
			left_on=["chaser", "chased"],
			right_on=["source", "target"],
			how="right",
		)
		.fill_null(0)
		.sort("target", "source")  # necessary for deterministic output
	).collect(engine="in-memory")

	diff = (pl.col("day") - days_range[-1]).abs()

	nodes = (
		store["ranking"]
		.filter(diff == diff.min())  # Get last valid day with update to rank
		.group_by("animal_id")
		.agg(pl.last("ordinal"))
	)

	return connections, nodes


def prep_chasings_heatmap(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
	phase_type: list[str],
	agg_switch: Literal["mean", "sum"],
) -> np.ndarray:
	"""Pivot chasing interactions into a chaser-vs-chased matrix for heatmap visualization."""
	join_df = pl.LazyFrame(
		(product(animals, animals)),
		schema=[
			("chased", pl.Enum(animals)),
			("chaser", pl.Enum(animals)),
		],
	)

	match agg_switch:
		case "sum":
			agg_func = pl.when(pl.len() > 0).then(pl.sum("chasings")).alias("sum")
		case "mean":
			agg_func = pl.mean("chasings").alias("mean")

	img = (
		store["chasings_df"]
		.lazy()
		.sort("chased", "chaser")
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by(["chaser", "chased"], maintain_order=True)
		.agg(agg_func)
		.join(join_df, on=["chaser", "chased"], how="right")
		.collect(engine="in-memory")
		.pivot(
			on="chaser",
			index="chased",
			values=agg_switch,
		)
		.drop("chased")
		.select(animals)
	)

	return img.to_numpy()


def prep_chasings_line(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
) -> pl.DataFrame:
	"""Calculate hourly chasing aggregates including mean and SEM for time-series plotting."""
	n_days = len(range(*days_range)) + 1

	join_df = pl.LazyFrame(
		(
			product(
				animals,
				animals,
				list(range(24)),
				list(range(days_range[0], days_range[-1] + 1)),
			)
		),
		schema=[
			("chased", pl.Enum(animals)),
			("chaser", pl.Enum(animals)),
			("hour", pl.Int8()),
			("day", pl.Int16()),
		],
	)

	df = (
		store["chasings_df"]
		.lazy()
		.filter(pl.col("day").is_between(*days_range))
		.join(
			join_df,
			on=["chaser", "chased", "hour", "day"],
			how="right",
		)
		.group_by("day", "hour", "chaser")
		.agg(pl.sum("chasings"))
		.group_by("hour", "chaser")
		.agg(
			pl.sum("chasings").alias("total"),
			pl.mean("chasings").alias("mean"),
			(pl.std("chasings") / math.sqrt(n_days)).alias("sem"),
		)
		.with_columns(
			(pl.col("mean") - pl.col("sem")).alias("lower"),
			(pl.col("mean") + pl.col("sem")).alias("upper"),
		)
		.sort("chaser", "hour")
	).collect(engine="in-memory")

	return df


def prep_activity(
	store: dict[str, pl.DataFrame],
	days_range: list[int, int],
	phase_type: list[str],
	animals: list[str],
	positions: list[str],
) -> pl.DataFrame:
	"""Aggregate visits and time spent per position, animal, and day."""
	df = (
		store["activity_df"]
		.lazy()
		.with_columns(pl.col("position").cast(pl.String))
		.filter(pl.col("phase").is_in(phase_type), pl.col("day").is_between(*days_range))
		.group_by(["day", "animal_id", "position"])
		.agg(
			pl.sum("visits_to_position").alias("visits"),
			pl.sum("time_in_position").alias("time"),
		)
		.sort(["animal_id", "position"])
		.fill_null(0)
	).collect(engine="in-memory")

	return df


def prep_activity_line(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
) -> pl.DataFrame:
	"""Calculate hourly detection rates and SEM to track activity levels over time."""
	n_days = len(range(*days_range)) + 1

	join_df = pl.LazyFrame(
		(
			product(
				animals,
				list(range(days_range[0], days_range[1] + 1)),
				list(range(24)),
			)
		),
		schema=[
			("animal_id", pl.Enum(animals)),
			("day", pl.Int16()),
			("hour", pl.Int8()),
		],
	)

	df = (
		store["main_df"]
		.lazy()
		.filter(pl.col("day").is_between(*days_range))
		.group_by("day", "hour", "animal_id")
		.agg(pl.len().alias("n_detections"))
		.join(
			join_df,
			on=["animal_id", "hour", "day"],
			how="right",
		)
		.group_by("hour", "animal_id")
		.agg(
			pl.sum("n_detections").alias("total"),
			pl.mean("n_detections").alias("mean"),
			(pl.std("n_detections") / math.sqrt(n_days)).alias("sem"),
		)
		.with_columns(
			(pl.col("mean") - pl.col("sem")).alias("lower"),
			(pl.col("mean") + pl.col("sem")).alias("upper"),
		)
		.sort("animal_id", "hour")
	).collect(engine="in-memory")

	return df


def prep_time_per_cage(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
	agg_switch: Literal["mean", "sum"],
	cages: list[str],
) -> np.ndarray:
	"""Pivot time spent in specific cages into an hourly format for heatmaps plots."""
	join_df = pl.LazyFrame(
		(
			product(
				list(range(24)),
				cages,
				animals,
			)
		),
		schema=[
			("hour", pl.Int8()),
			("cage", pl.Categorical()),
			("animal_id", pl.Enum(animals)),
		],
	)

	match agg_switch:
		case "sum":
			agg_func = (pl.sum("time_spent"),)
		case "mean":
			agg_func = (pl.mean("time_spent"),)

	img = (
		store["cage_occupancy"]
		.lazy()
		.filter(pl.col("day").is_between(*days_range))
		.sort("day", "hour")
		.group_by(["cage", "animal_id", "hour"], maintain_order=True)
		.agg(agg_func)
		.join(
			join_df,
			on=["hour", "cage", "animal_id"],
			how="right",
		)
		.collect(engine="in-memory")
		.pivot(
			on="hour",
			index=["cage", "animal_id"],
			values="time_spent",
		)
		.drop("cage", "animal_id")
	)

	return img.to_numpy().reshape(len(cages), len(animals), 24)


def prep_pairwise_sociability(
	store: dict[str, pl.DataFrame],
	phase_type: list[str],
	animals: list[str],
	days_range: list[int, int],
	agg_switch: Literal["mean", "sum"],
	pairwise_switch: Literal["pairwise_encounters", "time_together"],
	cages: list[str],
) -> np.ndarray:
	"""Generate a pivot table of pairwise encounters or shared time between animals per location."""
	join_df = pl.LazyFrame(
		product(cages, animals, animals),
		schema=[
			("position", pl.Categorical()),
			("animal_id", pl.Enum(animals)),
			("animal_id_2", pl.Enum(animals)),
		],
	)

	img = (
		store["pairwise_meetings"]
		.lazy()
		.with_columns(pl.col(pairwise_switch).round(2))
		.filter(
			pl.col("phase").is_in(phase_type),
			pl.col("day").is_between(*days_range),
		)
		.group_by(["animal_id", "animal_id_2", "position"], maintain_order=True)
		.agg(
			pl.sum(pairwise_switch).alias("sum"),
			pl.mean(pairwise_switch).alias("mean"),
		)
		.join(
			join_df,
			on=["position", "animal_id", "animal_id_2"],
			how="right",
		)
		.collect(engine="in-memory")
		.pivot(
			on="animal_id_2",
			index=["position", "animal_id"],
			values=agg_switch,
		)
		.drop("position", "animal_id")
	)

	return img.to_numpy().reshape(len(cages), len(animals), len(animals))


def prep_within_cohort_sociability(
	store: dict[str, pl.DataFrame],
	phase_type: list[str],
	animals: list[str],
	days_range: list[int, int],
	sociability_switch: Literal["raw", "normalized"] = "sociability",
) -> np.ndarray:
	"""Calculate and pivot the mean sociability scores between all animal pairs within a cohort."""
	join_df = pl.LazyFrame(
		product(animals, animals),
		schema=[
			("animal_id", pl.Enum(animals)),
			("animal_id_2", pl.Enum(animals)),
		],
	)
	img = (
		store["incohort_sociability"]
		.lazy()
		.with_columns(pl.col(sociability_switch).round(3))
		.filter(
			pl.col("phase").is_in(phase_type),
			pl.col("day").is_between(*days_range),
		)
		.group_by(["animal_id", "animal_id_2"], maintain_order=True)
		.agg(pl.mean(sociability_switch).alias("mean"))
		.join(
			join_df,
			on=["animal_id", "animal_id_2"],
			how="right",
		)
		.collect(engine="in-memory")
		.pivot(
			on="animal_id_2",
			index="animal_id",
			values="mean",
		)
		.drop("animal_id")
	)

	return img.to_numpy().reshape(len(animals), len(animals))


def prep_time_alone(
	store: dict[str, pl.DataFrame],
	phase_type: list[str],
	days_range: list[int, int],
) -> pl.DataFrame:
	"""Filter the time spent alone for the specified phases and day range."""
	df = (
		store["time_alone"]
		.filter(
			pl.col("phase").is_in(phase_type),
			pl.col("day").is_between(*days_range),
		)
		.sort("cage")
	)

	return df


def prep_network_sociability(
	store: dict[str, pl.DataFrame],
	animals: list[str],
	days_range: list[int, int],
) -> pl.DataFrame:
	"""Return a dataframe of edges representing time spent together."""
	join_df = pl.LazyFrame(
		data=(combinations(animals, 2)),
		schema=[
			("source", pl.Enum(animals)),
			("target", pl.Enum(animals)),
		],
	)

	connections = (
		store["incohort_sociability"]
		.lazy()
		.filter(pl.col("day").is_between(*days_range))
		.group_by("animal_id", "animal_id_2")
		.agg(pl.sum("sociability"))
		.join(
			join_df,
			left_on=["animal_id", "animal_id_2"],
			right_on=["source", "target"],
			how="right",
		)
		.sort("source", "target")  # Order is necesarry for deterministic result of node position
		.fill_null(0)
	).collect(engine="in-memory")

	return connections
