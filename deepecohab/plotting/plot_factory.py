from typing import Literal

import networkx as nx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from deepecohab.plotting.animals import ColorMapping, collapse_legend
from deepecohab.plotting.prepare import Heatmap


def _tick_labels(names: list[str]) -> list[str]:
	"""Turn snake_case position names into axis tick text."""
	return [name.capitalize().replace("_", " ") for name in names]


def _phase_markers(figure: go.Figure, phases: dict[str, float]) -> None:
	"""Mark the phase switch on an hour axis that begins at the first phase's onset."""
	switch = max(phases.values())
	color = "#C85C39" if phases["light_phase"] == switch else "#637DE5"
	figure.add_vline(x=switch, line_color=color, line_dash="dash", line_width=4)

	for name, symbol in (("light_phase", "☀️"), ("dark_phase", "🌙")):
		onset = phases[name]
		figure.add_annotation(
			x=(onset + (switch if onset < switch else 24)) / 2,
			y=1.15,
			xref="x",
			yref="paper",
			text=symbol,
			showarrow=False,
			font={"size": 25},
		)

	figure.update_layout(xaxis={"dtick": 1}, margin={"t": 80})


def _event_spans(figure: go.Figure, spans: pl.DataFrame, facets: list[str] | None = None) -> None:
	"""Shade where each event falls on a time axis, coloured and labelled by event.

	An event's colour comes from its place among the recording's events, so it is the
	same on every plot. On a faceted figure - one panel per cage - a span with a position
	is drawn only on that cage's panel; without panels it is labelled with its cages
	instead. The faceted figures are heatmaps, where a fill would tint the colour scale,
	so there the spans are outlined.
	"""
	if spans.is_empty():
		return

	palette = px.colors.qualitative.Pastel
	# Overlapping events would stack their labels, so each event takes its own corner.
	corners = ("top left", "bottom left", "middle left")

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

		if facets is None:
			text = f"{span['event']} ({span['position']})" if span["position"] else span["event"]
			font = {"size": 10}
			style = {
				"fillcolor": color.replace("rgb", "rgba").replace(")", ", 0.25)"),
				"line_width": 0,
				"layer": "below",
			}
		else:
			text = span["event"]
			font = {"size": 10, "color": color}
			style = {"line_color": color, "line_width": 2, "layer": "above"}

		for xaxis, yaxis, facet in panels:
			if facet is not None and span["position"] not in (None, facet):
				continue

			figure.add_shape(
				type="rect",
				xref=xaxis,
				yref=f"{yaxis} domain",
				x0=span["x0"],
				x1=span["x1"],
				y0=0,
				y1=1,
				label={"text": text, "textposition": corners[index % len(corners)], "font": font},
				**style,
			)


def _faceted_heatmap(
	heatmap: Heatmap,
	title: str,
	x_title: str,
	y_title: str,
	hover: tuple[str, str],
) -> go.Figure:
	"""Draw one imshow panel per facet, with pre-formatted hover text."""
	fig = px.imshow(
		heatmap.values,
		x=[str(label) for label in heatmap.x],
		y=heatmap.y,
		zmin=0,
		facet_col=0,
		facet_col_wrap=2,
		color_continuous_scale="Viridis",
		title=title,
	)

	for annotation, name in zip(fig.layout.annotations, heatmap.facets, strict=False):
		annotation["text"] = f"<b>{name.capitalize().replace('_', ' ')}</b>"

	value = "%{z}" if heatmap.text is None else "%{customdata}"
	fig.update_traces(
		hovertemplate="<br>".join([f"{hover[0]}: %{{x}}", f"{hover[1]}: %{{y}}", f"Value: {value}"])
	)

	# update_traces broadcasts one array to every facet, so each gets its own slice.
	if heatmap.text is not None:
		for index, trace in enumerate(fig.data):
			trace.customdata = heatmap.text[index]

	fig.update_layout(
		xaxis={"title": x_title},
		yaxis={"automargin": True, "title": y_title},
		coloraxis_colorbar={"title": {"text": heatmap.label}},
	)

	return fig


