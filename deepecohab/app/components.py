import json
import math
from collections import deque
from collections.abc import Sequence
from html import escape
from typing import Any
from urllib.parse import quote

import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import dcc, html

from deepecohab.core.data_model import Layout
from deepecohab.plotting import export as plot_export
from deepecohab.plotting.theme import COLORSCALES, PALETTES

DIALOG_CLASSES = {
	"content": "deh-dialog",
	"header": "deh-dialog-head",
	"title": "deh-dialog-title",
	"body": "deh-dialog-content",
}

EXPORT_FONT_SIZES = ["6", "7", "8", "9", "10", "12"]

#: A blank graph before its callback fills it in. Plotly's own default figure ``{}``
#: renders a white paper and grid, which flashes wrong on a dark card or theme.
EMPTY_FIGURE: dict[str, Any] = {
	"data": [],
	"layout": {
		"paper_bgcolor": "rgba(0,0,0,0)",
		"plot_bgcolor": "rgba(0,0,0,0)",
		"xaxis": {"visible": False},
		"yaxis": {"visible": False},
	},
}


def placeholder(message: str) -> html.Div:
	"""A centred info panel standing in for content a page cannot show yet."""
	return html.Div(
		[icon("info-circle", size=20), html.P(message)],
		className="deh-alert deh-alert-info",
		style={"maxWidth": "560px", "margin": "48px auto"},
	)


def icon(name: str, size: int = 18, class_name: str = "", **style) -> html.Span:
	"""A Tabler outline icon from ``assets/icons``, tinted by ``currentColor``.

	Args:
		name: file stem under ``assets/icons/`` (no extension).
		size: square size in px.
		class_name: extra CSS classes, e.g. to swap icons by theme.
		style: extra CSS merged over the size and mask, e.g. ``color=``.
	"""
	mask = f"url({dash.get_asset_url(f'icons/{name}.svg')}) center / contain no-repeat"
	return html.Span(
		className=f"deh-ic {class_name}".strip(),
		title=name.capitalize(),
		style={"width": size, "height": size, "WebkitMask": mask, "mask": mask, **style},
	)


def notify(kind: str, message: str) -> None:
	"""Show a toast through the shell's ``NotificationContainer``, from inside a callback.

	Sent with ``set_props`` rather than as an Output: Dash runs a page callback whose Output
	lives in the shell every time it inserts the page, whatever ``prevent_initial_call`` says.

	Args:
		kind: ``good``, ``warn``, ``bad`` or ``info``; picks the icon and its colour.
		message: the text shown.
	"""
	toast = {
		"action": "show",
		"message": message,
		"className": f"deh-toast deh-toast-{kind}",
		"withCloseButton": False,
		"autoClose": 5200,
	}
	dash.set_props("notifications", {"sendNotifications": [toast]})


def download_menu(
	pid: str, name: str, trigger: html.Button, tables: Sequence[str] = ()
) -> dmc.Menu:
	"""The download menu for one recording, opened by ``trigger``.

	Args:
		pid: id of the project the recording belongs to.
		name: recording name.
		trigger: the button that opens the menu; the two pages style it differently.
		tables: analysis tables to offer one by one, below the whole-recording files.
	"""
	base = f"/download/recording/{pid}/{quote(name, safe='')}"
	files = [
		("file-zip", "All analysis tables · parquet", f"{base}/tables.zip"),
		("file-zip", "All analysis tables · CSV", f"{base}/tables.zip?format=csv"),
		("paw", "Cohort · CSV", f"{base}/cohort.csv"),
		("file-description", "Recording config · JSON", f"{base}/config.json"),
		("database", "Raw registrations · parquet", f"{base}/raw.parquet"),
	]
	return dmc.Menu(
		[
			dmc.MenuTarget(trigger),
			dmc.MenuDropdown(
				[
					dmc.MenuLabel(name),
					*(
						dmc.MenuItem(
							label, leftSection=icon(icon_name, size=16), href=href, target="_blank"
						)
						for icon_name, label, href in files
					),
					*([dmc.MenuDivider(), dmc.MenuLabel("One table · parquet")] if tables else []),
					*(
						dmc.MenuItem(
							html.Code(table),
							leftSection=icon("table", size=16),
							href=f"{base}/table/{table}.parquet",
							target="_blank",
						)
						for table in tables
					),
				]
			),
		],
		position="bottom-end",
		classNames={"dropdown": "deh-menu deh-menu-scroll"},
	)


