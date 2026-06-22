import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest
import strategies as strat
from hypothesis import given, settings
from hypothesis import strategies as st

from deepecohab.core.create_data_structure import calculate_time_spent
from deepecohab.utils import auxfun

TZ_NAME = "Europe/Warsaw"
TZ = ZoneInfo(TZ_NAME)

CFG = {"phase": {"light_phase": "07:00:00", "dark_phase": "20:00:00"}}


def aware_dt_series(values: list[dt.datetime]) -> pl.Series:
	"""Build a zone-aware Datetime series in the project timezone."""
	return pl.Series("datetime", values).dt.replace_time_zone(TZ_NAME)


def at(*args: int) -> dt.datetime:
	return dt.datetime(*args, tzinfo=TZ)


@pytest.mark.parametrize(
	"hour,minute,expected",
	[
		(0, 0, "dark_phase"),  # midnight -> dark (wraps)
		(6, 59, "dark_phase"),  # just before light starts
		(7, 0, "light_phase"),  # boundary inclusive: light begins
		(12, 0, "light_phase"),  # mid-light
		(19, 59, "light_phase"),  # just before dark starts
		(20, 0, "dark_phase"),  # boundary inclusive: dark begins
		(23, 59, "dark_phase"),  # late night
	],
)
def test_phase_assignment_by_time_of_day(hour, minute, expected):
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 6, 15, hour, minute, 0)])})
	out = df.with_columns(auxfun.get_phase(CFG))
	assert out["phase"][0] == expected


def test_phase_is_enum_with_config_order():
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 6, 15, 12, 0, 0)])})
	out = df.with_columns(auxfun.get_phase(CFG))
	dtype = out.schema["phase"]
	assert isinstance(dtype, pl.Enum)
	# Categories follow config key order, not sorted-by-time order.
	assert dtype.categories.to_list() == ["light_phase", "dark_phase"]


def test_phase_three_phases_tile_day():
	"""Generalizes beyond two phases: morning/day/night tile the 24h clock."""
	cfg = {
		"phase": {
			"morning": "06:00:00",
			"day": "12:00:00",
			"night": "22:00:00",
		}
	}
	times = [
		(5, "night"),  # before first boundary -> wraps to last phase
		(6, "morning"),
		(11, "morning"),
		(12, "day"),
		(21, "day"),
		(22, "night"),
		(23, "night"),
	]
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 6, 15, h, 0, 0) for h, _ in times])})
	out = df.with_columns(auxfun.get_phase(cfg))
	assert out["phase"].to_list() == [name for _, name in times]


def test_phase_dst_spring_forward():
	"""Spring forward: in Europe/Warsaw, 2023-03-26 02:00 -> 03:00 (CET->CEST).
	The DST correction anchors to the first row's offset so that a fixed
	wall-clock time keeps the same phase across the transition.
	Rows before and after the jump that share a wall-clock hour should agree.
	"""
	before = at(2023, 3, 26, 1, 30, 0)  # 01:30 CET, before jump
	after = at(2023, 3, 26, 12, 0, 0)  # 12:00 CEST, after jump
	df = pl.DataFrame({"datetime": aware_dt_series([before, after])})
	out = df.with_columns(auxfun.get_phase(CFG))
	# 01:30 -> dark, 12:00 -> light. Sanity: transition does not misclassify noon.
	assert out["phase"].to_list() == ["dark_phase", "light_phase"]


def test_phase_dst_fall_back():
	"""Fall back: 2023-10-29 03:00 -> 02:00 (CEST->CET); the 02:00-03:00 hour
	repeats. Phase should still be derived from wall-clock time, not the raw
	UTC instant, for rows on either side of the transition.
	"""
	early = at(2023, 10, 29, 1, 0, 0)  # 01:00 CEST
	noon = at(2023, 10, 29, 12, 0, 0)  # 12:00 CET
	df = pl.DataFrame({"datetime": aware_dt_series([early, noon])})
	out = df.with_columns(auxfun.get_phase(CFG))
	assert out["phase"].to_list() == ["dark_phase", "light_phase"]


