"""Property/invariant tests for the antenna_analysis steps.

Where the per-function tests in ``test_*.py`` pin specific hand-computed values,
these draw randomised-but-valid inputs with Hypothesis and assert relationships
that must hold for *every* input -- cross-table consistency and the
missing-animal ("an animal dies / never shows up") contracts.

Inputs are kept inside a single light_phase occurrence (day 1, hour 12) so the
run-length ``phase_count`` of the hand-built frames matches the dense grid's
numbering (the phase_count footgun documented in strategies.py). Per animal the
generated cage stays never overlap in time, which is what the real data
guarantees and what the bitmask co-occupancy sweep relies on.

The steps read their input via ``auxfun._get_data``; instead of the ``monkeypatch``
fixture (which trips Hypothesis's function-scoped-fixture health check) we swap the
attribute directly and restore it, and drive the pure body via ``__wrapped__``.
"""

import datetime as dt
import math

import polars as pl
import strategies as strat
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from deepecohab.analysis import antenna_analysis

ANIMALS = ["A", "B", "C"]
CFG = strat.analysis_cfg(animal_ids=ANIMALS)
CAGES = strat.ANALYSIS_CAGES
DIRECTIONAL = strat.ANALYSIS_DIRECTIONAL
BASE = strat.at(2023, 5, 24, 12, 0, 0)  # day-1 light_phase, hour 12


# --- input injection ---------------------------------------------------------
def run(fn, table_for_key, **kwargs) -> pl.DataFrame:
	"""Run ``fn``'s pure body with ``auxfun._get_data`` swapped for ``table_for_key``.

	``table_for_key`` is a ``(cfg, key) -> LazyFrame`` callable, restored afterwards.
	"""
	orig = antenna_analysis.auxfun._get_data
	antenna_analysis.auxfun._get_data = table_for_key
	try:
		return fn.__wrapped__(CFG, **kwargs).collect()
	finally:
		antenna_analysis.auxfun._get_data = orig


# --- generators --------------------------------------------------------------
# One cage stay: (cage, gap-before-it, dwell). Bounded so a whole per-animal
# timeline (<= 4 stays) stays inside hour 12.
_stay = st.tuples(
	st.sampled_from(CAGES),
	st.floats(min_value=0, max_value=8, allow_nan=False),
	st.floats(min_value=0.5, max_value=20, allow_nan=False),
)
cage_plans = st.fixed_dictionaries({a: st.lists(_stay, max_size=4) for a in ANIMALS})


def padded_from_plan(plan: dict[str, list[tuple]]) -> pl.LazyFrame:
	"""Turn a per-animal stay plan into a padded_df.

	Each animal's stays are laid end-to-end (gap, dwell, gap, dwell, ...) from
	BASE, so one animal's intervals never overlap; different animals' do. The
	padded_df ``datetime`` marks the interval END.
	"""
	rows = []
	for animal, stays in plan.items():
		t = 0.0
		for cage, gap, dwell in stays:
			t += gap
			end = BASE + dt.timedelta(seconds=t + dwell)
			rows.append(
				{"animal_id": animal, "position": cage, "datetime": end, "time_spent": float(dwell)}
			)
			t += dwell
	return strat.padded_df_frame(rows, CFG)


# winner/loser chasing events for match_df: distinct animals, a directional
# tunnel, all within hour 12.
_match_event = st.builds(
	lambda pair, tunnel, sec: {
		"winner": pair[0],
		"loser": pair[1],
		"position": tunnel,
		"datetime": BASE + dt.timedelta(seconds=float(sec)),
	},
	st.lists(st.sampled_from(ANIMALS), min_size=2, max_size=2, unique=True),
	st.sampled_from(DIRECTIONAL),
	st.floats(min_value=0, max_value=600, allow_nan=False),
)


