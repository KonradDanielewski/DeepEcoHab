"""Tests for calculate_tube_test (head-on tunnel encounters).

A tube-test event: the loser enters a tunnel and retreats to the cage it came
from, while the winner enters the same tunnel from the opposite end during an
overlapping interval and exits later. The winner either follows the loser into
the cage it retreated to (CHASE) or returns to its own origin cage (GUARD).

calculate_tube_test reads main_df via auxfun._get_data (monkeypatched here) and
is driven through ``__wrapped__``. Events are placed in day-1 light_phase so the
hand-built phase_count matches the grid. Positions never repeat consecutively per
animal, so update_repeat_antenna_position is a no-op on these fixtures.
"""

import datetime as dt

import polars as pl
import strategies as strat

from deepecohab.analysis import antenna_analysis

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
at = strat.at


def run_tube(monkeypatch, main_lf, **kwargs) -> pl.DataFrame:
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: main_lf)
	return antenna_analysis.calculate_tube_test.__wrapped__(CFG, **kwargs).collect()


def encounter(
	loser="B",
	winner="A",
	*,
	behavior="chase",
	loser_dwell=2.0,
	winner_dwell=2.0,
	winner_tunnel_exit=(12, 0, 4),
):
	"""Rows for one head-on encounter in tunnel_1 (c1_c2 / c2_c1).

	Loser comes from cage_1, dips into the tunnel and retreats to cage_1. Winner
	comes from cage_2 into the same tunnel; for CHASE it ends in cage_1 (follows
	the loser), for GUARD it returns to cage_2 (its origin).
	"""
	winner_final = "cage_1" if behavior == "chase" else "cage_2"
	we = at(2023, 5, 24, *winner_tunnel_exit)

	return [
		{
			"animal_id": loser,
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 0),
			"time_spent": 1.0,
		},
		{
			"animal_id": winner,
			"position": "cage_2",
			"datetime": at(2023, 5, 24, 12, 0, 0, 500000),
			"time_spent": 1.0,
		},
		# loser tunnel exit at 12:00:03 (entry = exit - dwell)
		{
			"animal_id": loser,
			"position": "c1_c2",
			"datetime": at(2023, 5, 24, 12, 0, 3),
			"time_spent": loser_dwell,
		},
		# winner tunnel exit (entry = exit - dwell)
		{"animal_id": winner, "position": "c2_c1", "datetime": we, "time_spent": winner_dwell},
		{
			"animal_id": loser,
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 2.0,
		},
		{
			"animal_id": winner,
			"position": winner_final,
			"datetime": we + dt.timedelta(seconds=2),
			"time_spent": 2.0,
		},
	]


def total(result: pl.DataFrame, winner: str, loser: str) -> int:
	sub = result.filter((pl.col("winner") == winner) & (pl.col("loser") == loser))
	return int(sub["tube_test"].sum())


def test_chase_event_detected(monkeypatch):
	"""A head-on CHASE encounter is counted once, with the retreater as the loser."""
	result = run_tube(monkeypatch, strat.main_df_frame(encounter(behavior="chase"), CFG))
	assert total(result, "A", "B") == 1
	assert total(result, "B", "A") == 0  # direction guard, no double count


def test_guard_event_detected(monkeypatch):
	"""A head-on GUARD encounter (winner holds its origin cage) is counted once."""
	result = run_tube(monkeypatch, strat.main_df_frame(encounter(behavior="guard"), CFG))
	assert total(result, "A", "B") == 1


def test_winner_behavior_isolates_chase(monkeypatch):
	"""A CHASE encounter counts under CHASE/BOTH but not under GUARD."""
	rows = strat.main_df_frame(encounter(behavior="chase"), CFG)
	assert run_tube(monkeypatch, rows, winner_behavior="CHASE")["tube_test"].sum() == 1
	assert run_tube(monkeypatch, rows, winner_behavior="BOTH")["tube_test"].sum() == 1
	assert run_tube(monkeypatch, rows, winner_behavior="GUARD")["tube_test"].sum() == 0


def test_winner_behavior_isolates_guard(monkeypatch):
	"""A GUARD encounter counts under GUARD/BOTH but not under CHASE."""
	rows = strat.main_df_frame(encounter(behavior="guard"), CFG)
	assert run_tube(monkeypatch, rows, winner_behavior="GUARD")["tube_test"].sum() == 1
	assert run_tube(monkeypatch, rows, winner_behavior="BOTH")["tube_test"].sum() == 1
	assert run_tube(monkeypatch, rows, winner_behavior="CHASE")["tube_test"].sum() == 0


def test_max_dwell_excludes_inflated_segment(monkeypatch):
	"""An inflated loser tunnel dwell is dropped at the default cap but kept if raised."""
	rows = strat.main_df_frame(encounter(behavior="chase", loser_dwell=20.0), CFG)
	# Default max_dwell=10 drops the 20 s loser segment...
	assert run_tube(monkeypatch, rows)["tube_test"].sum() == 0
	# ...raising the cap past it restores the (still overlapping) encounter.
	assert run_tube(monkeypatch, rows, max_dwell=30.0)["tube_test"].sum() == 1


def test_non_overlapping_intervals_not_an_event(monkeypatch):
	"""If the two tunnel intervals do not overlap in time, it is not a tube test."""
	# Winner enters the tunnel only after the loser has already exited it.
	rows = strat.main_df_frame(
		encounter(behavior="chase", winner_dwell=2.0, winner_tunnel_exit=(12, 0, 7)), CFG
	)
	# loser tunnel interval [12:00:01, 12:00:03]; winner [12:00:05, 12:00:07] -> no overlap.
	assert run_tube(monkeypatch, rows)["tube_test"].sum() == 0


def test_same_origin_is_not_head_on(monkeypatch):
	"""Two animals entering the tunnel from the same cage is not a head-on encounter."""
	rows = [
		{
			"animal_id": "B",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 0),
			"time_spent": 1.0,
		},
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 0, 500000),
			"time_spent": 1.0,
		},
		{
			"animal_id": "B",
			"position": "c1_c2",
			"datetime": at(2023, 5, 24, 12, 0, 3),
			"time_spent": 2.0,
		},
		{
			"animal_id": "A",
			"position": "c1_c2",
			"datetime": at(2023, 5, 24, 12, 0, 4),
			"time_spent": 2.0,
		},
		{
			"animal_id": "B",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 2.0,
		},
		{
			"animal_id": "A",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 6),
			"time_spent": 2.0,
		},
	]
	assert run_tube(monkeypatch, strat.main_df_frame(rows, CFG))["tube_test"].sum() == 0


def test_no_events_yields_all_zero_grid(monkeypatch):
	"""No head-on encounters (a lone retreating animal) -> a full grid of zeros."""
	rows = [
		{
			"animal_id": "B",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 0),
			"time_spent": 1.0,
		},
		{
			"animal_id": "B",
			"position": "c1_c2",
			"datetime": at(2023, 5, 24, 12, 0, 3),
			"time_spent": 2.0,
		},
		{
			"animal_id": "B",
			"position": "cage_1",
			"datetime": at(2023, 5, 24, 12, 0, 5),
			"time_spent": 2.0,
		},
	]
	result = run_tube(monkeypatch, strat.main_df_frame(rows, CFG))
	assert result.height > 0
	assert result["tube_test"].sum() == 0
	assert result["tube_test"].null_count() == 0
