import base64
import copy
import math
import re
import textwrap
from functools import cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import plotly.graph_objects as go
import polars as pl

PX_PER_MM = 96 / 25.4

_ROUNDED_CORNERS_JS = Path(__file__).parents[1] / "app" / "assets" / "rounded_corners.js"

_CHAR = 0.55
"""Average glyph width as a fraction of font size, for text-fit estimates."""

_MIN_PANEL_LINES = 3.5
"""Panels shorter than this many lines of text at the chosen point size are warned about."""

_TICK_SCALE = 0.875
"""Tick and legend font size, as a fraction of the base font size."""

_TITLE_SCALE = 1.15
"""Figure title font size, as a multiple of the base font size."""

_LINE_HEIGHT = 1.6
"""One line of text, as a multiple of its font size: the height a title or legend row needs."""

_ROW_TITLE_HEIGHT = 1.7
"""The gap a facet row title needs above its panel, as a multiple of the base font size."""

_PANEL_GAP = 0.9
"""The gap between untitled stacked panels, as a multiple of the base font size."""

_MAX_PANEL_GAP = 0.3
"""Total share of the plot height the inter-panel gaps may take."""

_MIN_TICK_GAP = 1.15
"""Smallest slot a tick label may sit in, as a multiple of the tick font size."""

_MAX_LINE_PX = 1.5
"""Line width is capped here: a heavier stroke reads as a smear at export sizes."""

LEGEND_ITEM_PX = 46
"""Swatch, padding and margin around a legend label, in pixels."""

_LEGEND_WARN_FRACTION = 0.4
"""A legend wider than this share of the figure earns a warning."""

_PLOT_WIDTH_FRACTION = 0.72
"""Share of the figure width the plotting area gets once axes and margins are paid for."""

_EVENT_LABEL_FRACTION = 0.45
"""Share of the figure width an event label may run to before it wraps."""

_COLORBAR_THICKNESS = 0.8
"""Colour bar thickness, as a multiple of the base font size, floored at 6 px."""

_AXIS_STANDOFF = {"y": 0.4, "x": 0.3}
"""Gap between an axis title and its ticks, as a multiple of the base font size."""

_TICK_SPACING = 3.2
"""Smallest gap between automatic x ticks, as a multiple of the tick font size."""

_TICK_ROW_HEIGHT = 1.5
"""Height a row of tick labels needs, as a multiple of the tick font size."""

_COLORBAR_LABEL_CHARS = 4
"""Tick labels beside a colour bar, in characters: how far past it the legend must sit."""

_WIDE_LABEL_SCALE = 2.5
"""Labels longer than this many tick heights are thinned rather than rotated."""

_ROTATE_BELOW = 1.1
"""Horizontal labels are rotated once their slot falls below this share of their width."""

_ROTATED_TICK_GAP = 1.3
"""Smallest slot a rotated tick label may sit in, as a multiple of the tick font size."""

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(text: Any) -> str:
	"""Strip HTML tags a plotly title, tick label or annotation text may carry."""
	return _TAG_RE.sub("", str(text or ""))


def text_px(text: Any, size: float) -> float:
	"""Estimated width of the widest ``<br>``-separated line of ``text`` at font ``size``."""
	return max(len(_plain_text(line)) for line in str(text or "").split("<br>")) * _CHAR * size


def _title_text(title: Any) -> str:
	"""The text of a plotly title, given either as a bare string or a title dict."""
	if isinstance(title, str):
		return title
	if isinstance(title, dict):
		return str(title.get("text") or "")
	return ""


def _wrap_text(text: str, max_chars: int) -> str:
	"""Greedy word wrap to roughly ``max_chars`` per line, joined with plotly's ``<br>``."""
	# Neither break keeps a word whole past max_chars, as a plot title needs.
	words = " ".join(text.split())
	return "<br>".join(
		textwrap.wrap(words, max_chars, break_long_words=False, break_on_hyphens=False)
	)


def _axis_keys(layout: dict[str, Any], letter: str) -> list[str]:
	"""Every ``{letter}axis[N]`` key in ``layout``, in axis order (``xaxis`` first)."""
	prefix = f"{letter}axis"
	pattern = re.compile(rf"^{re.escape(prefix)}\d*$")
	keys = [key for key in layout if pattern.match(key)]
	return sorted(keys, key=lambda key: int(key[len(prefix) :] or 1))