def test_phase_count_simple_alternation():
	"""Each contiguous run of a phase gets the next number for that phase."""
	phases = ["light_phase", "light_phase", "dark_phase", "light_phase", "dark_phase"]
	lf = pl.LazyFrame({"phase": pl.Series(phases, dtype=pl.Enum(["light_phase", "dark_phase"]))})
	out = auxfun.get_phase_count(lf).collect()
	# runs: light#1 (rows 0-1), dark#1 (row2), light#2 (row3), dark#2 (row4)
	assert out["phase_count"].to_list() == [1, 1, 1, 2, 2]


def test_phase_count_single_run():
	phases = ["light_phase"] * 4
	lf = pl.LazyFrame({"phase": pl.Series(phases, dtype=pl.Enum(["light_phase", "dark_phase"]))})
	out = auxfun.get_phase_count(lf).collect()
	assert out["phase_count"].to_list() == [1, 1, 1, 1]


def test_phase_count_full_experiment_sequence():
	"""A long L/D/L/D... sequence numbers each phase 1,1,2,2,3,3,..."""
	units = ["light_phase", "dark_phase"] * 3  # 3 full days
	# expand each into a run of 2 rows to mimic multiple events per phase
	phases = [p for p in units for _ in range(2)]
	lf = pl.LazyFrame({"phase": pl.Series(phases, dtype=pl.Enum(["light_phase", "dark_phase"]))})
	out = auxfun.get_phase_count(lf).collect()
	assert out["phase_count"].to_list() == [
		1,
		1,  # light #1
		1,
		1,  # dark #1
		2,
		2,  # light #2
		2,
		2,  # dark #2
		3,
		3,  # light #3
		3,
		3,  # dark #3
	]


def test_phase_count_dtype_is_u16():
	phases = ["light_phase", "dark_phase"]
	lf = pl.LazyFrame({"phase": pl.Series(phases, dtype=pl.Enum(["light_phase", "dark_phase"]))})
	out = auxfun.get_phase_count(lf).collect()
	assert out.schema["phase_count"] == pl.UInt16
	assert "run_id" not in out.columns


GRID_CFG = {
	**CFG,
	"timezone": TZ_NAME,
	"experiment_timeline": {
		"start_date": "2023-05-24 00:00:00",
		"finish_date": "2023-05-26 23:00:00",
	},
}


def test_grid_phase_count_matches_build_time_grid():
	"""get_grid_phase_count reproduces build_time_grid's numbering by construction.

	The dark phase wraps midnight, so an evening (hours 20-23) and the following
	morning (hours 0-6) share one occurrence. Looking phase_count up from the grid
	keeps the two halves consistent, unlike run-length-encoding rows by calendar day.
	"""
	grid = auxfun.build_time_grid(GRID_CFG).collect()
	expected = {(r["day"], r["phase"], r["hour"]): r["phase_count"] for r in grid.to_dicts()}

	# A sparse subset of the grid's (day, phase, hour) keys, deliberately including
	# evening dark hours (the case the old rle-by-(day,phase) sort mis-numbered).
	probe = grid.select("day", "phase", "hour").sample(fraction=0.5, seed=0, shuffle=True)
	out = auxfun.get_grid_phase_count(probe.lazy(), GRID_CFG).collect()

	assert out.schema["phase_count"] == pl.UInt16
	for row in out.to_dicts():
		assert row["phase_count"] == expected[(row["day"], row["phase"], row["hour"])]


def test_grid_phase_count_evening_dark_shares_count_with_next_morning():
	"""The wrap-around night links day N evening with day N+1 morning under one count."""
	grid = auxfun.build_time_grid(GRID_CFG).collect()
	dark = grid.filter(pl.col("phase") == "dark_phase")

	day1_evening = dark.filter((pl.col("day") == 1) & (pl.col("hour") == 22))["phase_count"][0]
	day2_morning = dark.filter((pl.col("day") == 2) & (pl.col("hour") == 2))["phase_count"][0]
	assert day1_evening == day2_morning


