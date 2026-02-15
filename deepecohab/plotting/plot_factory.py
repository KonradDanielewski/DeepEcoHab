from typing import Literal

import networkx as nx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from deepecohab.utils import auxfun_plots


def plot_activity(
	df: pl.DataFrame,
	colors: np.ndarray,
	type_switch: Literal["visits", "time"],
	agg_switch: Literal["sum", "mean"],
) -> go.Figure:
	"""Plots bar graph of sum of cage and tunnel visits or time spent."""
	match type_switch:
		case "visits":
			position_title = "<b>Visits to each position</b>"
			position_y_title = "<b>Number of visits</b>"
		case "time":
			position_title = "<b>Time spent in each position</b>"
			position_y_title = "<b>Time spent [s]</b>"

	match agg_switch:
		case "sum":
			# NOTE: Investigate inconsistent px.histogram behavior (if position and animal_id swaped it works as expected)
			# Currently needs this group_by to present as necessary and px.bar
			df = df.group_by("animal_id", "position", maintain_order=True).agg(pl.sum(type_switch))
			fig = px.bar(
				df,
				x="position",
				y=type_switch,
				color="animal_id",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "position", type_switch],
				title=position_title,
				barmode="group",
			)
			fig.update_layout(barcornerradius=10)
			fig.update_traces(marker_line_width=0)
		case "mean":
			fig = px.box(
				df,
				x="position",
				y=type_switch,
				color="animal_id",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "position", "day", type_switch],
				title=position_title,
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	fig.update_layout(legend=dict(title="<b>Animal ID</b>"))
	fig.update_xaxes(title_text="<b>Position</b>")
	fig.update_yaxes(title_text=position_y_title)

	return fig


def plot_time_alone(
	df: pl.DataFrame, colors: list[str], agg_switch: Literal["mean", "sum"]
) -> go.Figure:
	"""Plot time alone as a relative bar plot TODO: consider normalization
	for visualization and hover info with real value"""
	match agg_switch:
		case "sum":
			fig = px.histogram(
				df,
				x="cage",
				y="time_alone",
				color="animal_id",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "cage", "day", "time_alone"],
				title="<b>Time spent alone</b>",
				barmode="group",
			)
		case "mean":
			fig = px.box(
				df,
				x="cage",
				y="time_alone",
				color="animal_id",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "cage", "day", "time_alone"],
				title="<b>Time spent alone</b>",
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	fig.update_xaxes(title_text="<b>Animal ID</b>")
	fig.update_yaxes(title_text="<b>Time alone [s]</b>")
	fig.update_layout(barcornerradius=10)

	return fig


def plot_sum_line_per_hour(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int]],
	input_type: Literal["activity", "chasings"],
) -> go.Figure:
	"""Plots line graph for activity or chasings."""

	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "<b>Antenna detections</b>"
			color_col = "animal_id"
			legend_title = "<b>Animal ID</b>"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "<b># of chasing events</b>"
			color_col = "chaser"
			legend_title = "<b>Chaser</b>"

	fig = px.line(
		df,
		x="hour",
		y="total",
		color=color_col,
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
		category_orders={color_col: animals},
		line_shape="spline",
		title=title,
	)

	fig.update_layout(legend=dict(title=legend_title))
	fig.update_yaxes(title=y_axes_label)
	fig.update_xaxes(title="<b>Hour of day</b>", range=[0, 23])

	return fig


def plot_mean_line_per_hour(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[str],
	input_type: Literal["activity", "chasings"],
) -> go.Figure:
	"""Plots line graph for activity or chasings with SEM shading."""

	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "<b>Antenna detections</b>"
			animal_col = "animal_id"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "<b># of chasing events</b>"
			animal_col = "chaser"

	fig = go.Figure()

	for animal, color in zip(animals, colors):
		animal_df = df.filter(pl.col(animal_col) == animal)

		x = animal_df["hour"].to_list()
		x_rev = x[::-1]
		y = animal_df["mean"].to_list()
		y_upper = animal_df["upper"].to_list()
		y_lower = animal_df["lower"].to_list()[::-1]

		shade_color = color.replace("rgb", "rgba").replace(")", ", 0.2)")  # shaded region is SEM

		fig.add_trace(
			go.Scatter(
				x=x + x_rev,
				y=y_upper + y_lower,
				fill="toself",
				fillcolor=shade_color,
				line_color="rgba(255,255,255,0)",
				showlegend=False,
				name=animal,
				legendgroup=animal,
				line=dict(shape="spline"),
			)
		)

		fig.add_trace(
			go.Scatter(
				x=x,
				y=y,
				line_color=color,
				name=animal,
				legendgroup=animal,
				line=dict(shape="spline"),
			)
		)

	fig.update_layout(
		title=title,
		legend=dict(
			title="<b>Animal ID</b>",
			tracegroupgap=0,
		),
	)
	fig.update_yaxes(title=y_axes_label)
	fig.update_xaxes(title="<b>Hour of day</b>")

	return fig


