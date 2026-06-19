"""Invariant property tests for the phase-grid builders in auxfun.py.

These functions are integration-ish (they synthesize whole-experiment grids), so
instead of a full oracle we assert structural invariants that must always hold.
"""

import datetime as dt

import strategies as strat
from hypothesis import given, settings
from hypothesis import strategies as st

from deepecohab.utils import auxfun


@settings(max_examples=150)
@given(
	start=strat.naive_datetimes.map(lambda d: d.replace(second=0, microsecond=0)),
	span_minutes=st.integers(min_value=30, max_value=5000),
	pcfg=strat.phase_configs,
)
def test_phase_durations_sum_and_positive_utc(start, span_minutes, pcfg):
	"""In UTC (no DST), every phase duration is positive and the durations sum to
	the experiment span within one minute of rounding slack.
	"""
	finish = start + dt.timedelta(minutes=span_minutes)
	cfg = {
		"experiment_timeline": {"start_date": start.isoformat(), "finish_date": finish.isoformat()},
		"timezone": "UTC",
		"phase": pcfg,
	}
	out = auxfun.get_phase_durations(cfg).collect()

	assert (out["duration_seconds"] > 0).all()
	assert abs(out["duration_seconds"].sum() - span_minutes * 60) <= 60


def test_phase_durations_positive_across_dst():
	"""A span crossing the Europe/Warsaw spring-forward still yields positive
	durations for every phase run.
	"""
	cfg = {
		"experiment_timeline": {
			"start_date": "2023-03-25 00:00:00",
			"finish_date": "2023-03-28 00:00:00",
		},
		"timezone": "Europe/Warsaw",
		"phase": {"light_phase": "07:00:00", "dark_phase": "20:00:00"},
	}
	out = auxfun.get_phase_durations(cfg).collect()
	assert out.height >= 1
	assert (out["duration_seconds"] > 0).all()