def test_day_single_date_is_one():
	df = pl.DataFrame(
		{"datetime": aware_dt_series([at(2023, 5, 24, h, 0, 0) for h in (0, 12, 23)])}
	)
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == [1, 1, 1]


def test_day_consecutive_dates():
	df = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[at(2023, 5, 24, 12, 0, 0), at(2023, 5, 25, 12, 0, 0), at(2023, 5, 26, 1, 0, 0)]
			)
		}
	)
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == [1, 2, 3]


def test_day_missing_day_leaves_gap():
	"""A whole missing day produces a gap in numbering, not renumbering.

	Dates 24th and 26th (25th absent) -> day 1 and day 3, never 1 and 2.
	"""
	df = pl.DataFrame(
		{"datetime": aware_dt_series([at(2023, 5, 24, 12, 0, 0), at(2023, 5, 26, 12, 0, 0)])}
	)
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == [1, 3]


def test_day_offset_anchored_to_min_not_first_row():
	"""Day is relative to the earliest date present, regardless of row order."""
	df = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[at(2023, 5, 26, 12, 0, 0), at(2023, 5, 24, 12, 0, 0)]  # out of order
			)
		}
	)
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == [3, 1]


def test_day_dtype_is_u16():
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 5, 24, 12, 0, 0)])})
	out = df.with_columns(auxfun.get_day())
	assert out.schema["day"] == pl.UInt16


def test_day_across_dst_boundary_counts_calendar_days():
	"""Day numbering is by calendar date, unaffected by the 23h DST day."""
	df = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[
					at(2023, 3, 25, 12, 0, 0),  # day before spring-forward
					at(2023, 3, 26, 12, 0, 0),  # the 23h day
					at(2023, 3, 27, 12, 0, 0),  # day after
				]
			)
		}
	)
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == [1, 2, 3]


# --- property-based tests ----------------------------------------------------
# The examples above pin specific documented semantics (boundary inclusivity,
# DST anchoring, gaps). These check the same functions against an independent
# Python oracle over the whole input space; see tests/strategies.py.


@settings(max_examples=300)
@given(naive=strat.naive_datetimes, tz=strat.timezones, pcfg=strat.phase_configs)
def test_phase_matches_reference_oracle(naive, tz, pcfg):
	"""For any instant, timezone and phase layout, get_phase agrees with the
	pure-Python mapping based on the local wall-clock time of day.
	"""
	df = pl.DataFrame({"datetime": strat.aware([naive], tz)})
	local_time = df["datetime"].dt.time()[0]  # single row -> dst_shift is zero
	out = df.with_columns(auxfun.get_phase({"phase": pcfg}))
	assert out["phase"][0] == strat.expected_phase(local_time, pcfg)


@settings(max_examples=300)
@given(labels=strat.phase_label_lists)
def test_phase_count_matches_reference_oracle(labels):
	"""phase_count equals the ordinal of each contiguous run within its phase,
	for any sequence of phase labels, and stays UInt16.
	"""
	lf = pl.LazyFrame({"phase": pl.Series(labels, dtype=pl.Enum(strat.PHASE_NAMES))})
	out = auxfun.get_phase_count(lf).collect()
	assert out["phase_count"].to_list() == strat.expected_phase_count(labels)
	assert out.schema["phase_count"] == pl.UInt16
	assert "run_id" not in out.columns


@settings(max_examples=200)
@given(naives=st.lists(strat.naive_datetimes, min_size=1, max_size=30), tz=strat.timezones)
def test_day_matches_reference_oracle(naives, tz):
	"""Day is the 1-indexed calendar offset from the earliest date present,
	regardless of order, gaps, timezone or DST, and stays UInt16.
	"""
	df = pl.DataFrame({"datetime": strat.aware(naives, tz)})
	dates = df["datetime"].dt.date().to_list()
	out = df.with_columns(auxfun.get_day())
	assert out["day"].to_list() == strat.expected_day(dates)
	assert out.schema["day"] == pl.UInt16


