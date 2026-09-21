import math
from typing import Literal

import networkx as nx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from deepecohab.plotting.animals import ColorMapping, collapse_legend
from deepecohab.plotting.prepare import Heatmap
from deepecohab.plotting.theme import AURORA, sample_palette


def _tick_labels(names: list[str]) -> list[str]:
	"""Turn snake_case position names into axis tick text."""
	return [name.capitalize().replace("_", " ") for name in names]


def _phase_markers(figure: go.Figure, phases: dict[str, float]) -> None:
	"""Mark the phase switch on an hour axis that begins at the first phase's onset.

	A single thin line, styled by the active template's shape defaults so it reads
	on either ground without competing with the Phase-coloured traces.
	"""
	switch = max(phases.values())

	figure.add_vline(x=switch, line_width=1.5)
	figure.update_layout(xaxis={"dtick": 1})


#: Where a span's label sits, as an (x-anchor, y, y-anchor) triple - the annotation
#: equivalent of the shape-label textposition it replaces.
_CORNERS: tuple[tuple[float, str], ...] = ((1.0, "top"), (0.0, "bottom"), (0.5, "middle"))


def _event_spans(figure: go.Figure, spans: pl.DataFrame, facets: list[str] | None = None) -> None:
	"""Shade where each event falls on a time axis, coloured and labelled by event.

	An event's colour comes from its place among the recording's events, so it is the
	same on every plot. On a faceted figure - one panel per cage - a span with a position
	is drawn only on that cage's panel; without panels it is labelled with its cages
	instead. The faceted figures are heatmaps, where a fill would tint the colour scale,
	so there the spans are outlined.

	The span itself is a shape, behind the data; its label is a separate annotation
	named ``event-label``, which plotly always draws in front of traces, at the same
	corner a shape label would have used.
	"""
	if spans.is_empty():
		return

	palette = px.colors.qualitative.Pastel

	if facets is None:
		# With no panel per cage, bouts of one event in different cages share a span.
		spans = spans.group_by("event", "x0", "x1", maintain_order=True).agg(
			pl.col("position").drop_nulls().unique().sort().str.join(", ")
		)
		panels: list[tuple[str, str, str | None]] = [("x", "y", None)]
	else:
		panels = [
			(trace.xaxis, trace.yaxis, facet)
			for facet, trace in zip(facets, figure.data, strict=True)
		]

	# An Enum's physical code is the event's place among the recording's events.
	for span in spans.with_columns(index=pl.col("event").to_physical()).iter_rows(named=True):
		index = span["index"]
		color = palette[index % len(palette)]
		# Overlapping events would stack their labels, so each event takes its own corner.
		y, yanchor = _CORNERS[index % len(_CORNERS)]

		if facets is None:
			text = f"{span['event']} ({span['position']})" if span["position"] else span["event"]
			font = {"size": 10}
			shape_style = {
				"fillcolor": color.replace("rgb", "rgba").replace(")", ", 0.25)"),
				"line_width": 0,
				"layer": "below",
			}
		else:
			text = span["event"]
			font = {"size": 10, "color": color}
			shape_style = {"line_color": color, "line_width": 2, "layer": "above"}

		for xaxis, yaxis, facet in panels:
			if facet is not None and span["position"] not in (None, facet):
				continue

			figure.add_shape(
				type="rect",
				name="event-span",
				xref=xaxis,
				yref=f"{yaxis} domain",
				x0=span["x0"],
				x1=span["x1"],
				y0=0,
				y1=1,
				**shape_style,
			)
			figure.add_annotation(
				name="event-label",
				x=span["x0"],
				y=y,
				xref=xaxis,
				yref=f"{yaxis} domain",
				xanchor="left",
				yanchor=yanchor,
				text=text,
				showarrow=False,
				font=font,
			)


