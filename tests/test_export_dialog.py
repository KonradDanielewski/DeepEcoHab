"""Tests for components.export_preview: the export dialog's live-preview logic.

Both the app's preview and the actual download go through this and, beneath it,
plotting.export.fit_for_export - so what's worth pinning here is how the dialog's
controls turn into that function's arguments, not the layout math itself (covered
in test_export.py).
"""

import json

import plotly.graph_objects as go

from deepecohab.app.components import export_preview

#: Shaped as the app's render callback builds it - already coerced to the numeric
#: types fit_for_export wants, unlike EXPORT_DEFAULTS's string-valued dmc props.
_BASE_FORM = {
	"style": "publication",
	"format": "svg",
	"width_mm": 85.0,
	"height_mm": 64.0,
	"pt": 8.0,
	"dpi": 300,
	"legend": True,
	"title_on": False,
	"events": True,
	"csv": True,
	"filename": "plot",
}


def _form(**overrides) -> dict:
	return {**_BASE_FORM, **overrides}


def test_publication_style_overrides_the_figures_own_template():
	fig = go.Figure(go.Scatter(x=[1], y=[1]), layout={"template": "dark"}).to_dict()

	result = export_preview(fig, "Title", _form(style="publication"))

	assert result["figure"].layout.template.layout.paper_bgcolor == "#ffffff"


def test_app_style_keeps_the_figures_own_template():
	fig = go.Figure(go.Scatter(x=[1], y=[1]), layout={"template": "dark"}).to_dict()

	result = export_preview(fig, "Title", _form(style="app"))

	assert result["figure"].layout.template.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_title_only_drawn_when_toggled_on():
	fig = go.Figure(go.Scatter(x=[1], y=[1])).to_dict()

	off = export_preview(fig, "My plot", _form(title_on=False))
	on = export_preview(fig, "My plot", _form(title_on=True))

	assert off["figure"].layout.title.text == ""
	assert on["figure"].layout.title.text == "My plot"


def test_has_events_is_false_without_event_label_annotations():
	fig = go.Figure(go.Scatter(x=[1], y=[1])).to_dict()

	assert export_preview(fig, "T", _form())["has_events"] is False


def test_has_events_is_true_with_an_event_label_annotation():
	fig = go.Figure(
		go.Scatter(x=[1], y=[1]),
		layout={"annotations": [{"name": "event-label-0", "text": "Tone", "x": 1, "y": 1}]},
	).to_dict()

	assert export_preview(fig, "T", _form())["has_events"] is True


def test_has_csv_reflects_whether_the_figure_has_tabular_data():
	xy = go.Figure(go.Scatter(x=[1], y=[1])).to_dict()
	pie = go.Figure(go.Pie(labels=["a"], values=[1])).to_dict()

	assert export_preview(xy, "T", _form())["has_csv"] is True
	assert export_preview(pie, "T", _form())["has_csv"] is False


def test_png_dims_caption_includes_pixel_size():
	fig = go.Figure(go.Scatter(x=[1], y=[1])).to_dict()

	dims = export_preview(fig, "T", _form(format="png", dpi=300))["dims"]

	assert "px" in dims


def test_payload_carries_the_original_unfitted_figure_and_resolved_params():
	fig = go.Figure(go.Scatter(x=[1], y=[1]), layout={"template": "dark"}).to_dict()

	result = export_preview(fig, "T", _form(csv=True))

	assert json.loads(result["payload_figure"]) == fig
	params = json.loads(result["payload_params"])
	assert params["title"] == "T"
	assert params["csv"] is True
