import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest
import strategies as strat
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from deepecohab.core import grids, transforms
from deepecohab.core.data_model import Timeline
from deepecohab.core.transforms import calculate_time_spent

TZ_NAME = "Europe/Warsaw"
TZ = ZoneInfo(TZ_NAME)

# Default phases put the light onset at midnight, so the origin is the recording start
# and day/hour come out equal to calendar day and wall-clock hour.
RECORDING = strat.analysis_recording(
	tz=TZ_NAME, start="2023-05-24 00:00:00", finish="2023-05-26 23:00:00"
)

# Onsets that make the dark phase wrap midnight, which the phase-mapping and grid tests
# below are written against. The experiment then starts at the 07:00 light onset.
WRAP_PHASES = {"light_phase": dt.time(7, 0), "dark_phase": dt.time(20, 0)}
WRAP_RECORDING = strat.analysis_recording(
	tz=TZ_NAME, start="2023-05-24 00:00:00", finish="2023-05-26 23:00:00", phases=WRAP_PHASES
)


def aware_dt_series(values: list[dt.datetime]) -> pl.Series:
	"""Build a Datetime series in the project timezone from zone-aware datetimes."""
	return pl.Series("datetime", values, dtype=pl.Datetime("us", TZ_NAME))


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
	out = df.with_columns(grids.get_phase(WRAP_RECORDING))
	assert out["phase"][0] == expected


def test_phase_is_enum_with_config_order():
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 6, 15, 12, 0, 0)])})
	out = df.with_columns(grids.get_phase(WRAP_RECORDING))
	dtype = out.schema["phase"]
	assert isinstance(dtype, pl.Enum)
	# Categories follow config key order, not sorted-by-time order.
	assert dtype.categories.to_list() == ["light_phase", "dark_phase"]


def test_phase_names_are_constrained_to_light_and_dark():
	"""The model names exactly two phases, so a third is rejected at validation."""
	with pytest.raises(ValidationError):
		Timeline(
			start_datetime=at(2023, 6, 15, 0, 0, 0),
			end_datetime=at(2023, 6, 16, 0, 0, 0),
			recording_timezone=TZ,
			phases={"morning": dt.time(6), "day": dt.time(12), "night": dt.time(22)},
			start_from="light_phase",
		)


def test_phase_dst_spring_forward():
	"""Spring forward: in Europe/Warsaw, 2023-03-26 02:00 -> 03:00 (CET->CEST).
	The DST correction anchors to the experiment start's offset so that a fixed
	wall-clock time keeps the same phase across the transition.
	Rows before and after the jump that share a wall-clock hour should agree.
	"""
	before = at(2023, 3, 26, 1, 30, 0)  # 01:30 CET, before jump
	after = at(2023, 3, 26, 12, 0, 0)  # 12:00 CEST, after jump
	df = pl.DataFrame({"datetime": aware_dt_series([before, after])})
	out = df.with_columns(grids.get_phase(WRAP_RECORDING))
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
	out = df.with_columns(grids.get_phase(WRAP_RECORDING))
	assert out["phase"].to_list() == ["dark_phase", "light_phase"]


GRID_RECORDING = WRAP_RECORDING


def test_grid_phase_count_matches_build_time_grid():
	"""get_grid_phase_count reproduces build_time_grid's numbering by construction.

	The dark phase wraps midnight, so an evening (hours 20-23) and the following
	morning (hours 0-6) share one occurrence. Looking phase_count up from the grid
	keeps the two halves consistent, unlike run-length-encoding rows by calendar day.
	"""
	grid = grids.build_time_grid(GRID_RECORDING).collect()
	expected = {(r["day"], r["phase"], r["hour"]): r["phase_count"] for r in grid.to_dicts()}

	# A sparse subset of the grid's (day, phase, hour) keys, deliberately including
	# evening dark hours (the case the old rle-by-(day,phase) sort mis-numbered).
	probe = grid.select("day", "phase", "hour").sample(fraction=0.5, seed=0, shuffle=True)
	out = grids.assign_phase_count(probe.lazy(), GRID_RECORDING).collect()

	assert out.schema["phase_count"] == pl.UInt16
	for row in out.to_dicts():
		assert row["phase_count"] == expected[(row["day"], row["phase"], row["hour"])]