def _category_labels(data: list[dict[str, Any]], key: str, letter: str) -> list[str] | None:
	"""String tick labels for one axis, read off a heatmap trace that uses it.

	A category axis carries no tick labels of its own in plotly - the labels live on
	the trace - so thinning them has to look at the trace, not the axis.
	"""
	prefix = f"{letter}axis"
	ref = letter + key[len(prefix) :]

	for trace in data:
		if trace.get("type") != "heatmap":
			continue
		if (trace.get(prefix) or letter) != ref:
			continue
		values = trace.get(letter)
		if isinstance(values, list) and values and isinstance(values[0], str):
			return values

	return None


def _thin_axis(axis: dict[str, Any], labels: list[Any], slot: float, tick: float) -> None:
	"""Drop enough tick labels that the survivors fit their slot, rotating first."""
	longest = max(len(str(label)) for label in labels) * _CHAR * tick

	if longest <= tick * _WIDE_LABEL_SCALE:
		step = math.ceil((longest * _LINE_HEIGHT) / slot) if slot < longest * _LINE_HEIGHT else 1
	else:
		axis["tickangle"] = -90 if slot < longest * _ROTATE_BELOW else 0
		step = (
			math.ceil((tick * _ROTATED_TICK_GAP) / slot) if slot < tick * _ROTATED_TICK_GAP else 1
		)

	if step > 1:
		kept = labels[::step]
		axis.update({"tickmode": "array", "tickvals": kept, "ticktext": kept})


