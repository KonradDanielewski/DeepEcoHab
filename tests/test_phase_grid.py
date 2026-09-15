"""Invariant property tests for the phase-grid builders in grids.py.

These functions are integration-ish (they synthesize whole-experiment grids), so
instead of a full oracle we assert structural invariants that must always hold.
"""

import datetime as dt

import strategies as strat
from hypothesis import given, settings, strategies as st

from deepecohab.core import recording_pipeline
from deepecohab.core.data_model import AnalysisParams


@settings(max_examples=150)
@given(
	start=strat.naive_datetimes.map(lambda d: d.replace(second=0, microsecond=0)),
	# Over 24h, so the start_from onset is always reached whatever the phase config.
	span_minutes=st.integers(min_value=1500, max_value=5000),
	pcfg=strat.phase_configs,
)
def test_phase_durations_sum_and_positive_utc(start, span_minutes, pcfg):
	"""In UTC (no DST), every phase duration is positive and the durations sum to
	the analysed span within one minute of rounding slack.

	The analysed span runs from the experiment start, not from acquisition, so the
	lead-in before the first start_from onset is not part of the total.
	"""
	finish = start + dt.timedelta(minutes=span_minutes)
	recording = strat.analysis_recording(
		tz="UTC", start=start.isoformat(), finish=finish.isoformat(), phases=pcfg
	)
	out = recording_pipeline.build_phase_durations(recording, AnalysisParams()).collect()
	analysed_start, analysed_end = recording.timeline.local_span

	assert (out["duration"] > dt.timedelta(0)).all()
	assert abs(out["duration"].sum() - (analysed_end - analysed_start)) <= dt.timedelta(minutes=1)


def test_phase_durations_positive_across_dst():
	"""A span crossing the Europe/Warsaw spring-forward still yields positive
	durations for every phase run.
	"""
	recording = strat.analysis_recording(
		tz="Europe/Warsaw",
		start="2023-03-25 00:00:00",
		finish="2023-03-28 00:00:00",
	)
	out = recording_pipeline.build_phase_durations(recording, AnalysisParams()).collect()
	assert out.height >= 1
	assert (out["duration"] > dt.timedelta(0)).all()