def format_dialog(prefix: str, note: str, props: dict[str, dict] | None = None) -> dmc.Modal:
	"""The Format dialog, shared by the recording cards and the builder.

	Args:
		prefix: ids are ``{prefix}-format-modal``, ``{prefix}-fmt`` (one per field key)
			and ``{prefix}-fmt-reset``.
		note: the line under the fields.
		props: each field's props by key; a ``"title"`` entry adds a plot title field.

	Returns:
		The dialog, kept mounted so props set while it is closed survive opening it.
	"""
	props = props or {}

	def field(component, key: str, label: str, **kwargs):
		return component(
			id={"type": f"{prefix}-fmt", "key": key},
			label=label,
			className="deh-field",
			classNames={"input": "deh-input"},
			**{**kwargs, **props.get(key, {})},
		)

	def text(key: str, label: str) -> dmc.TextInput:
		return field(dmc.TextInput, key, label, debounce=True, autoComplete="off")

	def bound(key: str, label: str) -> dmc.NumberInput:
		return field(dmc.NumberInput, key, label, debounce=True, hideControls=True)

	def select(key: str, label: str, choices: dict) -> dmc.Select:
		return field(dmc.Select, key, label, data=list(choices), clearable=True)

	return dmc.Modal(
		id=f"{prefix}-format-modal",
		title="Format",
		size=360,
		keepMounted=True,
		classNames=DIALOG_CLASSES,
		children=[
			html.Div(
				[
					*([text("title", "Title")] if "title" in props else []),
					text("xaxis", "X axis title"),
					# ponytail: numbers only, so a date axis would take epoch ms; parse date
					# strings here if anyone wants to bound a timeline.
					html.Div(
						[bound("xmin", "X min"), bound("xmax", "X max")],
						className="deh-format-pair",
					),
					text("yaxis", "Y axis title"),
					html.Div(
						[bound("ymin", "Y min"), bound("ymax", "Y max")],
						className="deh-format-pair",
					),
					text("colorbar", "Colour bar title"),
					html.Div(
						[bound("cmin", "Colour min"), bound("cmax", "Colour max")],
						className="deh-format-pair",
					),
					select("colorscale", "Colour scale", COLORSCALES),
					select("palette", "Category palette", PALETTES),
					html.P(note, className="deh-sub"),
				],
				className="deh-dialog-body",
			),
			html.Div(
				html.Button(
					[icon("refresh", size=14), "Reset formatting"],
					id=f"{prefix}-fmt-reset",
					className="deh-btn deh-btn-ghost",
				),
				className="deh-dialog-foot",
			),
		],
	)


def _seg(id_: str, data: list[dict], value: str) -> dmc.SegmentedControl:
	return dmc.SegmentedControl(id=id_, data=data, value=value, size="xs")


def _field_row(label: str, *controls: Any, **kwargs: Any) -> html.Div:
	"""One labelled row of the export form."""
	return html.Div([html.Span(label), *controls], className="deh-field", **kwargs)


