"""Tests for calculate_ranking (Plackett-Luce dominance ranking).

calculate_ranking replays each chasing event in match_df as a one-on-one match
and emits the full rating trajectory (one row per animal after every match). The
step reads match_df via auxfun._get_data, so we monkeypatch that to feed a small,
hand-built match table and exercise the pure compute body directly via
``__wrapped__`` (bypassing the lifecycle cache/parquet sink).
"""

import datetime as dt

import polars as pl
import pytest
import tzlocal
from openskill.models import PlackettLuce

from deepecohab.analysis import antenna_analysis

TZ = tzlocal.get_localzone()

PHASE_CFG = {"light_phase": "07:00:00", "dark_phase": "20:00:00"}

# The model configuration must match calculate_ranking exactly so expected
# ordinals computed here line up with the ones the step emits.
MODEL = PlackettLuce(limit_sigma=True, balance=True)


def at(*args: int) -> dt.datetime:
	"""Construct a zone-aware datetime in the project timezone."""
	return dt.datetime(*args, tzinfo=TZ)


def expected_ordinal(mu: float | None = None, sigma: float | None = None) -> float:
	"""Ordinal a never-playing animal should hold, rounded as the step rounds it."""
	return round(MODEL.rating(mu=mu, sigma=sigma).ordinal(), 3)


def make_match_df(rows: list[tuple[str, str, dt.datetime]]) -> pl.LazyFrame:
	"""Build a match_df LazyFrame from (loser, winner, datetime) tuples."""
	return pl.LazyFrame(
		{
			"loser": [r[0] for r in rows],
			"winner": [r[1] for r in rows],
			"datetime": [r[2] for r in rows],
		},
		schema={
			"loser": pl.Utf8,
			"winner": pl.Utf8,
			"datetime": pl.Datetime("us", str(TZ)),
		},
	)


def run_ranking(monkeypatch, match_df, animal_ids, prev_ranking=None) -> pl.DataFrame:
	"""Call the pure ranking body with match_df injected in place of _get_data."""
	monkeypatch.setattr(antenna_analysis.auxfun, "_get_data", lambda cfg, key: match_df)
	cfg = {"animal_ids": animal_ids, "phase": PHASE_CFG}
	kwargs = {} if prev_ranking is None else {"prev_ranking": prev_ranking}
	return antenna_analysis.calculate_ranking.__wrapped__(cfg, **kwargs).collect()


def final_block(result: pl.DataFrame) -> dict[str, float]:
	"""Map animal_id -> ordinal in the last-emitted block (final standings)."""
	last = result.filter(pl.col("datetime") == result["datetime"].max())
	return dict(last.select("animal_id", "ordinal").iter_rows())


def test_output_schema(monkeypatch):
	"""Result carries the rating columns plus the derived phase/day/hour."""
	match_df = make_match_df([("B", "A", at(2023, 5, 24, 12, 0, 0))])
	result = run_ranking(monkeypatch, match_df, ["A", "B"])
	assert set(result.columns) == {
		"animal_id",
		"mu",
		"sigma",
		"ordinal",
		"datetime",
		"phase",
		"day",
		"hour",
	}


def test_one_row_per_animal_per_match(monkeypatch):
	"""Every match emits one row for every animal (full trajectory)."""
	matches = [
		("B", "A", at(2023, 5, 24, 12, 0, 0)),
		("B", "A", at(2023, 5, 24, 12, 1, 0)),
		("B", "A", at(2023, 5, 24, 12, 2, 0)),
	]
	result = run_ranking(monkeypatch, make_match_df(matches), ["A", "B", "C"])
	assert result.height == len(matches) * 3  # 3 animals


def test_consistent_winner_outranks_loser(monkeypatch):
	"""If A always beats B, A's final ordinal exceeds B's."""
	matches = [("B", "A", at(2023, 5, 24, 12, i, 0)) for i in range(5)]
	result = run_ranking(monkeypatch, make_match_df(matches), ["A", "B"])

	ordinals = final_block(result)
	assert ordinals["A"] > ordinals["B"]


def test_uninvolved_animal_keeps_default_ordinal(monkeypatch):
	"""An animal that never plays stays at the model's default rating."""
	matches = [("B", "A", at(2023, 5, 24, 12, 0, 0))]
	result = run_ranking(monkeypatch, make_match_df(matches), ["A", "B", "C"])

	c_rows = result.filter(pl.col("animal_id") == "C")
	assert (c_rows["ordinal"] == expected_ordinal()).all()


def test_winner_and_loser_move_in_opposite_directions(monkeypatch):
	"""After one match the winner's ordinal rises above default and the loser's falls below."""
	match_df = make_match_df([("B", "A", at(2023, 5, 24, 12, 0, 0))])
	result = run_ranking(monkeypatch, match_df, ["A", "B"])

	ordinals = final_block(result)
	assert ordinals["A"] > expected_ordinal()
	assert ordinals["B"] < expected_ordinal()


# --- prev_ranking continuation (regression: this path used to crash) ---------


