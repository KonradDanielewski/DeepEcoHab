"""Shared Hypothesis strategies, frame builders, and reference oracles.

Imported by the test_* modules so every property-based test draws from the same
domains (timezones, phase layouts, animals, positions) and compares against the
same independent Python reference implementations.

tz construction: generated naive datetimes are localized as UTC instants and
converted to the target zone, so DST gaps / ambiguous hours never raise while the
local wall clock still sweeps those transitions.
"""

import datetime as dt
from pathlib import Path

import polars as pl
import toml
from hypothesis import strategies as st

# --- domains -----------------------------------------------------------------
# America/New_York covers EDT (and EST); the zones have DST transitions on
# different dates, widening coverage. UTC is the no-DST baseline.
TIMEZONES = ["UTC", "America/New_York", "Europe/Warsaw"]

# Inner phase dicts (wrap as {"phase": cfg} when calling auxfun). Includes the
# midnight-boundary edge cases that exercise get_phase's wrap-around branch.
PHASE_CONFIGS = [
	{"light_phase": "07:00:00", "dark_phase": "20:00:00"},
	{"light_phase": "00:00:00", "dark_phase": "13:00:00"},
	{"light_phase": "12:00:00", "dark_phase": "00:00:00"},
	{"light_phase": "22:00:00", "dark_phase": "10:00:00"},
]

ANIMALS = ["A", "B", "C", "D", "E", "F"]
CAGES = ["cage_1", "cage_2", "cage_3", "cage_4"]
POSITIONS = [*CAGES, "tunnel_1", "tunnel_2"]
PHASE_NAMES = ["light_phase", "dark_phase"]

_MIN, _MAX = dt.datetime(2023, 1, 1), dt.datetime(2023, 12, 31)

# --- strategies --------------------------------------------------------------
naive_datetimes = st.datetimes(min_value=_MIN, max_value=_MAX)
durations = st.floats(min_value=0, max_value=10 * 60, allow_nan=False, allow_infinity=False)
positive_durations = st.floats(
	min_value=0.1, max_value=10 * 60, allow_nan=False, allow_infinity=False
)
timezones = st.sampled_from(TIMEZONES)
phase_configs = st.sampled_from(PHASE_CONFIGS)
phase_label_lists = st.lists(st.sampled_from(PHASE_NAMES), min_size=1, max_size=40)

# One padding visit: an interval end, its duration, and which animal/position.
visit = st.fixed_dictionaries(
	{
		"end": naive_datetimes,
		"time_spent": durations,
		"animal_id": st.sampled_from(ANIMALS),
		"position": st.sampled_from(POSITIONS),
	}
)

# One presence event for time-alone: an animal in a cage from start for duration.
event = st.fixed_dictionaries(
	{
		"animal_id": st.sampled_from(ANIMALS),
		"position": st.sampled_from(CAGES),
		"start": naive_datetimes,
		"duration": positive_durations,
	}
)


# --- builders ----------------------------------------------------------------
def aware(naive: list[dt.datetime], tz: str) -> pl.Series:
	"""tz-aware Datetime series built via UTC so DST never raises."""
	return pl.Series("datetime", naive).dt.replace_time_zone("UTC").dt.convert_time_zone(tz)


def padding_frame(rows: list[dict], tz: str) -> pl.LazyFrame:
	"""Frame shaped for auxfun._get_minute_padding, one input row per visit."""
	return pl.LazyFrame(
		{
			"animal_id": pl.Series([r["animal_id"] for r in rows], dtype=pl.Enum(ANIMALS)),
			"position": pl.Series([r["position"] for r in rows], dtype=pl.Categorical),
			"datetime": aware([r["end"] for r in rows], tz),
			"time_spent": pl.Series([r["time_spent"] for r in rows], dtype=pl.Float64),
			"time_under": pl.Series(
				[dt.timedelta(seconds=r["time_spent"]) for r in rows], dtype=pl.Duration("us")
			),
		}
	)


def time_alone_frame(events: list[dict], tz: str) -> pl.DataFrame:
	"""Eager frame shaped for analysis._get_time_alone (datetime is interval END)."""
	ends = [e["start"] + dt.timedelta(seconds=e["duration"]) for e in events]
	return pl.DataFrame(
		{
			"animal_id": pl.Series([e["animal_id"] for e in events], dtype=pl.Enum(ANIMALS)),
			"position": pl.Series([e["position"] for e in events], dtype=pl.Categorical),
			"datetime": aware(ends, tz),
			"time_spent": pl.Series([float(e["duration"]) for e in events], dtype=pl.Float64),
		}
	)


# --- reference oracles -------------------------------------------------------
def expected_phase(local_time: dt.time, phase_cfg: dict[str, str]) -> str:
	"""Independent reimplementation of get_phase's mapping for one wall-clock time.

	The latest boundary at or before the time wins; before the first boundary it
	wraps to the last phase. Mirrors the when/then chain in auxfun.get_phase.
	"""
	boundaries = sorted((dt.time.fromisoformat(s), name) for name, s in phase_cfg.items())
	result = boundaries[-1][1]
	for start, name in boundaries:
		if local_time >= start:
			result = name
	return result