def _faceted_heatmap(
	heatmap: Heatmap,
	title: str,
	x_title: str,
	y_title: str,
	hover: tuple[str, str],
	*,
	square: bool = False,
	grid: bool = False,
) -> go.Figure:
	"""Draw one heatmap panel per facet, in reading order.

	Stacked one per row by default, sharing the x axis - the panels are then a day or
	an hour against animals, so lining their columns up matters. ``grid`` instead packs
	the panels into a roughly square grid, for panels - like a pairwise matrix - with no
	axis to share across facets. Every facet has the same labels, so only the outer
	panels carry tick labels.

	A single shared colour axis keeps the panels comparable, which is also why these
	figures offer one scope - cages or tunnels - at a time (§ Cage / tunnel scope).
	"""
	n = len(heatmap.facets)
	cols = math.ceil(math.sqrt(n)) if grid else 1
	rows = math.ceil(n / cols)
	figure = make_subplots(
		rows=rows,
		cols=cols,
		shared_xaxes=not grid,
		vertical_spacing=min(0.12, 1 / max(rows - 1, 1)),
		horizontal_spacing=0.1,
		subplot_titles=[f"<b>{name.capitalize().replace('_', ' ')}</b>" for name in heatmap.facets],
	)

	value = "%{z}" if heatmap.text is None else "%{customdata}"
	hovertemplate = f"{hover[0]}: %{{x}}<br>{hover[1]}: %{{y}}<br>Value: {value}<extra></extra>"

	for index, values in enumerate(heatmap.values):
		row, col = divmod(index, cols)
		figure.add_trace(
			go.Heatmap(
				z=values,
				x=[str(label) for label in heatmap.x],
				y=heatmap.y,
				customdata=heatmap.text[index] if heatmap.text is not None else None,
				coloraxis="coloraxis",
				hovertemplate=hovertemplate,
			),
			row=row + 1,
			col=col + 1,
		)
		figure.update_xaxes(showticklabels=index + cols >= n, row=row + 1, col=col + 1)
		figure.update_yaxes(showticklabels=col == 0, row=row + 1, col=col + 1)

	figure.update_xaxes(automargin=True)
	figure.update_xaxes(title_text=x_title, row=rows, col=1)
	figure.update_yaxes(title_text=y_title, automargin=True)
	figure.update_layout(
		title=title,
		coloraxis={
			"cmin": 0,
			"colorscale": AURORA,
			"colorbar": {"title": {"text": heatmap.label}},
		},
	)

	if square:
		# Each panel is animal-by-animal; a shared scale keeps its cells square instead
		# of stretched across the panel's width. make_subplots numbers axes in the same
		# row-major order this loop places traces in, so the panel at `index` owns axis
		# `index + 1`.
		for index in range(n):
			row, col = divmod(index, cols)
			axis = index + 1
			figure.update_yaxes(
				scaleanchor="x" if axis == 1 else f"x{axis}", scaleratio=1, row=row + 1, col=col + 1
			)
		# Shrink a panel to its cells, under its title, rather than padding empty rows around it,
		# and toward the colour bar rather than leaving a gap before it.
		figure.update_xaxes(constrain="domain", constraintoward="right")
		figure.update_yaxes(constrain="domain", constraintoward="top")

	return figure


def _position_plot(
	frame: pl.DataFrame,
	positions: list[str],
	mapping: ColorMapping,
	*,
	y: str,
	title: str,
	x_title: str,
	y_title: str,
	hover: dict[str, bool],
	agg: Literal["sum", "mean"],
	granularity: str,
) -> go.Figure:
	"""Per-animal values against position: grouped bars for a sum, boxes for a mean."""
	match agg:
		case "sum":
			# px.histogram re-aggregates in the browser and drops customdata with it,
			# so the sum arrives already aggregated and is drawn as plain bars.
			figure = px.bar(
				frame,
				x="position",
				y=y,
				color=mapping.trace_column,
				color_discrete_map=mapping.trace_colors,
				category_orders={mapping.trace_column: mapping.order},
				hover_data=hover,
				title=title,
				barmode="group",
			)
			figure.update_traces(marker_line_width=0)
		case "mean":
			figure = px.box(
				frame,
				x="position",
				y=y,
				color=mapping.trace_column,
				color_discrete_map=mapping.trace_colors,
				category_orders={mapping.trace_column: mapping.order},
				hover_data=hover | {granularity: True},
				title=title,
				boxmode="group",
				points="outliers",
			)
			figure.update_traces(boxmean=True)

	collapse_legend(figure, mapping)
	figure.update_xaxes(
		title_text=x_title,
		tickvals=list(range(len(positions))),
		ticktext=_tick_labels(positions),
	)
	figure.update_yaxes(title_text=y_title)
	figure.update_layout(barcornerradius=10, legend_title_text=mapping.legend_title)

	return figure