def export_dialog() -> dmc.Modal:
	"""The Export plot dialog, shared by the recording dashboard and the builder.

	A plain HTML form posts straight to ``/export`` on submit, so the browser
	downloads the rendered file the ordinary way - no ``dcc.Download``, which would
	base64-encode it into the callback response. Every visible control mirrors its
	value into a hidden field; ``deepecohab.app.downloads.export_plot`` reads those,
	not the Mantine widgets, which is what keeps the download working regardless of
	how a given dmc version wires its own inputs' ``name`` attributes.
	"""
	return dmc.Modal(
		id="export-dialog",
		title="Export plot",
		size=760,
		classNames=DIALOG_CLASSES,
		children=html.Div(
			[
				html.Div(
					[
						# The preview is the real export figure at its real pixel size - the
						# warnings beside it are measured there - so it is scaled to fit this
						# stage rather than re-fitted smaller. deh.fitPreview sets the
						# transform from the figure's own size; the stage clips the rest.
						html.Div(
							dcc.Graph(
								id="export-preview",
								figure=EMPTY_FIGURE,
								config={"staticPlot": True, "displayModeBar": False},
							),
							id="export-stage",
							className="deh-export-stage",
						),
						html.Div(id="export-dims", className="deh-sub"),
						html.Div(id="export-warnings"),
					],
					className="deh-export-preview",
				),
				html.Form(
					[
						_field_row(
							"Style",
							_seg(
								"export-style",
								[
									{"value": "publication", "label": "Publication"},
									{"value": "app", "label": "App theme"},
								],
								"publication",
							),
						),
						_field_row(
							"Format",
							_seg(
								"export-format",
								[
									{"value": "svg", "label": "SVG"},
									{"value": "pdf", "label": "PDF"},
									{"value": "png", "label": "PNG"},
								],
								"svg",
							),
						),
						_field_row(
							"Size",
							_seg(
								"export-width-preset",
								[
									{"value": "85", "label": "85 mm"},
									{"value": "114", "label": "114 mm"},
									{"value": "174", "label": "174 mm"},
									{"value": "custom", "label": "Custom"},
								],
								"85",
							),
							html.Div(
								[
									dmc.NumberInput(
										id="export-width", value=85, min=30, max=300, w=90
									),
									html.Span("x"),
									dmc.NumberInput(
										id="export-height", value=64, min=20, max=300, w=90
									),
									html.Span("mm"),
								],
								className="deh-mm-row",
							),
						),
						_field_row(
							"Font size",
							dmc.Select(
								id="export-pt",
								data=[{"value": p, "label": f"{p} pt"} for p in EXPORT_FONT_SIZES],
								value="8",
								allowDeselect=False,
								w=100,
							),
						),
						_field_row(
							"Resolution",
							_seg(
								"export-dpi",
								[
									{"value": "300", "label": "300 dpi"},
									{"value": "600", "label": "600 dpi"},
								],
								"300",
							),
							id="export-dpi-field",
							style={"display": "none"},
						),
						_field_row(
							"Include",
							dmc.Stack(
								[
									dmc.Checkbox(
										id="export-legend", label="Legend", checked=True, size="xs"
									),
									dmc.Checkbox(
										id="export-title-toggle",
										label="Title",
										checked=False,
										size="xs",
									),
									dmc.Checkbox(
										id="export-events",
										label="Event labels",
										checked=True,
										size="xs",
									),
									dmc.Checkbox(
										id="export-csv",
										label="Plotted data as CSV, in one zip",
										checked=True,
										size="xs",
									),
								],
								gap=6,
							),
						),
						dmc.TextInput(
							id="export-filename",
							label="File name",
							classNames={"input": "deh-mono"},
						),
						dcc.Input(type="hidden", name="figure", id="export-field-figure"),
						dcc.Input(type="hidden", name="params", id="export-field-params"),
						html.Div(
							[
								html.Button(
									"Cancel",
									type="button",
									id="export-cancel",
									className="deh-btn deh-btn-ghost",
								),
								html.Button(
									[icon("download", size=15), "Download"],
									type="submit",
									id="export-submit",
									className="deh-btn deh-btn-primary",
								),
							],
							className="deh-dialog-foot",
						),
					],
					id="export-form",
					method="POST",
					action="/export",
					target="_blank",
					className="deh-export-form",
				),
			],
			className="deh-export-body",
		),
	)