def plot_activity(
	df: pl.DataFrame,
	positions: list[str],
	mapping: ColorMapping,
	metric: Literal["visits", "time"],
	agg: Literal["sum", "mean"],
	granularity: str,
	value_label: str,
) -> go.Figure:
	"""Plots bar or box graph of cage and tunnel visits or time spent."""
	title = (
		"<b>Visits to each position</b>"
		if metric == "visits"
		else "<b>Time spent in each position</b>"
	)
	y_title = "<b>Number of visits</b>" if metric == "visits" else value_label
	hover = {mapping.animal_column: True, "position": True, metric: True}

	if metric == "time":
		hover |= {metric: False, "time_text": True}

	match agg:
		case "sum":
			fig = px.bar(
				df,
				x="position",
				y=metric,
				color=mapping.animal_column,
				color_discrete_map=mapping.by_animal,
				hover_data=hover,
				title=title,
				barmode="group",
			)
			fig.update_layout(barcornerradius=10)
			fig.update_traces(marker_line_width=0)
		case "mean":
			fig = px.box(
				df,
				x="position",
				y=metric,
				color=mapping.animal_column,
				color_discrete_map=mapping.by_animal,
				hover_data=hover | {granularity: True},
				title=title,
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	collapse_legend(fig, mapping)
	fig.update_layout(legend={"title": mapping.legend_title})
	fig.update_xaxes(
		title_text="<b>Position</b>",
		tickvals=list(range(len(positions))),
		ticktext=_tick_labels(positions),
	)
	fig.update_yaxes(title_text=y_title)

	return fig


def plot_time_alone(
	df: pl.DataFrame,
	positions: list[str],
	mapping: ColorMapping,
	agg: Literal["mean", "sum"],
	granularity: str,
	value_label: str,
	place: str = "cage",
) -> go.Figure:
	"""Plot time alone per position as a bar or box plot."""
	hover = {
		mapping.animal_column: True,
		"position": True,
		"time_alone": False,
		"time_alone_text": True,
	}

	match agg:
		case "sum":
			# px.histogram re-aggregates in the browser and drops customdata with it,
			# so the sum arrives already aggregated and is drawn as plain bars.
			fig = px.bar(
				df,
				x="position",
				y="time_alone",
				color=mapping.animal_column,
				color_discrete_map=mapping.by_animal,
				hover_data=hover,
				title="<b>Time spent alone</b>",
				barmode="group",
			)
			fig.update_traces(marker_line_width=0)
		case "mean":
			fig = px.box(
				df,
				x="position",
				y="time_alone",
				color=mapping.animal_column,
				color_discrete_map=mapping.by_animal,
				hover_data=hover | {granularity: True},
				title="<b>Time spent alone</b>",
				boxmode="group",
				points="outliers",
			)
			fig.update_traces(boxmean=True)

	collapse_legend(fig, mapping)
	fig.update_xaxes(
		title_text=f"<b>{place.capitalize()}</b>",
		tickvals=list(range(len(positions))),
		ticktext=_tick_labels(positions),
	)
	fig.update_yaxes(title_text=value_label)
	fig.update_layout(barcornerradius=10, legend_title_text=mapping.legend_title)

	return fig


def plot_sum_line_per_hour(
	df: pl.DataFrame,
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

	fig = px.line(
		df,
		x="hour",
		y="total",
		color=mapping.animal_column,
		color_discrete_map=mapping.by_animal,
		category_orders={mapping.animal_column: mapping.categories},
		line_shape="spline",
		title=title,
	)

	collapse_legend(fig, mapping)
	fig.update_layout(legend={"title": mapping.legend_title})
	fig.update_yaxes(title=y_axes_label)
	# Half a bin either side, so an event span over the first or last hour is not cut off.
	fig.update_xaxes(title="<b>Hour since phase onset</b>", range=[-0.5, 23.5])
	_phase_markers(fig, phases)
	_event_spans(fig, spans)

	return fig


def plot_mean_line_per_hour(
	df: pl.DataFrame,
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
		case "chasings":
			title = "<b>Chasing over time</b>"
			y_axes_label = "<b># of chasing events</b>"

	fig = go.Figure()

	for animal in df[mapping.animal_column].unique(maintain_order=True).to_list():
		animal_df = df.filter(pl.col(mapping.animal_column) == animal)
		color = mapping.colors[mapping.category_by_animal.get(animal, animal)]

		x = animal_df["hour"].to_list()
		y = animal_df["mean"].to_list()
		bounds = animal_df["upper"].to_list() + animal_df["lower"].to_list()[::-1]
		shade_color = color.replace("rgb", "rgba").replace(")", ", 0.2)")  # shaded region is SEM

		fig.add_trace(
			go.Scatter(
				x=x + x[::-1],
				y=bounds,
				fill="toself",
				fillcolor=shade_color,
				line_color="rgba(255,255,255,0)",
				showlegend=False,
				name=animal,
				line={"shape": "spline"},
			)
		)

		fig.add_trace(go.Scatter(x=x, y=y, line_color=color, name=animal, line={"shape": "spline"}))

	collapse_legend(fig, mapping)
	fig.update_layout(title=title, legend={"title": mapping.legend_title, "tracegroupgap": 0})
	fig.update_yaxes(title=y_axes_label)
	fig.update_xaxes(title="<b>Hour since phase onset</b>")
	_phase_markers(fig, phases)
	_event_spans(fig, spans)

	return fig


def plot_ranking_line(df: pl.DataFrame, mapping: ColorMapping, spans: pl.DataFrame) -> go.Figure:
	"""Plots line graph of ranking over time."""
	fig = px.line(
		df,
		x="datetime",
		y="ordinal",
		color=mapping.animal_column,
		color_discrete_map=mapping.by_animal,
		category_orders={mapping.animal_column: mapping.categories},
	)

	collapse_legend(fig, mapping)
	fig.update_layout(
		title="<b>Social dominance ranking in time</b>",
		legend={"title": mapping.legend_title, "tracegroupgap": 0},
		xaxis={"title": "<b>Timeline</b>"},
		yaxis={"title": "<b>Ranking</b>"},
	)
	_event_spans(fig, spans)

	return fig


def plot_ranking_distribution(df: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots line graph of ranking distribution with shaded area."""
	fig = px.line(
		df,
		x="ranking",
		y="probability_density",
		color=mapping.animal_column,
		color_discrete_map=mapping.by_animal,
		category_orders={mapping.animal_column: mapping.categories},
		hover_data=[mapping.animal_column, "ranking", "probability_density"],
	)
	fig.update_traces(fill="tozeroy")

	collapse_legend(fig, mapping)
	fig.update_layout(
		title="<b>Ranking probability distribution</b>",
		xaxis={"title": "<b>Ranking</b>"},
		yaxis={"title": "<b>Probability density</b>"},
		legend={"title": mapping.legend_title, "tracegroupgap": 0},
	)

	return fig


def plot_ranking_stability(
	df: pl.DataFrame,
	mapping: ColorMapping,
	granularity: str,
	spans: pl.DataFrame,
) -> go.Figure:
	"""Plots animal rank on a per day (or per phase) basis."""
	label = "Phase" if granularity == "phase_count" else "Day"
	cadence = "Daily" if granularity == "day" else "Per-phase"

	fig = go.Figure(
		layout={
			"title_x": 0.5,
			"title": f"<b>{cadence} dominance rank trajectories</b>",
			"legend_title_text": mapping.legend_title,
			"yaxis": {
				"title": "<b>Rank</b>",
				"autorange": "reversed",
				"type": "category",
				"categoryorder": "array",
				"categoryarray": df["rank"].unique().sort(),
			},
			"xaxis": {"title": f"<b>{label}</b>"},
		}
	)

	for animal in df[mapping.animal_column].unique(maintain_order=True).to_list():
		temp = df.filter(pl.col(mapping.animal_column) == animal).sort(granularity)
		color = mapping.colors[mapping.category_by_animal.get(animal, animal)]

		fig.add_trace(
			go.Scatter(
				x=temp[granularity],
				y=temp["rank"],
				mode="lines+markers",
				name=animal,
				line={"color": color},
				marker={"color": color},
			)
		)

	collapse_legend(fig, mapping)
	_event_spans(fig, spans)

	return fig


def plot_time_spent_per_cage(
	heatmap: Heatmap,
	kind: Literal["hourly", "daily"],
	spans: pl.DataFrame,
	place: str = "cage",
) -> go.Figure:
	"""Plots one heatmap per position of time spent, by hour or by window unit."""
	match kind:
		case "hourly":
			title = f"<b>Time spent per {place}</b>"
			x_title = "<b>Hour since phase onset</b>"
			hover = ("Hour", "Animal ID")
		case "daily":
			title = f"<b>{place.capitalize()} preference over time</b>"
			x_title = "<b>Window unit</b>"
			hover = ("Unit", "Animal ID")

	fig = _faceted_heatmap(heatmap, title, x_title, "<b>Animal ID</b>", hover)
	# The x axis is categorical, so a bin sits at its index among the columns, not its value.
	_event_spans(fig, spans.with_columns(pl.col("x0", "x1") - heatmap.x[0]), heatmap.facets)

	return fig


def plot_heatmap(
	img: np.ndarray,
	animals: list[str],
	title: str,
	hover: tuple[str, str, str],
) -> go.Figure:
	"""Plots a square animal-by-animal matrix.

	Args:
		img: the matrix, rows and columns in ``animals`` order.
		animals: axis labels for both rows and columns.
		title: figure title.
		hover: hover labels for the column, the row and the value.
	"""
	fig = px.imshow(
		img, x=animals, y=animals, zmin=0, color_continuous_scale="Viridis", title=title
	)

	column, row, value = hover
	fig.update_traces(hovertemplate=f"{column}: %{{x}}<br>{row}: %{{y}}<br>{value}: %{{z}}")
	fig.update_layout(yaxis={"automargin": True}, xaxis={"automargin": True})

	return fig


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

	return _faceted_heatmap(heatmap, title, "", "", ("X", "Y"))


def plot_metrics_polar(df: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots mean z-scores of metrics with SEM shading as a polar plot."""
	fig = go.Figure()

	for name, group in df.partition_by("animal_id", as_dict=True).items():
		animal = name[0] if isinstance(name, tuple) else name
		color = mapping.colors[mapping.category_by_animal.get(animal, animal)]
		shade_color = color.replace("rgb", "rgba").replace(")", ", 0.2)")

		group_closed = pl.concat([group, group.head(1)])
		theta = group_closed["metric"]

		fig.add_trace(
			go.Scatterpolar(
				r=group_closed["lower"],
				theta=theta,
				mode="lines",
				line={"width": 0, "color": color},
				line_shape="spline",
				showlegend=False,
				hoverinfo="skip",
				name=animal,
			)
		)

		fig.add_trace(
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
				name=animal,
			)
		)

		fig.add_trace(
			go.Scatterpolar(
				r=group_closed["mean"],
				theta=theta,
				mode="lines+markers",
				line={"color": color},
				line_shape="spline",
				name=animal,
			)
		)

	collapse_legend(fig, mapping)
	fig.update_layout(
		title="<b>Animal feature overview</b>",
		title_y=0.95,
		legend_title_text=mapping.legend_title,
		title_x=0.45,
		polar={
			"radialaxis": {
				"visible": True,
				# Series.min/max is typed as a broad union; arithmetic is valid for this numeric column.
				"range": [df["mean"].min() - 0.5, df["mean"].max() + 0.5],  # ty: ignore[unsupported-operator]
			}
		},
		legend={"tracegroupgap": 0},
		showlegend=True,
	)
	fig.update_polars(bgcolor="rgba(0,0,0,0)")

	return fig


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

	Returns:
		The network figure.
	"""
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
	# An animal with no edges is absent from the edge list, and every lookup below is
	# keyed on the cohort, so it has to join the graph as an isolated node.
	G.add_nodes_from(animals)

	match layout:
		case "spring":
			pos = nx.spring_layout(
				G, k=0.1, iterations=50, seed=42, weight=edge_weight, method="energy"
			)
		case "circular":
			pos = nx.circular_layout(animals)

	for animal in animals:
		match graph_type:
			case "chasings":
				assert nodes is not None, "Ranking nodes are required for a chasings network graph."
				ordinal = nodes.filter(pl.col("animal_id") == animal).select("ordinal").item()
			case "proportion_together":
				ordinal = 30
		pos[animal] = np.append(pos[animal], ordinal)

	edge_trace = _edge_traces(G, pos, edge_weight=edge_weight)
	node_trace = _node_trace(pos, colors, animals, include_ranking)

	fig = go.Figure(
		data=[*edge_trace, node_trace],
		layout=go.Layout(
			showlegend=False,
			hovermode="closest",
			title={"text": title, "x": 0.5, "y": 0.95},
		),
	)

	fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=False, automargin=True)
	fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=False, automargin=True)

	# A ring is only a ring while the axes share a scale.
	if layout == "circular":
		fig.update_yaxes(scaleanchor="x", scaleratio=1)

	return fig


def plot_social_stability(df: pl.DataFrame, mapping: ColorMapping) -> go.Figure:
	"""Plots the stability of a social relationship based on time spent together."""
	fig = px.scatter(
		df,
		x="stability",
		y="proportion_together",
		color=mapping.animal_column,
		color_discrete_map=mapping.by_animal,
		category_orders={mapping.animal_column: mapping.categories},
		hover_data={"animal_id_2": True},
		range_x=[0, 1],
		range_y=[0, 1],
		title="<b>Relationship stability</b>",
	)

	collapse_legend(fig, mapping)
	fig.update_layout(
		xaxis={"title": "<b>Relationship stability</b>"},
		yaxis={"title": "<b>Median proportion together</b>"},
		legend_title_text=mapping.legend_title,
	)
	fig.update_traces(marker_size=12)

	return fig


def plot_cage_preference(
	df: pl.DataFrame,
	positions: list[str],
	colors: list[str],
	granularity: str,
	value_label: str,
	place: str = "cage",
) -> go.Figure:
	"""Plots position preference on a per position basis (cohort preference summary)."""
	fig = px.box(
		df,
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

	fig.update_traces(boxmean=True)
	fig.update_yaxes(title_text=value_label)
	fig.update_xaxes(
		title_text=f"<b>{place.capitalize()}s</b>",
		tickvals=list(range(len(positions))),
		ticktext=_tick_labels(positions),
	)

	return fig