# --- pairwise <-> activity consistency ---------------------------------------
@settings(max_examples=60, deadline=None)
@given(plan=cage_plans)
def test_pairwise_time_together_never_exceeds_either_occupancy(plan):
	"""Co-presence time of a pair in a cage can't exceed either animal's occupancy.

	Cross-table invariant between two steps reading the same padded_df: the time
	A and B are *together* in a cage is bounded by the time each of them spends
	there at all. minimum_time=None keeps every meeting so the bound is tight.
	"""
	assume(any(plan.values()))  # the fully-empty padded_df is a separate extreme
	padded = padded_from_plan(plan)

	activity = run(antenna_analysis.calculate_activity, lambda c, key: padded)
	pairwise = run(
		antenna_analysis.calculate_pairwise_meetings, lambda c, key: padded, minimum_time=None
	)

	# No nulls, non-negative, and pairs are stored unordered (a < b).
	assert (
		pairwise.select("time_together", "pairwise_encounters").null_count().sum_horizontal().item()
		== 0
	)
	assert (pairwise["time_together"] >= 0).all()
	assert (pairwise["pairwise_encounters"] >= 0).all()
	assert (pairwise["animal_id"].cast(pl.String) < pairwise["animal_id_2"].cast(pl.String)).all()

	occ = {
		(a, p): t
		for a, p, t in activity.group_by("animal_id", "position")
		.agg(pl.sum("time_in_position"))
		.iter_rows()
	}
	for r in pairwise.filter(pl.col("time_together") > 0).iter_rows(named=True):
		a, b, cage, tt = r["animal_id"], r["animal_id_2"], r["position"], r["time_together"]
		bound = min(occ.get((a, cage), 0.0), occ.get((b, cage), 0.0))
		assert tt <= bound + 1e-6, f"{a},{b}@{cage}: together {tt} > min-occupancy {bound}"


# --- chasings totals reconcile with the event table -------------------------
@settings(max_examples=60, deadline=None)
@given(events=st.lists(_match_event, min_size=0, max_size=12))
def test_chasings_grid_total_equals_event_count(events):
	"""Summing the per-hour chasings grid recovers exactly the number of events.

	calculate_chasings only aggregates and zero-fills onto the dense grid, so no
	event may be lost or invented, every cell is non-negative and null-free, and
	no animal chases itself.
	"""
	match_df = strat.match_df_frame(events, CFG)
	chasings = run(antenna_analysis.calculate_chasings, lambda c, key: match_df)

	assert chasings["chasings"].null_count() == 0
	assert (chasings["chasings"] >= 0).all()
	assert chasings.filter(pl.col("chaser") == pl.col("chased")).height == 0
	assert int(chasings["chasings"].sum()) == len(events)

	# Per-chaser totals reconcile with the raw winners.
	expected: dict[str, int] = {}
	for e in events:
		expected[e["winner"]] = expected.get(e["winner"], 0) + 1
	got = {
		a: int(n)
		for a, n in chasings.group_by("chaser")
		.agg(pl.sum("chasings"))
		.filter(pl.col("chasings") > 0)
		.iter_rows()
	}
	assert got == expected


# --- missing-animal contracts ------------------------------------------------
@settings(max_examples=40, deadline=None)
@given(events=st.lists(_match_event, min_size=1, max_size=12), absent=st.sampled_from(ANIMALS))
def test_absent_animal_ranking_stays_frozen(events, absent):
	"""An animal that is in no match keeps its starting rating for the whole run.

	The 'animal dies / never interacts' case: ranking emits a row per animal after
	every match, and an animal never named as winner or loser must show a single,
	unchanged mu/sigma across all of them (never dropped, never drifting).
	"""
	events = [e for e in events if absent not in (e["winner"], e["loser"])]
	assume(events)  # need at least one match to drive the ranking

	match_df = strat.match_df_frame(events, CFG)
	ranking = run(antenna_analysis.calculate_ranking, lambda c, key: match_df)

	rows = ranking.filter(pl.col("animal_id") == absent)
	assert rows.height == len(events)  # present in the trajectory after every match
	assert rows["mu"].n_unique() == 1
	assert rows["sigma"].n_unique() == 1
	assert rows["ordinal"].unique().to_list() == [0.0]  # default rating's ordinal


