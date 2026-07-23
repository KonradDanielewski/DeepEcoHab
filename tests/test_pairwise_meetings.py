"""Tests for calculate_pairwise_meetings (co-occurrence time and encounter counts).

A sweep-line over cage occupancy intervals (a bitmask variant of _get_time_alone)
finds spans where >=2 animals share a cage, decodes the present set, stitches
temporally-contiguous spans of the same pair into one meeting, drops meetings
shorter than ``minimum_time`` and sums onto the dense grid. padded_df is read via
auxfun._get_data (monkeypatched); the body runs via ``__wrapped__``.

padded_df rows carry the interval END in ``datetime`` and its length in
``time_spent``; all events sit in day-1 light_phase.
"""

import datetime as dt

import polars as pl
import pytest
import strategies as strat

from deepecohab.analysis import antenna_analysis
from deepecohab.utils import auxfun

CFG = strat.analysis_cfg(animal_ids=["A", "B", "C"])
at = strat.at


def padded_pieces(rows, cfg) -> pl.LazyFrame:
	"""Split each ``stay`` row at minute marks with the real padding, as padded_df does.

	Feeds the actual ``_get_minute_padding`` so a multi-minute stay becomes several
	per-minute pieces (interpolated flags and all), exactly like the production
	padded_df the pairwise step consumes. This exercises the split -> re-stitch path.
	"""
	df = pl.DataFrame(
		{
			"animal_id": pl.Series(
				[r["animal_id"] for r in rows], dtype=pl.Enum(cfg["animal_ids"])
			),
			"position": pl.Series([r["position"] for r in rows], dtype=pl.Categorical),
			"datetime": pl.Series("datetime", [r["datetime"] for r in rows]),
			"time_spent": pl.Series([float(r["time_spent"]) for r in rows], dtype=pl.Float64),
			"time_under": pl.Series([dt.timedelta(0) for _ in rows], dtype=pl.Duration("us")),
		}
	)
	return auxfun._get_minute_padding(df.lazy(), cfg)


def run_pairwise(monkeypatch, padded_lf, **kwargs) -> pl.DataFrame:
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: padded_lf)
	return antenna_analysis.calculate_pairwise_meetings.__wrapped__(CFG, **kwargs).collect()


def pair_cell(result: pl.DataFrame, a: str, b: str, position: str) -> dict:
	"""Co-presence totals for the unordered pair (a, b) in one cage."""
	lo, hi = sorted([a, b])
	sub = result.filter(
		(pl.col("animal_id") == lo)
		& (pl.col("animal_id_2") == hi)
		& (pl.col("position") == position)
	)
	return {
		"time_together": sub["time_together"].sum(),
		"pairwise_encounters": sub["pairwise_encounters"].sum(),
	}


def stay(animal, position, end, length):
	"""One padded_df occupancy row: animal in position ending at `end` for `length` s."""
	return {"animal_id": animal, "position": position, "datetime": end, "time_spent": float(length)}


def test_output_schema_and_unordered_pairs(monkeypatch):
	"""Result carries time_together/pairwise_encounters; pairs are unordered (a < b)."""
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 15), 10),
	]
	result = run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG))

	assert {"time_together", "pairwise_encounters"}.issubset(set(result.columns))
	# unordered: animal_id is always the lexicographically smaller of the pair.
	assert (result["animal_id"].cast(pl.String) < result["animal_id_2"].cast(pl.String)).all()
	assert (
		result.select(pl.col("time_together", "pairwise_encounters"))
		.null_count()
		.sum_horizontal()
		.item()
		== 0
	)


def test_shared_time_and_one_encounter(monkeypatch):
	"""Overlapping cage stays yield exactly the overlap and a single encounter."""
	# A in cage_1 [12:00:00, 12:00:10]; B [12:00:05, 12:00:15]; overlap 5 s.
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 15), 10),
	]
	c = pair_cell(run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "B", "cage_1")
	assert c["time_together"] == 5.0
	assert c["pairwise_encounters"] == 1


def test_short_meeting_dropped_by_minimum_time(monkeypatch):
	"""A meeting shorter than minimum_time contributes nothing (cell stays zero)."""
	# overlap of 1 s, below the default minimum_time of 2 s.
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 19), 10),
	]
	c = pair_cell(run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "B", "cage_1")
	assert c["time_together"] == 0.0
	assert c["pairwise_encounters"] == 0


def test_minimum_time_none_keeps_short_meeting(monkeypatch):
	"""With minimum_time=None the same 1 s meeting is retained."""
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 19), 10),
	]
	c = pair_cell(
		run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG), minimum_time=None),
		"A",
		"B",
		"cage_1",
	)
	assert c["time_together"] == 1.0
	assert c["pairwise_encounters"] == 1


