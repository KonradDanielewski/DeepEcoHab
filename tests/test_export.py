"""Tests for plotting.export.fit_for_export - the layout pass, not kaleido rendering.

Rendering through kaleido was checked by hand at 85x64 and 174x140 mm while designing
these rules (see the blueprint); what is pinned here is the geometry the Python port
computes, since that is what a regression could silently get wrong. One test does render,
to pin that the rounded corners the app draws in the browser reach the exported file.
"""

import xml.etree.ElementTree as ET

import numpy as np
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from deepecohab.plotting import export


def test_size_and_font_scale_from_mm_and_pt():
	fig = go.Figure(go.Scatter(x=[1], y=[1]))

	fitted, notes = export.fit_for_export(fig, width_mm=85, height_mm=64, pt=8)

	assert fitted.layout.width == round(85 * export.PX_PER_MM)
	assert fitted.layout.height == round(64 * export.PX_PER_MM)
	assert fitted.layout.font.size == pytest.approx(8 * 96 / 72)
	assert notes == []


def test_title_is_drawn_only_when_given():
	fig = go.Figure(go.Scatter(x=[1], y=[1]))

	shown, _ = export.fit_for_export(fig, 85, 64, 8, title="Activity")
	hidden, _ = export.fit_for_export(fig, 85, 64, 8, title="")

	assert shown.layout.title.text == "Activity"
	assert hidden.layout.title.text == ""


def test_legend_always_moves_to_the_side():
	fig = go.Figure(
		[go.Scatter(x=[1], y=[1], name="a"), go.Scatter(x=[1], y=[1], name="b")],
		layout={"showlegend": True},
	)

	fitted, _ = export.fit_for_export(fig, 85, 64, 8)

	assert fitted.layout.legend.orientation == "v"
	assert fitted.layout.legend.x > 1  # past the plot, not underneath it


def test_show_legend_false_drops_it_entirely():
	fig = go.Figure(go.Scatter(x=[1], y=[1], name="a"), layout={"showlegend": True})

	fitted, _ = export.fit_for_export(fig, 85, 64, 8, show_legend=False)

	assert fitted.layout.showlegend is False
	assert fitted.layout.legend.x is None


def test_wide_legend_warns():
	fig = go.Figure(
		[go.Scatter(x=[1], y=[1], name="a very long series name indeed")],
		layout={"showlegend": True},
	)

	_, notes = export.fit_for_export(fig, width_mm=40, height_mm=64, pt=12)

	assert any("legend takes" in note for note in notes)


def test_event_label_is_wrapped_when_shown_and_dropped_otherwise():
	long_text = "Auditory Tone Test " * 4
	fig = go.Figure(
		layout={"shapes": [{"name": "event-label", "type": "rect", "label": {"text": long_text}}]}
	)

	shown, _ = export.fit_for_export(fig, 174, 140, 8, show_events=True)
	hidden, _ = export.fit_for_export(fig, 174, 140, 8, show_events=False)

	assert "<br>" in shown.layout.shapes[0].label.text
	assert hidden.layout.shapes[0].label.text == ""


def test_shape_and_scatter_lines_are_capped_at_1_5px():
	fig = go.Figure(
		go.Scatter(x=[1], y=[1], line={"width": 4}),
		layout={"shapes": [{"type": "rect", "line": {"width": 4}}]},
	)

	fitted, _ = export.fit_for_export(fig, 85, 64, 8)

	assert fitted.data[0].line.width == 1.5
	assert fitted.layout.shapes[0].line.width == 1.5


def test_axes_only_a_trace_names_are_fitted_too():
	fig = go.Figure(go.Box(y=[1, 2, 3]))

	fitted, _ = export.fit_for_export(fig, 85, 64, 8)

	assert fitted.layout.xaxis.automargin is True
	assert fitted.layout.yaxis.automargin is True


def test_shapes_above_the_plot_get_room_in_the_top_margin():
	fig = go.Figure(go.Scatter(x=[1], y=[1]))
	bare, _ = export.fit_for_export(fig, 85, 64, 8)
	fig.add_shape(type="rect", xref="x", yref="paper", x0=0, x1=1, y0=1.01, y1=1.035)

	banded, _ = export.fit_for_export(fig, 85, 64, 8)

	assert banded.layout.margin.t > bare.layout.margin.t


def test_forced_dtick_reverts_to_automatic_ticking():
	"""_phase_markers forces dtick=1 on the hour axis; export widens it back out."""
	fig = go.Figure(go.Scatter(x=[1], y=[1]), layout={"xaxis": {"dtick": 1}})

	fitted, _ = export.fit_for_export(fig, 85, 64, 8)

	assert fitted.layout.xaxis.dtick is None
	assert fitted.layout.xaxis.tickmode == "auto"


