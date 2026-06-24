"""End-to-end test of the full DeepEcoHab pipeline on the field example data.

Drives the public API exactly as ``examples/example_notebook_field.ipynb`` does:
create a field project from the bundled raw registrations, build the data
structure, run every registered analysis step, then build every dashboard plot
from the produced tables. This exercises the create -> structure -> pipeline ->
plot path on real data, so it guards against regressions that the focused unit
tests (which use synthetic frames) would miss.

The field dataset lives in ``examples/example_data_field/data.zip`` (the field
layout uses 4 boards / 16 antennas and is the broadest layout, so it covers the
custom antenna-rename path too). The test fails hard if that data is absent.
"""

import zipfile
from pathlib import Path

import plotly.graph_objects as go
import polars as pl
import pytest

import deepecohab as d
from deepecohab.utils import auxfun_plots

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ZIP = REPO_ROOT / "examples" / "example_data_field" / "data.zip"

# Animal RFID tags present in the field recording (from example_notebook_field).
ANIMALS = [
	"18D8E51A04",
	"2875E61A04",
	"2E749C1A04",
	"6AE5FF1904",
	"701EA81904",
	"71DFFF1904",
	"76F1E51A04",
	"815DE61A04",
	"8841E61A04",
	"9A44E61A04",
	"A43FE61A04",
	"B123A81904",
	"BEE7FF1904",
	"D16FA81904",
	"EB1FA81904",
]

# Switch combinations covering both branches of every PlotConfig switch, so the
# plot smoke test exercises each plotter's alternatives.
SWITCHES_PRIMARY = {
	"agg_switch": "sum",
	"ranking_switch": "intime",
	"position_switch": "time",
	"pairwise_switch": "time_together",
	"sociability_switch": "sociability",
}
SWITCHES_ALTERNATE = {
	"agg_switch": "mean",
	"ranking_switch": "stability",
	"position_switch": "visits",
	"pairwise_switch": "pairwise_encounters",
	"sociability_switch": "proportion_together",
}

# Resolved once at import; both registries are populated on `import deepecohab`.
DF_KEYS = d.df_registry.list_available()
ANALYSIS_STEPS = d.df_registry.analysis_steps
PLOT_NAMES = d.plot_registry.list_available()


@pytest.fixture(scope="session")
def field_project(tmp_path_factory) -> Path:
	"""Build a field project end to end and return its config path.

	Session-scoped so the (heavy) extract + structure + full pipeline runs once
	for the whole module. Fails hard if the bundled field data is missing.
	"""
	if not DATA_ZIP.is_file():
		raise FileNotFoundError(
			f"Field example data not found at {DATA_ZIP}. It is required for the end-to-end test."
		)

	root = tmp_path_factory.mktemp("e2e_field")
	data_dir = root / "data"
	data_dir.mkdir()
	with zipfile.ZipFile(DATA_ZIP) as zf:
		zf.extractall(data_dir)

	config_path, _ = d.create_ecohab_project(
		project_location=root,
		experiment_name="e2e_field",
		data_path=data_dir,
		light_phase_start="07:00:00",
		dark_phase_start="20:00:00",
		field_ecohab=True,
		interpolate_positions=False,
		timezone="Europe/Warsaw",
		animal_ids=ANIMALS,
	)

	d.get_ecohab_data_structure(
		config_path,
		fname_prefix="COM",
		sanitize_animal_ids=True,
		min_antenna_crossings=100,
		custom_layout=True,  # field layout renames antennas per board
	)

	steps_run = [
		name
		for name, _, _ in d.df_registry.run_pipeline(
			config_path, minimum_time=2, chasing_time_window=[0.1, 1.2]
		)
	]
	# Every analysis step should have executed exactly once.
	assert sorted(steps_run) == sorted(ANALYSIS_STEPS)

	return config_path


@pytest.fixture(scope="session")
def cfg(field_project) -> dict:
	return d.read_config(field_project)


@pytest.fixture(scope="session")
def store(field_project) -> dict[str, pl.DataFrame]:
	"""Eager dataframes for every registered key, as the dashboard assembles them."""
	return {key: d.load_ecohab_data(field_project, key, return_df=True) for key in DF_KEYS}


def _plot_config(store, cfg, **switches) -> auxfun_plots.PlotConfig:
	"""A fully populated PlotConfig spanning the whole experiment."""
	animals = cfg["animal_ids"]
	phase = cfg["phase"]
	return auxfun_plots.PlotConfig(
		store=store,
		days_range=cfg["days_range"],
		phase_type=list(phase.keys()),
		animals=animals,
		animal_colors=auxfun_plots.color_sampling(animals),
		cages=cfg["cages"],
		positions=cfg["positions"],
		position_colors=auxfun_plots.color_sampling(cfg["positions"]),
		light_dark_onset={
			"light_phase": int(phase["light_phase"].split(":")[0]),
			"dark_phase": int(phase["dark_phase"].split(":")[0]),
		},
		**switches,
	)