def fit_for_export(
	figure: go.Figure,
	width_mm: float,
	height_mm: float,
	pt: float,
	title: str = "",
	show_legend: bool = True,
	show_events: bool = True,
) -> tuple[go.Figure, list[str]]:
	"""Lay a figure out for its physical export size before kaleido renders it.

	The rules, in order: one font scale from ``pt``; automargin on every axis and the
	title, with long axis titles wrapped to the space they have; stacked panels get
	gaps sized to their titles, and row titles keep their spot; the legend always sits
	at the side, past the colour bar when there is one; dense category ticks are
	thinned, and a forced ``dtick`` goes back to automatic; event labels are drawn in
	front of the data at the tick size, or dropped when ``show_events`` is false; lines
	are capped at 1.5 px.

	Args:
		figure: the figure to export. Its ``layout.template`` is used as given - callers
			choose ``light``, ``dark`` or ``publication`` before calling this.
		width_mm: physical width.
		height_mm: physical height.
		pt: base font size in points; every other size scales from it.
		title: figure title to draw, or ``""`` to omit it.
		show_legend: keep the legend, or drop it entirely.
		show_events: keep event-span labels and lines, or drop them.

	Returns:
		A new figure sized and typeset for export, and warnings about anything that
		still would not fit - an oversized legend, or panels too short to read.
	"""
	source = figure.to_dict()
	data: list[dict[str, Any]] = copy.deepcopy(source.get("data", []))
	layout: dict[str, Any] = copy.deepcopy(source.get("layout", {}))
	notes: list[str] = []

	# A trace draws its axes whether or not the layout names them; name every one, so the
	# axis passes below reach them all.
	for trace in figure.data:
		if "xaxis" in trace:
			for letter in "xy":
				layout.setdefault(f"{letter}axis{(trace[f'{letter}axis'] or letter)[1:]}", {})

	width = round(width_mm * PX_PER_MM)
	height = round(height_mm * PX_PER_MM)
	base = pt * 96 / 72
	tick = base * _TICK_SCALE

	layout.update(
		{
			"width": width,
			"height": height,
			"autosize": False,
			"showlegend": layout.get("showlegend") if show_legend else False,
			"font": {**layout.get("font", {}), "size": base},
			"margin": {"l": 2, "r": 2, "t": 2, "b": 2, "pad": 0, "autoexpand": True},
			"title": {
				"text": title or "",
				"font": {"size": base * _TITLE_SCALE},
				"automargin": True,
				"x": 0,
				"xanchor": "left",
				"yref": "container",
				"y": 0.995,
				"yanchor": "top",
			},
		}
	)

	annotations: list[dict[str, Any]] = layout.get("annotations") or []
	for note in annotations:
		note["font"] = {**note.get("font", {}), "size": base}

	above = [
		note
		for note in annotations
		if (note.get("yref") or "paper") == "paper"
		and note.get("y", 0) > 1.001
		and note.get("yanchor") != "bottom"
	]
	side = [
		note
		for note in annotations
		if (note.get("xref") or "paper") == "paper" and abs(note.get("textangle") or 0) == 90
	]
	above_ids = {id(note) for note in above}
	side_ids = {id(note) for note in side}

	for note in above:
		note.update({"y": 1, "yanchor": "bottom", "yshift": 1})
	for note in side:
		note.update(
			{
				"text": _plain_text(note.get("text")).replace("_", " "),
				"x": 0,
				"xanchor": "left",
				"xshift": 0,
				"textangle": 0,
				"yanchor": "bottom",
			}
		)

	# Event labels ride a shape, clipped to the plot area; the toggle drops them entirely.
	label_chars = max(12, int((width * _EVENT_LABEL_FRACTION) / (_CHAR * tick)))
	for shape in layout.get("shapes") or []:
		line = shape.get("line")
		if line and line.get("width"):
			line["width"] = min(line["width"], _MAX_LINE_PX)
		label = shape.get("label")
		if label and label.get("text"):
			if show_events:
				label["font"] = {**label.get("font", {}), "size": tick}
				label["text"] = _wrap_text(_plain_text(label["text"]), label_chars)
			else:
				label["text"] = ""

	entries: dict[str, str] = {}
	if show_legend:
		for trace in data:
			if trace.get("showlegend") is False or not trace.get("name"):
				continue
			key = trace.get("legendgroup") or trace["name"]
			entries.setdefault(key, _plain_text(trace["name"]))

	longest_entry = max((len(name) for name in entries.values()), default=0)
	item_px = longest_entry * _CHAR * tick + LEGEND_ITEM_PX
	has_colorbar = any(key.startswith("coloraxis") for key in layout)
	axis_bottom = tick * _TICK_ROW_HEIGHT + base * _LINE_HEIGHT

	if entries:
		# The legend always sits at the side, past the colour bar when there is one.
		layout["legend"] = {
			"font": {"size": tick},
			"title": {"text": ""},
			"tracegroupgap": 0,
			"bgcolor": "rgba(0,0,0,0)",
			"itemwidth": 30,
			"orientation": "v",
			"x": 1.02
			+ (base * _COLORBAR_THICKNESS + tick * _COLORBAR_LABEL_CHARS)
			/ (width * _PLOT_WIDTH_FRACTION)
			if has_colorbar
			else 1.01,
			"xanchor": "left",
			"y": 1,
			"yanchor": "top",
		}
		if item_px > _LEGEND_WARN_FRACTION * width:
			notes.append(
				f"The legend takes {round(100 * item_px / width)}% of the width; "
				"widen the figure or shorten the names."
			)

	for key in list(layout):
		if not key.startswith("coloraxis"):
			continue
		bar = layout[key].get("colorbar") or {}
		layout[key]["colorbar"] = {
			**bar,
			# Print wants a physical thickness, not the theme's fraction of the plot.
			"thicknessmode": "pixels",
			"thickness": max(6, base * _COLORBAR_THICKNESS),
			"outlinewidth": 0,
			"tickfont": {"size": tick},
			"title": {**(bar.get("title") or {}), "font": {"size": tick}, "side": "right"},
			"xpad": 4,
			"ypad": 0,
		}

	# A pre-existing row title - not one this pass just relocated - drives extra gap.
	titles_above = any(
		note.get("yanchor") == "bottom"
		and (note.get("yref") or "paper") == "paper"
		and id(note) not in above_ids
		for note in annotations
	)
	top_px = (base * _LINE_HEIGHT if title else 0) + (
		base * _ROW_TITLE_HEIGHT if (above or titles_above) else 0
	)
	bottom_px = axis_bottom

	# A shape in paper units above the plot - the phase band - sits in the top margin, and
	# overhangs by a share of the plot height, so its room comes out of that height too.
	overhang = max(
		(
			max(shape.get("y0", 0), shape.get("y1", 0)) - 1
			for shape in layout.get("shapes") or []
			if shape.get("yref") == "paper"
		),
		default=0,
	)
	if overhang > 0:
		top_px += overhang * (height - top_px - bottom_px) / (1 + overhang)
	plot_h = max(height - top_px - bottom_px, 1)

	if entries and len(entries) * tick * _LINE_HEIGHT > plot_h:
		needed = math.ceil((len(entries) * tick * _LINE_HEIGHT + top_px + bottom_px) / PX_PER_MM)
		notes.append(
			f"The legend needs {needed} mm of height for {len(entries)} entries at {pt} pt."
		)

	y_keys = _axis_keys(layout, "y")

	def domain_of(key: str) -> tuple[float, float]:
		lo, hi = layout[key].get("domain", [0, 1])
		return (round(lo, 4), round(hi, 4))

	rows = sorted(dict.fromkeys(domain_of(key) for key in y_keys), key=lambda d: -d[1])
	n = len(rows)

	if n > 1:
		gap_px = base * (_ROW_TITLE_HEIGHT if titles_above else _PANEL_GAP)
		gap = min(gap_px / plot_h, _MAX_PANEL_GAP / (n - 1))
		span = (1 - gap * (n - 1)) / n
		mapping = {
			row: (max(0.0, 1 - (i + 1) * span - i * gap), min(1.0, 1 - i * span - i * gap))
			for i, row in enumerate(rows)
		}
		old_domains = {key: domain_of(key) for key in y_keys}
		for key in y_keys:
			layout[key]["domain"] = list(mapping[old_domains[key]])

		for note in annotations:
			if (note.get("yref") or "paper") != "paper" or note.get("y") is None:
				continue
			if id(note) in above_ids:
				continue
			for (lo, hi), (new_lo, new_hi) in mapping.items():
				if lo - 1e-3 <= note["y"] <= hi + 0.08:
					scale = (new_hi - new_lo) / (hi - lo)
					if id(note) in side_ids:
						note["y"] = new_hi
					elif note["y"] <= hi:
						note["y"] = new_lo + (note["y"] - lo) * scale
					else:
						note["y"] = new_hi + (note["y"] - hi) * scale
					break

		if span * plot_h < base * _MIN_PANEL_LINES:
			needed = math.ceil(
				(n * base * _MIN_PANEL_LINES + (n - 1) * gap_px + top_px + bottom_px) / PX_PER_MM
			)
			notes.append(
				f"{n} panels get {round(span * plot_h / PX_PER_MM)} mm each; give it at least "
				f"{needed} mm of height at {pt} pt."
			)

	layout.setdefault("margin", {})["t"] = max(2, top_px)

	def axis_title(axis: dict[str, Any], max_chars: int, standoff: float) -> dict[str, Any]:
		title = axis.get("title")
		existing: dict[str, Any] = title if isinstance(title, dict) else {}
		text = _plain_text(_title_text(title))
		return {
			**existing,
			"text": _wrap_text(text, max_chars) if text else "",
			"standoff": standoff,
			"font": {"size": base},
		}

	for key in y_keys:
		axis = layout[key]
		lo, hi = axis.get("domain", [0, 1])
		px_h = (hi - lo) * plot_h
		axis.update(
			{
				"automargin": True,
				"tickfont": {**axis.get("tickfont", {}), "size": tick},
				"title": axis_title(
					axis, max(8, int(px_h / (_CHAR * base))), base * _AXIS_STANDOFF["y"]
				),
			}
		)
		labels = _category_labels(data, key, "y")
		if labels and px_h / len(labels) < tick * _MIN_TICK_GAP:
			step = math.ceil((tick * _MIN_TICK_GAP) / (px_h / len(labels)))
			kept = labels[::step]
			axis.update({"tickmode": "array", "tickvals": kept, "ticktext": kept})

	plot_w = width * _PLOT_WIDTH_FRACTION - (item_px if entries else 0)
	for key in _axis_keys(layout, "x"):
		axis = layout[key]
		axis.update(
			{
				"automargin": True,
				"tickfont": {**axis.get("tickfont", {}), "size": tick},
				"title": axis_title(
					axis, max(10, int(plot_w / (_CHAR * base))), base * _AXIS_STANDOFF["x"]
				),
			}
		)
		labels = _category_labels(data, key, "x")
		if labels:
			_thin_axis(axis, labels, plot_w / len(labels), tick)
		elif axis.get("dtick") is not None:
			axis.pop("dtick", None)
			axis.update(
				{"tickmode": "auto", "nticks": max(3, int(plot_w / (tick * _TICK_SPACING)))}
			)

	if "polar" in layout:
		angular = layout["polar"].get("angularaxis") or {}
		layout["polar"]["angularaxis"] = {**angular, "tickfont": {"size": tick}}
		layout["polar"]["radialaxis"] = {
			**(layout["polar"].get("radialaxis") or {}),
			"tickfont": {"size": tick},
		}
		# Polar axes have no automargin: the angular labels hang past the circle, so the
		# margins make room for them and the legend is pinned beyond the right-hand ones.
		aliases = angular.get("labelalias") or {}
		labels = [
			str(aliases.get(t, t))
			for trace in data
			if trace.get("theta") is not None
			for t in trace["theta"]
		]
		if labels:
			label_px = max(text_px(label, tick) for label in labels) + tick
			label_h = max(label.count("<br>") + 1 for label in labels) * tick * _LINE_HEIGHT
			layout["margin"].update(
				{
					"l": label_px,
					"r": label_px + (item_px if entries else 0),
					"t": top_px + label_h,
					"b": label_h,
				}
			)
			if entries:
				layout["legend"].update({"xref": "container", "x": 1, "xanchor": "right"})

	for trace in data:
		if trace.get("type") in ("scatter", "scattergl"):
			line = trace.get("line")
			if line and line.get("width"):
				line["width"] = min(line["width"], _MAX_LINE_PX)

	return go.Figure(data=data, layout=layout), notes