def test_stacked_panels_get_non_overlapping_domains_top_to_bottom():
	fig = go.Figure(
		layout={
			"yaxis": {"domain": [0.55, 1.0]},
			"yaxis2": {"domain": [0.0, 0.45]},
		}
	)

	fitted, _ = export.fit_for_export(fig, 174, 140, 8)

	top = fitted.layout.yaxis.domain
	bottom = fitted.layout.yaxis2.domain
	assert top[0] > bottom[1]  # still stacked, top above bottom, with a gap
	assert top[1] <= 1.0
	assert bottom[0] >= 0.0


def test_too_many_short_panels_warns():
	layout = {f"yaxis{i or ''}": {"domain": [1 - (i + 1) * 0.05, 1 - i * 0.05]} for i in range(10)}

	_, notes = export.fit_for_export(go.Figure(layout=layout), 85, 30, 8)

	assert any("panels get" in note for note in notes)


def test_figure_data_csv_extracts_xy_traces():
	fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4], name="A")).to_dict()

	lines = export.figure_data_csv(fig)[0].splitlines()

	assert lines[0] == "trace,x,y"
	assert "A,1,3" in lines
	assert "A,2,4" in lines


def test_figure_data_csv_flattens_heatmap_z():
	fig = go.Figure(go.Heatmap(x=["c1", "c2"], y=["r1"], z=[[1, 2]])).to_dict()

	lines = export.figure_data_csv(fig)[0].splitlines()

	assert lines[0] == "trace,x,y,z"
	assert "heatmap,c2,r1,2" in lines


def test_figure_data_csv_writes_one_table_per_subplot():
	"""A line beside horizontal bars: one table each, though the bars' y holds names.

	Past polars' 100-row inference window, one shared table used to fail on the names.
	"""
	fig = go.Figure(go.Scatter(x=list(range(150)), y=[0.5] * 150, name="A"))
	fig.add_trace(go.Bar(x=[75], y=["A"], orientation="h", name="A", xaxis="x2", yaxis="y2"))

	lines, bars = (table.splitlines() for table in export.figure_data_csv(fig.to_dict()))

	assert len(lines) == 151 and lines[1] == "A,0,0.5"
	assert bars == ["trace,x,y", "A,75,A"]


def test_figure_data_csv_returns_none_for_untabular_traces():
	fig = go.Figure(go.Pie(labels=["a"], values=[1])).to_dict()

	assert export.figure_data_csv(fig) == []


def test_figure_data_csv_decodes_plotlys_typed_array_encoding():
	"""plotly.py serialises a numpy-backed trace's numbers as {dtype, bdata}, not a list."""
	fig = go.Figure(
		go.Scatter(x=np.array([1, 2], dtype="i8"), y=np.array([3, 4], dtype="i8"))
	).to_dict()
	assert isinstance(fig["data"][0]["x"], dict)  # confirms the encoding actually kicked in

	lines = export.figure_data_csv(fig)[0].splitlines()

	assert "1" in lines[1].split(",") and "3" in lines[1].split(",")
	assert "2" in lines[2].split(",") and "4" in lines[2].split(",")


def test_figure_data_csv_decodes_typed_array_heatmap_z_with_shape():
	fig = go.Figure(
		go.Heatmap(x=["c1", "c2"], y=["r1"], z=np.array([[1, 2]], dtype="f8"))
	).to_dict()
	assert isinstance(fig["data"][0]["z"], dict)

	lines = export.figure_data_csv(fig)[0].splitlines()

	assert "heatmap,c2,r1,2.0" in lines


def test_export_keeps_rounded_boxes_and_tiles(tmp_path):
	if not export.ensure_chrome_available():
		pytest.skip("kaleido has no Chrome to render through")
	fig = make_subplots(rows=1, cols=2)
	fig.add_trace(go.Box(y=[1, 2, 3, 4, 5]), row=1, col=1)
	fig.add_trace(go.Heatmap(z=[[1, 2], [3, 4]], xgap=1, ygap=2), row=1, col=2)
	path = tmp_path / "rounded.svg"

	export.export_figure(fig, path, 85, 64, 8, "svg")

	svg = ET.parse(path).getroot()
	ns = "{http://www.w3.org/2000/svg}"
	box = next(node for node in svg.iter(f"{ns}path") if node.get("class") == "box")
	assert "Q" in box.get("d")
	assert next(svg.iter(f"{ns}image")).get("clip-path", "").startswith("url(#deh-tiles-")
