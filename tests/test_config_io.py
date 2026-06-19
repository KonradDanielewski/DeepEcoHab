"""Config and IO helpers in auxfun.py (filesystem round-trips via tmp_path).

Property tests that write a config use tempfile.TemporaryDirectory (not the
tmp_path fixture) so Hypothesis does not flag a reused function-scoped fixture.
"""

import datetime as dt
import tempfile
from pathlib import Path

import polars as pl
import pytest
import strategies as strat
from hypothesis import given
from hypothesis import strategies as st

from deepecohab.utils import auxfun


# --- read_config -------------------------------------------------------------
def test_read_config_dict_passthrough():
	cfg = {"a": 1, "b": [1, 2]}
	assert auxfun.read_config(cfg) is cfg


@given(cfg=strat.config_dicts)
def test_read_config_toml_roundtrip(cfg):
	with tempfile.TemporaryDirectory() as d:
		path = strat.config_file(d, cfg)
		assert auxfun.read_config(path) == cfg
		assert auxfun.read_config(str(path)) == cfg


@pytest.mark.parametrize("bad", [123, None, 4.5])
def test_read_config_bad_type_raises(bad):
	with pytest.raises(TypeError):
		auxfun.read_config(bad)


# --- make_project_path -------------------------------------------------------
@given(name=st.from_regex(r"[A-Za-z0-9_]{1,20}", fullmatch=True))
def test_make_project_path(name):
	out = auxfun.make_project_path(Path("base") / "dir", name)
	today = dt.datetime.today().strftime("%Y-%m-%d")
	assert out == Path("base") / "dir" / f"{name}_{today}"


# --- load_ecohab_data / _get_data --------------------------------------------
def test_load_bad_key_raises(tmp_path):
	with pytest.raises(KeyError):
		auxfun.load_ecohab_data({"project_location": str(tmp_path)}, "not_a_key")


def test_load_missing_file_returns_none(tmp_path):
	(tmp_path / "results").mkdir()
	assert auxfun.load_ecohab_data({"project_location": str(tmp_path)}, "main_df") is None


def test_get_data_missing_file_raises(tmp_path):
	(tmp_path / "results").mkdir()
	with pytest.raises(FileNotFoundError):
		auxfun._get_data({"project_location": str(tmp_path)}, "main_df")


def test_load_roundtrip_lazy_and_eager(tmp_path):
	results = tmp_path / "results"
	results.mkdir()
	df = pl.DataFrame({"a": [1, 2, 3]})
	df.write_parquet(results / "main_df.parquet")
	cfg = {"project_location": str(tmp_path)}

	lazy = auxfun.load_ecohab_data(cfg, "main_df")
	assert isinstance(lazy, pl.LazyFrame)
	assert lazy.collect().equals(df)

	eager = auxfun.load_ecohab_data(cfg, "main_df", return_df=True)
	assert isinstance(eager, pl.DataFrame)
	assert eager.equals(df)


# --- add_cages_to_config / add_positions_to_config ---------------------------
@given(antenna_map=strat.antenna_combinations)
def test_add_cages_to_config(antenna_map):
	with tempfile.TemporaryDirectory() as d:
		path = strat.config_file(d, {"antenna_combinations": antenna_map})
		auxfun.add_cages_to_config(path)
		assert auxfun.read_config(path)["cages"] == strat.expected_cages(antenna_map)


@given(antenna_map=strat.antenna_combinations, tunnels=strat.tunnels_maps)
def test_add_positions_to_config(antenna_map, tunnels):
	with tempfile.TemporaryDirectory() as d:
		path = strat.config_file(d, {"antenna_combinations": antenna_map, "tunnels": tunnels})
		auxfun.add_positions_to_config(path)
		assert auxfun.read_config(path)["positions"] == strat.expected_positions(
			antenna_map, tunnels
		)


