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
) -> tuple[go.Figure, pl.DataFrame]:
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
			fig = px.histogram(
				df,
				x="animal_id",
				y=type_switch,
				color="position",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "position", "day", type_switch],
				title=position_title,
				barmode="group",
			)
			fig.update_layout(barcornerradius=10)
		case "mean":
			fig = px.box(
				df,
				x="animal_id",
				y=type_switch,
				color="position",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "position", "day", type_switch],
				title=position_title,
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	fig.update_xaxes(title_text="<b>Animal ID</b>")
	fig.update_yaxes(title_text=position_y_title)

	return fig, df


def plot_time_alone(
	df: pl.DataFrame, colors: list[str], agg_switch: Literal["mean", "sum"]
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plot time alone as a relative bar plot TODO: consider normalization
	for visualization and hover info with real value"""
	match agg_switch:
		case "sum":
			fig = px.histogram(
				df,
				x="animal_id",
				y="time_alone",
				color="cage",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "cage", "day", "time_alone"],
				title="Time spent alone",
				barmode="group",
			)
		case "mean":
			fig = px.box(
				df,
				x="animal_id",
				y="time_alone",
				color="cage",
				color_discrete_sequence=colors,
				hover_data=["animal_id", "cage", "day", "time_alone"],
				title="Time spent alone",
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	fig.update_xaxes(title_text="<b>Animal ID</b>")
	fig.update_yaxes(title_text="<b>Time alone [s]</b>")
	fig.update_layout(barcornerradius=10)

	return fig, df


def plot_sum_line_per_hour(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int]],
	input_type: Literal["activity", "chasings"],
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots line graph for activity or chasings."""

	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "Antenna detections"
			color_col = "animal_id"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "# of chasing events"
			color_col = "chaser"

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
	fig.update_yaxes(title=y_axes_label)
	fig.update_xaxes(title="<b>Hours</b>", range=[0, 23])

	return fig, df


def plot_mean_line_per_hour(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[str],
	input_type: Literal["activity", "chasings"],
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots line graph for activity or chasings with SEM shading."""

	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "Antenna detections"
			animal_col = "animal_id"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "# of chasing events"
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
			title="animal_id",
			tracegroupgap=0,
		),
	)
	fig.update_yaxes(title=y_axes_label)
	fig.update_xaxes(title="<b>Hours</b>")

	return fig, df


def plot_ranking_line(
	df: pl.DataFrame,
	colors,
	animals,
) -> tuple[go.Figure, pl.DataFrame]:
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
			title="animal_id",
			tracegroupgap=0,
		),
		xaxis=dict(title="Timeline"),
		yaxis=dict(
			title="Ranking",
		),
	)

	return fig, df

def plot_ranking_over_days(
	df: pl.DataFrame,
	colors,
	animals,
) -> tuple[go.Figure, pl.DataFrame]:

	fig = px.line(
		df,
		x="day",
		y="ordinal",
		color="animal_id",
		color_discrete_map={animal: color for animal, color in zip(animals, colors)},
		line_shape="spline",
	)

	fig.update_layout(
		title="<b>Social dominance ranking over days</b>",
		xaxis=dict(title="Day"),
		yaxis=dict(title="Mean rank"),
	)

	return fig, df


def plot_ranking_distribution(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[tuple[int, int, int, float]],
) -> tuple[go.Figure, pl.DataFrame]:
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
			title="Ranking",
		),
		yaxis=dict(
			title="Probability density",
		),
		legend=dict(
			title="animal_id",
			tracegroupgap=0,
		),
	)

	return fig, df

def plot_ranking_stability(
    df: pl.DataFrame,
    colors: list[str],
    animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
    #Plot daily dominance rank trajectories (rank stability across days).

    fig = go.Figure()

    df = df.sort(["animal_id", "day"])

    for animal, color in zip(animals, colors):
        animal_df = df.filter(pl.col("animal_id") == animal)

        fig.add_trace(
            go.Scatter(
                x=animal_df["day"].to_list(),
                y=animal_df["rank"].to_list(),
                mode="lines+markers",
                name=animal,
                line=dict(color=color),
                legendgroup=animal,
            )
        )

    fig.update_layout(
        title="<b>Daily dominance rank trajectories</b>",
        legend=dict(
            title="animal_id",
            tracegroupgap=0,
        ),
        xaxis=dict(title="Day"),
        yaxis=dict(
            title="Rank (1 = most dominant)",
            autorange="reversed",
        ),
    )

    return fig, df


def time_spent_per_cage(
	img: np.ndarray,
	animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots N-cages of heatmaps with per hour time spent for each animal"""
	fig = px.imshow(
		img,  # 24 hours in a day,
		y=animals,
		facet_col=0,
		facet_col_wrap=2,
		title="<b>Time spent per cage</b>",
	)

	for annotation in fig.layout.annotations:
		annotation["text"] = f"Cage {int(annotation['text'].split('=')[1]) + 1}"

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"Hour: %{x}",
				"Animal ID: %{y}",
				"Time [s]: %{z}",
			]
		)
	)

	return fig, img


