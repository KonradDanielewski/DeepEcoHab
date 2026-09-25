import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field as dc_field
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import polars.selectors as cs

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

#: What the Blocks box on an ordered field's chip accepts, and the one example it shows.
BIN_HINT = "3, or 1-3, 4-6"

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

#: What Format can override, each bound to the element whose automatic title it was set
#: on. An override lapses once that title changes - another field or measure landed
#: there - so a renamed axis never ends up labelling a different quantity.
FORMAT_BINDS: dict[str, str] = {
	"title": "title",
	"xaxis": "xaxis",
	"xmin": "xaxis",
	"xmax": "xaxis",
	"yaxis": "yaxis",
	"ymin": "yaxis",
	"ymax": "yaxis",
	"colorbar": "colorbar",
	"cmin": "colorbar",
	"cmax": "colorbar",
	"colorscale": "coloraxis",
	"palette": "colorway",
}

#: Format's numeric bounds, each upper one paired with the lower it must stay above.
FORMAT_PAIRS: dict[str, str] = {"xmax": "xmin", "ymax": "ymin", "cmax": "cmin"}
FORMAT_BOUNDS: frozenset[str] = frozenset(FORMAT_PAIRS) | frozenset(FORMAT_PAIRS.values())


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
	PlotType("line", "Line", px.line, ("x", "y")),
	PlotType("scatter", "Scatter", px.scatter, ("x", "y")),
	PlotType("bar", "Bar", px.bar, ("x", "y"), {"barmode": "group"}),
	PlotType("area", "Area", px.area, ("x", "y")),
	PlotType("box", "Box", px.box, ("y",), {"points": "all"}),
	PlotType("violin", "Violin", px.violin, ("y",), {"box": False, "points": "all"}),
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
	take off again - makes each box a spread over animals instead. Only for a plot type
	that draws a spread, and only while Detail is still empty.
	"""
	if state["kind"] not in DISTRIBUTIONS or state["channels"].get(DETAIL):
		return state

	available = {item.name for item in catalog}
	seeded = [name for name in OBSERVATION if name in available]

	if seeded:
		state["channels"][DETAIL] = seeded

	return state


def label_for(field: Field, mode: str) -> str:
	"""What a field's axis reads as, which for Value depends on how it collapses."""
	if field.agg != "metric":
		return field.label

	return f"{field.label} ({MEASURE_MODES.get(mode, mode)})"


def assigned(state: dict[str, Any]) -> dict[str, list[str]]:
	"""The channels that currently hold at least one field."""
	return {channel: names for channel, names in state["channels"].items() if names}


def _shelved(state: dict[str, Any], catalog: Sequence[Field], *, discrete: bool) -> list[Field]:
	"""Fields of one kind on a shelf, in shelf order and without repeats."""
	fields = {item.name: item for item in catalog}
	picked: dict[str, Field] = {}

	for names in assigned(state).values():
		for name in names:
			item = fields.get(name)
			if item is not None and item.discrete is discrete:
				picked.setdefault(name, item)

	return list(picked.values())


def group_keys(state: dict[str, Any], catalog: Sequence[Field]) -> list[str]:
	"""Every discrete field on a shelf, in shelf order and without repeats.

	These are what the frame is grouped by, so the measure is computed once per drawn
	point rather than once per hourly row.
	"""
	return [item.name for item in _shelved(state, catalog, discrete=True)]


def measures(state: dict[str, Any], catalog: Sequence[Field]) -> list[Field]:
	"""Every aggregating field on a shelf, without repeats: what :func:`group_keys` groups."""
	return _shelved(state, catalog, discrete=False)


