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

The steps read their input via ``Recording.load_results``; instead of the ``monkeypatch``
fixture (which trips Hypothesis's function-scoped-fixture health check) we swap the
attribute directly and restore it, and call the step directly.
"""

import datetime as dt
import math

import polars as pl
import strategies as strat
from hypothesis import assume, given, settings, strategies as st

from deepecohab.core import antenna_analysis, transforms
from deepecohab.core.data_model import AnalysisParams, Recording

ANIMALS = ["A", "B", "C"]
RECORDING = strat.analysis_recording(animal_ids=ANIMALS)
CAGES = strat.ANALYSIS_CAGES
DIRECTIONAL = strat.ANALYSIS_DIRECTIONAL
BASE = strat.at(2023, 5, 24, 12, 0, 0)  # day-1 light_phase, hour 12


# --- input injection ---------------------------------------------------------
def run(fn, table_for_key, **kwargs) -> pl.DataFrame:
	"""Run ``fn``'s pure body with ``Recording.load_results`` swapped for ``table_for_key``.

	``table_for_key`` is a ``(recording, key) -> LazyFrame`` callable, restored afterwards.
	"""
	original = Recording.load_results
	Recording.load_results = lambda self, key, eager=False: table_for_key(self, key)
	try:
		return fn(RECORDING, AnalysisParams(**kwargs)).collect()
	finally:
		Recording.load_results = original


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
	return strat.padded_df_frame(rows, RECORDING)


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
	there at all. minimum_time=0 keeps every meeting so the bound is tight.
	"""
	assume(any(plan.values()))  # the fully-empty padded_df is a separate extreme
	padded = padded_from_plan(plan)

	activity = run(antenna_analysis.calculate_activity, lambda recording, key: padded)
	pairwise = run(
		antenna_analysis.calculate_pairwise_meetings, lambda recording, key: padded, minimum_time=0
	)

	# No nulls, non-negative, and pairs are stored unordered (a < b).
	assert (
		pairwise.select("time_together", "pairwise_encounters").null_count().sum_horizontal().item()
		== 0
	)
	assert (pairwise["time_together"] >= dt.timedelta(0)).all()
	assert (pairwise["pairwise_encounters"] >= 0).all()
	assert (pairwise["animal_id"].cast(pl.String) < pairwise["animal_id_2"].cast(pl.String)).all()

	occ = {
		(a, p): t
		for a, p, t in activity.group_by("animal_id", "position")
		.agg(pl.sum("time_in_position"))
		.iter_rows()
	}
	for r in pairwise.filter(pl.col("time_together") > dt.timedelta(0)).iter_rows(named=True):
		a, b, cage, tt = r["animal_id"], r["animal_id_2"], r["position"], r["time_together"]
		bound = min(occ.get((a, cage), dt.timedelta(0)), occ.get((b, cage), dt.timedelta(0)))
		assert tt <= bound + dt.timedelta(microseconds=1), (
			f"{a},{b}@{cage}: together {tt} > min-occupancy {bound}"
		)


# One cage stay that may span several minutes: (cage, gap-before, dwell). Dwells
# reach past a minute mark and start on a fractional second, so padding really
# splits them -- the exact scenario that used to inflate encounters.
_long_stay = st.tuples(
	st.sampled_from(CAGES),
	st.floats(min_value=0, max_value=30, allow_nan=False),
	st.floats(min_value=0.5, max_value=200, allow_nan=False),
)
long_cage_plans = st.fixed_dictionaries({a: st.lists(_long_stay, max_size=4) for a in ANIMALS})


def split_padded_from_plan(plan: dict[str, list[tuple]]) -> tuple[pl.LazyFrame, dict]:
	"""Lay each animal's stays end-to-end, then minute-split them via real padding.

	Returns the padded_df and the per-(animal, cage) visit counts taken straight from
	the plan (one stay == one visit), so a test can bound encounters by visit totals.
	"""
	rows = []
	visits: dict[tuple[str, str], int] = {}
	for animal, stays in plan.items():
		t = 0.5  # fractional second so pieces have fractional time_spent
		for cage, gap, dwell in stays:
			t += gap
			end = BASE + dt.timedelta(seconds=t + dwell)
			rows.append(
				{"animal_id": animal, "position": cage, "datetime": end, "time_spent": float(dwell)}
			)
			visits[(animal, cage)] = visits.get((animal, cage), 0) + 1
			t += dwell
	frame = pl.DataFrame(
		{
			"animal_id": pl.Series([r["animal_id"] for r in rows], dtype=pl.Enum(ANIMALS)),
			"position": pl.Series([r["position"] for r in rows], dtype=pl.Categorical),
			"datetime": pl.Series("datetime", [r["datetime"] for r in rows]),
			"time_spent": strat.seconds([r["time_spent"] for r in rows]),
			"time_under": pl.Series([dt.timedelta(0) for _ in rows], dtype=pl.Duration("us")),
		}
	)
	return transforms.split_on_minute_boundaries(frame.lazy(), RECORDING), visits


@settings(max_examples=60, deadline=None)
@given(plan=long_cage_plans)
def test_pairwise_encounters_never_exceed_visit_sum(plan):
	"""A pair can't meet in a cage more often than their combined visits to it.

	The user's invariant. Stays span minute marks so padded_df splits them into many
	pieces; the sweep must re-stitch those pieces per visit rather than count each
	piece as a fresh encounter (the bug that pushed encounters above the visit sum).
	minimum_time=0 keeps every meeting, making the bound tightest.
	"""
	assume(any(plan.values()))
	padded, visits = split_padded_from_plan(plan)
	pairwise = run(
		antenna_analysis.calculate_pairwise_meetings, lambda recording, key: padded, minimum_time=0
	)

	for r in pairwise.filter(pl.col("pairwise_encounters") > 0).iter_rows(named=True):
		a, b, cage, enc = r["animal_id"], r["animal_id_2"], r["position"], r["pairwise_encounters"]
		bound = visits.get((a, cage), 0) + visits.get((b, cage), 0)
		assert enc <= bound, f"{a},{b}@{cage}: {enc} encounters > {bound} combined visits"


# --- chasings totals reconcile with the event table -------------------------
@settings(max_examples=60, deadline=None)
@given(events=st.lists(_match_event, min_size=0, max_size=12))
def test_chasings_grid_total_equals_event_count(events):
	"""Summing the per-hour chasings grid recovers exactly the number of events.

	calculate_chasings only aggregates and zero-fills onto the dense grid, so no
	event may be lost or invented, every cell is non-negative and null-free, and
	no animal chases itself.
	"""
	match_df = strat.match_df_frame(events, RECORDING)
	chasings = run(antenna_analysis.calculate_chasings, lambda recording, key: match_df)

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

	match_df = strat.match_df_frame(events, RECORDING)
	ranking = run(antenna_analysis.calculate_ranking, lambda recording, key: match_df)

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

	activity = run(antenna_analysis.calculate_activity, lambda recording, key: padded)

	rows = activity.filter(pl.col("animal_id") == absent)
	assert rows.height > 0
	assert rows["time_in_position"].sum() == dt.timedelta(0)
	assert rows["visits_to_position"].sum() == 0
	assert rows["time_alone"].sum() == dt.timedelta(0)
	# Every position still represented for the absent animal.
	assert set(rows["position"].cast(pl.String).unique()) == set(
		RECORDING.layout.positions_non_directional
	)


# --- features stay finite for an animal with no interactions -----------------
def test_absent_animal_appears_in_features_with_finite_values(monkeypatch):
	"""A behaviourally-silent animal surfaces in features via the dense activity grid.

	C never chases, is never chased and shares no cage time, but activity_df is dense
	(C present with zeros), so features must still list C for every metric with
	finite, non-null value and exposure.
	"""
	PHASE = pl.Enum(["light_phase", "dark_phase"])
	AN = pl.Enum(ANIMALS)

	def base(n):
		return {
			"phase": pl.Series(["light_phase"] * n, dtype=PHASE),
			"day": pl.Series([1] * n, dtype=pl.UInt16),
			"phase_count": pl.Series([1] * n, dtype=pl.UInt16),
			"hour": pl.Series([12] * n, dtype=pl.UInt8),
		}

	chasings = pl.LazyFrame(
		{
			**base(1),
			"chaser": pl.Series(["A"], dtype=AN),
			"chased": pl.Series(["B"], dtype=AN),
			"chasings": pl.Series([1], dtype=pl.UInt32),
		}
	)
	# activity is dense: all three animals present, C with zeros.
	activity = pl.LazyFrame(
		{
			**base(3),
			"animal_id": pl.Series(["A", "B", "C"], dtype=AN),
			"visits_to_position": pl.Series([10, 20, 0], dtype=pl.UInt32),
			"time_alone": strat.seconds([1.0, 2.0, 0.0]),
			"time_in_position": strat.seconds([3600.0, 3600.0, 0.0]),
		}
	)
	pairwise = pl.LazyFrame(
		{
			**base(1),
			# A cage: pairwise_meetings covers tunnels, but features counts cage time only.
			"position": pl.Series(["cage_1"], dtype=pl.Categorical),
			"animal_id": pl.Series(["A"], dtype=AN),
			"animal_id_2": pl.Series(["B"], dtype=AN),
			"time_together": strat.seconds([5.0]),
			"pairwise_encounters": pl.Series([1], dtype=pl.UInt32),
		}
	)
	# One row per antenna registration: A seen 5 times, B 3, C never.
	main = pl.LazyFrame({**base(8), "animal_id": pl.Series(["A"] * 5 + ["B"] * 3, dtype=AN)})
	tables = {
		"chasings_df": chasings,
		"pairwise_meetings": pairwise,
		"activity_df": activity,
		"main_df": main,
	}
	monkeypatch.setattr(Recording, "load_results", lambda self, key, eager=False: tables[key])

	result = antenna_analysis.calculate_features(RECORDING, AnalysisParams()).collect()

	c_rows = result.filter(pl.col("animal_id") == "C")
	assert set(c_rows["metric"].unique()) == {
		"time_alone",
		"n_chasing",
		"n_chased",
		"activity",
		"time_together",
		"pairwise_encounters",
		"n_chasing_per_detection",
	}
	for column in ("value", "exposure"):
		assert c_rows[column].null_count() == 0
		assert all(math.isfinite(v) for v in c_rows[column].to_list())

	# A chased once over 5 detections; the rate is sum(value) / sum(exposure).
	per_detection = result.filter(
		pl.col("animal_id") == "A", pl.col("metric") == "n_chasing_per_detection"
	)
	assert per_detection["value"].sum() == 1.0
	assert per_detection["exposure"].sum() == 5.0
