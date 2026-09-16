"""Plot types, encoding channels, and the aggregation behind every figure.

Moved from ``scripts/plot_builder/figure.py``. The channel list a plot type offers is
read off the plotly express signature, so the shelves on screen are exactly the ones
that function accepts. Everything dropped on a discrete channel becomes a group-by key;
the measure dropped on a continuous one decides what is computed over those groups.
"""

import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field as dc_field
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from deepecohab.app.builder.catalog import EXPOSURE, METRIC, VALUE, Field, Kind, metric_names
from deepecohab.plotting import theme

#: Builder figures render with this template initially; the app callback overrides it
#: to match the viewer's theme before the figure reaches the browser.
TEMPLATE = "dark"

#: How a metric measure collapses. The rate is the only one that reads the same at
#: every grouping level, so it leads and is the default.
MEASURE_MODES: dict[str, str] = {
	"rate": "rate",
	"total": "total",
	"exposure": "exposure, h",
	"mean": "hourly mean",
}
DEFAULT_MODE = "rate"

#: Every plotly express encoding we are willing to expose, in shelf order.
CHANNELS: tuple[str, ...] = (
	"x",
	"y",
	"z",
	"r",
	"theta",
	"path",
	"values",
	"color",
	"symbol",
	"size",
	"line_dash",
	"line_group",
	"pattern_shape",
	"facet_col",
	"facet_row",
	"animation_frame",
	"text",
	"hover_name",
)

#: Not a plotly argument: fields here only add keys to the group-by, which is how a box
#: gets one point per animal instead of one per hour.
DETAIL = "detail"

#: Plot types that draw a spread rather than a point, so they are meaningless until
#: something on Detail says what one observation is.
DISTRIBUTIONS: frozenset[str] = frozenset({"box", "violin", "strip", "histogram", "ecdf"})

#: The finest identity a project table holds: one animal within one recording. Tags are
#: reused between recordings, so animal_id on its own would merge different animals.
OBSERVATION: tuple[str, ...] = ("recording", "animal_id")

#: Which chips each shelf accepts. Anything absent takes every kind.
ACCEPTS: dict[str, frozenset[Kind]] = {
	"z": frozenset({"measure"}),
	"size": frozenset({"measure"}),
	"values": frozenset({"measure"}),
	"path": frozenset({"dimension", "time"}),
	"symbol": frozenset({"dimension", "time"}),
	"line_dash": frozenset({"dimension", "time"}),
	"line_group": frozenset({"dimension", "time"}),
	"pattern_shape": frozenset({"dimension", "time"}),
	"facet_col": frozenset({"dimension", "time"}),
	"facet_row": frozenset({"dimension", "time"}),
	"animation_frame": frozenset({"dimension", "time"}),
	"hover_name": frozenset({"dimension", "time"}),
	DETAIL: frozenset({"dimension", "time"}),
}

#: Shelves that hold an ordered list instead of replacing on every drop.
MULTI: frozenset[str] = frozenset({"path", DETAIL})

LABELS: dict[str, str] = {
	"x": "X",
	"y": "Y",
	"z": "Z",
	"r": "Radius",
	"theta": "Angle",
	"path": "Path",
	"values": "Values",
	"color": "Colour",
	"symbol": "Marker",
	"size": "Size",
	"line_dash": "Dash",
	"line_group": "Line group",
	"pattern_shape": "Pattern",
	"facet_col": "Facet col",
	"facet_row": "Facet row",
	"animation_frame": "Animate",
	"text": "Label",
	"hover_name": "Hover",
	DETAIL: "Detail",
}


@dataclass(frozen=True)
class PlotType:
	"""One entry in the plot picker.

	Attributes:
		name: picker key, also what the builder state holds.
		label: what the picker reads as.
		builder: the plotly express function to call.
		required: channels that must be filled before a figure can be drawn.
		extra: keyword arguments always passed to ``builder``.
	"""

	name: str
	label: str
	builder: Any
	required: tuple[str, ...] = ()
	extra: dict[str, Any] = dc_field(default_factory=dict)

	@property
	def channels(self) -> tuple[str, ...]:
		"""The shelves this plot type offers, read off its own signature."""
		accepted = inspect.signature(self.builder).parameters
		return (*(channel for channel in CHANNELS if channel in accepted), DETAIL)