def plot_ranking_line(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int, float]],
) -> go.Figure:
	"""Plots line graph of ranking over time."""
	fig = px.line(
		df,
		x="datetime",
		y="ordinal",
		color="animal_id",
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
	)

	fig.update_layout(
		title="<b>Social dominance ranking in time</b>",
		legend=dict(
			title="<b>Animal ID</b>",
			tracegroupgap=0,
		),
		xaxis=dict(title="<b>Timeline</b>"),
		yaxis=dict(
			title="<b>Ranking</b>",
		),
	)

	return fig


def plot_ranking_distribution(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int, float]],
) -> go.Figure:
	"""Plots line graph of ranking distribution with shaded area."""
	fig = px.line(
		df,
		x="ranking",
		y="probability_density",
		color="animal_id",
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
		hover_data=["animal_id", "ranking", "probability_density"],
	)
	fig.update_traces(fill="tozeroy")

	fig.update_layout(
		title="<b>Ranking probability distribution</b>",
		xaxis=dict(
			title="<b>Ranking</b>",
		),
		yaxis=dict(
			title="<b>Probability density</b>",
		),
		legend=dict(
			title="<b>Animal ID</b>",
			tracegroupgap=0,
		),
	)

	return fig


def plot_ranking_stability(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int, float]],
) -> go.Figure:
	"""Plots animal rank on a per day basis"""
	color_map = {animal: color for animal, color in zip(animals, colors)}

	fig = go.Figure(
		layout=dict(
			title_x=0.5,
			title="<b>Daily dominance rank Trajectories</b>",
			legend_title_text="<b>Animal ID</b>",
			yaxis=dict(
				title="<b>Rank</b>",
				autorange="reversed",
				type="category",
				categoryorder="array",
				categoryarray=df["rank"].unique().sort(),
			),
			xaxis=dict(
				title="<b>Day</b>",
			),
		)
	)
	for animal in animals:
		temp = df.filter(pl.col("animal_id") == animal).sort("day")
		fig.add_trace(
			go.Scatter(
				x=temp["day"],
				y=temp["rank"],
				mode="lines+markers",
				name=animal,
				line=dict(color=color_map[animal]),
				marker=dict(color=color_map[animal]),
			)
		)

	return fig


def time_spent_per_cage(
	img: np.ndarray,
	animals: list[str],
) -> go.Figure:
	"""Plots N-cages of heatmaps with per hour time spent for each animal"""
	fig = px.imshow(
		img,  # 24 hours in a day,
		y=animals,
		facet_col=0,
		facet_col_wrap=2,
		title="<b>Time spent per cage</b>",
	)

	for annotation in fig.layout.annotations:
		annotation["text"] = f"<b>Cage {int(annotation['text'].split('=')[1]) + 1}</b>"

	fig.update_layout(xaxis=dict(title="Hour of day"), xaxis2=dict(title="Hour of day"))

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"Hour: %{x}",
				"Animal ID: %{y}",
				"Time [s]: %{z}",
			]
		)
	)

	return fig


def plot_chasings_heatmap(
	img: np.ndarray,
	animals: list[str],
) -> go.Figure:
	"""Plots heatmap for number of chasings."""
	z_label = "Number: %{z}"

	fig = px.imshow(
		img,
		x=animals,
		y=animals,
		zmin=0,
		color_continuous_scale="Viridis",
		title="<b>Number of chasings</b>",
	)

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"Chaser: %{x}",
				"Chased: %{y}",
				z_label,
			]
		)
	)

	return fig


def plot_sociability_heatmap(
	img: np.ndarray,
	type_switch: Literal["pairwise_encounters", "time_together"],
	animals: list[str],
) -> go.Figure:
	"""Plots heatmaps for pairwise encounters or time spent together."""
	match type_switch:
		case "pairwise_encounters":
			pairwise_title = "<b>Number of pairwise encounters</b>"
			pairwise_z_label = "<b>Number: %{z}</b>"
		case "time_together":
			pairwise_title = "<b>Time spent together</b>"
			pairwise_z_label = "<b>Time [s]: %{z}</b>"

	fig = px.imshow(
		img,
		zmin=0,
		x=animals,
		y=animals,
		facet_col=0,
		facet_col_wrap=2,
		color_continuous_scale="Viridis",
		title=pairwise_title,
	)

	for annotation in fig.layout.annotations:
		annotation["text"] = f"<b>Cage {int(annotation['text'].split('=')[1]) + 1}</b>"

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"X: %{x}",
				"Y: %{y}",
				pairwise_z_label,
			]
		)
	)

	return fig