@cache
def ensure_chrome_available() -> bool:
	"""Whether kaleido has a Chrome binary to render through, checked once per process.

	kaleido 1.3 needs one; call this at app start so export can be disabled with a
	clear message instead of every attempt failing deep inside kaleido.
	"""
	import kaleido

	try:
		kaleido.get_chrome_sync()
		return True
	except Exception:
		return False


def export_figure(
	figure: go.Figure,
	path: str | Path,
	width_mm: float,
	height_mm: float,
	pt: float,
	format: Literal["svg", "pdf", "png"],
	dpi: int = 300,
	title: str = "",
	show_legend: bool = True,
	show_events: bool = True,
) -> list[str]:
	"""Fit a figure to its export size and render it to disk.

	SVG and PDF keep the physical size the figure was fit to; a PNG is rasterised at
	``scale = dpi / 96`` so its pixel dimensions match the requested resolution while
	the layout - built for ``width_mm``/``height_mm`` at 96 px/inch - stays unscaled.

	Args:
		figure: the figure to export.
		path: where to write the file.
		width_mm: physical width.
		height_mm: physical height.
		pt: base font size in points.
		format: image format kaleido renders. No TIFF or EPS: kaleido 1 dropped EPS.
		dpi: raster resolution; ignored for ``svg`` and ``pdf``.
		title: figure title to draw, or ``""`` to omit it.
		show_legend: keep the legend, or drop it entirely.
		show_events: keep event-span labels and lines, or drop them.

	Returns:
		Warnings from :func:`fit_for_export`, so a caller can surface them alongside
		the file it wrote.
	"""
	import kaleido

	fitted, notes = fit_for_export(figure, width_mm, height_mm, pt, title, show_legend, show_events)
	scale = dpi / 96 if format == "png" else 1
	# Rounded boxes and tiles are drawn by the app's script, not by plotly, so kaleido's page
	# loads it too - which figure.write_image has no way to ask for.
	page = kaleido.PageGenerator(others=[(_ROUNDED_CORNERS_JS.as_uri(), "utf-8")])
	kaleido.write_fig_sync(
		fitted, path=path, opts={"format": format, "scale": scale}, kopts={"page_generator": page}
	)

	return notes


