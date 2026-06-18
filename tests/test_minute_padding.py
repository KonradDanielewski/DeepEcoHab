import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest
import strategies as strat
from hypothesis import given, settings
from hypothesis import strategies as st

from deepecohab.utils import auxfun

TZ_NAME = "Europe/Warsaw"
TZ = ZoneInfo(TZ_NAME)
CFG = {"phase": {"light_phase": "07:00:00", "dark_phase": "20:00:00"}}

MINUTE = dt.timedelta(minutes=1)


def at(*args: int) -> dt.datetime:
	return dt.datetime(*args, tzinfo=TZ)


def make_lf(rows: list[dict]) -> pl.LazyFrame:
	"""rows: {"end": datetime, "time_spent": float_s, "time_under": timedelta,
	optional "animal_id"/"position"}.
	"""
	return pl.LazyFrame(
		{
			"animal_id": pl.Series(
				[r.get("animal_id", "A") for r in rows], dtype=pl.Enum(["A", "B"])
			),
			"position": pl.Series(
				[r.get("position", "cage_1") for r in rows], dtype=pl.Categorical
			),
			"datetime": pl.Series("datetime", [r["end"] for r in rows]).dt.replace_time_zone(
				TZ_NAME
			),
			"time_spent": pl.Series([float(r["time_spent"]) for r in rows], dtype=pl.Float64),
			"time_under": pl.Series([r["time_under"] for r in rows], dtype=pl.Duration("us")),
		}
	)


def piece_starts(out: pl.DataFrame) -> pl.Series:
	"""Reconstruct each piece's start = datetime(end) - time_spent."""
	return out.select(
		(
			pl.col("datetime")
			- pl.duration(microseconds=(pl.col("time_spent") * 1_000_000).round().cast(pl.Int64))
		).alias("__s")
	)["__s"]


def test_within_minute_not_split():
	"""Interval inside one clock minute -> single passthrough row."""
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 0, 40), "time_spent": 20, "time_under": MINUTE / 4}]
	)  # 12:00:20 -> 12:00:40
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out.height == 1
	assert out["interpolated"].to_list() == [False]
	assert out["time_spent"][0] == pytest.approx(20)
	assert out["time_under"][0] == MINUTE / 4


def test_interval_exactly_one_aligned_minute_not_split():
	"""[12:00:00, 12:01:00) is one aligned minute -> single piece."""
	lf = make_lf([{"end": at(2023, 6, 15, 12, 1, 0), "time_spent": 60, "time_under": MINUTE}])
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out.height == 1
	assert out["interpolated"].to_list() == [False]


def test_single_minute_crossing_splits_into_two():
	"""12:00:40 -> 12:01:20 crosses 12:01:00 -> two 20s pieces, both interpolated."""
	lf = make_lf([{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": 40, "time_under": MINUTE}])
	out = auxfun._get_minute_padding(lf, CFG).collect().sort("datetime")
	assert out.height == 2
	assert out["interpolated"].to_list() == [True, True]
	assert out["time_spent"].to_list() == pytest.approx([20, 20])
	halves = out["time_under"].to_list()
	assert halves[0] == pytest.approx(MINUTE / 2, abs=dt.timedelta(microseconds=2))
	assert halves[1] == pytest.approx(MINUTE / 2, abs=dt.timedelta(microseconds=2))


def test_multi_minute_crossing_piece_count():
	"""A 2m40s interval crossing three minute marks yields four pieces."""
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 3, 20), "time_spent": 40 + 120, "time_under": MINUTE}]
	)  # 12:00:40 -> 12:03:20 spans minutes 0,1,2,3 -> 4 pieces
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out.height == 4
	assert out["interpolated"].to_list() == [True, True, True, True]


def test_time_spent_conserved():
	original = 40
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": original, "time_under": MINUTE}]
	)
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out["time_spent"].sum() == pytest.approx(original)


def test_time_under_conserved():
	tu = dt.timedelta(seconds=37)
	lf = make_lf([{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": 40, "time_under": tu}])
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out["time_under"].sum() == pytest.approx(tu, abs=dt.timedelta(microseconds=4))


def test_no_piece_exceeds_one_minute():
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 3, 20), "time_spent": 40 + 120, "time_under": MINUTE}]
	)
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert (out["time_spent"] <= 60 + 1e-6).all()


def test_each_piece_within_single_clock_minute():
	"""No piece straddles a minute mark: start and (end - 1us) share a minute."""
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 3, 20), "time_spent": 40 + 120, "time_under": MINUTE}]
	)
	out = auxfun._get_minute_padding(lf, CFG).collect()
	starts = piece_starts(out)
	ends = out["datetime"]
	start_min = starts.dt.truncate("1m")
	end_min = (ends - dt.timedelta(microseconds=1)).dt.truncate("1m")
	assert (start_min == end_min).all()


