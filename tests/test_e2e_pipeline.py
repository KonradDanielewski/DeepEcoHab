"""End-to-end test of the full DeepEcoHab pipeline on real catalog recordings.

Drives the public API as a user does: create a project, add recordings from their
metadata JSON and raw parquet, run every analysis step, then build every dashboard
plot from the produced tables. This exercises the add -> analyse -> load -> plot
path on real data, so it guards against regressions the focused unit tests (which
use synthetic frames) would miss.

The recordings live outside the repo, so the module skips when the catalog is not
on this machine.
"""

import datetime as dt
import itertools
import json
from dataclasses import replace
from pathlib import Path

import plotly.graph_objects as go
import polars as pl
import pytest

import deepecohab as d
from deepecohab.auxiliary_analysis.tube_test import calculate_tube_test
from deepecohab.core.data_model import DataFrameRegistry, Project
from deepecohab.plotting import PlotContext, PlotRegistry, available_attributes
from deepecohab.plotting.animals import resolve_colors

pytestmark = pytest.mark.e2e

CATALOG = Path.home() / "Documents/deepecohab/data_catalog/Eco-HAB/deh_new_backend_testing"

# Resolved once at import; both registries are populated on `import deepecohab`. The
# tube test is not among them: it is an auxiliary analysis the fixture runs by hand.
DF_KEYS = DataFrameRegistry.list_available()
PLOT_NAMES = PlotRegistry.list_available()


@pytest.fixture(scope="session")
def analysed_recording(tmp_path_factory):
	"""Add every catalog recording to a fresh project and analyse them.

	Session-scoped so the (heavy) add + full pipeline runs once for the module. The
	tube test is no longer a pipeline step, so it is run and sunk here the way a user
	would, which is also what makes its plot buildable below.

	Returns the first recording, which the assertions below inspect.
	"""
	if not CATALOG.is_dir():
		pytest.skip(f"catalog not available at {CATALOG}")

	metadata = sorted(CATALOG.glob("*/*.json"))
	data = sorted(CATALOG.glob("*/*.parquet"))
	if not metadata:
		pytest.skip(f"no recordings found under {CATALOG}")

	project = Project.create(
		project_name="e2e",
		experimenter="test",
		location=tmp_path_factory.mktemp("e2e_project"),
	)
	report = project.add_recordings(zip(metadata, data, strict=True))
	assert not report.failed, f"recordings rejected: {report.failed}"

	project.run_analysis()
	for recording in project.recordings:
		calculate_tube_test(recording, max_dwell=10.0, winner_behavior="BOTH").sink_parquet(
			recording.results_path / "tube_test_df.parquet"
		)

	yield project[report.added[0]]
	project.close()


@pytest.fixture(scope="session")
def store(analysed_recording) -> dict[str, pl.DataFrame]:
	"""Eager dataframes for every registered key."""
	return {key: analysed_recording.load_results(key, eager=True) for key in DF_KEYS}


@pytest.fixture(scope="session")
def context(analysed_recording) -> PlotContext:
	"""Plot context over the analysed recording, caching the tables it reads."""
	return PlotContext.from_recording(analysed_recording)


def _option_combinations(spec, context) -> list[dict]:
	"""Every combination of a plot's constrained options."""
	options = [option for option in spec.options_for(context) if option.choices]
	combinations = itertools.product(
		*[[(option.name, choice) for choice in option.choices] for option in options]
	)

	return [dict(combination) for combination in combinations] or [{}]


# --- the data structure ------------------------------------------------------


