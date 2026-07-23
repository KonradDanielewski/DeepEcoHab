"""Tests for calculate_incohort_sociability (observed togetherness minus chance).

For each pair and cage, observed co-presence (as a fraction of phase duration) is
compared to the chance expectation from each animal's independent occupancy
(product of occupancy proportions); sociability is the observed-minus-chance
difference summed over cages (DOI:10.7554/eLife.19532).

The step reads three upstream tables via auxfun._get_data — ``activity_df``,
``pairwise_meetings`` and ``phase_durations`` — so we monkeypatch it with a
key-dispatching stub and call the body via ``__wrapped__``. All fixtures live in a
single light_phase occurrence (day 1, phase_count 1) so the arithmetic is by hand.
"""

import polars as pl
import pytest
import strategies as strat

from deepecohab.analysis import antenna_analysis

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
PHASE_ENUM = pl.Enum(["light_phase", "dark_phase"])
ANIMAL_ENUM = pl.Enum(CFG["animal_ids"])


def activity_frame(entries: list[tuple[str, str, float]]) -> pl.LazyFrame:
	"""activity_df rows (animal_id, position, time_in_position) in light_phase day 1."""
	n = len(entries)
	return pl.LazyFrame(
		{
			"phase": pl.Series(["light_phase"] * n, dtype=PHASE_ENUM),
			"day": pl.Series([1] * n, dtype=pl.UInt16),
			"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
			"hour": pl.Series([12] * n, dtype=pl.UInt8),
			"position": pl.Series([e[1] for e in entries], dtype=pl.Categorical),
			"animal_id": pl.Series([e[0] for e in entries], dtype=ANIMAL_ENUM),
			"time_in_position": pl.Series([float(e[2]) for e in entries], dtype=pl.Float64),
		}
	)


def pairwise_frame(entries: list[tuple[str, str, str, float]]) -> pl.LazyFrame:
	"""pairwise_meetings rows (a, b, position, time_together) in light_phase day 1."""
	n = len(entries)
	return pl.LazyFrame(
		{
			"phase": pl.Series(["light_phase"] * n, dtype=PHASE_ENUM),
			"day": pl.Series([1] * n, dtype=pl.UInt16),
			"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
			"hour": pl.Series([12] * n, dtype=pl.UInt8),
			"position": pl.Series([e[2] for e in entries], dtype=pl.Categorical),
			"animal_id": pl.Series([e[0] for e in entries], dtype=ANIMAL_ENUM),
			"animal_id_2": pl.Series([e[1] for e in entries], dtype=ANIMAL_ENUM),
			"time_together": pl.Series([float(e[3]) for e in entries], dtype=pl.Float64),
			"pairwise_encounters": pl.Series([1] * n, dtype=pl.UInt32),
		}
	)


def durations_frame(duration_seconds: float) -> pl.LazyFrame:
	return pl.LazyFrame(
		{
			"phase": pl.Series(["light_phase"], dtype=PHASE_ENUM),
			"phase_count": pl.Series([1], dtype=pl.UInt16),
			"duration_seconds": pl.Series([float(duration_seconds)], dtype=pl.Float64),
		}
	)


def run_sociability(monkeypatch, *, activity, pairwise, durations) -> pl.DataFrame:
	tables = {
		"activity_df": activity,
		"pairwise_meetings": pairwise,
		"phase_durations": durations,
	}
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: tables[key])
	return antenna_analysis.calculate_incohort_sociability.__wrapped__(CFG).collect()


def pair_row(result: pl.DataFrame, a: str, b: str) -> dict:
	return result.filter((pl.col("animal_id") == a) & (pl.col("animal_id_2") == b)).row(
		0, named=True
	)


def test_sociability_value_single_cage(monkeypatch):
	"""proportion_together = T/D and sociability = T/D - (a*b)/D^2 for one cage."""
	# A occupies cage_1 for 40 s, B for 30 s, together 20 s, phase duration 100 s.
	activity = activity_frame([("A", "cage_1", 40), ("B", "cage_1", 30)])
	pairwise = pairwise_frame([("A", "B", "cage_1", 20)])
	result = run_sociability(
		monkeypatch, activity=activity, pairwise=pairwise, durations=durations_frame(100)
	)

	row = pair_row(result, "A", "B")
	assert row["proportion_together"] == pytest.approx(0.2)  # 20 / 100
	assert row["sociability"] == pytest.approx(0.2 - (40 * 30) / 100**2)  # 0.2 - 0.12 = 0.08


def test_sociability_sums_over_cages(monkeypatch):
	"""Sociability is summed across cages."""
	activity = activity_frame(
		[("A", "cage_1", 40), ("B", "cage_1", 30), ("A", "cage_2", 10), ("B", "cage_2", 10)]
	)
	pairwise = pairwise_frame([("A", "B", "cage_1", 20), ("A", "B", "cage_2", 5)])
	result = run_sociability(
		monkeypatch, activity=activity, pairwise=pairwise, durations=durations_frame(100)
	)

	cage1 = 20 / 100 - (40 * 30) / 100**2
	cage2 = 5 / 100 - (10 * 10) / 100**2
	row = pair_row(result, "A", "B")
	assert row["sociability"] == pytest.approx(cage1 + cage2)
	assert row["proportion_together"] == pytest.approx(20 / 100 + 5 / 100)


def test_zero_when_observed_equals_chance(monkeypatch):
	"""When observed togetherness equals the chance expectation, sociability is 0."""
	# a*b/D = 50*40/100 = 20 = T, so observed == chance.
	activity = activity_frame([("A", "cage_1", 50), ("B", "cage_1", 40)])
	pairwise = pairwise_frame([("A", "B", "cage_1", 20)])
	result = run_sociability(
		monkeypatch, activity=activity, pairwise=pairwise, durations=durations_frame(100)
	)

	assert pair_row(result, "A", "B")["sociability"] == pytest.approx(0.0)


def test_denominator_is_phase_duration(monkeypatch):
	"""Sociability normalizes by wall-clock phase duration (incl. any recording gap).

	get_phase_durations measures each phase occurrence's wall-clock length over the
	experiment window, so a power outage that leaves dead minutes inside the window
	inflates duration_seconds. With observed togetherness unchanged, a larger
	duration therefore shrinks both proportion_together and sociability. This pins
	that denominator behavior (the normalization the published metric relies on).
	"""
	activity = activity_frame([("A", "cage_1", 40), ("B", "cage_1", 30)])
	pairwise = pairwise_frame([("A", "B", "cage_1", 20)])

	short = run_sociability(
		monkeypatch, activity=activity, pairwise=pairwise, durations=durations_frame(100)
	)
	tall = run_sociability(
		monkeypatch, activity=activity, pairwise=pairwise, durations=durations_frame(200)
	)

	assert (
		pair_row(tall, "A", "B")["proportion_together"]
		< pair_row(short, "A", "B")["proportion_together"]
	)
	assert pair_row(tall, "A", "B")["sociability"] < pair_row(short, "A", "B")["sociability"]
