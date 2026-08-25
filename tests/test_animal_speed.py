import datetime as dt

import polars as pl

from deepecohab.analysis import antenna_analysis
from deepecohab.plotting import plot_factory
from deepecohab.utils import auxfun_plots


def test_calculate_animal_speed_keeps_valid_tunnel_crossings(monkeypatch):
	cfg = {
		"positions": ["cage_1", "tunnel_1"],
		"cages": ["cage_1"],
		"antenna_combinations": {"1_2": "c1_c2", "2_1": "c2_c1", "1_1": "cage_1"},
	}
	main_df = pl.LazyFrame(
		{
			"animal_id": ["A", "A", "B", "B", "B"],
			"position": ["c1_c2", "c2_c1", "c1_c2", "cage_1", "c2_c1"],
			"datetime": [dt.datetime(2023, 5, 24, 12, 0, second) for second in [2, 6, 7, 9, 20]],
			"time_spent": [2.0, 4.0, 0.0, 2.0, 11.0],
			"day": [1] * 5,
			"phase": ["light_phase"] * 5,
		}
	)
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: main_df)

	result = antenna_analysis.calculate_animal_speed.__wrapped__(cfg).collect()

	assert result.select("animal_id", "position", "speed_cm_s").to_dicts() == [
		{"animal_id": "A", "position": "c1_c2", "speed_cm_s": 10.0},
		{"animal_id": "A", "position": "c2_c1", "speed_cm_s": 5.0},
	]


def test_speed_plot_preparation_respects_filters_and_builds_daily_means():
	speed_df = pl.DataFrame(
		{
			"animal_id": ["A", "A", "B"],
			"day": [1, 2, 1],
			"phase": ["light_phase", "light_phase", "dark_phase"],
			"position": ["c1_c2", "c2_c1", "c1_c2"],
			"time_spent": [2.0, 1.0, 0.5],
			"speed_cm_s": [10.0, 20.0, 40.0],
		}
	)
	store = {"speed_df": speed_df}

	distribution = auxfun_plots.prep_animal_speed(store, [1, 1], ["light_phase"])
	daily = auxfun_plots.prep_animal_speed_daily(store, [1, 2], ["light_phase"])
	fig = plot_factory.plot_animal_speed(distribution, ["A", "B"], ["#111", "#222"])

	assert distribution["speed_cm_s"].to_list() == [10.0]
	assert daily.select("day", "animal_id", "mean_speed_cm_s").to_dicts() == [
		{"day": 1, "animal_id": "A", "mean_speed_cm_s": 10.0},
		{"day": 2, "animal_id": "A", "mean_speed_cm_s": 20.0},
	]
	assert fig.layout.title.text == "<b>Tunnel-crossing speed</b>"