def plot_within_cohort_heatmap(
	img: np.ndarray,
	animals: list[str],
	sociability_switch: Literal["proportion_together", "sociability"],
) -> go.Figure:
	"""Plots heatmap for within-cohort sociability."""
	match sociability_switch:
		case "proportion_together":
			title = "<b>Proportional time spent together</b>"
		case "sociability":
			title = "<b>Within-cohort sociability</b>"

	fig = px.imshow(
		img,
		zmin=0,
		x=animals,
		y=animals,
		color_continuous_scale="Viridis",
		title=title,
	)

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"X: %{x}",
				"Y: %{y}",
				"Sociability: %{z}",
			]
		)
	)

	return fig


def plot_metrics_polar(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[str],
) -> go.Figure:
	"""Plots a polar line with different metrics per animal."""
	fig = px.line_polar(
		df,
		r="value",
		theta="metric",
		color="animal_id",
		line_close=True,
		line_shape="spline",
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
		range_r=[df["value"].min() - 0.5, df["value"].max() + 0.5],
		title="<b>Animal feature overview</b>",
	)

	fig.update_polars(bgcolor="rgba(0,0,0,0)")
	fig.update_layout(title_y=0.95, legend_title_text="<b>Animal ID</b>", title_x=0.45)

	return fig


def plot_network_graph(
	connections: pl.DataFrame,
	nodes: pl.DataFrame | None,
	animals: list[str],
	colors: list[str],
	graph_type: Literal["chasings", "proportion_together"],
) -> go.Figure:
	"""Plots network graph of social structure."""
	match graph_type:
		case "chasings":
			edge_weight = "chasings"
			graph = nx.DiGraph
			title = "<b>Dominance network graph</b>"
			include_ranking = True
		case "proportion_together":
			edge_weight = "proportion_together"
			graph = nx.Graph
			title = "<b>Sociability network graph</b>"
			include_ranking = False

	G = nx.from_pandas_edgelist(connections, create_using=graph, edge_attr=edge_weight)
	pos = nx.spring_layout(G, k=0.1, iterations=200, seed=42, weight=edge_weight, method="energy")

	for animal in animals:
		match graph_type:
			case "chasings":
				ordinal = nodes.filter(pl.col("animal_id") == animal).select("ordinal").item()
			case "proportion_together":
				ordinal = 30
		pos[animal] = np.append(pos[animal], ordinal)

	edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_weight=edge_weight)
	node_trace = auxfun_plots.create_node_trace(pos, colors, animals, include_ranking)

	fig = go.Figure(
		data=edge_trace + [node_trace],
		layout=go.Layout(
			showlegend=False,
			hovermode="closest",
			title=dict(text=title, x=0.5, y=0.95),
		),
	)

	fig.update_xaxes(
		showticklabels=False,
		showgrid=False,
		zeroline=False,
	)
	fig.update_yaxes(
		showticklabels=False,
		showgrid=False,
		zeroline=False,
	)

	return fig


def plot_social_stability(
	df: pl.DataFrame | None,
	animals: list[str],
	colors: list[str],
) -> go.Figure:
	"""Plots the stability of a social relationship based on time spent together."""
	fig = px.scatter(
		df,
		x="stability",
		y="proportion_together",
		color="animal_id",
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
		hover_data={"animal_id", "animal_id_2"},
		range_x=[0, 1],
		range_y=[0, 1],
		range_color=[0, 1],
		title="<b>Relationship stability</b>",
	)

	fig.update_layout(
		xaxis=dict(title="<b>Relationship stability</b>"),
		yaxis=dict(title="<b>Median proportion together</b>"),
	)
	fig.update_traces(marker_size=12)

	return fig


def plot_cage_preference(
	df: pl.DataFrame | None,
	cages: list[str],
	colors: list[str],
) -> go.Figure:
	"""Plots cage preference on a per cage basis (cohort preference summary)."""
	fig = px.box(
		df,
		x="position",
		y="time_in_position",
		color="position",
		points="outliers",
		hover_data={"animal_id", "day"},
		color_discrete_map={cage: color for cage, color in zip(cages, colors)},
		title="<b>Cage preference</b>",
	)

	fig.update_traces(boxmean=True)
	fig.update_yaxes(title_text="<b>Avg time per day [h]</b>")
	fig.update_xaxes(title_text="<b>Cages</b>")
	fig.update_layout(legend=dict(title=""))

	return fig
