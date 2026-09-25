"""Tests for the plot builder's field catalog and figure aggregation.

A small synthetic project table stands in for a real one, shaped like
``Project.load_project_table()``'s long format: one row per animal, hour and metric.
"""

import polars as pl
import pytest

from deepecohab.app.builder import catalog, figure
from deepecohab.plotting import theme


@pytest.fixture
def frame() -> pl.LazyFrame:
	return pl.DataFrame(
		{
			"value": [1.0, 3.0, 2.0, 2.0],
			"exposure": [1.0, 1.0, 1.0, 1.0],
			"metric": ["activity", "activity", "time_alone", "time_alone"],
			"day": [1, 1, 1, 1],
			"hour": [0, 1, 0, 1],
			"phase_count": [1, 1, 1, 1],
			"phase": ["light_phase", "light_phase", "light_phase", "light_phase"],
			"recording": ["rec1", "rec1", "rec1", "rec1"],
			"animal_id": ["A", "B", "A", "B"],
			"genotype": ["WT", "HET", "WT", "HET"],
			"sex": ["F", "M", "F", "M"],
			"n_mice": [2, 2, 2, 2],
		}
	).lazy()


@pytest.fixture
def fields(frame) -> list[catalog.Field]:
	return catalog.prepare(frame)[1]


def test_prepare_classifies_fields(fields):
	by_name = {field.name: field for field in fields}

	assert by_name["value"].kind == "measure"
	assert by_name["value"].agg == "metric"
	assert by_name["metric"].kind == "dimension"
	assert by_name["metric"].group == "Measure"
	assert by_name["hour"].kind == "time"
	assert by_name["genotype"].kind == "dimension"
	assert by_name["genotype"].group == "Animal"
	assert by_name["recording"].group == "Recording"


def test_build_frame_computes_rate(frame, fields):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"]},
		"filters": {"metric": ["activity"]},
	}
	data = figure.build_frame(frame, state, fields)

	assert data.sort("hour")["value"].to_list() == pytest.approx([1.0, 3.0])


def test_warnings_for_blocks_unfaceted_multi_metric(frame, fields):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"]},
		"filters": {},
	}
	notes = figure.warnings_for(frame, state, fields)

	assert any(note.blocking for note in notes)


def test_warnings_for_allows_faceted_multi_metric(frame, fields):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"], "facet_row": ["metric"]},
		"filters": {},
	}
	notes = figure.warnings_for(frame, state, fields)

	assert not any(note.blocking for note in notes)


def test_build_figure_colours_by_sample_palette(frame, fields):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"], "color": ["genotype"]},
		"filters": {"metric": ["activity"]},
	}
	fig, notes = figure.build_figure(frame, state, fields)

	assert notes == []
	colors = {trace.line.color for trace in fig.data}
	assert colors == set(figure.theme.sample_palette(2))


def test_format_override_lapses_once_its_axis_shows_something_else(frame, fields):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"], "facet_col": ["genotype"]},
		"filters": {"metric": ["activity"]},
	}
	fig, _notes = figure.build_figure(frame, state, fields)
	auto = figure.auto_titles(fig)
	fmt = {
		"xaxis": {"on": auto["xaxis"], "value": "Hour of day"},
		"yaxis": {"on": "Some other field", "value": "Stale"},
	}
	figure.apply_format(fig, fmt)

	assert {axis.title.text for axis in fig.select_xaxes() if axis.title.text} == {"Hour of day"}
	assert fig.layout.yaxis.title.text == auto["yaxis"]


def test_colour_range_takes_one_bound_and_skips_an_inverted_pair(frame, fields):
	state = {
		"kind": "density_heatmap",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["animal_id"], "z": ["value"]},
		"filters": {"metric": ["activity"]},
	}
	fig, _notes = figure.build_figure(frame, state, fields)
	on = figure.auto_titles(fig)["colorbar"]
	figure.apply_format(fig, {"cmin": {"on": on, "value": 1}})
	assert (fig.layout.coloraxis.cauto, fig.layout.coloraxis.cmin) == (False, 1)

	fig, _notes = figure.build_figure(frame, state, fields)
	figure.apply_format(fig, {"cmin": {"on": on, "value": 5}, "cmax": {"on": on, "value": 2}})
	assert fig.layout.coloraxis.cmin is None


