"""Tests for the pure helpers in deepecohab.utils.auxfun_dashboard.

Only the framework-agnostic logic is covered (validation, string/option helpers,
filter-expression building). The Dash component builders (generate_*) are out of
scope. Importing auxfun_dashboard pulls in dash/plotly but NOT cache_config, so no
\\cache directory is created.
"""

import datetime as dt
import json

import plotly.graph_objects as go
import polars as pl
import pytest
import strategies as strat
from dash import exceptions
from hypothesis import given
from hypothesis import strategies as st

from deepecohab.utils import auxfun_dashboard as dash_helpers


# --- _is_valid_time ----------------------------------------------------------
@given(s=st.text(max_size=10))
def test_is_valid_time_matches_strptime(s):
	"""_is_valid_time agrees with strptime('%H:%M') for any string."""
	try:
		dt.datetime.strptime(s, "%H:%M")
		valid = True
	except (ValueError, TypeError):
		valid = False
	assert dash_helpers._is_valid_time(s) is valid


@given(t=st.times())
def test_is_valid_time_accepts_hm(t):
	assert dash_helpers._is_valid_time(t.strftime("%H:%M")) is True


@given(ts=strat.time_strings_hms)
def test_is_valid_time_rejects_seconds(ts):
	"""%H:%M:%S strings are rejected; only %H:%M is accepted."""
	assert dash_helpers._is_valid_time(ts) is False


def test_is_valid_time_none_is_false():
	assert dash_helpers._is_valid_time(None) is False


# --- _get_status -------------------------------------------------------------
@pytest.mark.parametrize("idx", ["proj-loc", "data-loc", "light-start", "dark-start", "other"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_get_status_blank_is_false(idx, blank):
	assert dash_helpers._get_status(idx, blank) is False


@given(t=st.times())
def test_get_status_time_inputs_delegate_to_is_valid_time(t):
	hm = t.strftime("%H:%M")
	assert dash_helpers._get_status("light-start", hm) is True
	assert dash_helpers._get_status("dark-start", hm) is True


def test_get_status_data_loc_requires_directory(tmp_path):
	assert dash_helpers._get_status("data-loc", str(tmp_path)) is True
	a_file = tmp_path / "x.txt"
	a_file.write_text("hi")
	assert dash_helpers._get_status("data-loc", str(a_file)) is False


def test_get_status_unknown_idx_passes_through():
	assert dash_helpers._get_status("whatever", "nonblank") is True


# --- get_display_name --------------------------------------------------------
@given(
	words=st.lists(st.from_regex(r"[a-z]+", fullmatch=True), min_size=1, max_size=5),
	sep=st.sampled_from(["-", "_"]),
)
def test_get_display_name_titlecases_and_joins(words, sep):
	out = dash_helpers.get_display_name(sep.join(words), sep)
	assert out == " ".join(w.capitalize() for w in words)
	assert sep not in out


# --- get_options_from_ids ----------------------------------------------------
@given(
	ids=st.lists(st.from_regex(r"[a-z][a-z_-]{0,8}", fullmatch=True), max_size=8, unique=True),
	delist=st.lists(st.from_regex(r"[a-z][a-z_-]{0,8}", fullmatch=True), max_size=4),
)
def test_get_options_from_ids(ids, delist):
	"""One option per id not in delist, order preserved, label is the display name."""
	out = dash_helpers.get_options_from_ids(ids, "-", delist)
	assert [o["value"] for o in out] == [i for i in ids if i not in delist]
	assert all(o["label"] == dash_helpers.get_display_name(o["value"], "-") for o in out)


# --- build_filter_expr -------------------------------------------------------
def test_build_filter_expr_none_when_not_applicable():
	assert (
		dash_helpers.build_filter_expr(["animal_id", "time_alone"], [1, 5], ["dark_phase"]) is None
	)
	assert dash_helpers.build_filter_expr(["day"], None, None) is None


def test_build_filter_expr_only_present_columns():
	assert len(dash_helpers.build_filter_expr(["day"], [1, 5], ["dark_phase"])) == 1
	assert len(dash_helpers.build_filter_expr(["phase"], [1, 5], ["dark_phase"])) == 1


@given(
	rows=st.lists(
		st.tuples(st.integers(1, 12), st.sampled_from(strat.PHASE_NAMES)),
		min_size=1,
		max_size=30,
	),
	bound_a=st.integers(1, 12),
	bound_b=st.integers(1, 12),
	phase_filter=st.lists(st.sampled_from(strat.PHASE_NAMES), unique=True),
)
def test_build_filter_expr_filters_match_oracle(rows, bound_a, bound_b, phase_filter):
	"""Applying the built expression filters day-in-range AND phase-in-set, the
	same as a direct polars filter.
	"""
	lo, hi = sorted((bound_a, bound_b))
	df = pl.DataFrame({"day": [r[0] for r in rows], "phase": [r[1] for r in rows]})
	expr = dash_helpers.build_filter_expr(df.columns, [lo, hi], phase_filter)

	out = df.filter(expr) if expr is not None else df
	expected = df.filter(pl.col("day").is_between(lo, hi), pl.col("phase").is_in(phase_filter))
	assert out.sort(["day", "phase"]).rows() == expected.sort(["day", "phase"]).rows()


# --- get_plot_file -----------------------------------------------------------
def test_get_plot_file_json_roundtrips():
	fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[4, 5, 6]))
	name, content = dash_helpers.get_plot_file(fig, "json", "myplot")
	assert name == "myplot.json"
	loaded = json.loads(content)
	assert "data" in loaded and "layout" in loaded


def test_get_plot_file_bad_fmt_raises_prevent_update():
	with pytest.raises(exceptions.PreventUpdate):
		dash_helpers.get_plot_file(go.Figure(), "csv", "x")
