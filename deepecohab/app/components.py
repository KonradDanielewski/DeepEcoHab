"""Small building blocks shared across app pages."""

import json
from typing import Any

import dash
import dash_mantine_components as dmc
import plotly.graph_objects as go
from dash import dcc, html

from deepecohab.plotting import export as plot_export

_DIALOG_CLASSES = {
	"content": "deh-dialog",
	"header": "deh-dialog-head",
	"title": "deh-dialog-title",
	"body": "deh-dialog-content",
}

EXPORT_FONT_SIZES = ["6", "7", "8", "9", "10", "12"]


def icon(name: str, size: int = 18, class_name: str = "", **style) -> html.Span:
	"""A Tabler outline icon from ``assets/icons``, tinted by ``currentColor``.

	Args:
		name: file stem under ``assets/icons/`` (no extension).
		size: square size in px.
		class_name: extra CSS classes, e.g. to swap icons by theme.
		style: extra CSS merged over the size and mask, e.g. ``color=``.

	Returns:
		A ``span`` masked to the icon shape and filled with the current text colour.
	"""
	mask = f"url({dash.get_asset_url(f'icons/{name}.svg')}) center / contain no-repeat"
	return html.Span(
		className=f"deh-ic {class_name}".strip(),
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


def _seg(id_: str, data: list[dict], value: str) -> dmc.SegmentedControl:
	return dmc.SegmentedControl(id=id_, data=data, value=value, size="xs")


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
		classNames=_DIALOG_CLASSES,
		children=html.Div(
			[
				html.Div(
					[
						dcc.Graph(
							id="export-preview",
							figure={},
							config={"staticPlot": True, "displayModeBar": False},
							style={"height": "320px"},
						),
						html.Div(id="export-dims", className="deh-sub"),
						html.Div(id="export-warnings"),
					],
					className="deh-export-preview",
				),
				html.Form(
					[
						html.Div(
							[
								html.Span("Style"),
								_seg(
									"export-style",
									[
										{"value": "publication", "label": "Publication"},
										{"value": "app", "label": "App theme"},
									],
									"publication",
								),
							],
							className="deh-field",
						),
						html.Div(
							[
								html.Span("Format"),
								_seg(
									"export-format",
									[
										{"value": "svg", "label": "SVG"},
										{"value": "pdf", "label": "PDF"},
										{"value": "png", "label": "PNG"},
									],
									"svg",
								),
							],
							className="deh-field",
						),
						html.Div(
							[
								html.Span("Size"),
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
											id="export-width",
											value=85,
											min=30,
											max=300,
											w=90,
										),
										html.Span("x"),
										dmc.NumberInput(
											id="export-height",
											value=64,
											min=20,
											max=300,
											w=90,
										),
										html.Span("mm"),
									],
									className="deh-mm-row",
								),
							],
							className="deh-field",
						),
						html.Div(
							[
								html.Span("Font size"),
								dmc.Select(
									id="export-pt",
									data=[
										{"value": p, "label": f"{p} pt"} for p in EXPORT_FONT_SIZES
									],
									value="8",
									allowDeselect=False,
									w=100,
								),
							],
							className="deh-field",
						),
						html.Div(
							[
								html.Span("Resolution"),
								_seg(
									"export-dpi",
									[
										{"value": "300", "label": "300 dpi"},
										{"value": "600", "label": "600 dpi"},
									],
									"300",
								),
							],
							id="export-dpi-field",
							className="deh-field",
							style={"display": "none"},
						),
						html.Div(
							[
								html.Span("Include"),
								dmc.Stack(
									[
										dmc.Checkbox(
											id="export-legend",
											label="Legend",
											checked=True,
											size="xs",
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
							],
							className="deh-field",
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

	annotations = working.layout.annotations or ()
	shapes = working.layout.shapes or ()
	has_events = any(str(a.name or "").startswith("event-label") for a in annotations) or any(
		s.label and s.label.text for s in shapes
	)
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
