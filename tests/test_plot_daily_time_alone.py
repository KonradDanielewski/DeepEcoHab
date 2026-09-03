import polars as pl

from deepecohab.utils.auxfun_plots import prep_daily_time_alone


def test_prep_daily_time_alone_sums_cages_by_animal_and_day():
	df = pl.DataFrame(
		{
			"animal_id": ["B", "A", "A", "B", "B", "A"],
			"position": ["cage_1", "cage_1", "cage_2", "cage_2", "tunnel_1", "cage_1"],
			"phase": [
				"dark_phase",
				"dark_phase",
				"dark_phase",
				"dark_phase",
				"dark_phase",
				"dark_phase",
			],
			"day": [2, 1, 1, 1, 1, 2],
			"time_alone": [10.0, 20.0, 5.0, 30.0, 40.0, 15.0],
		}
	)

	result = prep_daily_time_alone({"activity_df": df}, [1, 2], ["dark_phase"])

	assert result.to_dicts() == [
		{"animal_id": "A", "day": 1, "total_time_alone": 25.0},
		{"animal_id": "B", "day": 1, "total_time_alone": 30.0},
		{"animal_id": "B", "day": 2, "total_time_alone": 10.0},
		{"animal_id": "A", "day": 2, "total_time_alone": 15.0},
	]