def test_main_df_schema_and_values(analysed_recording):
	main_df = analysed_recording.load_results("main_df", eager=True)
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

	cohort = set(analysed_recording.cohort.animal_tags)
	assert set(main_df["animal_id"].unique()).issubset(cohort)
	assert set(main_df["phase"].unique()).issubset(set(analysed_recording.timeline.phases))
	# main_df carries *directional* tunnel positions (e.g. c1_c2), so they come from
	# the antenna map plus "undefined", not the undirected position list.
	allowed = set(analysed_recording.layout.antenna_combinations.values()) | {"undefined"}
	assert set(main_df["position"].cast(pl.String).unique()).issubset(allowed)
	assert main_df["position"].null_count() == 0
	assert (main_df["time_spent"] >= dt.timedelta(0)).all()
	assert main_df["day"].min() >= 1
	assert main_df["datetime"].is_sorted()


# --- analysis pipeline outputs -----------------------------------------------


@pytest.mark.parametrize("key", DF_KEYS)
def test_dataframe_produced_and_nonempty(analysed_recording, key):
	"""Every registered data key was sunk to parquet and loads as a non-empty frame.

	event_bouts is the exception when the recording declares no events.
	"""
	assert (analysed_recording.results_path / f"{key}.parquet").is_file(), f"{key} not written"

	frame = analysed_recording.load_results(key)
	assert isinstance(frame, pl.LazyFrame)
	if key == "event_bouts" and not analysed_recording.events:
		return
	assert frame.select(pl.len()).collect().item() > 0, f"{key} is empty"


def test_ranking_one_rating_set_per_animal(analysed_recording):
	ranking = analysed_recording.load_results("ranking", eager=True)
	assert {"animal_id", "mu", "sigma", "ordinal", "datetime"}.issubset(set(ranking.columns))
	assert set(ranking["animal_id"].unique()).issubset(set(analysed_recording.cohort.animal_tags))
	assert ranking["sigma"].min() > 0


# --- cross-table consistency on real data ------------------------------------
# These assert relationships *between* the produced tables, which the per-step
# unit tests (single synthetic input) cannot see. They are the real-data analogue
# of the invariants in test_analysis_properties.py.


def test_no_nan_or_inf_in_any_float_column(store):
	"""No produced table carries a null, NaN or inf in any floating-point column.

	The pipeline zero-fills its grids and guards constant-metric z-scores; this
	confirms that holds across every table on real data (a stray NaN/inf would flow
	silently into plots and downstream stats).
	"""
	for key, frame in store.items():
		for column, dtype in frame.schema.items():
			if dtype in (pl.Float32, pl.Float64):
				values = frame[column]
				assert values.null_count() == 0, f"{key}.{column} has nulls"
				assert not values.is_nan().any(), f"{key}.{column} has NaN"
				assert not values.is_infinite().any(), f"{key}.{column} has inf"


def test_no_nulls_in_any_table(store):
	"""Every cell of every produced table is populated.

	A null here means a grid join missed - the failure mode behind the phase_count
	alignment bugs - so it is worth asserting across the board, not just on floats.
	"""
	for key, frame in store.items():
		assert frame.null_count().sum_horizontal().item() == 0, f"{key} has nulls"


def test_chasings_grid_reconciles_with_match_events(analysed_recording):
	"""The per-hour chasings grid sums to exactly the number of chasing events.

	chasings_df is just match_df aggregated and zero-filled onto the dense grid, so
	on real data their totals must agree and per-chaser totals must match the raw
	winners -- no event lost or invented by the grid expansion.
	"""
	match_df = analysed_recording.load_results("match_df", eager=True)
	chasings = analysed_recording.load_results("chasings_df", eager=True)

	assert chasings.filter(pl.col("chaser") == pl.col("chased")).height == 0
	assert int(chasings["chasings"].sum()) == match_df.height

	per_chaser = {
		animal: int(count)
		for animal, count in chasings.group_by("chaser").agg(pl.sum("chasings")).iter_rows()
		if count > 0
	}
	expected = {
		animal: int(count)
		for animal, count in match_df.group_by("winner").agg(pl.len()).iter_rows()
	}
	assert per_chaser == expected