PLOTS: tuple[PlotType, ...] = (
	PlotType("line", "Line", px.line, ("x", "y"), {"markers": True}),
	PlotType("scatter", "Scatter", px.scatter, ("x", "y")),
	PlotType("bar", "Bar", px.bar, ("x", "y"), {"barmode": "group"}),
	PlotType("area", "Area", px.area, ("x", "y")),
	PlotType("box", "Box", px.box, ("y",), {"points": "all"}),
	PlotType("violin", "Violin", px.violin, ("y",), {"box": True, "points": "all"}),
	PlotType("strip", "Strip", px.strip, ("y",)),
	PlotType("histogram", "Histogram", px.histogram, ("x",)),
	PlotType("ecdf", "ECDF", px.ecdf, ("x",)),
	PlotType("density_heatmap", "Density heatmap", px.density_heatmap, ("x", "y")),
	PlotType("scatter_polar", "Polar scatter", px.scatter_polar, ("r", "theta")),
	PlotType("line_polar", "Polar line", px.line_polar, ("r", "theta"), {"line_close": True}),
	PlotType("bar_polar", "Polar bar", px.bar_polar, ("r", "theta")),
	PlotType("sunburst", "Sunburst", px.sunburst, ("path", "values")),
	PlotType("treemap", "Treemap", px.treemap, ("path", "values")),
)

BY_NAME: dict[str, PlotType] = {plot.name: plot for plot in PLOTS}


def plot_type(name: str) -> PlotType:
	"""The plot type called ``name``, falling back to the first one."""
	return BY_NAME.get(name, PLOTS[0])


def accepts(channel: str, kind: Kind) -> bool:
	"""Whether a chip of ``kind`` may be dropped on ``channel``."""
	return kind in ACCEPTS.get(channel, frozenset({"dimension", "time", "measure"}))


def new_state(name: str = PLOTS[0].name, mode: str = DEFAULT_MODE) -> dict[str, Any]:
	"""An empty builder state for the given plot type."""
	return {"kind": name, "channels": {}, "filters": {}, "measure_as": mode}


def seed_detail(state: dict[str, Any], catalog: Sequence[Field]) -> dict[str, Any]:
	"""Give a distribution something to be a distribution over.

	A box whose Detail shelf is empty is one aggregated number, so it draws a single
	point. Filling the shelf with the identity columns - visibly, as chips the user can
	take off again - makes each box a spread over animals instead.

	Args:
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		The state, with Detail seeded when the plot type needs it and it is empty.
	"""
	if state["kind"] not in DISTRIBUTIONS or state["channels"].get(DETAIL):
		return state

	available = {item.name for item in catalog}
	seeded = [name for name in OBSERVATION if name in available]

	if seeded:
		state["channels"][DETAIL] = seeded

	return state


def label_for(field: Field, mode: str) -> str:
	"""What a field's axis reads as, which for Value depends on how it collapses.

	Args:
		field: the field being plotted.
		mode: the active measure mode.

	Returns:
		The axis title.
	"""
	if field.agg != "metric":
		return field.label

	return f"{field.label} ({MEASURE_MODES.get(mode, mode)})"


def assigned(state: dict[str, Any]) -> dict[str, list[str]]:
	"""The channels that currently hold at least one field."""
	return {channel: names for channel, names in state["channels"].items() if names}


def group_keys(state: dict[str, Any], catalog: Sequence[Field]) -> list[str]:
	"""Every discrete field on a shelf, in shelf order and without repeats.

	These are what the frame is grouped by, so the measure is computed once per drawn
	point rather than once per hourly row.

	Args:
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		The group-by keys.
	"""
	fields = {item.name: item for item in catalog}
	keys: list[str] = []

	for names in assigned(state).values():
		for name in names:
			item = fields.get(name)
			if item is not None and item.discrete and name not in keys:
				keys.append(name)

	return keys


def measures(state: dict[str, Any], catalog: Sequence[Field]) -> list[Field]:
	"""Every aggregating field on a shelf, without repeats.

	Args:
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		The measures to compute over the group-by keys.
	"""
	fields = {item.name: item for item in catalog}
	picked: dict[str, Field] = {}

	for names in assigned(state).values():
		for name in names:
			item = fields.get(name)
			if item is not None and not item.discrete:
				picked.setdefault(name, item)

	return list(picked.values())


def apply_filters(frame: pl.LazyFrame, filters: dict[str, Any]) -> pl.LazyFrame:
	"""Narrow the frame to what the filter rail selects.

	Args:
		frame: the project table.
		filters: column to a list of accepted values, or to a ``lo``/``hi`` range.

	Returns:
		The filtered frame; a filter with nothing selected is ignored.
	"""
	schema = frame.collect_schema()

	for column, chosen in filters.items():
		if column not in schema or not chosen:
			continue

		if isinstance(chosen, dict):
			frame = frame.filter(pl.col(column).is_between(chosen["lo"], chosen["hi"]))
		else:
			frame = frame.filter(pl.col(column).cast(pl.String).is_in(list(chosen)))

	return frame


