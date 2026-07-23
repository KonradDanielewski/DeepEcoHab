"""Tests for calculate_activity (per-animal occupancy, visits and solitary time).

calculate_activity combines per-position dwell/visit counts (_get_activity) and
solitary time (_get_time_alone) from padded_df, then reindexes onto the dense
animal x position x hour grid (build_experiment_grid), zero-filling empty cells.
padded_df is read via auxfun._get_data (monkeypatched); the body runs via
``__wrapped__``. Events sit in day-1 light_phase so phase_count matches the grid.
"""

import polars as pl
import strategies as strat

from deepecohab.analysis import antenna_analysis

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
at = strat.at


def run_activity(monkeypatch, padded_lf) -> pl.DataFrame:
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: padded_lf)
	return antenna_analysis.calculate_activity.__wrapped__(CFG).collect()


def cell(result: pl.DataFrame, animal: str, position: str) -> dict:
	"""Sum the metrics for one animal/position over the (single) active hour."""
	sub = result.filter((pl.col("animal_id") == animal) & (pl.col("position") == position))
	return {
		"time_in_position": sub["time_in_position"].sum(),
		"visits_to_position": sub["visits_to_position"].sum(),
		"time_alone": sub["time_alone"].sum(),
	}


def test_output_schema_and_dense_grid(monkeypatch):
	"""Result spans every animal x position cell with the three metric columns."""
	rows = [
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 5.0,
		}
	]
	result = run_activity(monkeypatch, strat.padded_df_frame(rows, CFG))

	assert {"time_in_position", "visits_to_position", "time_alone"}.issubset(set(result.columns))
	# Every animal and every position appears (dense grid), with no nulls.
	assert set(result["animal_id"].unique()) == set(CFG["animal_ids"])
	assert set(result["position"].cast(pl.String).unique()) == set(CFG["positions"])
	assert (
		result.select(pl.col("time_in_position", "visits_to_position", "time_alone"))
		.null_count()
		.sum_horizontal()
		.item()
		== 0
	)


def test_interpolated_reads_excluded_from_visits_but_keep_time(monkeypatch):
	"""An interpolated piece adds its dwell time but is not counted as a visit."""
	rows = [
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 5.0,
			"interpolated": False,
		},
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 10),
			"time_spent": 3.0,
			"interpolated": True,
		},
	]
	c = cell(run_activity(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "cage_1")

	assert c["time_in_position"] == 8.0  # both pieces contribute their time
	assert c["visits_to_position"] == 1  # only the non-interpolated read is a visit


def test_solitary_time_recorded(monkeypatch):
	"""A lone animal's time_alone equals its occupancy for that cell."""
	rows = [
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 10),
			"time_spent": 10.0,
		}
	]
	c = cell(run_activity(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "cage_1")

	assert c["time_in_position"] == 10.0
	assert c["time_alone"] == 10.0


def test_missing_animal_is_zero_filled(monkeypatch):
	"""An animal that never appears in padded_df still gets dense zero rows.

	This is the 'animal goes missing / dies mid-experiment' contract: the dead
	animal is present in every grid cell with zero occupancy/visits/solitary time,
	never absent.
	"""
	rows = [
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 5.0,
		}
	]
	result = run_activity(monkeypatch, strat.padded_df_frame(rows, CFG))

	c_rows = result.filter(pl.col("animal_id") == "C")
	assert c_rows.height > 0
	assert c_rows["time_in_position"].sum() == 0
	assert c_rows["visits_to_position"].sum() == 0
	assert c_rows["time_alone"].sum() == 0
