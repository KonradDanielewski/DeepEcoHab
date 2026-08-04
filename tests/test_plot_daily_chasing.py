import polars as pl
import pytest

from deepecohab.plotting.plot_catalog import plot_registry
from deepecohab.plotting.plot_factory import plot_daily_chasing
from deepecohab.utils.auxfun_plots import prep_daily_chasing


def test_prep_daily_chasing_sums_each_chasers_daily_counts():
	df = pl.DataFrame(
		{
			"chaser": ["A", "A", "A", "B", "B"],
			"chased": ["B", "C", "B", "A", "A"],
			"day": [1, 1, 2, 1, 2],
			"hour": [8, 9, 8, 8, 8],
			"chasings": [2, 3, 4, 1, 0],
		}
	)

	result = prep_daily_chasing({"chasings_df": df}, ["A", "B"], [1, 2])

	assert result.to_dicts() == [
		{"animal_id": "A", "day": 1, "total_chasing": 5},
		{"animal_id": "A", "day": 2, "total_chasing": 4},
		{"animal_id": "B", "day": 1, "total_chasing": 1},
		{"animal_id": "B", "day": 2, "total_chasing": 0},
	]


def test_prep_daily_chasing_requires_expected_columns():
	with pytest.raises(ValueError, match="missing required columns: chasings"):
		prep_daily_chasing(
			{"chasings_df": pl.DataFrame({"chaser": ["A"], "day": [1]})}, ["A"], [1, 1]
		)


def test_plot_daily_chasing_uses_project_stacked_bar_style():
	df = pl.DataFrame(
		{"animal_id": ["A", "A", "B", "B"], "day": [1, 2, 1, 2], "total_chasing": [2, 3, 1, 4]}
	)

	fig = plot_daily_chasing(df, ["A", "B"], ["rgb(1, 2, 3)", "rgb(4, 5, 6)"])

	assert fig.layout.title.text == "<b>Chasing per day</b>"
	assert fig.layout.legend.title.text == "<b>Chaser</b>"
	assert fig.layout.xaxis.title.text == "<b>Day</b>"
	assert fig.layout.yaxis.title.text == "<b># of chasing events</b>"
	assert fig.layout.barmode == "stack"
	assert fig.layout.barcornerradius == 10
	assert [trace.type for trace in fig.data] == ["bar", "bar"]
	assert [trace.marker.color for trace in fig.data] == ["rgb(1, 2, 3)", "rgb(4, 5, 6)"]


def test_daily_chasing_plot_is_registered():
	assert "chasings-daily-bar" in plot_registry.list_available()
	assert plot_registry.get_dependencies("chasings-daily-bar") == [
		"store",
		"animals",
		"days_range",
		"animal_colors",
	]