def test_hour_label_from_piece_start():
	"""Hour column reflects the piece START, not the original interval end."""
	# 11:59:40 -> 12:00:20 crosses both the minute AND the hour mark at 12:00.
	lf = make_lf([{"end": at(2023, 6, 15, 12, 0, 20), "time_spent": 40, "time_under": MINUTE}])
	out = auxfun._get_minute_padding(lf, CFG).collect().sort("datetime")
	assert out.height == 2
	# first piece 11:59:40-12:00:00 -> hour 11; second 12:00:00-12:00:20 -> hour 12
	assert out["hour"].cast(pl.Int64).to_list() == [11, 12]


def test_zero_duration_row_survives_without_nan():
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 0, 0), "time_spent": 0, "time_under": dt.timedelta(0)}]
	)
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert out.height == 1
	assert out["interpolated"].to_list() == [False]
	assert out["time_under"][0] == dt.timedelta(0)


def test_row_id_present_in_output():
	lf = make_lf([{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": 40, "time_under": MINUTE}])
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert "row_id" in out.columns


def test_row_id_dedup_recovers_original_count():
	"""unique(row_id, keep=first) returns exactly one row per original visit."""
	rows = [
		{"end": at(2023, 6, 15, 12, 0, 40), "time_spent": 20, "time_under": MINUTE},  # no split
		{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": 40, "time_under": MINUTE},  # 2 pieces
		{"end": at(2023, 6, 15, 12, 3, 20), "time_spent": 160, "time_under": MINUTE},  # 4 pieces
	]
	lf = make_lf(rows)
	out = auxfun._get_minute_padding(lf, CFG).collect()

	# more pieces than originals, but exactly len(rows) distinct row_ids
	assert out.height > len(rows)
	assert out["row_id"].n_unique() == len(rows)
	deduped = out.unique("row_id", keep="first")
	assert deduped.height == len(rows)
	assert sorted(deduped["row_id"].to_list()) == list(range(len(rows)))


def test_row_ids_are_contiguous_from_zero():
	rows = [
		{"end": at(2023, 6, 15, 12, 0, 40), "time_spent": 20, "time_under": MINUTE}
		for _ in range(5)
	]
	lf = make_lf(rows)
	out = auxfun._get_minute_padding(lf, CFG).collect()
	assert sorted(out["row_id"].unique().to_list()) == list(range(5))


def test_dedup_first_piece_holds_piece_values_not_original():
	"""Documents that keep='first' yields the FIRST PIECE's durations.

	For a split visit, the deduped row's time_spent is the first piece's length,
	NOT the original visit length. This is correct for counting but must not be
	read as the original duration.
	"""
	lf = make_lf(
		[{"end": at(2023, 6, 15, 12, 1, 20), "time_spent": 40, "time_under": MINUTE}]
	)  # splits into 20s + 20s at 12:01:00
	out = auxfun._get_minute_padding(lf, CFG).collect()
	first = out.unique("row_id", keep="first").row(0, named=True)
	assert first["time_spent"] == pytest.approx(20)  # first piece, not 40


# --- property-based tests ----------------------------------------------------
# Timezone and phase config are drawn inside @given (st.sampled_from), so each
# example exercises a random combination, including DST zones and midnight
# phase boundaries; see tests/strategies.py.


@settings(max_examples=200)
@given(v=strat.visit, tz=strat.timezones, pcfg=strat.phase_configs)
def test_property_conserves_time_spent(v, tz, pcfg):
	"""However a single visit is split across minute marks, total time_spent is
	preserved and no piece exceeds one minute, in any timezone / phase config.
	"""
	out = auxfun._get_minute_padding(strat.padding_frame([v], tz), {"phase": pcfg}).collect()
	assert out["time_spent"].sum() == pytest.approx(v["time_spent"], abs=1e-6)
	assert (out["time_spent"] <= 60 + 1e-6).all()


@settings(max_examples=200)
@given(
	rows=st.lists(strat.visit, min_size=1, max_size=20),
	tz=strat.timezones,
	pcfg=strat.phase_configs,
)
def test_property_preserves_identity_and_dedup(rows, tz, pcfg):
	"""Padding may explode rows into per-minute pieces, but unique(row_id,
	keep="first") recovers exactly one row per original visit, and every piece
	keeps the animal_id/position of the visit it came from (row_id i == row i).
	"""
	out = auxfun._get_minute_padding(strat.padding_frame(rows, tz), {"phase": pcfg}).collect()

	assert out["row_id"].n_unique() == len(rows)
	assert sorted(out["row_id"].unique().to_list()) == list(range(len(rows)))
	assert out.unique("row_id", keep="first").height == len(rows)

	for i, r in enumerate(rows):
		pieces = out.filter(pl.col("row_id") == i)
		assert pieces["animal_id"].unique().to_list() == [r["animal_id"]]
		assert pieces["position"].unique().to_list() == [r["position"]]