def export_preview(fig: dict[str, Any], title: str, form: dict[str, Any]) -> dict[str, Any]:
	"""Fit ``fig`` for the export dialog's current settings and describe the result.

	Both the live preview and the actual download go through
	:func:`deepecohab.plotting.export.fit_for_export`/``export_figure``, so this is the
	one place that decides how the dialog's controls turn into that function's
	arguments - the Flask route re-derives the same figure from the same JSON payload
	this returns, rather than trusting whatever kaleido would render from the preview.

	Args:
		fig: the plot's live figure, as captured from its ``dcc.Graph``.
		title: the card's title, drawn only when the Title checkbox is on.
		form: the dialog's current control values - style, format, width_mm, height_mm,
			pt, dpi, legend, title_on, events, csv and filename.

	Returns:
		The fitted preview figure, warning alerts, a dimensions caption, whether this
		figure has events or tabular data to offer, and the JSON payload the download
		form posts.
	"""
	working = go.Figure(fig)
	if form["style"] == "publication":
		working.update_layout(template="publication")

	shapes = working.layout.shapes or ()
	has_events = any(s.label and s.label.text for s in shapes)
	show_events = has_events and form["events"]

	fitted, notes = plot_export.fit_for_export(
		working,
		form["width_mm"],
		form["height_mm"],
		form["pt"],
		title if form["title_on"] else "",
		form["legend"],
		show_events,
	)

	csv_text = plot_export.figure_data_csv(fig)
	dims = f"{form['width_mm']:g} x {form['height_mm']:g} mm · {form['pt']:g} pt"
	if form["format"] == "png":
		px = round(form["width_mm"] / 25.4 * form["dpi"])
		py = round(form["height_mm"] / 25.4 * form["dpi"])
		dims += f" · {form['dpi']:g} dpi = {px} x {py} px"

	payload_params = {**form, "title": title, "csv": form["csv"] and csv_text is not None}
	return {
		"figure": fitted,
		"warnings": [
			html.Div([icon("alert-triangle", size=15), note], className="deh-alert deh-alert-warn")
			for note in notes
		],
		"dims": dims,
		"has_events": has_events,
		"has_csv": csv_text is not None,
		"payload_figure": json.dumps(fig),
		"payload_params": json.dumps(payload_params),
	}


#: Cage box size and the spacing between neighbouring cages, in SVG user units.
_HAB_W, _HAB_H, _HAB_GAP = 92, 66, 180


def _habitat_positions(layout: Layout) -> dict[str, tuple[float, float]]:
	"""Cage centres, derived from the layout graph rather than read from the config.

	Cages and tunnels form a graph. Its longest cycle goes on a circle - four cages give
	the square everyone sketches on the whiteboard, eight give an octagon - and a cage
	that is not on that cycle is pushed one gap further out along its neighbour's spoke.
	Nothing about four cages is written in, so any topology the backend accepts draws.

	Returns:
		Centre ``(x, y)`` per ``cell_id``, in the same units as ``_HAB_W``.
	"""
	# Imported here rather than at module scope: networkx costs ~150ms to import, and the
	# habitat map is the only thing in the app that needs it.
	import networkx as nx

	declared = [cage.cell_id for cage in layout.cages]
	if not declared:
		return {}

	graph = nx.Graph()
	graph.add_nodes_from(declared)
	graph.add_edges_from((tunnel.start_cell_id, tunnel.end_cell_id) for tunnel in layout.tunnels)

	cycles = nx.cycle_basis(graph)
	ring: list[str] = max(cycles, key=lambda cycle: len(cycle)) if cycles else declared
	# Lead with the first cage the config declares and run clockwise from there, so the
	# same habitat always draws the same way round.
	lead = ring.index(min(ring, key=declared.index))
	ring = ring[lead:] + ring[:lead]
	if len(ring) > 2 and declared.index(ring[1]) > declared.index(ring[-1]):
		ring = [ring[0], *reversed(ring[1:])]

	# x, y, and the angle and radius a cage hanging off this one would be pushed out along.
	placed: dict[str, tuple[float, float, float, float]] = {}
	count = len(ring)
	radius = max(120.0, _HAB_GAP / (2 * math.sin(math.pi / count))) if count > 1 else 0.0
	for index, cell in enumerate(ring):
		angle = math.radians(90 + 180 / count - (360 / count) * index)
		placed[cell] = (radius * math.cos(angle), -radius * math.sin(angle), angle, radius)

	queue = deque(ring)
	while queue:
		cell = queue.popleft()
		_, _, spoke, reach = placed[cell]
		# Settled before any of them is placed, so siblings fan out around the spoke
		# rather than each one shifting the next.
		kids = [neighbour for neighbour in graph[cell] if neighbour not in placed]
		for index, kid in enumerate(kids):
			angle = spoke + math.radians((index - (len(kids) - 1) / 2) * 22)
			out = reach + _HAB_GAP
			placed[kid] = (out * math.cos(angle), -out * math.sin(angle), angle, out)
			queue.append(kid)

	return {cell: (x, y) for cell, (x, y, _, _) in placed.items()}