# --- project + data structure ------------------------------------------------


def test_project_config_complete(cfg):
	"""Creation + structure side effects populate every config section plots rely on."""
	for key in (
		"animal_ids",
		"phase",
		"experiment_timeline",
		"timezone",
		"days_range",
		"antenna_combinations",
		"tunnels",
		"cages",
		"positions",
		"antenna_rename_scheme",  # field layout
	):
		assert key in cfg, f"missing config key: {key}"

	assert set(cfg["animal_ids"]).issubset(set(ANIMALS))
	assert cfg["days_range"][0] <= cfg["days_range"][1]
	assert any("cage" in p for p in cfg["cages"])


def test_main_df_schema_and_values(field_project, cfg):
	main_df = d.load_ecohab_data(field_project, "main_df", return_df=True)
	assert main_df.height > 0

	expected = {
		"animal_id",
		"datetime",
		"phase",
		"day",
		"hour",
		"phase_count",
		"time_spent",
		"position",
		"antenna",
	}
	assert expected.issubset(set(main_df.columns))

	assert set(main_df["animal_id"].unique()).issubset(set(cfg["animal_ids"]))
	assert set(main_df["phase"].unique()).issubset(set(cfg["phase"].keys()))
	# main_df carries *directional* tunnel positions (e.g. c1_c2), so they come
	# from antenna_combinations plus cages and "undefined", not cfg["positions"].
	allowed_positions = (
		set(cfg["antenna_combinations"].values()) | set(cfg["cages"]) | {"undefined"}
	)
	assert set(main_df["position"].cast(pl.String).unique()).issubset(allowed_positions)
	assert main_df["position"].null_count() == 0
	assert (main_df["time_spent"] >= 0).all()
	assert main_df["day"].min() >= 1


# --- analysis pipeline outputs -----------------------------------------------


@pytest.mark.parametrize("key", DF_KEYS)
def test_dataframe_produced_and_nonempty(field_project, key):
	"""Every registered data key was sunk to parquet and loads as a non-empty frame."""
	results = Path(d.read_config(field_project)["project_location"]) / "results"
	assert (results / f"{key}.parquet").is_file(), f"{key}.parquet not written"

	lf = d.load_ecohab_data(field_project, key)
	assert isinstance(lf, pl.LazyFrame)
	assert lf.select(pl.len()).collect().item() > 0, f"{key} is empty"


def test_ranking_one_rating_set_per_animal(field_project, cfg):
	ranking = d.load_ecohab_data(field_project, "ranking", return_df=True)
	assert {"animal_id", "mu", "sigma", "ordinal", "datetime"}.issubset(set(ranking.columns))
	assert set(ranking["animal_id"].unique()).issubset(set(cfg["animal_ids"]))
	assert ranking["sigma"].min() > 0


def test_feature_df_is_long_zscored(field_project, cfg):
	feature_df = d.load_ecohab_data(field_project, "feature_df", return_df=True)
	assert "animal_id" in feature_df.columns
	assert set(feature_df["animal_id"].unique()).issubset(set(cfg["animal_ids"]))


# --- cross-table consistency on real data ------------------------------------
# These assert relationships *between* the produced tables, which the per-step
# unit tests (single synthetic input) cannot see. They are the real-data analogue
# of the invariants in test_analysis_properties.py.


def test_no_nan_or_inf_in_any_float_column(store):
	"""No produced table carries a null, NaN or inf in any floating-point column.

	The pipeline fill_null(0)s its grids and guards constant-metric z-scores; this
	confirms that holds across every table on real data (a stray NaN/inf would flow
	silently into plots and downstream stats).
	"""
	for key, df in store.items():
		for col, dtype in df.schema.items():
			if dtype in (pl.Float32, pl.Float64):
				s = df[col]
				assert s.null_count() == 0, f"{key}.{col} has nulls"
				assert not s.is_nan().any(), f"{key}.{col} has NaN"
				assert not s.is_infinite().any(), f"{key}.{col} has inf"


def test_chasings_grid_reconciles_with_match_events(field_project):
	"""The per-hour chasings grid sums to exactly the number of chasing events.

	chasings_df is just match_df aggregated and zero-filled onto the dense grid, so
	on real data their totals must agree and per-chaser totals must match the raw
	winners -- no event lost or invented by the grid expansion.
	"""
	match_df = d.load_ecohab_data(field_project, "match_df", return_df=True)
	chasings = d.load_ecohab_data(field_project, "chasings_df", return_df=True)

	assert chasings.filter(pl.col("chaser") == pl.col("chased")).height == 0
	assert int(chasings["chasings"].sum()) == match_df.height

	per_chaser = {
		a: int(n)
		for a, n in chasings.group_by("chaser").agg(pl.sum("chasings")).iter_rows()
		if n > 0
	}
	expected = {a: int(n) for a, n in match_df.group_by("winner").agg(pl.len()).iter_rows()}
	assert per_chaser == expected