def _plotly_array(value: Any) -> Any:
	"""A trace field as a plain nested list, decoding plotly's typed-array form.

	Recent plotly.py encodes a numeric numpy array as ``{"dtype": ..., "bdata": ...}``
	(plus ``"shape"`` for anything beyond 1-D, e.g. a heatmap's ``z``) instead of a
	plain JSON list, for a smaller payload over the wire. A string array - axis
	category labels, hover text - is unaffected and passes through unchanged.
	"""
	if not (isinstance(value, dict) and "bdata" in value and "dtype" in value):
		return value
	array = np.frombuffer(base64.b64decode(value["bdata"]), dtype=value["dtype"])
	if "shape" in value:
		array = array.reshape(tuple(int(n) for n in str(value["shape"]).split(",")))
	return array.tolist()


def _axis_values(values: list[Any], axis: dict[str, Any]) -> list[Any]:
	"""A trace's coordinates as its axis labels them, where the trace holds plain numbers.

	Epoch milliseconds on a date axis become ISO datetimes, and positions on an axis whose
	ticks are relabelled through ``tickvals``/``ticktext`` become that tick text.
	"""
	if not values or not all(isinstance(value, int | float) for value in values):
		return values
	if axis.get("type") == "date":
		stamps = np.array(values, dtype="float64").astype("datetime64[ms]")
		return np.datetime_as_string(stamps).tolist()
	if axis.get("tickvals") is not None and axis.get("ticktext") is not None:
		labels = dict(zip(axis["tickvals"], axis["ticktext"], strict=False))
		return [labels.get(value, value) for value in values]
	return values