def test_activity_metrics_nonnegative(analysed_recording):
	"""Occupancy, visit and solitary-time metrics are all non-negative on real data."""
	activity = analysed_recording.load_results("activity_df", eager=True)
	assert (activity["time_in_position"] >= dt.timedelta(0)).all()
	assert (activity["time_alone"] >= dt.timedelta(0)).all()
	assert (activity["visits_to_position"] >= 0).all()


def test_time_alone_never_exceeds_occupancy(analysed_recording):
	"""Solitary time can never exceed total occupancy in the same animal/position cell.

	Regression guard for the calendar-column alignment: ``_get_activity`` and
	``_get_time_alone`` must bin onto the same grid cells, so the two left-joins in
	``calculate_activity`` line up cell-for-cell and no occupancy row is dropped
	while its solitary-time counterpart is kept.
	"""
	activity = analysed_recording.load_results("activity_df", eager=True)
	offenders = activity.filter(pl.col("time_alone") > pl.col("time_in_position"))
	assert offenders.height == 0, (
		f"{offenders.height} cells have time_alone > time_in_position:\n{offenders}"
	)


def test_pairwise_meetings_unordered_and_nonnegative(analysed_recording):
	"""Pairs are stored unordered (a < b); time and encounter counts are non-negative."""
	pairwise = analysed_recording.load_results("pairwise_meetings", eager=True)
	assert (pairwise["animal_id"].cast(pl.String) < pairwise["animal_id_2"].cast(pl.String)).all()
	assert (pairwise["time_together"] >= dt.timedelta(0)).all()
	assert (pairwise["pairwise_encounters"] >= 0).all()


def test_pairwise_encounters_never_exceed_visit_sum(analysed_recording):
	"""A pair cannot meet more often than their combined visits to the cage.

	The user's invariant, on real data: the sweep must re-stitch the minute-split
	pieces of one stay rather than count each piece as a fresh encounter.
	"""
	activity = analysed_recording.load_results("activity_df", eager=True)
	pairwise = analysed_recording.load_results("pairwise_meetings", eager=True)

	visits = {
		(animal, position): count
		for animal, position, count in activity.group_by("animal_id", "position")
		.agg(pl.sum("visits_to_position"))
		.iter_rows()
	}
	offenders = [
		row
		for row in pairwise.filter(pl.col("pairwise_encounters") > 0).iter_rows(named=True)
		if row["pairwise_encounters"]
		> visits.get((row["animal_id"], row["position"]), 0)
		+ visits.get((row["animal_id_2"], row["position"]), 0)
	]
	assert not offenders, f"{len(offenders)} pairs meet more often than they visit"


def test_sociability_proportion_within_bounds(analysed_recording):
	"""proportion_together lies in [0, n_cages]; pairs are unordered.

	proportion_together sums a per-cage co-presence fraction (each <= 1) over the
	cages, so it cannot exceed the cage count or fall below zero.
	"""
	sociability = analysed_recording.load_results("incohort_sociability", eager=True)
	n_cages = len(analysed_recording.layout.cage_names)
	assert (sociability["proportion_together"] >= -1e-9).all()
	assert (sociability["proportion_together"] <= n_cages + 1e-6).all()
	assert (
		sociability["animal_id"].cast(pl.String) < sociability["animal_id_2"].cast(pl.String)
	).all()


def test_every_cohort_animal_present_in_feature_table(analysed_recording):
	"""Every cohort animal surfaces in the feature table (via the dense activity grid).

	Even an animal with no chasing or pairwise activity is present because activity_df
	is dense, so no animal silently drops out of the ML feature set.
	"""
	feature_df = analysed_recording.load_results("feature_df", eager=True)
	assert set(feature_df["animal_id"].unique()) == set(analysed_recording.cohort.animal_tags)