@settings(max_examples=40, deadline=None)
@given(plan=cage_plans, absent=st.sampled_from(ANIMALS))
def test_absent_animal_zero_filled_in_activity(plan, absent):
	"""An animal absent from padded_df still occupies every grid cell, all-zero.

	Locks the dense-grid contract for activity: a missing animal is present with
	zero occupancy / visits / solitary time, never silently dropped from the table.
	"""
	plan = {a: ([] if a == absent else stays) for a, stays in plan.items()}
	assume(any(plan.values()))
	padded = padded_from_plan(plan)

	activity = run(antenna_analysis.calculate_activity, lambda c, key: padded)

	rows = activity.filter(pl.col("animal_id") == absent)
	assert rows.height > 0
	assert rows["time_in_position"].sum() == 0
	assert rows["visits_to_position"].sum() == 0
	assert rows["time_alone"].sum() == 0
	# Every position still represented for the absent animal.
	assert set(rows["position"].cast(pl.String).unique()) == set(CFG["positions"])


# --- features stay finite for an animal with no interactions -----------------
def test_absent_animal_appears_in_features_with_finite_zscores(monkeypatch):
	"""A behaviourally-silent animal surfaces in features via the dense activity grid.

	C never chases, is never chased, wins/loses no tube tests and shares no cage
	time, but activity_df is dense (C present with zeros), so features must still
	list C for every metric with finite, non-null z-scores.
	"""
	PHASE = pl.Enum(["light_phase", "dark_phase"])
	AN = pl.Enum(ANIMALS)

	def base(n):
		return {
			"phase": pl.Series(["light_phase"] * n, dtype=PHASE),
			"day": pl.Series([1] * n, dtype=pl.UInt16),
			"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
		}

	chasings = pl.LazyFrame(
		{
			**base(1),
			"chaser": pl.Series(["A"], dtype=AN),
			"chased": pl.Series(["B"], dtype=AN),
			"chasings": pl.Series([1], dtype=pl.UInt32),
		}
	)
	tube = pl.LazyFrame(
		{
			**base(1),
			"winner": pl.Series(["A"], dtype=AN),
			"loser": pl.Series(["B"], dtype=AN),
			"tube_test": pl.Series([1], dtype=pl.UInt32),
		}
	)
	# activity is dense: all three animals present, C with zeros.
	activity = pl.LazyFrame(
		{
			**base(3),
			"animal_id": pl.Series(["A", "B", "C"], dtype=AN),
			"visits_to_position": pl.Series([10, 20, 0], dtype=pl.UInt32),
			"time_alone": pl.Series([1.0, 2.0, 0.0], dtype=pl.Float64),
		}
	)
	pairwise = pl.LazyFrame(
		{
			**base(1),
			"animal_id": pl.Series(["A"], dtype=AN),
			"animal_id_2": pl.Series(["B"], dtype=AN),
			"time_together": pl.Series([5.0], dtype=pl.Float64),
			"pairwise_encounters": pl.Series([1], dtype=pl.UInt32),
		}
	)
	tables = {
		"chasings_df": chasings,
		"tube_test_df": tube,
		"pairwise_meetings": pairwise,
		"activity_df": activity,
	}
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda c, key: tables[key])

	result = antenna_analysis.calculate_features.__wrapped__(CFG).collect()

	c_rows = result.filter(pl.col("animal_id") == "C")
	assert set(c_rows["metric"].unique()) == {
		"time_alone",
		"n_chasing",
		"n_chased",
		"n_wins",
		"n_loses",
		"activity",
		"time_together",
		"pairwise_encounters",
	}
	assert c_rows["z-score"].null_count() == 0
	assert all(math.isfinite(z) for z in c_rows["z-score"].to_list())