def _habitat_mouth(x: float, y: float, dx: float, dy: float) -> tuple[float, float]:
	"""Where a tunnel leaving the cage at ``(x, y)`` towards ``(dx, dy)`` meets its wall."""
	length = math.hypot(dx, dy) or 1.0
	reach = 13 + min(
		_HAB_W / 2 / (abs(dx / length) or 1e-6),
		_HAB_H / 2 / (abs(dy / length) or 1e-6),
	)
	return x + dx / length * reach, y + dy / length * reach


def _habitat_band(miss: float | None) -> str:
	"""The quality class for one antenna, on the bands the header badge already uses."""
	if miss is None or miss < 1:
		return ""
	return "warn" if miss < 2.5 else "bad"


def _habitat_svg(layout: Layout, label: str, antenna_miss: dict[str, float] | None) -> str:
	"""The habitat as one SVG element, for ``deh.paintHabitat`` to paint in.

	Every interpolated piece comes from a hand-editable ``config.json`` and this string is
	set as ``innerHTML``, so all of it is escaped.
	"""
	at = _habitat_positions(layout)
	cages = {cage.cell_id: cage for cage in layout.cages}

	tubes, labels, antennas = [], [], []
	for tunnel in layout.tunnels:
		ax, ay = at[tunnel.start_cell_id]
		bx, by = at[tunnel.end_cell_id]
		line = f"M{ax:.2f} {ay:.2f} L{bx:.2f} {by:.2f}"
		tubes.append(
			f'<path class="deh-hab-tube" d="{line}"/><path class="deh-hab-tube-in" d="{line}"/>'
		)
		labels.append(
			f'<text class="deh-hab-tunnel" x="{(ax + bx) / 2:.2f}" '
			f'y="{(ay + by) / 2 + 3.5:.2f}">T{tunnel.tunnel_no}</text>'
		)
		# zip stops at the shorter side, which is what leaves a dead-end tunnel with the
		# one antenna it has.
		ends = (
			(_habitat_mouth(ax, ay, bx - ax, by - ay), tunnel.start_cell_id),
			(_habitat_mouth(bx, by, ax - bx, ay - by), tunnel.end_cell_id),
		)
		for ((px, py), cell), antenna in zip(ends, tunnel.antennas, strict=False):
			miss = (antenna_miss or {}).get(str(antenna))
			band = _habitat_band(miss)
			title = f"Antenna {antenna} · {cages[cell].name} end of {tunnel.name}"
			if miss is not None:
				title += f" · {miss:.2f}% missed passes"
			antennas.append(
				f'<g class="deh-hab-ant{f" {band}" if band else ""}">'
				f"<title>{escape(title)}</title>"
				f'<circle cx="{px:.2f}" cy="{py:.2f}" r="11"/>'
				f'<text x="{px:.2f}" y="{py:.2f}">{escape(str(antenna))}</text></g>'
			)

	# Drawn last, so a cage box covers any antenna that falls inside it.
	boxes = []
	for cage in layout.cages:
		x, y = at[cage.cell_id]
		title = f"{cage.name} · {cage.cage_type} · antennas {', '.join(cage.antennas)}"
		boxes.append(
			f'<g class="deh-hab-cage {escape(cage.cage_type)}"><title>{escape(title)}</title>'
			f'<rect x="{x - _HAB_W / 2:.2f}" y="{y - _HAB_H / 2:.2f}" '
			f'width="{_HAB_W}" height="{_HAB_H}" rx="13"/>'
			f'<text class="deh-hab-name" x="{x:.2f}" y="{y - 2:.2f}">'
			f"{escape(cage.name.replace('cage_', 'Cage '))}</text>"
			f'<text class="deh-hab-type" x="{x:.2f}" y="{y + 15:.2f}">'
			f"{escape(cage.cage_type)}</text></g>"
		)

	xs = [x for x, _ in at.values()]
	ys = [y for _, y in at.values()]
	x0, y0 = min(xs) - _HAB_W / 2 - 40, min(ys) - _HAB_H / 2 - 40
	return (
		f'<svg viewBox="{x0:.2f} {y0:.2f} {max(xs) + _HAB_W / 2 + 40 - x0:.2f} '
		f'{max(ys) + _HAB_H / 2 + 40 - y0:.2f}" role="img" aria-label="{escape(label)}" '
		f'preserveAspectRatio="xMidYMid meet">'
		f"{''.join(tubes)}{''.join(antennas)}{''.join(labels)}{''.join(boxes)}</svg>"
	)