def test_phase_never_straddles_an_experiment_day():
	"""Anchoring day 1 on a phase onset puts every phase occurrence inside one day.

	The dark phase wraps midnight here, which used to split one occurrence across two
	calendar days and was the case grid-based numbering had to reconcile. Counting days
	from the light onset removes it: every experiment day opens on a start_from onset,
	so both phases of the cycle fall inside it.
	"""
	grid = grids.build_time_grid(GRID_RECORDING).collect()
	spread = grid.group_by("phase_count").agg(pl.col("day").n_unique().alias("days"))

	assert spread["days"].max() == 1
	# Day 1 is complete, so it holds exactly one light and one dark occurrence.
	assert grid.filter(pl.col("day") == 1)["phase_count"].n_unique() == 2


def test_day_single_date_is_one():
	df = pl.DataFrame(
		{"datetime": aware_dt_series([at(2023, 5, 24, h, 0, 0) for h in (0, 12, 23)])}
	)
	out = df.with_columns(grids.get_day(RECORDING))
	assert out["day"].to_list() == [1, 1, 1]


def test_day_consecutive_dates():
	df = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[at(2023, 5, 24, 12, 0, 0), at(2023, 5, 25, 12, 0, 0), at(2023, 5, 26, 1, 0, 0)]
			)
		}
	)
	out = df.with_columns(grids.get_day(RECORDING))
	assert out["day"].to_list() == [1, 2, 3]


def test_day_missing_day_leaves_gap():
	"""A whole missing day produces a gap in numbering, not renumbering.

	Dates 24th and 26th (25th absent) -> day 1 and day 3, never 1 and 2.
	"""
	df = pl.DataFrame(
		{"datetime": aware_dt_series([at(2023, 5, 24, 12, 0, 0), at(2023, 5, 26, 12, 0, 0)])}
	)
	out = df.with_columns(grids.get_day(RECORDING))
	assert out["day"].to_list() == [1, 3]


def test_day_anchored_to_experiment_start_not_to_the_frame():
	"""Day counts from the recording's origin, so a frame missing day 1 still numbers right.

	This is the regression: numbering from the frame's own earliest date made a sparse
	table - match_df, say - call its first row day 1 whenever day 1 held no events.
	"""
	sparse = pl.DataFrame({"datetime": aware_dt_series([at(2023, 5, 26, 12, 0, 0)])})
	assert sparse.with_columns(grids.get_day(RECORDING))["day"].to_list() == [3]

	out_of_order = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[at(2023, 5, 26, 12, 0, 0), at(2023, 5, 24, 12, 0, 0)]  # out of order
			)
		}
	)
	assert out_of_order.with_columns(grids.get_day(RECORDING))["day"].to_list() == [3, 1]


def test_day_dtype_is_u16():
	df = pl.DataFrame({"datetime": aware_dt_series([at(2023, 5, 24, 12, 0, 0)])})
	out = df.with_columns(grids.get_day(RECORDING))
	assert out.schema["day"] == pl.UInt16


