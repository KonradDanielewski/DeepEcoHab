"""Tests for calculate_chasings (per-hour chasing counts on the dense grid).

calculate_chasings aggregates the event-level match_df into per-(chaser, chased,
tunnel, hour) counts and reindexes them onto the dense ordered-pair x tunnel grid
so absent cells are 0. It reads match_df via auxfun._get_data, which we
monkeypatch; the body is called via ``__wrapped__``.

All events are placed in day-1 light_phase so the run-length phase_count of the
hand-built match_df equals the grid's numbering (the first light phase is 1).
"""

import polars as pl
import strategies as strat

from deepecohab.analysis import antenna_analysis

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
at = strat.at


def run_chasings(monkeypatch, match_lf) -> pl.DataFrame:
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: match_lf)
	return antenna_analysis.calculate_chasings.__wrapped__(CFG).collect()


def cell(result: pl.DataFrame, chaser: str, chased: str, position: str) -> int:
	"""Total chasings for one ordered pair in one tunnel (summed over the grid)."""
	sub = result.filter(
		(pl.col("chaser") == chaser)
		& (pl.col("chased") == chased)
		& (pl.col("position") == position)
	)
	return int(sub["chasings"].sum())


def test_output_schema_and_zero_fill(monkeypatch):
	"""Result is the dense ordered-pair x tunnel grid with a chasings count."""
	rows = [
		{"winner": "A", "loser": "B", "position": "c1_c2", "datetime": at(2023, 5, 24, 12, 0, 0)}
	]
	result = run_chasings(monkeypatch, strat.match_df_frame(rows, CFG))

	assert {"chaser", "chased", "position", "chasings"}.issubset(set(result.columns))
	# Every ordered pair appears (A!=B etc.), and unobserved cells are 0, not null.
	assert result["chasings"].null_count() == 0
	# Self-pairs are excluded from the ordered-pair grid.
	assert result.filter(pl.col("chaser") == pl.col("chased")).height == 0


def test_counts_per_ordered_pair(monkeypatch):
	"""Two A-over-B chases and one B-over-A chase land in the right directed cells."""
	rows = [
		{"winner": "A", "loser": "B", "position": "c1_c2", "datetime": at(2023, 5, 24, 12, 0, 0)},
		{"winner": "A", "loser": "B", "position": "c1_c2", "datetime": at(2023, 5, 24, 12, 0, 5)},
		{"winner": "B", "loser": "A", "position": "c1_c2", "datetime": at(2023, 5, 24, 12, 0, 9)},
	]
	result = run_chasings(monkeypatch, strat.match_df_frame(rows, CFG))

	assert cell(result, "A", "B", "c1_c2") == 2
	assert cell(result, "B", "A", "c1_c2") == 1


def test_winner_is_chaser_loser_is_chased(monkeypatch):
	"""The match winner becomes the chaser; the count never lands on the reversed cell."""
	rows = [
		{"winner": "A", "loser": "B", "position": "c1_c2", "datetime": at(2023, 5, 24, 12, 0, 0)}
	]
	result = run_chasings(monkeypatch, strat.match_df_frame(rows, CFG))

	assert cell(result, "A", "B", "c1_c2") == 1
	assert cell(result, "B", "A", "c1_c2") == 0


def test_counts_are_per_tunnel(monkeypatch):
	"""A chase in one tunnel does not leak into another tunnel's cell."""
	rows = [
		{"winner": "A", "loser": "B", "position": "c2_c3", "datetime": at(2023, 5, 24, 12, 0, 0)}
	]
	result = run_chasings(monkeypatch, strat.match_df_frame(rows, CFG))

	assert cell(result, "A", "B", "c2_c3") == 1
	assert cell(result, "A", "B", "c1_c2") == 0


def test_empty_match_df_yields_all_zero_grid(monkeypatch):
	"""No chasing events anywhere (e.g. a quiet day) -> a full grid of zeros."""
	result = run_chasings(monkeypatch, strat.match_df_frame([], CFG))

	assert result.height > 0  # the dense grid still exists
	assert result["chasings"].sum() == 0
	assert result["chasings"].null_count() == 0
