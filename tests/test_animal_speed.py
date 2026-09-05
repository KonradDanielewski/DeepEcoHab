import polars as pl

from deepecohab.plotting import plot_factory
from deepecohab.utils import auxfun_plots


def test_prep_animal_speed_keeps_valid_selected_tunnel_crossings():
	main_df = pl.DataFrame(
		{
			"animal_id": ["A", "A", "B", "B", "B"],
			"day": [1, 1, 1, 1, 1],
			"phase": ["light_phase"] * 5,
			"phase_count": [1] * 5,
			"datetime": pl.datetime_range(
				pl.datetime(2026, 1, 1),
				pl.datetime(2026, 1, 1, 0, 0, 4),
				"1s",
				eager=True,
			),
			"position": ["c1_c2", "c2_c1", "c1_c2", "cage_1", "c2_c1"],
			"time_spent": [2.0, 4.0, 0.0, 2.0, 11.0],
		}
	)

	result = auxfun_plots.prep_animal_speed(
		{"main_df": main_df}, [1, 1], ["light_phase"], ["c1_c2", "c2_c1"]
	)

	assert result.select("animal_id", "position", "speed_cm_s").to_dicts() == [
		{"animal_id": "A", "position": "c2_c1", "speed_cm_s": 5.0},
		{"animal_id": "A", "position": "c1_c2", "speed_cm_s": 10.0},
	]


def test_speed_plot_respects_dashboard_filters():
	store = {
		"main_df": pl.DataFrame(
			{
				"animal_id": ["A", "A", "B"],
				"day": [1, 2, 1],
				"phase": ["light_phase", "light_phase", "dark_phase"],
				"position": ["c1_c2", "c2_c1", "c1_c2"],
				"time_spent": [2.0, 1.0, 0.5],
				"speed_cm_s": [10.0, 20.0, 30.0],
			}
		)
	}

	df = auxfun_plots.prep_animal_speed(store, [1, 1], ["light_phase"], ["c1_c2", "c2_c1"])
	fig = plot_factory.plot_animal_speed(df, ["A", "B"], ["#111111", "#222222"])

	assert df["speed_cm_s"].to_list() == [10.0]
	assert fig.layout.title.text == "<b>Tunnel-crossing speed</b>"
	assert fig.layout.yaxis.title.text == "<b>Speed [cm/s]</b>"


def test_speed_summaries_show_daily_means_and_slow_crossing_percentage():
	main_df = pl.DataFrame(
		{
			"animal_id": ["A", "A", "A", "A", "B", "B", "B", "B", "B"],
			"day": [1, 1, 1, 2, 1, 1, 1, 1, 1],
			"phase": [
				"light_phase",
				"light_phase",
				"light_phase",
				"light_phase",
				"light_phase",
				"light_phase",
				"dark_phase",
				"light_phase",
				"light_phase",
			],
			"position": [
				"c1_c2",
				"c2_c1",
				"c1_c2",
				"c1_c2",
				"c1_c2",
				"c2_c1",
				"c1_c2",
				"cage_1",
				"c1_c2",
			],
			"time_spent": [2.0, 4.0, 12.0, 1.0, 5.0, 15.0, 3.0, 20.0, 0.0],
		}
	)
	store = {"main_df": main_df}
	tunnels = ["c1_c2", "c2_c1"]

	daily = auxfun_plots.prep_animal_speed_daily(store, [1, 1], ["light_phase"], tunnels)
	slow = auxfun_plots.prep_slow_crossings(store, [1, 1], ["light_phase"], tunnels)

	assert daily.to_dicts() == [
		{"day": 1, "animal_id": "A", "mean_speed_cm_s": 7.5},
		{"day": 1, "animal_id": "B", "mean_speed_cm_s": 4.0},
	]
	assert slow.to_dicts() == [
		{"animal_id": "A", "crossings": 3, "slow_crossings": 1, "slow_percentage": 33.33},
		{"animal_id": "B", "crossings": 2, "slow_crossings": 1, "slow_percentage": 50.0},
	]
