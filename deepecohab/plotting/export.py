"""Lay a figure out for a physical export size, then render it.

Plotly does not fit a figure to a target size on its own: legends overlap plots,
long axis titles get clipped, and stacked panels collide. :func:`fit_for_export`
applies one set of rules - checked through kaleido at 85x64 and 174x140 mm on a
stacked heatmap, a line plot with events and a four-row facet plot - so both the
app and a notebook get the same, readable output. It mirrors the blueprint's
``fitForExport``, used for the live export preview, rule for rule.
"""

import base64
import copy
import math
import re
from pathlib import Path
from typing import Any, Literal

import numpy as np
import plotly.graph_objects as go
import polars as pl

PX_PER_MM = 96 / 25.4

_CHAR = 0.55
"""Average glyph width as a fraction of font size, for text-fit estimates."""

_MIN_PANEL_LINES = 3.5
"""Panels shorter than this many lines of text at the chosen point size are warned about."""

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(text: Any) -> str:
	"""Strip HTML tags a plotly title, tick label or annotation text may carry."""
	return _TAG_RE.sub("", str(text or ""))


def _title_text(title: Any) -> str:
	"""The text of a plotly title, given either as a bare string or a title dict."""
	if isinstance(title, str):
		return title
	if isinstance(title, dict):
		return str(title.get("text") or "")
	return ""


def _wrap_text(text: str, max_chars: int) -> str:
	"""Greedy word wrap to roughly ``max_chars`` per line, joined with plotly's ``<br>``."""
	lines: list[str] = []
	line = ""
	for word in text.split():
		if line and len(line) + 1 + len(word) > max_chars:
			lines.append(line)
			line = word
		else:
			line = f"{line} {word}".strip()
	lines.append(line)
	return "<br>".join(lines)


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

	if longest <= tick * 2.5:
		step = math.ceil((longest * 1.6) / slot) if slot < longest * 1.6 else 1
	else:
		axis["tickangle"] = -90 if slot < longest * 1.1 else 0
		step = math.ceil((tick * 1.3) / slot) if slot < tick * 1.3 else 1

	if step > 1:
		kept = labels[::step]
		axis.update({"tickmode": "array", "tickvals": kept, "ticktext": kept})


