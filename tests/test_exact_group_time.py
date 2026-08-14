from datetime import datetime, timedelta

import polars as pl
import pytest

from deepecohab.plotting.plot_catalog import exact_group_time
from deepecohab.plotting.plot_factory import plot_exact_group_time
from deepecohab.utils.auxfun_plots import prep_exact_group_time


def occupancy(animal: str, start: datetime, end: datetime, cage: str = "cage_1") -> dict:
	return {
		"datetime": end,
		"time_spent": (end - start).total_seconds(),
		"day": 1,
		"phase_count": 1,
		"phase": "light_phase",
		"animal_id": animal,
		"position": cage,
	}


def test_exact_group_time_excludes_larger_group_spans():
	start = datetime(2026, 1, 1, 12)
	padded = pl.DataFrame(
		[
			occupancy("A", start, start + timedelta(seconds=10)),
			occupancy("B", start, start + timedelta(seconds=10)),
			occupancy("C", start + timedelta(seconds=4), start + timedelta(seconds=7)),
		]
	)

	result = prep_exact_group_time({"padded_df": padded}, ["light_phase"], [1, 1], ["cage_1"])
	times = dict(result.select("group", "seconds").iter_rows())

	assert times["A + B"] == pytest.approx(7)
	assert times["A + B + C"] == pytest.approx(3)
	assert sum(times.values()) == pytest.approx(10)


def test_exact_group_time_respects_phase_and_range_filters():
	start = datetime(2026, 1, 1, 12)
	rows = [occupancy(animal, start, start + timedelta(seconds=5)) for animal in ("A", "B")]
	rows.extend(
		{**occupancy(animal, start, start + timedelta(seconds=9)), "day": 2}
		for animal in ("A", "B")
	)
	result = prep_exact_group_time(
		{"padded_df": pl.DataFrame(rows)}, ["light_phase"], [2, 2], ["cage_1"]
	)

	assert result["seconds"].sum() == pytest.approx(9)


def test_exact_group_time_plot_has_bar_and_membership_markers():
	df = pl.DataFrame(
		{
			"day": [1],
			"phase": ["light_phase"],
			"cage": ["cage_1"],
			"group_size": [2],
			"group": ["A + B"],
			"seconds": [3600.0],
		}
	)
	fig = plot_exact_group_time(df, ["cage_1"], ["A", "B"], ["red", "blue"])

	bar = next(trace for trace in fig.data if trace.type == "bar")
	assert list(bar.y) == [1.0]
	assert set(bar.customdata) == {"A + B"}
	assert {trace.name for trace in fig.data if trace.showlegend} == {"A", "B"}


def test_native_plot_filters_to_groups_with_only_selected_animals():
	start = datetime(2026, 1, 1, 12)
	padded = pl.DataFrame(
		[
			occupancy("A", start, start + timedelta(seconds=10)),
			occupancy("B", start, start + timedelta(seconds=10)),
			occupancy("C", start + timedelta(seconds=4), start + timedelta(seconds=7)),
		]
	)
	fig = exact_group_time(
		store={"padded_df": padded},
		phase_type=["light_phase"],
		days_range=[1, 1],
		granularity="day",
		cages=["cage_1"],
		animals=["A", "B", "C"],
		exact_group_animals=["A", "B"],
		animal_colors=["red", "blue", "green"],
	)

	bar = next(trace for trace in fig.data if trace.type == "bar")
	assert set(bar.customdata) == {"A + B"}
	assert list(bar.y) == [pytest.approx(7 / 3600)]


def test_exact_group_plot_arranges_four_cages_in_two_by_two_grid():
	df = pl.DataFrame(
		{
			"cage": [f"cage_{index}" for index in range(1, 5)],
			"group": ["A + B"] * 4,
			"seconds": [60.0, 120.0, 180.0, 360.0],
		}
	)
	fig = plot_exact_group_time(
		df,
		[f"cage_{index}" for index in range(1, 5)],
		["A", "B"],
		["red", "blue"],
	)

	bars = [trace for trace in fig.data if trace.type == "bar"]
	assert [trace.xaxis for trace in bars] == ["x", "x2", "x5", "x6"]
	assert list(fig.layout.xaxis.range) == list(fig.layout.xaxis3.range)
	assert list(fig.layout.xaxis2.range) == list(fig.layout.xaxis4.range)
	assert list(fig.layout.xaxis5.range) == list(fig.layout.xaxis7.range)
	assert list(fig.layout.xaxis6.range) == list(fig.layout.xaxis8.range)
	for axis_name in ("yaxis3", "yaxis4", "yaxis7", "yaxis8"):
		assert getattr(fig.layout, axis_name).showticklabels is False
	bar_ranges = [
		list(getattr(fig.layout, axis_name).range)
		for axis_name in ("yaxis", "yaxis2", "yaxis5", "yaxis6")
	]
	assert bar_ranges == [bar_ranges[0]] * 4
	assert bar_ranges[0] == [0, pytest.approx(360 / 3600 * 1.05)]
	assert fig.layout.height >= 860


def test_exact_group_plot_keeps_unselected_animals_in_legend():
	df = pl.DataFrame({"cage": ["cage_1"], "group": ["A + B"], "seconds": [60.0]})
	fig = plot_exact_group_time(
		df,
		["cage_1"],
		["A", "B"],
		["red", "blue"],
		["A", "B", "C"],
		["red", "blue", "green"],
	)

	legend_traces = {trace.name: trace for trace in fig.data if trace.name}
	assert set(legend_traces) == {"A", "B", "C"}
	assert legend_traces["C"].visible == "legendonly"