def test_day_across_dst_boundary_is_24_elapsed_hours():
	"""An experiment day is 24 elapsed hours, which the 23h calendar day shifts.

	The origin is midnight on the 25th, so day 2 opens at midnight on the 26th. The
	spring-forward makes that calendar day only 23 hours long, so day 3 opens at 01:00
	on the 27th rather than at midnight - and 00:30 that morning is still day 2.
	"""
	recording = strat.analysis_recording(
		tz=TZ_NAME, start="2023-03-25 00:00:00", finish="2023-03-28 00:00:00"
	)
	df = pl.DataFrame(
		{
			"datetime": aware_dt_series(
				[
					at(2023, 3, 25, 12, 0, 0),  # day before spring-forward
					at(2023, 3, 26, 12, 0, 0),  # the 23h calendar day
					at(2023, 3, 27, 0, 30, 0),  # still day 2: the boundary moved to 01:00
					at(2023, 3, 27, 12, 0, 0),  # day after
				]
			)
		}
	)
	out = df.with_columns(grids.get_day(recording))
	assert out["day"].to_list() == [1, 2, 2, 3]


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
	# Spans the drawn range, so every instant sits at or after the experiment start.
	recording = strat.analysis_recording(
		tz=tz, start="2022-12-30 00:00:00", finish="2023-12-31 23:00:00", phases=pcfg
	)
	local_time = strat.expected_time_of_day(df["datetime"][0], recording.timeline.experiment_start)
	out = df.with_columns(grids.get_phase(recording))
	assert out["phase"][0] == strat.expected_phase(local_time, pcfg)


def test_phase_count_matches_reference_oracle():
	"""The grid numbers each contiguous phase run with the next global ordinal."""
	grid = grids.build_time_grid(GRID_RECORDING).collect()
	assert grid["phase_count"].to_list() == strat.expected_phase_count(grid["phase"].to_list())
	assert grid.schema["phase_count"] == pl.UInt16


@settings(max_examples=200)
@given(naives=st.lists(strat.naive_datetimes, min_size=1, max_size=30), tz=strat.timezones)
def test_day_matches_reference_oracle(naives, tz):
	"""Day is the 1-indexed 24h block of elapsed time from the experiment start,
	regardless of order, gaps, timezone or DST, and stays UInt16.
	"""
	df = pl.DataFrame({"datetime": strat.aware(naives, tz)})
	recording = strat.analysis_recording(
		tz=tz, start="2022-12-30 00:00:00", finish="2023-12-31 23:00:00"
	)
	origin = recording.timeline.experiment_start

	out = df.with_columns(grids.get_day(recording))
	assert out["day"].to_list() == strat.expected_day(df["datetime"].to_list(), origin)
	assert out.schema["day"] == pl.UInt16


# --- property-based tests for the remaining pure transforms ------------------


@settings(max_examples=200)
@given(naives=st.lists(strat.naive_datetimes, min_size=1, max_size=20), tz=strat.timezones)
def test_hour_matches_reference_oracle(naives, tz):
	"""get_hour == the hour within the elapsed day from the experiment start, dtype UInt8."""
	df = pl.DataFrame({"datetime": strat.aware(naives, tz)})
	recording = strat.analysis_recording(
		tz=tz, start="2022-12-30 00:00:00", finish="2023-12-31 23:00:00"
	)
	origin = recording.timeline.experiment_start

	out = df.with_columns(grids.get_hour(recording))
	assert out["hour"].to_list() == strat.expected_hour(df["datetime"].to_list(), origin)
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


def test_time_spent_is_not_rounded():
	"""time_spent keeps full microsecond precision (regression: it was rounded to 10ms).

	The occupancy interval start is reconstructed as ``datetime - time_spent`` by the
	pairwise / time-alone sweeps; rounding time_spent here would shift that start off
	the true entry time and fragment continuous stays into spurious extra meetings.
	"""
	# A 1.234567 s gap: rounding to 2 decimals (the old behaviour) would report 1.23.
	frame = pl.LazyFrame(
		{
			"animal_id": pl.Series(["A", "A"], dtype=pl.Enum(["A"])),
			"datetime": aware_dt_series(
				[at(2023, 6, 15, 12, 0, 0), at(2023, 6, 15, 12, 0, 1, 234_567)]
			),
		}
	)
	out = calculate_time_spent(frame).collect()
	assert out["time_spent"].to_list() == [dt.timedelta(0), dt.timedelta(seconds=1.234567)]