def test_palette_recolours_categories_unless_too_short(frame, fields, monkeypatch):
	state = {
		"kind": "line",
		"measure_as": "rate",
		"channels": {"x": ["hour"], "y": ["value"], "color": ["genotype"]},
		"filters": {"metric": ["activity"]},
		"format": {"palette": {"on": "", "value": "Set1"}},
	}
	fig, _notes = figure.build_figure(frame, state, fields)
	assert {trace.line.color for trace in fig.data} == set(theme.PALETTES["Set1"][:2])
	assert figure.auto_titles(fig)["colorway"] == ""

	monkeypatch.setitem(theme.PALETTES, "One", ["rgb(0, 0, 0)"])
	state["format"] = {"palette": {"on": "", "value": "One"}}
	fig, _notes = figure.build_figure(frame, state, fields)
	assert list(fig.layout.colorway) == theme.sample_palette(2)


def test_reduce_dispatches_every_trigger(frame, fields, monkeypatch):
	"""``_reduce`` matches each trigger it handles, and prevents the update on anything else.

	The reducer is one ``match`` over the id Dash triggered with, so a mistyped pattern
	silently falls through to ``PreventUpdate`` rather than failing loudly.
	"""
	import dash
	from dash.exceptions import PreventUpdate

	dash.Dash(__name__, use_pages=True, pages_folder="")  # the page module registers itself

	from deepecohab.app import services
	from deepecohab.app.pages import builder as page

	monkeypatch.setattr(services, "builder_frame", lambda location: (frame, fields))

	def reduce(trigger, value=None, event=None, state=None):
		monkeypatch.setattr(dash._callback_context, "context_value", None, raising=False)
		monkeypatch.setattr(
			page,
			"ctx",
			type("Ctx", (), {"triggered_id": trigger, "triggered": [{"value": value}]}),
		)
		return page._reduce(
			event,
			None,
			None,
			None,
			None,
			None,
			None,
			state if state is not None else figure.new_state(),
			{"location": "somewhere"},
			None,
			[],
			{"title": ""},  # the automatic titles an override is pinned to
		)

	held = figure.new_state()
	held["channels"] = {"x": ["hour"], "y": ["value"]}
	held["filters"] = {"metric": {"mode": "pick", "values": ["activity"]}}

	assert reduce("builder-clear", state=dict(held, channels={"x": ["hour"]}))[0]["channels"] == {}
	assert reduce({"type": "builder-kind", "kind": "bar"})[0]["kind"] == "bar"
	assert reduce({"type": "builder-mode", "mode": "mean"})[0]["measure_as"] == "mean"
	assert (
		reduce({"type": "chip-x", "shelf": "x", "field": "hour"}, state=held)[0]["channels"]["x"]
		== []
	)
	assert (
		"metric"
		not in reduce({"type": "chip-x", "shelf": page.FILTERS, "field": "metric"}, state=held)[0][
			"filters"
		]
	)
	assert reduce({"type": "chip-send", "field": "hour", "from": page.PALETTE, "to": "x"})[0][
		"channels"
	]["x"] == ["hour"]
	assert reduce("dnd-event", event={"field": "hour", "shelf": "x"})[0]["channels"]["x"] == [
		"hour"
	]
	assert (
		reduce({"type": "filter-mode", "field": "hour", "mode": "range"}, state=held)[0]["filters"][
			"hour"
		]["mode"]
		== "range"
	)
	assert reduce({"type": "filter-pick", "field": "metric"}, value=["time_alone"], state=held)[0][
		"filters"
	]["metric"]["values"] == ["time_alone"]
	assert reduce({"type": "filter-range", "field": "hour"}, value=[0, 1], state=held)[0][
		"filters"
	]["hour"] == {"mode": "range", "lo": 0, "hi": 1}
	assert (
		reduce({"type": "chip-bin", "field": "hour"}, value=" 1-3, 4-6 ", state=held)[0]["bins"][
			"hour"
		]
		== "1-3, 4-6"
	)
	assert (
		reduce({"type": "builder-fmt", "key": "title"}, value="T")[0]["format"]["title"]["value"]
		== "T"
	)

	# A Blocks spec outlives the field it was typed on unless something clears it, and
	# would then come back to life under the field when it is dropped again.
	binned = dict(held, channels={"facet_col": ["day"]}, bins={"day": "1-3, 4-6"})
	assert reduce({"type": "builder-mode", "mode": "rate"}, state=binned)[0]["bins"] == {
		"day": "1-3, 4-6"
	}
	unshelved = dict(binned, channels={})
	assert "bins" not in reduce({"type": "builder-mode", "mode": "rate"}, state=unshelved)[0]

	formatted = reduce({"type": "builder-fmt", "key": "title"}, value="T")[0]
	assert "format" not in reduce("builder-fmt-reset", value=1, state=formatted)[0]

	for unknown in ("no-such-id", {"type": "no-such-type"}, {"type": "chip-x", "shelf": "x"}):
		with pytest.raises(PreventUpdate):
			reduce(unknown)