def expected_phase_count(labels: list[str]) -> list[int]:
	"""Reference for get_phase_count: the ordinal of each contiguous run within
	its own phase (1,1,2,2,3... for an alternating L/D sequence).
	"""
	counts: dict[str, int] = {}
	out: list[int] = []
	prev: object = None
	for label in labels:
		if label != prev:
			counts[label] = counts.get(label, 0) + 1
		out.append(counts[label])
		prev = label
	return out


def expected_day(dates: list[dt.date]) -> list[int]:
	"""Reference for get_day: calendar offset from the earliest date, 1-indexed."""
	earliest = min(dates)
	return [(d - earliest).days + 1 for d in dates]


# === additional infra for the utils-coverage expansion =======================

DIRECTIONAL_TUNNELS = ["c1_c2", "c2_c1", "c2_c3", "c3_c2"]
TUNNEL_POSITIONS = ["tunnel_1", "tunnel_2", "tunnel_3", "tunnel_4"]

# --- additional strategies ---------------------------------------------------
# Valid time strings. _is_valid_time (dashboard) only accepts %H:%M; config
# templates accept the %H:%M:%S form.
time_strings_hms = st.builds(lambda t: t.strftime("%H:%M:%S"), st.times())
time_strings_hm = st.builds(lambda t: t.strftime("%H:%M"), st.times())

# Strings that are not valid HH:MM times (no colon -> strptime fails).
junk_strings = st.text(max_size=12).filter(lambda s: ":" not in s)

# datetimes truncated to whole seconds, so consecutive diffs are integral and
# round(2) introduces no half-rounding ambiguity (for calculate_time_spent).
whole_second_datetimes = naive_datetimes.map(lambda d: d.replace(microsecond=0))

# antenna_combinations: antenna-pair key -> position (cages + directional tunnels)
antenna_combinations = st.dictionaries(
	keys=st.from_regex(r"[0-9]_[0-9]", fullmatch=True),
	values=st.sampled_from(CAGES + DIRECTIONAL_TUNNELS),
	min_size=1,
	max_size=8,
)

# tunnels map: directional tunnel -> undirected position
tunnels_maps = st.dictionaries(
	keys=st.sampled_from(DIRECTIONAL_TUNNELS),
	values=st.sampled_from(TUNNEL_POSITIONS),
	max_size=4,
)

animal_id_lists = st.lists(st.sampled_from(ANIMALS), min_size=0, max_size=6, unique=True)

# TOML round-trippable config values (no None; homogeneous arrays for the toml
# lib; printable-ASCII text to avoid escaping/control-char round-trip issues).
# Config-realistic alphabet (names/paths/times). The bundled toml encoder
# mishandles several specials in strings (lone backslashes, commas/quotes inside
# arrays), so we restrict to characters it round-trips reliably — this exercises
# read_config without fuzzing the third-party encoder.
_safe_text = st.text(
	alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-:/ ",
	max_size=15,
)
_toml_scalars = st.one_of(
	_safe_text,
	st.integers(min_value=-1000, max_value=1000),
	st.booleans(),
)
_toml_lists = st.one_of(
	st.lists(_safe_text, max_size=5),
	st.lists(st.integers(min_value=-100, max_value=100), max_size=5),
)
config_dicts = st.dictionaries(
	keys=st.from_regex(r"[a-z_][a-z0-9_]{0,11}", fullmatch=True),
	values=st.one_of(_toml_scalars, _toml_lists),
	max_size=8,
)


# --- additional builders -----------------------------------------------------
def config_file(tmp_path, cfg: dict) -> Path:
	"""Write cfg to <tmp_path>/config.toml and return the path."""
	path = Path(tmp_path) / "config.toml"
	with open(path, "w") as f:
		toml.dump(cfg, f)
	return path


def grouped_event_frame(rows: list[dict], tz: str) -> pl.LazyFrame:
	"""Frame with animal_id + datetime in the given row order (NOT sorted), for
	calculate_time_spent tests. rows: {"animal_id", "end"}.
	"""
	return pl.LazyFrame(
		{
			"animal_id": pl.Series([r["animal_id"] for r in rows], dtype=pl.Enum(ANIMALS)),
			"datetime": aware([r["end"] for r in rows], tz),
		}
	)


# --- additional reference oracles --------------------------------------------
def expected_hour(datetimes: list[dt.datetime]) -> list[int]:
	"""Reference for get_hour: the local wall-clock hour of each tz-aware instant."""
	return [d.hour for d in datetimes]


def expected_time_spent(animals: list[str], datetimes: list[dt.datetime]) -> list[float]:
	"""Reference for calculate_time_spent: per-animal consecutive gap in
	seconds in row order; first occurrence of each animal is 0.0.
	"""
	last: dict[str, dt.datetime] = {}
	out: list[float] = []
	for animal, t in zip(animals, datetimes, strict=False):
		out.append(0.0 if animal not in last else round((t - last[animal]).total_seconds(), 2))
		last[animal] = t
	return out


def expected_cages(antenna_map: dict[str, str]) -> list[str]:
	"""Reference for add_cages_to_config: sorted unique cage-named positions."""
	return sorted({v for v in antenna_map.values() if "cage" in v})


def expected_positions(antenna_map: dict[str, str], tunnels: dict[str, str]) -> list[str]:
	"""Reference for add_positions_to_config: undirected positions plus 'undefined'."""
	return sorted({tunnels.get(v, v) for v in antenna_map.values()} | {"undefined"})