def test_add_occupancy_bounds_reconstructs_exact_start():
	"""``start`` is ``datetime - time_spent`` reconstructed to the exact microsecond.

	Regression guard: reconstructing via ``pl.duration(seconds=time_spent)`` rounds the
	boundary through a float and can land 1 us off (e.g. for 2087.043558 s), which
	accumulates into extra pairwise encounters. add_occupancy_bounds must build the
	duration from whole microseconds so the boundary is exact.
	"""
	end = at(2023, 6, 15, 12, 0, 0)
	# time_spent whose float-seconds duration is off by 1 us from the true value.
	time_spent = 2087.043558
	frame = pl.LazyFrame(
		{
			"animal_id": pl.Series(["A"], dtype=pl.Enum(["A"])),
			"datetime": aware_dt_series([end]),
			"time_spent": strat.seconds([time_spent]),
		}
	)
	out = transforms.add_occupancy_bounds(frame).collect()

	expected_start = end - dt.timedelta(microseconds=round(time_spent * 1_000_000))
	assert out["end"][0] == end
	assert out["start"][0] == expected_start
	# exact to the microsecond, not merely close
	assert (out["end"][0] - out["start"][0]) == dt.timedelta(microseconds=2_087_043_558)


def test_add_occupancy_bounds_abutting_intervals_share_boundary():
	"""Two consecutive stays of one animal reconstruct to a shared, identical boundary.

	The exit of one interval (its ``datetime``/``end``) must equal the reconstructed
	``start`` of the next, so the sweep sees them as touching, not overlapping or
	gapped. A fractional gap makes this sensitive to boundary rounding.
	"""
	t0 = at(2023, 6, 15, 12, 0, 0)
	first_len = 5.5
	second_len = 12.25
	t1 = t0 + dt.timedelta(seconds=first_len)  # end of the first interval
	t2 = t1 + dt.timedelta(seconds=second_len)  # end of the second interval
	frame = pl.LazyFrame(
		{
			"animal_id": pl.Series(["A", "A"], dtype=pl.Enum(["A"])),
			"datetime": aware_dt_series([t1, t2]),
			"time_spent": strat.seconds([first_len, second_len]),
		}
	)
	out = transforms.add_occupancy_bounds(frame).collect().sort("datetime")
	# second interval's start == first interval's end, exactly.
	assert out["start"][1] == out["end"][0] == t1


@given(
	animals=strat.animal_id_lists,
	positions=st.lists(st.sampled_from(strat.CAGES), min_size=0, max_size=4, unique=True),
)
def test_build_animal_grid_single_is_full_product(animals, positions):
	"""A single-animal grid is the full animal x position cartesian product."""
	recording = strat.analysis_recording(animal_ids=animals)
	out = grids.build_animal_grid(recording, "animal_id", positions=positions).collect()
	assert set(out.columns) == {"animal_id", "position"}
	assert out.height == len(animals) * len(positions)
	if animals and positions:
		assert set(out.select("animal_id", "position").iter_rows()) == {
			(a, p) for a in animals for p in positions
		}


@given(animals=strat.animal_id_lists)
def test_build_animal_grid_pairs(animals):
	"""Ordered pair grids enumerate a != b both ways; unordered enumerate a < b once."""
	recording = strat.analysis_recording(animal_ids=animals)
	n = len(animals)

	ordered = grids.build_animal_grid(recording, ("winner", "loser"), ordered=True).collect()
	assert ordered.columns == ["winner", "loser"]
	assert ordered.height == n * (n - 1)
	assert (ordered["winner"] == ordered["loser"]).sum() == 0

	unordered = grids.build_animal_grid(
		recording, ("animal_id", "animal_id_2"), ordered=False
	).collect()
	assert unordered.height == n * (n - 1) // 2


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
	recording = strat.analysis_recording(tunnels_map=tunnels)
	out = transforms.remove_tunnel_directionality(lf, recording).collect()
	assert out["position"].to_list() == [tunnels.get(p, p) for p in positions]
	assert out.schema["position"] == pl.Categorical