# --- property-based tests for the remaining pure transforms ------------------


@settings(max_examples=200)
@given(naives=st.lists(strat.naive_datetimes, min_size=1, max_size=20), tz=strat.timezones)
def test_hour_matches_reference_oracle(naives, tz):
	"""get_hour == the local wall-clock hour for any instant/timezone, dtype UInt8."""
	df = pl.DataFrame({"datetime": strat.aware(naives, tz)})
	out = df.with_columns(auxfun.get_hour())
	assert out["hour"].to_list() == strat.expected_hour(df["datetime"].to_list())
	assert out.schema["hour"] == pl.UInt8


@settings(max_examples=200)
@given(
	rows=st.lists(
		st.fixed_dictionaries(
			{"animal_id": st.sampled_from(strat.ANIMALS), "end": strat.whole_second_datetimes}
		),
		min_size=1,
		max_size=25,
	),
	tz=strat.timezones,
)
def test_time_spent_matches_reference_oracle(rows, tz):
	"""time_spent is the per-animal consecutive gap in seconds, in row order
	(the function does NOT sort); the first row of each animal is 0.
	"""
	out = calculate_time_spent(strat.grouped_event_frame(rows, tz)).collect()
	# The naive ends are the UTC instants the column differences, so they are the
	# right oracle input regardless of the display timezone (avoids DST round-trip).
	expected = strat.expected_time_spent([r["animal_id"] for r in rows], [r["end"] for r in rows])
	assert out["time_spent"].to_list() == expected


@given(
	animals=strat.animal_id_lists,
	positions=st.lists(st.sampled_from(strat.CAGES), min_size=0, max_size=4, unique=True),
)
def test_build_animal_grid_single_is_full_product(animals, positions):
	"""A single-animal grid is the full animal x position cartesian product."""
	cfg = {"animal_ids": animals}
	out = auxfun.build_animal_grid(cfg, "animal_id", positions=positions).collect()
	assert set(out.columns) == {"animal_id", "position"}
	assert out.height == len(animals) * len(positions)
	if animals and positions:
		assert set(out.select("animal_id", "position").iter_rows()) == {
			(a, p) for a in animals for p in positions
		}


@given(animals=strat.animal_id_lists)
def test_build_animal_grid_pairs(animals):
	"""Ordered pair grids enumerate a != b both ways; unordered enumerate a < b once."""
	cfg = {"animal_ids": animals}
	n = len(animals)

	ordered = auxfun.build_animal_grid(cfg, ("winner", "loser"), ordered=True).collect()
	assert ordered.columns == ["winner", "loser"]
	assert ordered.height == n * (n - 1)
	assert (ordered["winner"] == ordered["loser"]).sum() == 0

	unordered = auxfun.build_animal_grid(cfg, ("animal_id", "animal_id_2"), ordered=False).collect()
	assert unordered.height == n * (n - 1) // 2


def test_build_animal_grid_rejects_bad_columns():
	"""A non-pair tuple of column names is rejected."""
	import pytest

	with pytest.raises(ValueError):
		auxfun.build_animal_grid({"animal_ids": ["A", "B"]}, ("a", "b", "c"))


@given(
	positions=st.lists(
		st.sampled_from(strat.CAGES + strat.DIRECTIONAL_TUNNELS + ["undefined"]),
		min_size=1,
		max_size=20,
	),
	tunnels=strat.tunnels_maps,
)
def test_remove_tunnel_directionality_maps_only_tunnels(positions, tunnels):
	"""Directional tunnels are replaced by their undirected name; everything else
	(cages, undefined) passes through; the column stays Categorical.
	"""
	lf = pl.LazyFrame({"position": pl.Series(positions, dtype=pl.Categorical)})
	out = auxfun.remove_tunnel_directionality(lf, {"tunnels": tunnels}).collect()
	assert out["position"].to_list() == [tunnels.get(p, p) for p in positions]
	assert out.schema["position"] == pl.Categorical