def apply_filters(frame: pl.LazyFrame, filters: dict[str, Any]) -> pl.LazyFrame:
	"""Narrow the frame to what the filter rail selects.

	Args:
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


#: One field's blocks: an even block size, or the exact spans the user typed.
Bins = int | list[tuple[float, float]]


def parse_bins(spec: str) -> Bins | None:
	"""Read what the Blocks box holds, or ``None`` when it holds nothing usable.

	Two shapes, told apart by the dash - every ordered field the builder offers counts
	up from zero, so a leading minus is never a value:

	* ``3`` - even blocks of three, however many the data runs to.
	* ``1-3, 4-6, 7-14`` - exactly those spans, in that order, any width, gaps allowed.

	Both ends of a span are included, so ``1-3`` is three days and ``1-3, 4-6`` tiles
	without gap or overlap.

	A value in none of the typed spans is dropped; a value in two lands in the first.
	"""
	text = str(spec).strip()

	if "-" not in text:
		return size if text.isdigit() and (size := int(text)) > 1 else None

	ranges = []
	for part in text.split(","):
		low, _, high = part.partition("-")
		try:
			bounds = (float(low), float(high))
		except ValueError:
			return None
		if bounds[1] < bounds[0]:
			return None
		ranges.append(bounds)

	return ranges or None


def apply_bins(frame: pl.LazyFrame, bins: dict[str, Bins]) -> pl.LazyFrame:
	"""Replace each binned column with the integer key of the block its value falls in.

	The key is the block's own start for an even size, or the span's position in the
	typed order; either way it stays numeric, so grouping and sorting still run in
	order. What span it stands for is only spelled out once the frame is aggregated.
	A value outside every typed span belongs to no block, so its rows are dropped.
	"""
	for name, spec in bins.items():
		if isinstance(spec, int):
			column = pl.col(name)
			frame = frame.with_columns(
				((column - column.min()) // spec * spec + column.min()).alias(name)
			)
			continue

		key = pl.lit(None, pl.Int32)
		for index, (low, high) in reversed(list(enumerate(spec))):
			key = pl.when(pl.col(name).is_between(low, high)).then(index).otherwise(key)
		frame = frame.with_columns(key.alias(name)).filter(pl.col(name).is_not_null())

	return frame


def label_bins(data: pl.DataFrame, bins: dict[str, Bins], catalog: Sequence[Field]) -> pl.DataFrame:
	"""Rewrite each block key as the span it covers, e.g. ``day 4-6``."""
	labels = {item.name: item.label for item in catalog}
	spans = []

	for name, spec in bins.items():
		if name not in data.columns:
			continue
		pretty = labels.get(name, name)
		if isinstance(spec, int):
			span = pl.format("{} {}-{}", pl.lit(pretty), pl.col(name), pl.col(name) + spec - 1)
		else:
			span = pl.col(name).replace_strict(
				list(range(len(spec))),
				[f"{pretty} {low:g}-{high:g}" for low, high in spec],
				return_dtype=pl.String,
			)
		spans.append(span.alias(name))

	return data.with_columns(spans)


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

	A numeric ordered field named in ``state["bins"]`` is grouped in the blocks
	:func:`parse_bins` reads there rather than one group per value, so the field reads
	as ``day 1-3``, ``day 4-6`` - which is what a facet needs to compare one stretch of
	a recording to another. A block spec that cannot be read is ignored here and
	reported by :func:`warnings_for`.

	Returns:
		The aggregated frame, with one column per field on a shelf.
	"""
	frame = apply_filters(frame, state.get("filters", {}))
	keys = group_keys(state, catalog)
	wanted = measures(state, catalog)
	mode = state.get("measure_as", DEFAULT_MODE)

	if mode == "mean":
		# An hour's value is split over the positions it happened in; put it back
		# together first, or the mean would be over positions rather than hours.
		spread = {"position", "position_type"} - set(keys)
		frame = frame.group_by(cs.exclude(VALUE, EXPOSURE, *spread)).agg(
			pl.sum(VALUE), pl.sum(EXPOSURE)
		)

	# Only what is grouped is binned: a leftover block for a field since taken off every
	# shelf would otherwise still rewrite its column.
	bins = {
		name: parsed
		for name, spec in state.get("bins", {}).items()
		if name in keys and (parsed := parse_bins(spec)) is not None
	}
	frame = apply_bins(frame, bins)

	def collected(grouped: pl.LazyFrame) -> pl.DataFrame:
		return label_bins(
			grouped.sort(keys).collect() if keys else grouped.collect(), bins, catalog
		)

	if not wanted:
		return collected(frame.group_by(keys).agg(pl.len().alias("rows")))

	value = next((item for item in wanted if item.agg == "metric"), None)
	plain = [pl.mean(item.name) for item in wanted if item.agg != "metric"]

	if value is None:
		return collected(frame.group_by(keys).agg(plain) if keys else frame.select(plain))

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

	return collected(grouped)


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
		frame: read only for the metric count a pooling warning needs.

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

	grouped = group_keys(state, catalog)
	unreadable = [
		name
		for name, spec in state.get("bins", {}).items()
		if name in grouped and parse_bins(spec) is None
	]
	if unreadable:
		notes.append(
			Note(
				f"Blocks for {', '.join(unreadable)} could not be read, so every value is "
				f"still its own group. Type a block size or spans: {BIN_HINT}."
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
	readable instead of waiting for that warning to say so. A plot type without a
	Facet row shelf is left alone.
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
	"""An empty canvas carrying ``message`` in the middle of it instead of a figure."""
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
		# Format's palette is drawn here, while plotly express still hands out the colours;
		# one too short to give every category its own is skipped, as the form says.
		picked = theme.PALETTES.get(state.get("format", {}).get("palette", {}).get("value"))
		fits = picked is not None and len(picked) >= n
		kwargs["color_discrete_sequence"] = picked[:n] if fits else theme.sample_palette(n)

	try:
		figure = plot.builder(data, **kwargs, **plot.extra, labels=labels, template=TEMPLATE)
	except Exception as error:  # plotly rejects plenty of otherwise sensible combinations
		return placeholder(f"{type(error).__name__}: {error}"), [note.text for note in notes]

	# The declared colorway is what tells Format this figure has categories to recolour.
	figure.update_layout(
		margin={"l": 60, "r": 20, "t": 40, "b": 40},
		legend={"title": None},
		colorway=kwargs.get("color_discrete_sequence"),
	)
	figure.for_each_annotation(lambda note: note.update(text=note.text.split("=")[-1]))

	return figure, [note.text for note in notes]


def auto_titles(figure: go.Figure) -> dict[str, str | None]:
	"""The titles plotly express gave each element Format can change.

	Args:
		figure: a figure straight out of ``build_figure``.

	Returns:
		Title text per element: ``""`` when the element is drawn untitled, ``None``
		when the figure has no such element (no cartesian axes, no colour bar). The
		colour axis and colorway carry no text, so they are ``""`` whenever present.
	"""
	cartesian = any(getattr(trace, "xaxis", None) for trace in figure.data)
	colorbar = figure.layout.coloraxis.colorbar.title.text

	def axis_title(axes: Iterable[Any]) -> str | None:
		return (
			next((axis.title.text for axis in axes if axis.title.text), "") if cartesian else None
		)

	return {
		"title": figure.layout.title.text or "",
		"xaxis": axis_title(figure.select_xaxes()),
		"yaxis": axis_title(figure.select_yaxes()),
		"colorbar": colorbar or None,
		"coloraxis": None if colorbar is None else "",
		"colorway": "" if figure.layout.colorway else None,
	}


def live_format(fmt: dict[str, Any], auto: dict[str, str | None]) -> dict[str, Any]:
	"""The overrides in ``fmt`` whose element still carries the title they were set on."""
	return {
		key: entry["value"] for key, entry in fmt.items() if entry["on"] == auto[FORMAT_BINDS[key]]
	}


def inverted(low: float | None, high: float | None) -> bool:
	"""Whether a pair of Format bounds crosses, which draws nothing but the form's error."""
	return low is not None and high is not None and low >= high


def apply_format(figure: go.Figure, fmt: dict[str, Any]) -> dict[str, str | None]:
	"""Draw the Format overrides that still hold onto ``figure``.

	Args:
		figure: a figure straight out of ``build_figure``.
		fmt: ``state["format"]``, key -> ``{"on": title it was set on, "value": ...}``.

	Returns:
		The automatic titles, as ``auto_titles`` read them before any override.
	"""
	auto = auto_titles(figure)
	live = live_format(fmt, auto)

	if "title" in live:
		figure.update_layout(title_text=live["title"])
	for letter, axes in (("x", figure.select_xaxes), ("y", figure.select_yaxes)):
		every = list(axes())
		if f"{letter}axis" in live:
			# Facets title only their outer axes; an untitled axis gets it on the first.
			for axis in [axis for axis in every if axis.title.text] or every[:1]:
				axis.title.text = live[f"{letter}axis"]
		low, high = live.get(f"{letter}min"), live.get(f"{letter}max")
		if (low is not None or high is not None) and not inverted(low, high):
			# minallowed/maxallowed hold one bound while the data still sets the other; a
			# figure that drew its own range hands it back to autorange for them to count.
			for axis in every:
				axis.update(
					autorange=True,
					range=None,
					autorangeoptions={"minallowed": low, "maxallowed": high},
				)
	if "colorbar" in live:
		figure.update_layout(coloraxis_colorbar_title_text=live["colorbar"])
	if scale := theme.COLORSCALES.get(live.get("colorscale")):
		figure.update_layout(coloraxis_colorscale=scale)

	cmin, cmax = live.get("cmin"), live.get("cmax")
	if (cmin is not None or cmax is not None) and not inverted(cmin, cmax):
		# With cauto off plotly fills a missing bound from the data; on, it ignores both.
		figure.update_layout(coloraxis={"cauto": False, "cmin": cmin, "cmax": cmax})

	return auto


def prune(state: dict[str, Any], keep: Iterable[str]) -> tuple[dict[str, Any], list[str]]:
	"""Drop assignments the new plot type has no shelf for.

	Args:
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