def build_frame(
	frame: pl.LazyFrame,
	state: dict[str, Any],
	catalog: Sequence[Field],
) -> pl.DataFrame:
	"""Collapse the project table to one row per drawn point.

	Value is always grouped by Metric internally, even when Metric holds no shelf of
	its own, so a rate divides only after both halves are summed within one metric -
	the hourly rows then sum to a phase, a day or a whole recording without the
	mean-of-rates distortion. Metric only survives into the output when it is itself
	on a shelf; otherwise exactly one metric must be selected, which
	``warnings_for`` blocks on if it is not.

	Args:
		frame: the project table, scanned lazily.
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		The aggregated frame, with one column per field on a shelf.
	"""
	frame = apply_filters(frame, state.get("filters", {}))
	keys = group_keys(state, catalog)
	wanted = measures(state, catalog)
	mode = state.get("measure_as", DEFAULT_MODE)

	if not wanted:
		return frame.group_by(keys).agg(pl.len().alias("rows")).sort(keys).collect()

	value = next((item for item in wanted if item.agg == "metric"), None)
	plain = [pl.mean(item.name) for item in wanted if item.agg != "metric"]

	if value is None:
		grouped = frame.group_by(keys).agg(plain) if keys else frame.select(plain)
		return grouped.sort(keys).collect() if keys else grouped.collect()

	agg_keys = keys if METRIC in keys else [*keys, METRIC]

	match mode:
		case "total":
			grouped = frame.group_by(agg_keys).agg(*plain, pl.sum(VALUE).alias(value.name))
		case "exposure":
			grouped = frame.group_by(agg_keys).agg(*plain, pl.sum(EXPOSURE).alias(value.name))
		case "mean":
			grouped = frame.group_by(agg_keys).agg(*plain, pl.mean(VALUE).alias(value.name))
		case _:  # "rate"
			summed = frame.group_by(agg_keys).agg(
				*plain, pl.sum(VALUE).alias("_v"), pl.sum(EXPOSURE).alias("_e")
			)
			grouped = summed.with_columns(
				pl.when(pl.col("_e") > 0)
				.then(pl.col("_v") / pl.col("_e"))
				.otherwise(None)
				.alias(value.name)
			).drop("_v", "_e")

	if METRIC not in keys:
		grouped = grouped.drop(METRIC)

	return grouped.sort(keys).collect() if keys else grouped.collect()


#: What a metric's rate reads as, for the "Value would pool..." warning. Mirrors
#: docs/technical_documentation_writeup.md § "The metrics and their exposures"; a
#: metric this does not name is still listed, just without a unit hint.
METRIC_UNITS: dict[str, str] = {
	"activity": "visits/hour",
	"time_alone": "fraction of time",
	"time_together": "fraction, per partner",
	"pairwise_encounters": "encounters/partner-hour",
	"n_chasing": "chasings/partner-hour",
	"n_chased": "chasings/partner-hour",
	"n_chasing_per_detection": "chasings/detection",
}

#: Shelves that give a faceted metric its own axis, so pooling several is not a problem.
FACETS: tuple[str, ...] = ("facet_row", "facet_col")


@dataclass(frozen=True)
class Note:
	"""One line for the banner above the plot.

	Attributes:
		text: the message.
		blocking: whether the plot cannot be drawn until this is resolved.
	"""

	text: str
	blocking: bool = False


def warnings_for(
	frame: pl.LazyFrame, state: dict[str, Any], catalog: Sequence[Field]
) -> list[Note]:
	"""Everything worth saying before the figure is trusted.

	Args:
		frame: the project table, for the metric count a pooling warning needs.
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		Notes for the banner, blocking ones first.
	"""
	plot = plot_type(state["kind"])
	notes: list[Note] = []

	missing = [LABELS[channel] for channel in plot.required if not state["channels"].get(channel)]
	if missing:
		notes.append(Note(f"Drop a field on {', '.join(missing)} to draw the plot.", blocking=True))

	uses_value = any(item.agg == "metric" for item in measures(state, catalog))
	picked = state.get("filters", {}).get(METRIC) or metric_names(frame)
	faceted = any(METRIC in state["channels"].get(channel, []) for channel in FACETS)

	if uses_value and len(picked) > 1 and not faceted:
		units = "; ".join(
			f"{name} ({METRIC_UNITS[name]})" if name in METRIC_UNITS else name for name in picked
		)
		notes.append(
			Note(
				f"Value would pool {len(picked)} metrics with different units ({units}). "
				"Filter Metric to one, or put Metric on Facet row or Facet col so each gets "
				"its own axis.",
				blocking=True,
			)
		)

	if state["kind"] in DISTRIBUTIONS and not state["channels"].get(DETAIL):
		notes.append(
			Note(
				"Detail is empty, so every group collapses to one number and each box is "
				"drawn from a single point. Drop recording and animal id on Detail to spread "
				"it over animals."
			)
		)

	if state.get("measure_as") == "mean" and uses_value:
		notes.append(
			Note(
				"An hourly mean weights every hour equally, however much of it was observed; "
				"the rate is the one that sums correctly over a phase or a day."
			)
		)

	return notes