def test_tube_test_winners_losers_in_cohort(analysed_recording):
	"""Tube-test counts are non-negative, self-pairs absent, animals in the cohort."""
	tube_test = analysed_recording.load_results("tube_test_df", eager=True)
	cohort = set(analysed_recording.cohort.animal_tags)
	assert set(tube_test["winner"].unique()).issubset(cohort)
	assert set(tube_test["loser"].unique()).issubset(cohort)
	assert tube_test.filter(pl.col("winner") == pl.col("loser")).height == 0
	assert (tube_test["tube_test"] >= 0).all()


def test_recording_quality_accounts_for_every_registration(analysed_recording):
	"""Detected passes add up to the registrations inside the recording window.

	recording_quality is built straight off recording.data rather than a produced
	table, so this is the one place the two are reconciled. It also catches a
	registration at an antenna the layout does not name, which the grid would drop.
	"""
	start, end = analysed_recording.timeline.local_span
	registrations = (
		analysed_recording.data.filter(pl.col("datetime").is_between(start, end))
		.select(pl.len())
		.collect()
		.item()
	)
	quality = analysed_recording.load_results("recording_quality", eager=True)

	assert quality["detected"].sum() == registrations
	assert quality["miss_rate"].is_between(0, 100).all()


def test_pipeline_order_places_the_data_structure_first():
	"""The tables main_df feeds cannot be built before it."""
	order = DataFrameRegistry.step_order()
	position = {name: index for index, name in enumerate(order)}
	for step, requirements in DataFrameRegistry._requires.items():
		for requirement in requirements:
			assert position[requirement] < position[step], f"{requirement} must precede {step}"


# --- dashboard plots ---------------------------------------------------------


@pytest.mark.parametrize("plot_name", PLOT_NAMES)
def test_plot_builds_and_serializes(context, plot_name):
	"""Every plot builds and survives serialization, for every option combination.

	Serializing is the point: a figure carrying a ``Duration`` constructs happily
	and only raises once it is turned into JSON, which is what the dashboard and
	every export path do. Asserting on the Figure object alone missed that.
	"""
	spec = PlotRegistry.spec(plot_name)

	for options in _option_combinations(spec, context):
		figure = context.plot(plot_name, **options)
		assert isinstance(figure, go.Figure), f"{plot_name} {options} did not return a Figure"
		figure.to_json()


def test_plot_specs_are_serializable(context):
	"""Every spec describes itself in JSON a web client can consume."""
	descriptions = d.plot_specs(context)
	assert len(descriptions) == len(PLOT_NAMES)
	json.dumps(descriptions)


def test_every_plot_declares_the_tables_it_reads(context):
	"""A plot's `requires` names real analysis steps, all present after a full run."""
	for name in PLOT_NAMES:
		requires = PlotRegistry.spec(name).requires
		assert requires, f"{name} declares no required tables"
		unknown = set(requires) - set(DF_KEYS) - {"tube_test_df"}
		assert not unknown, f"{name} requires unregistered table(s) {sorted(unknown)}"
		assert all(table in context for table in requires)


def test_missing_table_is_reported_with_the_plot_name(context):
	"""Building a plot whose tables are absent names the plot and the tables."""

	class Empty:
		def table(self, key):
			raise AssertionError("should not be reached")

		def has(self, key):
			return False

	bare = replace(context, tables=Empty())

	with pytest.raises(ValueError, match="activity-bar"):
		bare.plot("activity-bar")


def test_animal_colors_are_stable_across_plots(context):
	"""One animal keeps one colour, whichever table names the animal column."""
	by_animal = resolve_colors(context, "animal_id").colors
	by_chaser = resolve_colors(context, "animal_id", animal_column="chaser").colors

	assert by_animal == by_chaser
	assert set(by_animal) == set(context.animal_ids)


def test_attribute_coloring_groups_animals(context):
	"""Animals sharing an attribute value share a colour."""
	for attribute in available_attributes(context):
		mapping = resolve_colors(context, attribute)
		assert set(mapping.by_animal) == set(context.animal_ids)

		for animal, category in mapping.category_by_animal.items():
			assert mapping.by_animal[animal] == mapping.colors[category]
