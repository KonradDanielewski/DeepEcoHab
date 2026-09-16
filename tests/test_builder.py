"""Tests for the plot builder's field catalog and figure aggregation.

A small synthetic project table stands in for a real one, shaped like
``Project.load_project_table()``'s long format: one row per animal, hour and metric.
"""

import polars as pl
import pytest

from deepecohab.app.builder import catalog, figure


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