def auto_facet_metric(state: dict[str, Any]) -> dict[str, Any]:
	"""Give Value its own axis per metric when several could still land on it.

	Called right after Value lands on a shelf. Dropping Value with more than one
	metric still selected, and Metric not already assigned anywhere, would otherwise
	trip the pooled-units warning; putting Metric on Facet row keeps each metric
	readable instead of waiting for that warning to say so.

	Args:
		state: the builder state, just after Value landed on a shelf.

	Returns:
		The state, Metric seeded onto Facet row when the plot type has one, Metric is
		not already assigned anywhere, and more than one metric is still selected.
	"""
	plot = plot_type(state["kind"])
	if "facet_row" not in plot.channels or state["channels"].get("facet_row"):
		return state

	if any(METRIC in names for names in state["channels"].values()):
		return state

	picked = state.get("filters", {}).get(METRIC)
	if isinstance(picked, list) and len(picked) == 1:
		return state

	state["channels"]["facet_row"] = [METRIC]
	return state


def placeholder(message: str) -> go.Figure:
	"""An empty canvas carrying an instruction instead of a figure.

	Args:
		message: what to say in the middle of it.

	Returns:
		The empty figure.
	"""
	figure = go.Figure()
	figure.update_layout(
		template=TEMPLATE,
		xaxis={"visible": False},
		yaxis={"visible": False},
		margin={"l": 20, "r": 20, "t": 20, "b": 20},
		annotations=[
			{
				"text": message,
				"showarrow": False,
				"xref": "paper",
				"yref": "paper",
				"x": 0.5,
				"y": 0.5,
				"font": {"size": 15, "color": "#7f8ca5"},
			}
		],
	)

	return figure


def build_figure(
	frame: pl.LazyFrame,
	state: dict[str, Any],
	catalog: Sequence[Field],
) -> tuple[go.Figure, list[str]]:
	"""Aggregate and draw whatever the shelves currently describe.

	Args:
		frame: the project table.
		state: the builder state.
		catalog: the fields the palette offered.

	Returns:
		The figure and any warnings to show above it.
	"""
	plot = plot_type(state["kind"])
	notes = warnings_for(frame, state, catalog)
	blocking = next((note for note in notes if note.blocking), None)

	if blocking is not None:
		return placeholder(blocking.text), [note.text for note in notes if note is not blocking]

	data = build_frame(frame, state, catalog)
	if data.is_empty():
		return placeholder("No rows match the current filters."), [note.text for note in notes]

	mode = state.get("measure_as", DEFAULT_MODE)
	labels = {item.name: label_for(item, mode) for item in catalog}
	kwargs: dict[str, Any] = {
		channel: list(names) if channel in MULTI else names[0]
		for channel, names in assigned(state).items()
		if channel != DETAIL
	}

	# Builder colours come from sample_palette(n) for the categories actually on the
	# Colour shelf, not the colorway's first n: plotly express walks the colorway in
	# order, so two categories would get neighbouring, hard-to-tell-apart samples.
	color_field = kwargs.get("color")
	color_item = next((item for item in catalog if item.name == color_field), None)
	if isinstance(color_field, str) and color_item is not None and color_item.kind == "dimension":
		n = data.select(pl.col(color_field).n_unique()).item()
		kwargs["color_discrete_sequence"] = theme.sample_palette(n)

	try:
		figure = plot.builder(data, **kwargs, **plot.extra, labels=labels, template=TEMPLATE)
	except Exception as error:  # plotly rejects plenty of otherwise sensible combinations
		return placeholder(f"{type(error).__name__}: {error}"), [note.text for note in notes]

	figure.update_layout(margin={"l": 60, "r": 20, "t": 40, "b": 40}, legend={"title": None})
	figure.for_each_annotation(lambda note: note.update(text=note.text.split("=")[-1]))

	return figure, [note.text for note in notes]


def prune(state: dict[str, Any], keep: Iterable[str]) -> tuple[dict[str, Any], list[str]]:
	"""Drop assignments the new plot type has no shelf for.

	Args:
		state: the builder state.
		keep: the channels the new plot type supports.

	Returns:
		The state and the labels of the channels that were cleared.
	"""
	supported = set(keep)
	dropped = [
		LABELS.get(channel, channel)
		for channel, names in state["channels"].items()
		if names and channel not in supported
	]
	state["channels"] = {
		channel: names for channel, names in state["channels"].items() if channel in supported
	}

	return state, dropped