def figure_data_csv(figure: dict[str, Any]) -> list[str]:
	"""The data actually drawn in ``figure``, as one long CSV per subplot.

	Generic across chart types rather than reading from a plot-specific table, so the
	export dialog's "plotted data" checkbox needs no per-plot backend hook: every trace
	contributes its ``x``/``y`` (or ``r``/``theta``, or a heatmap's flattened ``z``) as
	rows tagged with the trace's name. A trace shaped some other way - a pie's
	``labels``/``values``, say - contributes nothing.

	Args:
		figure: a plotly figure, as the dict a ``dcc.Graph`` carries.

	Returns:
		One CSV per subplot that holds data, in drawing order; empty if none does. Subplots
		never share a table: their columns need not agree - a line's ``y`` is a value where
		the horizontal bar beside it has a label.
	"""
	subplots: dict[tuple[str, str], list[dict[str, Any]]] = {}
	layout = figure.get("layout", {})

	def axis(trace: dict[str, Any], letter: str) -> dict[str, Any]:
		ref = trace.get(f"{letter}axis") or letter
		return layout.get(f"{letter}axis{ref[1:]}", {})

	for trace in figure.get("data", []):
		rows = subplots.setdefault((trace.get("xaxis") or "x", trace.get("yaxis") or "y"), [])
		name = trace.get("name") or trace.get("type", "trace")
		x, y = _plotly_array(trace.get("x")), _plotly_array(trace.get("y"))
		z = _plotly_array(trace.get("z"))
		r, theta = _plotly_array(trace.get("r")), _plotly_array(trace.get("theta"))

		if trace.get("type") == "heatmap" and z is not None:
			xs = x or list(range(len(z[0]) if z else 0))
			ys = y or list(range(len(z)))
			rows.extend(
				{"trace": name, "x": xv, "y": yv, "z": value}
				for yv, row in zip(ys, z, strict=False)
				for xv, value in zip(xs, row, strict=False)
			)
		elif r is not None and theta is not None:
			rows.extend(
				{"trace": name, "theta": t, "r": rv} for rv, t in zip(r, theta, strict=False)
			)
		elif x is not None and y is not None:
			texts = _plotly_array(trace.get("text"))
			has_text = isinstance(texts, list) and len(texts) == len(x)
			xs, ys = _axis_values(x, axis(trace, "x")), _axis_values(y, axis(trace, "y"))
			for index, (xv, yv) in enumerate(zip(xs, ys, strict=False)):
				if x[index] is None or x[index] != x[index]:  # a gap between segments, not a point
					continue
				row = {"trace": name, "x": xv, "y": yv}
				if has_text:
					row["text"] = texts[index]
				rows.append(row)

	return [
		pl.DataFrame(rows, infer_schema_length=None).write_csv()
		for rows in subplots.values()
		if rows
	]