def plot_activity(
	frame: pl.DataFrame,
	positions: list[str],
	mapping: ColorMapping,
	metric: Literal["visits", "time"],
	agg: Literal["sum", "mean"],
	granularity: str,
	value_label: str,
) -> go.Figure:
	"""Plots bar or box graph of cage and tunnel visits or time spent."""
	hover = {mapping.trace_column: True, "position": True, metric: True}

	if metric == "time":
		hover |= {metric: False, "time_text": True}

	return _position_plot(
		frame,
		positions,
		mapping,
		y=metric,
		title="<b>Visits to each position</b>"
		if metric == "visits"
		else "<b>Time spent in each position</b>",
		x_title="<b>Position</b>",
		y_title="<b>Number of visits</b>" if metric == "visits" else value_label,
		hover=hover,
		agg=agg,
		granularity=granularity,
	)


def plot_time_alone(
	frame: pl.DataFrame,
	positions: list[str],
	mapping: ColorMapping,
	agg: Literal["mean", "sum"],
	granularity: str,
	value_label: str,
	place: str = "cage",
) -> go.Figure:
	"""Plot time alone per position as a bar or box plot."""
	return _position_plot(
		frame,
		positions,
		mapping,
		y="time_alone",
		title="<b>Time spent alone</b>",
		x_title=f"<b>{place.capitalize()}</b>",
		y_title=value_label,
		hover={
			mapping.trace_column: True,
			"position": True,
			"time_alone": False,
			"time_alone_text": True,
		},
		agg=agg,
		granularity=granularity,
	)


def plot_sum_line_per_hour(
	frame: pl.DataFrame,
	mapping: ColorMapping,
	input_type: Literal["activity", "chasings"],
	phases: dict[str, float],
	spans: pl.DataFrame,
) -> go.Figure:
	"""Plots hourly totals for activity or chasings."""
	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "<b>Antenna detections</b>"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "<b># of chasing events</b>"

	figure = px.line(
		frame,
		x="hour",
		y="total",
		color=mapping.trace_column,
		color_discrete_map=mapping.trace_colors,
		category_orders={mapping.trace_column: mapping.order},
		line_shape="spline",
		title=title,
	)

	collapse_legend(figure, mapping)
	figure.update_layout(legend={"title": mapping.legend_title})
	figure.update_yaxes(title=y_axes_label)
	figure.update_xaxes(title="<b>Hour since phase onset</b>", range=[-0.5, 23.5])
	figure.update_traces(mode="lines")
	_phase_markers(figure, phases)
	_event_spans(figure, spans)

	return figure