# --- add_days_to_config / append_start_end_to_config -------------------------
def test_add_days_to_config(tmp_path):
	path = strat.config_file(tmp_path, {})
	auxfun.add_days_to_config(path, pl.LazyFrame({"day": [3, 1, 2, 2, 5]}))
	assert auxfun.read_config(path)["days_range"] == [1, 5]


def test_append_start_end_to_config(tmp_path):
	path = strat.config_file(tmp_path, {})
	ts = [
		dt.datetime(2023, 5, 2, 8, 0),
		dt.datetime(2023, 5, 1, 7, 0),
		dt.datetime(2023, 5, 3, 9, 0),
	]
	lf = pl.LazyFrame({"datetime": pl.Series("datetime", ts)})

	_, start, end = auxfun.append_start_end_to_config(path, lf)
	assert start == str(min(ts))
	assert end == str(max(ts))
	on_disk = auxfun.read_config(path)
	assert on_disk["experiment_timeline"] == {"start_date": start, "finish_date": end}


# --- set_animal_ids ----------------------------------------------------------
def test_set_animal_ids_explicit_list_filters_without_sorting(tmp_path):
	path = strat.config_file(tmp_path, {})
	lf = pl.LazyFrame({"animal_id": ["A", "B", "C", "A"]})
	out = auxfun.set_animal_ids(
		path, lf, sanitize_animal_ids=False, min_antenna_crossings=100, animal_ids=["B", "A"]
	).collect()

	cfg = auxfun.read_config(path)
	assert cfg["animal_ids"] == ["B", "A"]  # explicit branch keeps caller order
	assert cfg["dropped_ids"] == []
	assert set(out["animal_id"].to_list()) == {"A", "B"}


@given(
	counts=st.dictionaries(
		st.sampled_from(strat.ANIMALS), st.integers(0, 200), min_size=1, max_size=6
	),
	threshold=st.integers(1, 150),
)
def test_set_animal_ids_sanitize_drops_ghosts(counts, threshold):
	rows = [a for a, c in counts.items() for _ in range(c)]
	with tempfile.TemporaryDirectory() as d:
		path = strat.config_file(d, {})
		lf = pl.LazyFrame({"animal_id": pl.Series(rows, dtype=pl.Utf8)})
		auxfun.set_animal_ids(path, lf, sanitize_animal_ids=True, min_antenna_crossings=threshold)

		cfg = auxfun.read_config(path)
		assert cfg["animal_ids"] == sorted(a for a, c in counts.items() if c >= threshold)
		# Only animals actually present (c > 0) can be flagged as ghosts.
		assert sorted(cfg["dropped_ids"]) == sorted(
			a for a, c in counts.items() if 0 < c < threshold
		)


# --- padded_df (caching wrapper) ----------------------------
def _padding_lf():
	return strat.padding_frame(
		[
			{
				"end": dt.datetime(2023, 6, 15, 12, 1, 20),
				"time_spent": 40.0,
				"animal_id": "A",
				"position": "cage_1",
			}
		],
		"UTC",
	)


def test_padded_df_writes_and_caches(tmp_path):
	(tmp_path / "results").mkdir()
	cfg = {
		"project_location": str(tmp_path),
		"phase": {"light_phase": "07:00:00", "dark_phase": "20:00:00"},
	}
	parquet = tmp_path / "results" / "padded_df.parquet"

	auxfun.padded_df(_padding_lf(), cfg, save_data=True, overwrite=False)
	assert parquet.exists()

	cached = auxfun.padded_df(_padding_lf(), cfg, save_data=True, overwrite=False)
	assert isinstance(cached, pl.LazyFrame)


def test_padded_df_no_save(tmp_path):
	(tmp_path / "results").mkdir()
	cfg = {
		"project_location": str(tmp_path),
		"phase": {"light_phase": "07:00:00", "dark_phase": "20:00:00"},
	}
	auxfun.padded_df(_padding_lf(), cfg, save_data=False, overwrite=True)
	assert not (tmp_path / "results" / "padded_df.parquet").exists()