def _by_position(frame: pl.LazyFrame) -> pl.LazyFrame:
	"""The fixture with every hour spread unevenly over two positions of different types."""
	return pl.concat(
		[
			frame.with_columns(
				pl.col("value", "exposure") * share,
				pl.lit(position).alias("position"),
				pl.lit(kind).alias("position_type"),
			)
			for position, kind, share in (("cage_1", "home", 0.25), ("cage_2", "stimulus", 0.75))
		]
	)


@pytest.mark.parametrize("mode", list(figure.MEASURE_MODES))
def test_an_hour_spread_over_positions_reads_the_same_in_every_mode(frame, fields, mode):
	"""Summing the positions back is what every mode must do, the hourly mean included."""
	state = {
		"kind": "line",
		"measure_as": mode,
		"channels": {"x": ["genotype"], "y": ["value"]},
		"filters": {"metric": ["activity"]},
	}
	split = _by_position(frame)
	whole = figure.build_frame(frame, state, fields).sort("genotype")
	parts = figure.build_frame(split, state, catalog.prepare(split)[1]).sort("genotype")

	assert parts["value"].to_list() == pytest.approx(whole["value"].to_list())


@pytest.mark.parametrize("mode", list(figure.MEASURE_MODES))
def test_hover_lists_fields_without_changing_what_is_drawn(frame, mode):
	split = _by_position(frame)
	fields = catalog.prepare(split)[1]
	state = {
		"kind": "line",
		"measure_as": mode,
		"channels": {"x": ["genotype"], "y": ["value"]},
		"filters": {"metric": ["activity"]},
	}
	bare = figure.build_frame(split, state, fields).sort("genotype")
	state["channels"][figure.HOVER] = ["position", "animal_id", "hour", "n_mice"]
	hovered = figure.build_frame(split, state, fields).sort("genotype")

	assert hovered["value"].to_list() == pytest.approx(bare["value"].to_list())
	assert hovered.select("position", "animal_id", "hour").rows() == [
		("cage_1, cage_2", "B", "1"),
		("cage_1, cage_2", "A", "0"),
	]


def test_position_type_filter_keeps_only_those_positions(frame):
	split = _by_position(frame)
	fields = catalog.prepare(split)[1]
	state = {
		"kind": "line",
		"measure_as": "total",
		"channels": {"x": ["genotype"], "y": ["value"]},
		"filters": {"metric": ["activity"], "position_type": ["stimulus"]},
	}
	data = figure.build_frame(split, state, fields).sort("genotype")

	assert {field.name: field.group for field in fields}["position_type"] == "Position"
	assert dict(data.select("genotype", "value").iter_rows()) == {"HET": 2.25, "WT": 0.75}


def _daily(frame: pl.LazyFrame, days: int) -> pl.LazyFrame:
	"""The fixture repeated over ``days`` days, so a block has something to span."""
	return pl.concat(
		[frame.with_columns(pl.lit(day, dtype=pl.Int64).alias("day")) for day in range(1, days + 1)]
	)


def _binned(frame, fields, spec: str):
	state = {
		"kind": "line",
		"measure_as": "total",
		"channels": {"x": ["day"], "y": ["value"]},
		"filters": {"metric": ["activity"]},
		"bins": {"day": spec},
	}
	return figure.build_frame(frame, state, fields), state


@pytest.mark.parametrize(
	("spec", "expected"),
	[
		("3", ["day 1-3", "day 4-6"]),
		("5", ["day 1-5", "day 6-10"]),
		("1-3, 4-6", ["day 1-3", "day 4-6"]),
		# Uneven spans, more than two of them, in the order typed rather than sorted.
		("4-6, 1-2, 3-3", ["day 4-6", "day 1-2", "day 3-3"]),
	],
)
def test_build_frame_bins_ordered_field(frame, fields, spec, expected):
	data, _state = _binned(_daily(frame, 6), fields, spec)

	assert data["day"].to_list() == expected


def test_build_frame_drops_values_outside_every_span(frame, fields):
	data, _state = _binned(_daily(frame, 6), fields, "1-2, 5-6")

	assert data["day"].to_list() == ["day 1-2", "day 5-6"]
	# 4 rows/day over 2 days, activity only: (1.0 + 3.0) per day.
	assert data["value"].to_list() == pytest.approx([8.0, 8.0])


def test_unreadable_block_spec_warns_without_blocking(frame, fields):
	_data, state = _binned(_daily(frame, 6), fields, "every other")
	notes = figure.warnings_for(frame, state, fields)

	assert any("could not be read" in note.text and not note.blocking for note in notes)


@pytest.mark.parametrize(
	("spec", "expected"),
	[("3", 3), ("1", None), ("", None), ("2-4", [(2.0, 4.0)]), ("4-2", None), ("x-y", None)],
)
def test_parse_bins(spec, expected):
	assert figure.parse_bins(spec) == expected