def plot_mean_line_per_hour(
	frame: pl.DataFrame,
	mapping: ColorMapping,
	input_type: Literal["activity", "chasings"],
	phases: dict[str, float],
	spans: pl.DataFrame,
) -> go.Figure:
	"""Plots hourly means for activity or chasings with SEM shading."""
	match input_type:
		case "activity":
			title = "<b>Activity over time</b>"
			y_axes_label = "<b>Antenna detections</b>"
			hover_label = "Detections"
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "<b># of chasing events</b>"
			hover_label = "Events"

	figure = go.Figure()

	for trace_value in mapping.order:
		trace_rows = frame.filter(pl.col(mapping.trace_column) == trace_value)
		if trace_rows.is_empty():
			continue
		color = mapping.trace_colors[trace_value]

		x = trace_rows["hour"].to_list()
		y = trace_rows["mean"].to_list()
		bounds = trace_rows["upper"].to_list() + trace_rows["lower"].to_list()[::-1]
		shade_color = color.replace("rgb", "rgba").replace(")", ", 0.2)")  # shaded region is SEM

		figure.add_trace(
			go.Scatter(
				x=x + x[::-1],
				y=bounds,
				fill="toself",
				fillcolor=shade_color,
				line_color="rgba(255,255,255,0)",
				mode="lines",
				showlegend=False,
				name=trace_value,
				line={"shape": "spline"},
				hoverinfo="skip",
			)
		)

		figure.add_trace(
			go.Scatter(
				x=x,
				y=y,
				mode="lines",
				line_color=color,
				name=trace_value,
				line={"shape": "spline"},
				hovertemplate=(
					f"{mapping.legend_title}: {trace_value}<br>Hour: %{{x}}<br>"
					f"{hover_label}: %{{y:.1f}}<extra></extra>"
				),
			)
		)

	collapse_legend(figure, mapping)
	figure.update_layout(title=title, legend={"title": mapping.legend_title, "tracegroupgap": 0})
	figure.update_yaxes(title=y_axes_label)
	figure.update_xaxes(title="<b>Hour since phase onset</b>")
	_phase_markers(figure, phases)
	_event_spans(figure, spans)

	return figure


def plot_ranking_line(frame: pl.DataFrame, mapping: ColorMapping, spans: pl.DataFrame) -> go.Figure:
	"""Plots line graph of ranking over time."""
	figure = px.line(
		frame,
		x="datetime",
		y="ordinal",
		color=mapping.trace_column,
		color_discrete_map=mapping.trace_colors,
		category_orders={mapping.trace_column: mapping.order},
	)

	collapse_legend(figure, mapping)
	figure.update_layout(
		title="<b>Social dominance ranking in time</b>",
		legend={"title": mapping.legend_title, "tracegroupgap": 0},
		xaxis={"title": "<b>Timeline</b>"},
		yaxis={"title": "<b>Ranking</b>"},
	)
	_event_spans(figure, spans)

	return figure


