"""Tests for calculate_features (per-animal, z-scored EcoHAB feature table).

calculate_features collapses the upstream tables to one value per animal per
phase/day for eight metrics, aligns them, z-scores each metric across the table,
and returns long form (one row per animal/metric). It reads chasings_df,
tube_test_df, pairwise_meetings and activity_df via auxfun._get_data, which we
monkeypatch with a key-dispatching stub; the body runs via ``__wrapped__``. All
fixtures live in one light_phase occurrence (day 1, phase_count 1).
"""

import math

import polars as pl
import strategies as strat

from deepecohab.analysis import antenna_analysis

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
PHASE_ENUM = pl.Enum(["light_phase", "dark_phase"])
ANIMAL_ENUM = pl.Enum(CFG["animal_ids"])

METRICS = {
	"time_alone",
	"n_chasing",
	"n_chased",
	"n_wins",
	"n_loses",
	"activity",
	"time_together",
	"pairwise_encounters",
}


def _base(n: int) -> dict:
	return {
		"phase": pl.Series(["light_phase"] * n, dtype=PHASE_ENUM),
		"day": pl.Series([1] * n, dtype=pl.UInt16),
		"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
	}


def chasings_frame(rows: list[tuple[str, str, int]]) -> pl.LazyFrame:
	"""chasings_df rows (chaser, chased, chasings)."""
	return pl.LazyFrame(
		{
			**_base(len(rows)),
			"chaser": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"chased": pl.Series([r[1] for r in rows], dtype=ANIMAL_ENUM),
			"chasings": pl.Series([r[2] for r in rows], dtype=pl.UInt32),
		}
	)


def tube_frame(rows: list[tuple[str, str, int]]) -> pl.LazyFrame:
	"""tube_test_df rows (winner, loser, tube_test)."""
	return pl.LazyFrame(
		{
			**_base(len(rows)),
			"winner": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"loser": pl.Series([r[1] for r in rows], dtype=ANIMAL_ENUM),
			"tube_test": pl.Series([r[2] for r in rows], dtype=pl.UInt32),
		}
	)


def activity_frame(rows: list[tuple[str, int, float]]) -> pl.LazyFrame:
	"""activity_df rows (animal_id, visits_to_position, time_alone)."""
	return pl.LazyFrame(
		{
			**_base(len(rows)),
			"animal_id": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"visits_to_position": pl.Series([r[1] for r in rows], dtype=pl.UInt32),
			"time_alone": pl.Series([float(r[2]) for r in rows], dtype=pl.Float64),
		}
	)


def pairwise_frame(rows: list[tuple[str, str, float, int]]) -> pl.LazyFrame:
	"""pairwise_meetings rows (animal_id, animal_id_2, time_together, encounters)."""
	return pl.LazyFrame(
		{
			**_base(len(rows)),
			"animal_id": pl.Series([r[0] for r in rows], dtype=ANIMAL_ENUM),
			"animal_id_2": pl.Series([r[1] for r in rows], dtype=ANIMAL_ENUM),
			"time_together": pl.Series([float(r[2]) for r in rows], dtype=pl.Float64),
			"pairwise_encounters": pl.Series([r[3] for r in rows], dtype=pl.UInt32),
		}
	)


def run_features(monkeypatch, *, chasings, tube, activity, pairwise) -> pl.DataFrame:
	tables = {
		"chasings_df": chasings,
		"tube_test_df": tube,
		"pairwise_meetings": pairwise,
		"activity_df": activity,
	}
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: tables[key])
	return antenna_analysis.calculate_features.__wrapped__(CFG).collect()


def metric_map(result: pl.DataFrame, metric: str) -> dict[str, float]:
	sub = result.filter(pl.col("metric") == metric)
	return dict(sub.select("animal_id", "z-score").iter_rows())


def test_output_is_long_with_all_metrics(monkeypatch):
	"""Result is long-format: one row per animal/metric over the eight metrics."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 1)]),
		tube=tube_frame([("A", "B", 1)]),
		activity=activity_frame([("A", 10, 0.0), ("B", 20, 0.0)]),
		pairwise=pairwise_frame([("A", "B", 5.0, 1)]),
	)
	assert set(result.columns) == {"phase", "day", "phase_count", "animal_id", "metric", "z-score"}
	assert set(result["metric"].unique()) == METRICS


def test_constant_metric_zscores_to_zero(monkeypatch):
	"""A metric with zero variance must yield 0.0, never NaN/inf (the std==0 guard).

	This is the 'no behavior' case: with no chasings or tube tests anywhere, those
	count metrics are constant 0 across animals and must z-score to 0.0.
	"""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 0), ("B", "A", 0)]),
		tube=tube_frame([("A", "B", 0), ("B", "A", 0)]),
		activity=activity_frame([("A", 10, 0.0), ("B", 20, 0.0)]),
		pairwise=pairwise_frame([("A", "B", 0.0, 0)]),
	)
	# No NaN / inf anywhere in the table.
	zs = result["z-score"].to_list()
	assert all(math.isfinite(z) for z in zs)
	# The constant (all-zero) metrics z-score to exactly 0.
	for metric in ("n_chasing", "n_chased", "n_wins", "n_loses", "time_alone"):
		assert set(metric_map(result, metric).values()) == {0.0}


def test_all_zero_inputs_produce_all_zero_zscores(monkeypatch):
	"""When every metric is constant (all zero), the whole table is 0.0, not NaN."""
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 0), ("B", "A", 0)]),
		tube=tube_frame([("A", "B", 0), ("B", "A", 0)]),
		activity=activity_frame([("A", 0, 0.0), ("B", 0, 0.0)]),
		pairwise=pairwise_frame([("A", "B", 0.0, 0)]),
	)
	assert result["z-score"].to_list() == [0.0] * result.height


def test_zscore_values(monkeypatch):
	"""A two-animal activity contrast z-scores to the expected ±value."""
	# Only `activity` varies (A=10 visits, B=20). Sample std (ddof=1) of {10,20}
	# is sqrt(50); z = (x-15)/sqrt(50) -> -/+0.7071, rounded to -/+0.71.
	result = run_features(
		monkeypatch,
		chasings=chasings_frame([("A", "B", 0), ("B", "A", 0)]),
		tube=tube_frame([("A", "B", 0), ("B", "A", 0)]),
		activity=activity_frame([("A", 10, 0.0), ("B", 20, 0.0)]),
		pairwise=pairwise_frame([("A", "B", 0.0, 0)]),
	)
	activity = metric_map(result, "activity")
	assert activity["A"] == -0.71
	assert activity["B"] == 0.71