def fit_for_export(
	fig: go.Figure,
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
		fig: the figure to export. Its ``layout.template`` is used as given - callers
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
	source = fig.to_dict()
	data: list[dict[str, Any]] = copy.deepcopy(source.get("data", []))
	layout: dict[str, Any] = copy.deepcopy(source.get("layout", {}))
	notes: list[str] = []

	width = round(width_mm * PX_PER_MM)
	height = round(height_mm * PX_PER_MM)
	base = pt * 96 / 72
	tick = base * 0.875

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
				"font": {"size": base * 1.15},
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

	# Event labels are drawn in front of the data; the toggle drops them entirely.
	for note in annotations:
		if not str(note.get("name") or "").startswith("event-label"):
			continue
		if show_events:
			note["font"] = {**note.get("font", {}), "size": tick}
			width_chars = max(12, int((width * 0.45) / (_CHAR * tick)))
			note["text"] = _wrap_text(_plain_text(note.get("text")), width_chars)
		else:
			note["visible"] = False

	for shape in layout.get("shapes") or []:
		line = shape.get("line")
		if line and line.get("width"):
			line["width"] = min(line["width"], 1.5)
		label = shape.get("label")
		if label and label.get("text"):
			if show_events:
				label["font"] = {**label.get("font", {}), "size": tick}
			else:
				label["text"] = ""

	entries: dict[str, str] = {}
	if show_legend:
		for trace in data:
			if trace.get("showlegend") is False or not trace.get("name"):
				continue
			key = trace.get("legendgroup") or trace["name"]
			entries.setdefault(key, _plain_text(trace["name"]))

	item_px = (max((len(name) for name in entries.values()), default=0)) * _CHAR * tick + 46
	has_colorbar = any(key.startswith("coloraxis") for key in layout)
	axis_bottom = tick * 1.5 + base * 1.6

	if entries:
		# The legend always sits at the side, past the colour bar when there is one.
		layout["legend"] = {
			"font": {"size": tick},
			"title": {"text": ""},
			"tracegroupgap": 0,
			"bgcolor": "rgba(0,0,0,0)",
			"itemwidth": 30,
			"orientation": "v",
			"x": 1.02 + (base * 0.8 + tick * 4) / (width * 0.72) if has_colorbar else 1.01,
			"xanchor": "left",
			"y": 1,
			"yanchor": "top",
		}
		if item_px > 0.4 * width:
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
			"thickness": max(6, base * 0.8),
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
	top_px = (base * 1.6 if title else 0) + (base * 1.7 if (above or titles_above) else 0)
	bottom_px = axis_bottom
	plot_h = max(height - top_px - bottom_px, 1)

	if entries and len(entries) * tick * 1.6 > plot_h:
		needed = math.ceil((len(entries) * tick * 1.6 + top_px + bottom_px) / PX_PER_MM)
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
		gap_px = base * (1.7 if titles_above else 0.9)
		gap = min(gap_px / plot_h, 0.3 / (n - 1))
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
				"title": axis_title(axis, max(8, int(px_h / (_CHAR * base))), base * 0.4),
			}
		)
		labels = _category_labels(data, key, "y")
		if labels and px_h / len(labels) < tick * 1.15:
			step = math.ceil((tick * 1.15) / (px_h / len(labels)))
			kept = labels[::step]
			axis.update({"tickmode": "array", "tickvals": kept, "ticktext": kept})

	plot_w = width * 0.72 - (item_px if entries else 0)
	for key in _axis_keys(layout, "x"):
		axis = layout[key]
		axis.update(
			{
				"automargin": True,
				"tickfont": {**axis.get("tickfont", {}), "size": tick},
				"title": axis_title(axis, max(10, int(plot_w / (_CHAR * base))), base * 0.3),
			}
		)
		labels = _category_labels(data, key, "x")
		if labels:
			_thin_axis(axis, labels, plot_w / len(labels), tick)
		elif axis.get("dtick") is not None:
			axis.pop("dtick", None)
			axis.update({"tickmode": "auto", "nticks": max(3, int(plot_w / (tick * 3.2)))})

	if "polar" in layout:
		layout["polar"]["angularaxis"] = {
			**(layout["polar"].get("angularaxis") or {}),
			"tickfont": {"size": tick},
		}
		layout["polar"]["radialaxis"] = {
			**(layout["polar"].get("radialaxis") or {}),
			"tickfont": {"size": tick},
		}

	for trace in data:
		if trace.get("type") in ("scatter", "scattergl"):
			line = trace.get("line")
			if line and line.get("width"):
				line["width"] = min(line["width"], 1.5)

	return go.Figure(data=data, layout=layout), notes


def ensure_chrome_available() -> bool:
	"""Whether kaleido has a Chrome binary to render through.

	kaleido 1.3 needs one; call this once at app start so export can be disabled with
	a clear message instead of every attempt failing deep inside kaleido.
	"""
	import kaleido

	try:
		kaleido.get_chrome_sync()
		return True
	except Exception:
		return False


def export_figure(
	fig: go.Figure,
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
		fig: the figure to export.
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
	fitted, notes = fit_for_export(fig, width_mm, height_mm, pt, title, show_legend, show_events)
	scale = dpi / 96 if format == "png" else 1
	fitted.write_image(str(path), format=format, scale=scale)

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


def figure_data_csv(fig: dict[str, Any]) -> str | None:
	"""The data actually drawn in ``fig``, as one long CSV, or ``None`` if there is none.

	Generic across chart types rather than reading from a plot-specific table, so the
	export dialog's "plotted data" checkbox needs no per-plot backend hook: every trace
	contributes its ``x``/``y`` (or ``r``/``theta``, or a heatmap's flattened ``z``) as
	rows tagged with the trace's name. A trace shaped some other way - a pie's
	``labels``/``values``, say - contributes nothing.

	Args:
		fig: a plotly figure, as the dict a ``dcc.Graph`` carries.

	Returns:
		The CSV text, or ``None`` when no trace has tabular data to offer.
	"""
	rows: list[dict[str, Any]] = []

	for trace in fig.get("data", []):
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
			for index, (xv, yv) in enumerate(zip(x, y, strict=False)):
				row = {"trace": name, "x": xv, "y": yv}
				if has_text:
					row["text"] = texts[index]
				rows.append(row)

	return pl.DataFrame(rows).write_csv() if rows else None