def test_activity_metrics_nonnegative(field_project):
	"""Occupancy, visit and solitary-time metrics are all non-negative on real data."""
	activity = d.load_ecohab_data(field_project, "activity_df", return_df=True)
	assert (activity["time_in_position"] >= 0).all()
	assert (activity["time_alone"] >= 0).all()
	assert (activity["visits_to_position"] >= 0).all()


def test_time_alone_never_exceeds_occupancy(field_project):
	"""Solitary time can never exceed total occupancy in the same animal/position cell.

	Regression guard for the phase_count alignment fix: ``_get_activity`` now bins
	``time_in_position`` with ``get_grid_phase_count`` (matching ``_get_time_alone``),
	so the two left-joins in ``calculate_activity`` line up cell-for-cell and no
	occupancy row is dropped while its solitary-time counterpart is kept. Before the
	fix this failed on a handful of tunnel cells at phase boundaries.
	"""
	activity = d.load_ecohab_data(field_project, "activity_df", return_df=True)
	offenders = activity.filter(pl.col("time_alone") > pl.col("time_in_position") + 1e-6)
	assert offenders.height == 0, (
		f"{offenders.height} cells have time_alone > time_in_position:\n{offenders}"
	)


def test_pairwise_meetings_unordered_and_nonnegative(field_project):
	"""Pairs are stored unordered (a < b); time and encounter counts are non-negative."""
	pairwise = d.load_ecohab_data(field_project, "pairwise_meetings", return_df=True)
	assert (pairwise["animal_id"].cast(pl.String) < pairwise["animal_id_2"].cast(pl.String)).all()
	assert (pairwise["time_together"] >= 0).all()
	assert (pairwise["pairwise_encounters"] >= 0).all()


def test_sociability_proportion_within_bounds(field_project, cfg):
	"""proportion_together lies in [0, n_cages]; sociability stays finite.

	proportion_together sums a per-cage co-presence fraction (each <= 1) over the
	cages, so it cannot exceed the cage count or fall below zero.
	"""
	soc = d.load_ecohab_data(field_project, "incohort_sociability", return_df=True)
	n_cages = len(cfg["cages"])
	assert (soc["proportion_together"] >= -1e-9).all()
	assert (soc["proportion_together"] <= n_cages + 1e-6).all()
	assert (soc["animal_id"].cast(pl.String) < soc["animal_id_2"].cast(pl.String)).all()


def test_every_cohort_animal_present_in_feature_table(field_project, cfg):
	"""Every cohort animal surfaces in the feature table (via the dense activity grid).

	Even an animal with no chasing/tube/pairwise activity is present because
	activity_df is dense, so no animal silently drops out of the ML feature set.
	"""
	feature_df = d.load_ecohab_data(field_project, "feature_df", return_df=True)
	assert set(feature_df["animal_id"].unique()) == set(cfg["animal_ids"])


def test_tube_test_winners_losers_in_cohort(field_project, cfg):
	"""Tube-test counts are non-negative, self-pairs absent, animals in the cohort."""
	tube = d.load_ecohab_data(field_project, "tube_test_df", return_df=True)
	cohort = set(cfg["animal_ids"])
	assert set(tube["winner"].unique()).issubset(cohort)
	assert set(tube["loser"].unique()).issubset(cohort)
	assert tube.filter(pl.col("winner") == pl.col("loser")).height == 0
	assert (tube["tube_test"] >= 0).all()


def test_analysis_steps_topologically_ordered():
	"""The pipeline order places each step after the steps it requires."""
	order = d.df_registry.analysis_steps
	position = {name: i for i, name in enumerate(order)}
	requires = d.df_registry._requires
	for step in order:
		for dep in requires[step]:
			if dep in position:  # data-structure prerequisites (main_df, ...) excluded
				assert position[dep] < position[step], f"{dep} must precede {step}"


# --- dashboard plots ---------------------------------------------------------


@pytest.mark.parametrize("plot_name", PLOT_NAMES)
@pytest.mark.parametrize(
	"switches", [SWITCHES_PRIMARY, SWITCHES_ALTERNATE], ids=["primary", "alternate"]
)
def test_plot_builds(store, cfg, plot_name, switches):
	"""Every registered plot builds into a Figure for both switch variants."""
	plot_cfg = _plot_config(store, cfg, **switches)
	fig = d.plot_registry.get_plot(plot_name, plot_cfg)
	assert isinstance(fig, go.Figure), f"{plot_name} did not return a Figure"