def test_three_animals_decode_all_pairs(monkeypatch):
	"""Three animals sharing a cage produce all three pairs (bitmask decode)."""
	# Identical interval [12:00:00, 12:00:10] for A, B and C.
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("C", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
	]
	result = run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG))
	for a, b in (("A", "B"), ("A", "C"), ("B", "C")):
		c = pair_cell(result, a, b, "cage_1")
		assert c["time_together"] == 10.0, f"pair {a},{b}"
		assert c["pairwise_encounters"] == 1, f"pair {a},{b}"


def test_separate_meetings_counted_twice(monkeypatch):
	"""Two disjoint co-presence bouts of the same pair count as two encounters."""
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 5), 5),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 5), 5),
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 25), 5),
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 25), 5),
	]
	c = pair_cell(run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "B", "cage_1")
	assert c["pairwise_encounters"] == 2
	assert c["time_together"] == 10.0


def test_contiguous_spans_stitched_into_one_meeting(monkeypatch):
	"""A continuous A/B meeting split by a third animal's events is one encounter.

	C enters and leaves while A and B stay put, so the sweep cuts the A/B span into
	contiguous pieces; stitching must recombine them into a single meeting.
	"""
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 20), 20),  # [12:00:00, 12:00:20]
		stay("B", "cage_1", at(2023, 5, 24, 12, 0, 20), 20),  # [12:00:00, 12:00:20]
		stay("C", "cage_1", at(2023, 5, 24, 12, 0, 10), 5),  # [12:00:05, 12:00:10]
	]
	c = pair_cell(run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG)), "A", "B", "cage_1")
	assert c["pairwise_encounters"] == 1
	assert c["time_together"] == 20.0


def test_continuous_costay_split_across_minutes_is_one_encounter(monkeypatch):
	"""A single continuous co-stay counts once, even though padding splits it.

	Regression for the elevated pairwise_encounters: A and B sit together in a cage
	across several wall-clock minute marks. padded_df cuts that stay into per-minute
	pieces, but reconstructing exact interval bounds lets the sweep re-stitch them
	into ONE meeting. A boundary-rounding bug fragments the pieces into many spurious
	encounters instead. The fractional-second offset makes it sensitive to that bug.
	"""
	# both continuously in cage_1 over [12:00:20.5, 12:03:40.5]: 200 s across 3 marks.
	start = at(2023, 5, 24, 12, 0, 20, 500_000)
	end = at(2023, 5, 24, 12, 3, 40, 500_000)
	length = (end - start).total_seconds()
	rows = [
		{"animal_id": "A", "position": "cage_1", "datetime": end, "time_spent": length},
		{"animal_id": "B", "position": "cage_1", "datetime": end, "time_spent": length},
	]
	padded = padded_pieces(rows, CFG)
	# sanity: the stay really was split into multiple pieces per animal.
	assert padded.collect().filter(pl.col("animal_id") == "A").height > 1

	c = pair_cell(run_pairwise(monkeypatch, padded), "A", "B", "cage_1")
	assert c["pairwise_encounters"] == 1
	assert c["time_together"] == pytest.approx(length)


def test_encounters_never_exceed_sum_of_visits(monkeypatch):
	"""User's invariant: a pair can't meet more often than their combined visit count.

	A has three cage_1 visits and B two; some overlap, some don't. However the
	meetings fall out, the encounter count for the pair in that cage cannot exceed
	3 + 2 = 5 -- a pair meeting requires at least one of them to (re-)enter.
	"""

	def visit(a, s, e):
		return {
			"animal_id": a,
			"position": "cage_1",
			"datetime": e,
			"time_spent": (e - s).total_seconds(),
		}

	rows = [
		visit("A", at(2023, 5, 24, 12, 0, 0), at(2023, 5, 24, 12, 0, 10)),
		visit("B", at(2023, 5, 24, 12, 0, 5), at(2023, 5, 24, 12, 0, 15)),  # overlaps A#1
		visit("A", at(2023, 5, 24, 12, 0, 30), at(2023, 5, 24, 12, 0, 40)),  # alone
		visit("A", at(2023, 5, 24, 12, 1, 0), at(2023, 5, 24, 12, 1, 20)),
		visit("B", at(2023, 5, 24, 12, 1, 10), at(2023, 5, 24, 12, 1, 25)),  # overlaps A#3
	]
	result = run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG), minimum_time=None)
	c = pair_cell(result, "A", "B", "cage_1")
	visits_a, visits_b = 3, 2
	assert c["pairwise_encounters"] <= visits_a + visits_b
	assert c["pairwise_encounters"] == 2  # exactly the two overlapping bouts


def test_no_cooccupancy_yields_zero_grid(monkeypatch):
	"""Animals that never share a cage produce an all-zero grid."""
	rows = [
		stay("A", "cage_1", at(2023, 5, 24, 12, 0, 10), 10),
		stay("B", "cage_2", at(2023, 5, 24, 12, 0, 10), 10),
	]
	result = run_pairwise(monkeypatch, strat.padded_df_frame(rows, CFG))
	assert result.height > 0
	assert result["time_together"].sum() == 0
	assert result["pairwise_encounters"].sum() == 0