def plot_chasings_heatmap(
	img: np.ndarray,
	animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
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

	return fig, img


def plot_sociability_heatmap(
	img: np.ndarray,
	type_switch: Literal["pairwise_encounters", "time_together"],
	animals: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots heatmaps for pairwise encounters or time spent together."""
	match type_switch:
		case "pairwise_encounters":
			pairwise_title = "<b>Number of pairwise encounters</b>"
			pairwise_z_label = "Number: %{z}"
		case "time_together":
			pairwise_title = "<b>Time spent together</b>"
			pairwise_z_label = "Time [s]: %{z}"

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
		annotation["text"] = f"Cage {int(annotation['text'].split('=')[1]) + 1}"

	fig.update_traces(
		hovertemplate="<br>".join(
			[
				"X: %{x}",
				"Y: %{y}",
				pairwise_z_label,
			]
		)
	)

	return fig, img


def plot_within_cohort_heatmap(
	img: np.ndarray, animals: list[str]
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots heatmap for within-cohort sociability."""
	fig = px.imshow(
		img,
		zmin=0,
		x=animals,
		y=animals,
		color_continuous_scale="Viridis",
		title="<b>Within-cohort sociability</b>",
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

	return fig, img


def plot_metrics_polar(
	df: pl.DataFrame,
	animals: list[str],
	colors: list[str],
) -> tuple[go.Figure, pl.DataFrame]:
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
		title="<b>Social dominance metrics</b>",
	)

	fig.update_polars(bgcolor="rgba(0,0,0,0)")
	fig.update_layout(title_y=0.95, title_x=0.45)

	return fig, df


def plot_network_graph(
	connections: pl.DataFrame,
	nodes: pl.DataFrame | None,
	animals,
	colors,
	graph_type: Literal["chasings", "sociability"],
) -> tuple[go.Figure, pl.DataFrame]:
	"""Plots network graph of social structure."""
	match graph_type:
		case "chasings":
			edge_weight = "chasings"
			graph = nx.DiGraph
			title = "<b>Dominance network graph</b>"
		case "sociability":
			edge_weight = "sociability"
			graph = nx.Graph
			title = "<b>Sociability network graph</b>"

	G = nx.from_pandas_edgelist(connections, create_using=graph, edge_attr=edge_weight)
	pos = nx.spring_layout(G, k=0.1, iterations=200, seed=42, weight=edge_weight, method="energy")

	for animal in animals:
		match graph_type:
			case "chasings":
				ordinal = nodes.filter(pl.col("animal_id") == animal).select("ordinal").item()
			case "sociability":
				ordinal = 20
		pos[animal] = np.append(pos[animal], ordinal)

	edge_trace = auxfun_plots.create_edges_trace(G, pos, edge_weight=edge_weight)
	node_trace = auxfun_plots.create_node_trace(pos, colors, animals)

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

	return fig, connections