def plot_ranking_distribution(frame: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots line graph of ranking distribution with shaded area."""
	figure = px.line(
		frame,
		x="ranking",
		y="probability_density",
		color=mapping.trace_column,
		color_discrete_map=mapping.trace_colors,
		category_orders={mapping.trace_column: mapping.order},
		hover_data=[mapping.trace_column, "ranking", "probability_density"],
	)
	figure.update_traces(fill="tozeroy")

	collapse_legend(figure, mapping)
	figure.update_layout(
		title="<b>Ranking probability distribution</b>",
		xaxis={"title": "<b>Ranking</b>"},
		yaxis={"title": "<b>Probability density</b>"},
		legend={"title": mapping.legend_title, "tracegroupgap": 0},
	)

	return figure


def plot_ranking_stability(
	frame: pl.DataFrame,
	mapping: ColorMapping,
	granularity: str,
	spans: pl.DataFrame,
) -> go.Figure:
	"""Plots animal rank on a per day (or per phase) basis."""
	label = "Phase" if granularity == "phase_count" else "Day"
	cadence = "Daily" if granularity == "day" else "Per-phase"

	figure = go.Figure(
		layout={
			"title_x": 0.5,
			"title": f"<b>{cadence} dominance rank trajectories</b>",
			"legend_title_text": mapping.legend_title,
			"yaxis": {
				"title": "<b>Rank</b>",
				"autorange": "reversed",
				"type": "category",
				"categoryorder": "array",
				"categoryarray": frame["rank"].unique().sort(),
			},
			"xaxis": {"title": f"<b>{label}</b>"},
		}
	)

	for trace_value in mapping.order:
		trace_rows = frame.filter(pl.col(mapping.trace_column) == trace_value).sort(granularity)
		if trace_rows.is_empty():
			continue
		color = mapping.trace_colors[trace_value]

		figure.add_trace(
			go.Scatter(
				x=trace_rows[granularity],
				y=trace_rows["rank"],
				mode="lines+markers",
				name=trace_value,
				line={"color": color},
				marker={"color": color},
			)
		)

	collapse_legend(figure, mapping)
	_event_spans(figure, spans)

	return figure


def plot_time_spent_per_cage(
	heatmap: Heatmap,
	kind: Literal["hourly", "daily"],
	spans: pl.DataFrame,
	place: str = "cage",
	granularity: str = "day",
) -> go.Figure:
	"""Plots one heatmap per position of time spent, by hour or by window unit."""
	match kind:
		case "hourly":
			title = f"<b>Time spent per {place}</b>"
			x_title = "<b>Hour since phase onset</b>"
			hover = ("Hour", "Animal ID")
		case "daily":
			label = "Phase" if granularity == "phase_count" else "Day"
			title = f"<b>{place.capitalize()} preference over time</b>"
			x_title = f"<b>{label}</b>"
			hover = (label, "Animal ID")

	figure = _faceted_heatmap(heatmap, title, x_title, "<b>Animal ID</b>", hover)
	# The x axis is categorical, so a bin sits at its index among the columns, not its value.
	_event_spans(figure, spans.with_columns(pl.col("x0", "x1") - heatmap.x[0]), heatmap.facets)

	return figure


def plot_heatmap(
	matrix: np.ndarray,
	animals: list[str],
	title: str,
	hover: tuple[str, str, str],
) -> go.Figure:
	"""Plots a square animal-by-animal matrix.

	Args:
		matrix: rows and columns in ``animals`` order.
		animals: axis labels for both rows and columns.
		title: figure title.
		hover: hover labels for the column, the row and the value.
	"""
	figure = px.imshow(
		matrix, x=animals, y=animals, zmin=0, color_continuous_scale=AURORA, title=title
	)

	column, row, value = hover
	figure.update_traces(hovertemplate=f"{column}: %{{x}}<br>{row}: %{{y}}<br>{value}: %{{z}}")
	# Square cells leave spare width; it goes left of the matrix, not between it and the colour bar.
	figure.update_layout(
		yaxis={"automargin": True}, xaxis={"automargin": True, "constraintoward": "right"}
	)

	return figure


def plot_sociability_heatmap(
	heatmap: Heatmap,
	metric: Literal["pairwise_encounters", "time_together"],
) -> go.Figure:
	"""Plots one pair matrix per cage, of meetings or time spent together."""
	title = (
		"<b>Number of pairwise encounters</b>"
		if metric == "pairwise_encounters"
		else "<b>Time spent together</b>"
	)

	return _faceted_heatmap(heatmap, title, "", "", ("X", "Y"), square=True, grid=True)


def plot_metrics_polar(frame: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots mean z-scores of metrics with SEM shading as a polar plot."""
	figure = go.Figure()

	for trace_value in mapping.order:
		group = frame.filter(pl.col(mapping.trace_column) == trace_value)
		if group.is_empty():
			continue
		color = mapping.trace_colors[trace_value]
		shade_color = color.replace("rgb", "rgba").replace(")", ", 0.2)")

		group_closed = pl.concat([group, group.head(1)])
		theta = group_closed["metric"]

		figure.add_trace(
			go.Scatterpolar(
				r=group_closed["lower"],
				theta=theta,
				mode="lines",
				line={"width": 0, "color": color},
				line_shape="spline",
				showlegend=False,
				hoverinfo="skip",
				name=trace_value,
			)
		)

		figure.add_trace(
			go.Scatterpolar(
				r=group_closed["upper"],
				theta=theta,
				mode="lines",
				fill="tonext",
				fillcolor=shade_color,
				line={"width": 0, "color": color},
				line_shape="spline",
				showlegend=False,
				hoverinfo="skip",
				name=trace_value,
			)
		)

		figure.add_trace(
			go.Scatterpolar(
				r=group_closed["mean"],
				theta=theta,
				mode="lines",
				line={"color": color},
				line_shape="spline",
				name=trace_value,
			)
		)

	collapse_legend(figure, mapping)
	means = frame["mean"]
	figure.update_layout(
		title="<b>Animal feature overview</b>",
		title_y=0.95,
		legend_title_text=mapping.legend_title,
		title_x=0.45,
		polar={
			"radialaxis": {
				"visible": True,
				# Series.min/max is typed as a broad union; arithmetic is valid for this column.
				"range": [means.min() - 0.5, means.max() + 0.5],  # ty: ignore[unsupported-operator]
			}
		},
		legend={"tracegroupgap": 0},
		showlegend=True,
	)
	figure.update_polars(bgcolor="rgba(0,0,0,0)")

	return figure


def _edge_traces(
	graph: nx.Graph,
	pos: dict[str, np.ndarray],
	cmap: str = "Viridis",
	edge_weight: Literal["chasings", "proportion_together"] = "chasings",
) -> list[go.Scatter]:
	"""One trace per edge, its width and colour scaled by the edge's weight.

	Weights are z-scored and squashed through a logistic so the palette spans the
	cohort's own range; a cohort whose edges all carry the same weight has no spread
	to scale by, and takes the middle of the colorscale throughout.

	Args:
		graph: the network, whose edges carry ``edge_weight`` as an attribute.
		pos: node positions, as ``(x, y, ranking)`` per node.
		cmap: any named plotly colorscale.
		edge_weight: which edge attribute drives width and colour.

	Returns:
		One :class:`go.Scatter` per edge, self-loops excluded.
	"""
	edge_widths = np.array([graph.edges[edge][edge_weight] for edge in graph.edges()])

	mu: float = edge_widths.mean()
	std: float = edge_widths.std()

	if std == 0 or np.isnan(std):
		normalized_for_colors = np.full_like(edge_widths, 0.5)
	else:
		z_scores = (edge_widths - mu) / std
		normalized_for_colors = 1 / (1 + np.exp(-z_scores))

	colorscale: list[str] = px.colors.sample_colorscale(cmap, normalized_for_colors.tolist())

	edge_trace: list[go.Scatter] = []

	for index, edge in enumerate(graph.edges()):
		if edge[0] == edge[1]:
			continue
		source_x, source_y = pos[edge[0]][:2]
		target_x, target_y = pos[edge[1]][:2]
		edge_width = normalized_for_colors[index] * 10  # scaled up for visibility

		edge_trace.append(
			go.Scatter(
				x=[source_x, target_x, None],
				y=[source_y, target_y, None],
				line={
					"width": edge_width,
					"color": colorscale[index],
				},
				hoverinfo="none",
				mode="lines+markers",
				marker={"size": edge_width, "symbol": "arrow", "angleref": "previous"},
				opacity=0.5,
				showlegend=False,
			)
		)

	return edge_trace


def _node_trace(
	pos: dict[str, np.ndarray],
	colors: list[str],
	animals: list[str],
	include_ranking: bool,
) -> go.Scatter:
	"""One trace holding every node, sized by the ranking its position carries.

	Args:
		pos: node positions, as ``(x, y, ranking)`` per node.
		colors: one colour per animal, aligned with ``animals``.
		animals: the nodes to draw, in the order the colours are given.
		include_ranking: whether the hover text names the ranking as well as the animal.
	"""
	sizes = [pos[node][2] if pos[node][2] > 0 else 0.1 for node in animals]

	return go.Scatter(
		x=[pos[node][0] for node in animals],
		y=[pos[node][1] for node in animals],
		text=[f"<b>{node}</b>" for node in animals],
		hovertext=[
			f"Mouse ID: {node}<br>Ranking: {size}" if include_ranking else f"Mouse ID: {node}"
			for node, size in zip(animals, sizes, strict=True)
		],
		hoverinfo="text",
		mode="markers+text",
		textposition="top center",
		showlegend=False,
		marker={"showscale": False, "colorscale": colors, "size": sizes, "color": colors},
	)


def plot_network_graph(
	connections: pl.DataFrame,
	nodes: pl.DataFrame | None,
	animals: list[str],
	colors: list[str],
	graph_type: Literal["chasings", "proportion_together"],
	layout: Literal["spring", "circular"] = "spring",
) -> go.Figure:
	"""Plots network graph of social structure.

	Args:
		connections: edge list carrying the weight column for ``graph_type``.
		nodes: ranking table, required for a chasings graph and ignored otherwise.
		animals: every cohort animal, in the order they ring a circular layout.
		colors: one colour per animal, aligned with ``animals``.
		graph_type: which relationship the edges carry.
		layout: ``"spring"`` places nodes by edge weight, ``"circular"`` rings them
			evenly so node positions stay comparable between plots.
	"""
	match graph_type:
		case "chasings":
			assert nodes is not None, "Ranking nodes are required for a chasings network graph."
			edge_weight = "chasings"
			graph_class = nx.DiGraph
			title = "<b>Dominance network graph</b>"
			include_ranking = True
			ordinals = dict(nodes.select("animal_id", "ordinal").iter_rows())
		case "proportion_together":
			edge_weight = "proportion_together"
			graph_class = nx.Graph
			title = "<b>Sociability network graph</b>"
			include_ranking = False
			ordinals = dict.fromkeys(animals, 30)

	graph = nx.from_pandas_edgelist(connections, create_using=graph_class, edge_attr=edge_weight)
	graph.add_nodes_from(animals)

	match layout:
		case "spring":
			pos = nx.spring_layout(
				graph, k=0.1, iterations=50, seed=42, weight=edge_weight, method="energy"
			)
		case "circular":
			pos = nx.circular_layout(animals)

	for animal in animals:
		pos[animal] = np.append(pos[animal], ordinals[animal])

	edge_trace = _edge_traces(graph, pos, edge_weight=edge_weight)
	node_trace = _node_trace(pos, colors, animals, include_ranking)

	figure = go.Figure(
		data=[*edge_trace, node_trace],
		layout=go.Layout(
			showlegend=False,
			hovermode="closest",
			title={"text": title, "x": 0.5, "y": 0.95},
		),
	)

	figure.update_xaxes(showticklabels=False, showgrid=False, zeroline=False, automargin=True)
	figure.update_yaxes(
		showticklabels=False,
		showgrid=False,
		zeroline=False,
		automargin=True,
		scaleanchor="x",
		scaleratio=1,
	)

	return figure


def plot_social_stability(frame: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots the stability of a social relationship based on time spent together."""
	figure = px.scatter(
		frame,
		x="stability",
		y="proportion_together",
		color=mapping.trace_column,
		color_discrete_map=mapping.trace_colors,
		category_orders={mapping.trace_column: mapping.order},
		hover_data={"animal_id_2": True},
		range_x=[0, 1],
		range_y=[0, 1],
		title="<b>Relationship stability</b>",
	)

	collapse_legend(figure, mapping)
	figure.update_layout(
		xaxis={"title": "<b>Relationship stability</b>"},
		yaxis={"title": "<b>Median proportion together</b>"},
		legend_title_text=mapping.legend_title,
	)
	figure.update_traces(marker_size=12)

	return figure


def plot_quality_heatmap(matrix: np.ndarray, animals: list[str], antennas: list[str]) -> go.Figure:
	"""Plots the share of each animal's passes over each antenna that went unrecorded."""
	figure = px.imshow(
		matrix,
		x=antennas,
		y=animals,
		zmin=0,
		color_continuous_scale=AURORA,
		title="<b>Missed passes by animal and antenna</b>",
	)
	figure.update_traces(
		hovertemplate="Antenna: %{x}<br>Animal: %{y}<br>Missed: %{z:.2f}%<extra></extra>"
	)
	figure.update_layout(
		xaxis={"title": "<b>Antenna</b>", "type": "category", "constraintoward": "right"},
		yaxis={"automargin": True, "title": "<b>Animal ID</b>"},
		coloraxis_colorbar={"title": {"text": "<b>Missed [%]</b>"}},
	)

	return figure


def plot_quality_by_antenna(frame: pl.DataFrame) -> go.Figure:
	"""Plots the pooled miss rate per antenna."""
	figure = px.bar(
		frame,
		x="antenna",
		y="miss_rate",
		hover_data={"antenna": True, "miss_rate": ":.2f", "detected": True, "missed": True},
		title="<b>Missed passes per antenna</b>",
	)
	figure.update_traces(marker_line_width=0, marker_color=AURORA[0][1])
	figure.update_layout(barcornerradius=10)
	figure.update_xaxes(title_text="<b>Antenna</b>", type="category")
	figure.update_yaxes(title_text="<b>Missed [%]</b>")

	return figure


def plot_cage_preference(
	frame: pl.DataFrame,
	positions: list[str],
	colors: list[str],
	granularity: str,
	value_label: str,
	place: str = "cage",
) -> go.Figure:
	"""Plots position preference on a per position basis (cohort preference summary)."""
	figure = px.box(
		frame,
		x="position",
		y="time_in_position",
		color="position",
		points="outliers",
		hover_data={
			"animal_id": True,
			granularity: True,
			"time_in_position": False,
			"time_in_position_text": True,
		},
		color_discrete_map=dict(zip(positions, colors, strict=True)),
		category_orders={"position": positions},
		title=f"<b>{place.capitalize()} preference</b>",
	)

	figure.update_traces(boxmean=True)
	figure.update_layout(colorway=colors)
	figure.update_yaxes(title_text=value_label)
	figure.update_xaxes(
		title_text=f"<b>{place.capitalize()}s</b>",
		tickvals=list(range(len(positions))),
		ticktext=_tick_labels(positions),
	)

	return figure


def plot_timeline(
	frame: pl.DataFrame, animals: list[str], positions: list[str], spans: pl.DataFrame
) -> go.Figure:
	"""Plots each animal's position over time as a compact Gantt-style strip.

	A multi-day recording carries tens of thousands of visits, well past what an SVG
	bar chart (``px.timeline``) renders smoothly - so each position and animal gets one
	WebGL line trace instead of one bar per visit, its visits drawn as NaN-separated
	segments at that position's colour.

	Both axes are numeric so plotly ships them as compact typed arrays rather than a
	hundred thousand date strings: times are wall-clock epoch milliseconds on a date axis
	(plotly drops a date string's zone too, so they read the same), animals are their row
	index, named by the tick labels and, in the hover, by the trace's ``meta``.
	"""
	colors = dict(zip(positions, sample_palette(len(positions)), strict=True))
	row_dtype = np.min_scalar_type(len(animals))
	visits = frame.with_columns(pl.col("start", "end").dt.replace_time_zone(None).dt.epoch("ms"))
	groups = visits.partition_by("position", "animal_id", as_dict=True)
	figure = go.Figure()

	for position in positions:
		legend = True
		for row, animal in enumerate(animals):
			rows = groups.get((position, animal))
			if rows is None:
				continue

			x = np.full(3 * rows.height, np.nan)
			x[0::3] = rows["start"].to_numpy()
			x[1::3] = rows["end"].to_numpy()
			figure.add_trace(
				go.Scattergl(
					x=x,
					y=np.full(x.size, row, dtype=row_dtype),
					mode="lines",
					line={"width": 10, "color": colors[position]},
					name=position,
					legendgroup=position,
					showlegend=legend,
					meta=animal,
					hovertemplate=f"{position}<br>Animal: %{{meta}}<br>%{{x}}<extra></extra>",
				)
			)
			legend = False

	figure.update_yaxes(
		title=None,
		tickvals=list(range(len(animals))),
		ticktext=animals,
		range=[len(animals) - 0.5, -0.5],
		zeroline=False,
	)
	figure.update_xaxes(title="<b>Timeline</b>", type="date")
	figure.update_layout(
		title="<b>Position timeline</b>",
		legend={"title": "Position"},
		colorway=list(colors.values()),
	)
	_event_spans(figure, spans)

	return figure