@pytest.mark.parametrize("as_lazy", [True, False], ids=["lazyframe", "dataframe"])
def test_prev_ranking_seeds_starting_ratings(monkeypatch, as_lazy):
	"""prev_ranking resumes an animal from its prior mu/sigma instead of the default.

	C never plays, so its emitted ordinal must equal the ordinal of the seeded
	rating throughout. Previously this branch raised (model undefined / wrong
	value type), so simply producing the right number is the regression guard.
	"""
	prev = pl.DataFrame(
		{"animal_id": ["C"], "mu": [40.0], "sigma": [2.0]},
		schema={"animal_id": pl.Utf8, "mu": pl.Float64, "sigma": pl.Float64},
	)
	prev_ranking = prev.lazy() if as_lazy else prev

	matches = [("B", "A", at(2023, 5, 24, 12, i, 0)) for i in range(3)]
	result = run_ranking(
		monkeypatch, make_match_df(matches), ["A", "B", "C"], prev_ranking=prev_ranking
	)

	c_rows = result.filter(pl.col("animal_id") == "C")
	assert (c_rows["ordinal"] == expected_ordinal(mu=40.0, sigma=2.0)).all()


def test_prev_ranking_defaults_animals_not_listed(monkeypatch):
	"""Animals absent from prev_ranking still start from the model default."""
	prev = pl.DataFrame(
		{"animal_id": ["C"], "mu": [40.0], "sigma": [2.0]},
		schema={"animal_id": pl.Utf8, "mu": pl.Float64, "sigma": pl.Float64},
	)
	# A and B are not in prev_ranking; with no matches between... use a B/A match
	# but check a third uninvolved default animal D.
	matches = [("B", "A", at(2023, 5, 24, 12, 0, 0))]
	result = run_ranking(
		monkeypatch, make_match_df(matches), ["A", "B", "C", "D"], prev_ranking=prev
	)

	d_rows = result.filter(pl.col("animal_id") == "D")
	assert (d_rows["ordinal"] == expected_ordinal()).all()


# --- get_prev_ranking + round-trip ------------------------------------------


def test_get_prev_ranking_shape(monkeypatch):
	"""get_prev_ranking yields exactly the animal_id/mu/sigma prev_ranking shape."""
	matches = [("B", "A", at(2023, 5, 24, 12, i, 0)) for i in range(3)]
	result = run_ranking(monkeypatch, make_match_df(matches), ["A", "B"])

	prev = antenna_analysis.get_prev_ranking(result).collect()
	assert set(prev.columns) == {"animal_id", "mu", "sigma"}
	assert sorted(prev["animal_id"].to_list()) == ["A", "B"]
	assert prev.height == 2


def test_get_prev_ranking_takes_latest_rating(monkeypatch):
	"""The collapsed rating is the chronologically last one (matches final standings)."""
	matches = [("B", "A", at(2023, 5, 24, 12, i, 0)) for i in range(5)]
	result = run_ranking(monkeypatch, make_match_df(matches), ["A", "B"])

	prev = {
		r["animal_id"]: r
		for r in antenna_analysis.get_prev_ranking(result).collect().iter_rows(named=True)
	}
	for animal, ordinal in final_block(result).items():
		seeded = MODEL.rating(mu=prev[animal]["mu"], sigma=prev[animal]["sigma"])
		assert round(seeded.ordinal(), 3) == ordinal


def test_round_trip_continues_from_prev(monkeypatch):
	"""get_prev_ranking output fed back as prev_ranking carries ratings forward.

	Phase 1 lets A dominate B; phase 2 only has a C/D match, so A and B are
	uninvolved and must retain their phase-1 ratings via the seeded prev_ranking.
	"""
	phase1 = [("B", "A", at(2023, 5, 24, 12, i, 0)) for i in range(5)]
	r1 = run_ranking(monkeypatch, make_match_df(phase1), ["A", "B", "C", "D"])
	final1 = final_block(r1)

	prev = antenna_analysis.get_prev_ranking(r1)  # LazyFrame
	phase2 = [("D", "C", at(2023, 5, 25, 12, 0, 0))]
	r2 = run_ranking(monkeypatch, make_match_df(phase2), ["A", "B", "C", "D"], prev_ranking=prev)
	final2 = final_block(r2)

	assert final2["A"] == final1["A"]
	assert final2["B"] == final1["B"]
	assert final2["A"] > final2["B"]


# --- empty match_df (no chasing events at all) ------------------------------


def test_empty_match_df_emits_empty_schema(monkeypatch):
	"""With no chasing events to replay, ranking returns an empty, well-typed frame.

	Exercises the dedicated ``else`` branch in calculate_ranking that builds an
	empty result from an explicit schema; the derived phase/day/hour columns are
	still appended, so the schema must match the populated case.
	"""
	empty = make_match_df([])
	result = run_ranking(monkeypatch, empty, ["A", "B", "C"])

	assert result.height == 0
	assert set(result.columns) == {
		"animal_id",
		"mu",
		"sigma",
		"ordinal",
		"datetime",
		"phase",
		"day",
		"hour",
	}