#: Legend keys, as (extra class, label); the empty class is the plain standard cage.
_HAB_KEYS = (
	("social", "social"),
	("", "standard"),
	("nonsocial", "nonsocial"),
	("tunnel", "tunnel"),
	("ant", "antenna"),
)

#: Shown only when there are miss rates to band by; same cuts as the header's quality badge.
_HAB_BAND_KEYS = (("ant warn", "1-2.5% missed"), ("ant bad", "2.5% and over"))


def habitat_map(
	layout: Layout,
	label: str,
	*,
	antenna_miss: dict[str, float] | None = None,
	height: int | None = None,
) -> list:
	"""The habitat a recording was made in, as an SVG map and its legend.

	Drawn from ``layout`` alone, so it renders for a recording whose pipeline has never
	run. The SVG rides on a ``data-hab`` attribute for ``deh.paintHabitat`` to paint in,
	because Dash carries no SVG components; being a real SVG rather than a figure is what
	lets it inherit the theme tokens and hover for free.

	Args:
		layout: the validated habitat, as ``config.json`` lays it out.
		label: the SVG's accessible name, e.g. ``"Habitat of 2024-05-02"``.
		antenna_miss: missed-pass percentage per antenna, which tints each one on the same
			bands as the header's quality badge and adds its rate to the tooltip. Without it
			every antenna draws plain, which is what a recording with no results shows.
		height: map height in px; the CSS falls back to 300px.
	"""
	return [
		html.Div(
			className="deh-hab",
			style={"height": f"{height}px"} if height else {},
			**{"data-hab": _habitat_svg(layout, label, antenna_miss)},  # ty: ignore[invalid-argument-type]
		),
		html.Div(
			[
				html.Span([html.I(className=f"deh-hab-key {modifier}".strip()), name])
				for modifier, name in _HAB_KEYS + (_HAB_BAND_KEYS if antenna_miss else ())
			],
			className="deh-hab-legend",
		),
	]
