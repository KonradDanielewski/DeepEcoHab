"""Plotting-layer tests that need no recording on disk.

The end-to-end plot tests need the local catalog and skip without it, so the rules
the plotting layer relies on are pinned here instead: the palette, the duration
rendering, the registry's registration-time guards, and core's independence from
plotting.
"""

import datetime as dt
import json
import subprocess
import sys
from dataclasses import replace
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import plotly.graph_objects as go
import polars as pl
import pytest
import strategies

from deepecohab.plotting import (
	animals as animals_module,
	durations,
	export,
	plot_factory,
	prepare,
	theme,
)
from deepecohab.plotting.context import PlotContext
from deepecohab.plotting.prepare import Heatmap
from deepecohab.plotting.registry import PlotRegistry

ANIMALS = ["0035A", "0035B", "0035C", "0035D"]


@pytest.fixture
def context() -> PlotContext:
	"""A context over a four-animal cohort split by sex and treatment."""
	cohort = pl.DataFrame(
		{
			"animal_id": ANIMALS,
			"subject_name": ["m1", "m2", "m3", "m4"],
			"sex": ["M", "M", "F", "F"],
			"genotype": ["WT", "WT", "WT", "WT"],
			"treatment": ["vehicle", "drug", "vehicle", "drug"],
			"mouse_line": ["l"] * 4,
			"genetic_background": ["b"] * 4,
		}
	)

	return PlotContext(
		_loaded={"animals": cohort},
		animal_ids=list(ANIMALS),
		cages=["cage_1", "cage_2"],
		# As layout.positions_non_directional carries them: cages, tunnels, sentinel.
		positions=["cage_1", "cage_2", "tunnel_1", "tunnel_2", "undefined"],
		phases={"light_phase": 0.0, "dark_phase": 12.0},
		days_range=(1, 3),
		phase_range=(1, 6),
		tunnels_map={"tunnel_1_a": "tunnel_1", "tunnel_1_b": "tunnel_1"},
	)


# --- palette -----------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 4, 12, 13, 24])
def test_palette_returns_one_distinct_colour_per_value(count):
	"""Phase is cyclic, so the closing endpoint must not repeat the first colour."""
	colors = theme.sample_palette(count)

	assert len(colors) == count
	assert len(set(colors)) == count


def test_palette_is_empty_for_no_values():
	"""An empty cohort asks for no colours rather than raising."""
	assert theme.sample_palette(0) == []


def test_themes_register_without_changing_the_default():
	"""Importing the package must not restyle a user's other figures."""
	import plotly.io as pio

	assert "dark" in pio.templates
	assert "light" in pio.templates


# --- durations ---------------------------------------------------------------


def _frame(values: list[dt.timedelta]) -> pl.DataFrame:
	return pl.DataFrame({"t": pl.Series(values, dtype=pl.Duration("us"))})


@pytest.mark.parametrize(
	("value", "expected"),
	[
		(dt.timedelta(seconds=4), "seconds"),
		(dt.timedelta(minutes=5), "minutes"),
		(dt.timedelta(hours=3), "hours"),
		(dt.timedelta(days=2), "days"),
	],
)
def test_unit_follows_the_largest_value(value, expected):
	"""The unit is picked so the biggest value reads as a whole number."""
	assert durations._pick_unit(_frame([value]), "t") == expected


def test_unit_of_an_empty_column_falls_back_to_seconds():
	"""A filtered-away selection still needs a label."""
	assert durations._pick_unit(_frame([]), "t") == "seconds"


@pytest.mark.parametrize(
	("value", "unit", "expected"),
	[
		(dt.timedelta(0), "hours", "0s"),
		(dt.timedelta(milliseconds=350), "seconds", "350ms"),
		# Trimming to whole seconds would call this zero, which it is not.
		(dt.timedelta(milliseconds=350), "hours", "<1s"),
		(dt.timedelta(hours=3, minutes=7, seconds=4, microseconds=500), "hours", "3h 7m 4s"),
		(dt.timedelta(days=2, hours=1), "days", "2d 1h"),
	],
)
def test_hover_text_is_trimmed_to_the_units_resolution(value, unit, expected):
	"""Hover text keeps the precision the axis implies, and never denies a value."""
	frame, _label = durations.to_display(_frame([value]), "t", unit)

	assert frame["t_text"].item() == expected


def test_value_and_label_agree_on_the_unit():
	"""The number plotted and the unit in the axis title come from one call."""
	frame, label = durations.to_display(_frame([dt.timedelta(hours=3)]), "t", "hours")

	assert label == "<b>Time [h]</b>"
	assert frame["t"].item() == pytest.approx(3.0)


def test_to_display_replaces_the_duration_and_adds_its_text():
	"""A Duration cannot be serialized by plotly, so the column becomes a float."""
	frame, _ = durations.to_display(_frame([dt.timedelta(hours=2)]), "t", "hours")

	assert frame.schema["t"] == pl.Float64
	assert frame["t_text"].to_list() == ["2h"]


# --- scope -------------------------------------------------------------------


def scoped_proportion(context, scope, rows, phase_seconds: float = 100.0) -> float:
	"""proportion_together for one pair at one scope, from (position, seconds) rows."""
	phase_enum = pl.Enum(["light_phase", "dark_phase"])
	pairwise = pl.DataFrame(
		{
			"phase": pl.Series(["light_phase"] * len(rows), dtype=phase_enum),
			"day": pl.Series([1] * len(rows), dtype=pl.UInt16),
			"phase_count": pl.Series([1] * len(rows), dtype=pl.UInt16),
			"hour": pl.Series([0] * len(rows), dtype=pl.UInt8),
			"position": pl.Series([row[0] for row in rows], dtype=pl.Categorical),
			"animal_id": pl.Series([ANIMALS[0]] * len(rows), dtype=pl.Enum(ANIMALS)),
			"animal_id_2": pl.Series([ANIMALS[1]] * len(rows), dtype=pl.Enum(ANIMALS)),
			"time_together": pl.Series(
				[dt.timedelta(seconds=row[1]) for row in rows], dtype=pl.Duration("us")
			),
		}
	)
	phase_durations = pl.DataFrame(
		{
			"phase": pl.Series(["light_phase"], dtype=phase_enum),
			"phase_count": pl.Series([1], dtype=pl.UInt16),
			"duration": pl.Series([dt.timedelta(seconds=phase_seconds)], dtype=pl.Duration("us")),
		}
	)
	scoped = replace(
		context,
		_loaded={"pairwise_meetings": pairwise, "phase_durations": phase_durations},
	)

	return prepare._proportion_together(scoped, scope).collect()["proportion_together"].item()


def test_tunnels_are_the_positions_that_are_neither_cages_nor_undefined(context):
	"""Tunnels are derived, so a context never has to state them twice."""
	assert context.tunnels == ["tunnel_1", "tunnel_2"]


@pytest.mark.parametrize(
	("scope", "expected"),
	[
		("cages", ["cage_1", "cage_2"]),
		("tunnels", ["tunnel_1", "tunnel_2"]),
		("all", ["cage_1", "cage_2", "tunnel_1", "tunnel_2"]),
	],
)
def test_scope_never_selects_the_undefined_sentinel(context, scope, expected):
	"""``undefined`` is not a place, so no scope may attribute a measure to it."""
	assert context.scope_positions(scope) == expected


@pytest.mark.parametrize(
	("scope", "expected"),
	[
		("cages", {"cage_1"}),
		("tunnels", {"tunnel_1"}),
		("all", {"cage_1", "tunnel_1", "undefined"}),
	],
)
def test_activity_scope_keeps_undefined_only_at_all(context, scope, expected):
	"""Activity shows where time went unplaced, so ``all`` keeps the sentinel."""
	positions = ["cage_1", "tunnel_1", "undefined"]
	activity_df = pl.DataFrame(
		{
			"phase": ["light_phase"] * 3,
			"day": [1] * 3,
			"animal_id": [ANIMALS[0]] * 3,
			"position": pl.Series(positions, dtype=pl.Categorical),
			"visits_to_position": [1] * 3,
			"time_in_position": pl.Series([dt.timedelta(seconds=10)] * 3, dtype=pl.Duration("us")),
		}
	)
	scoped = replace(context, _loaded={**context._loaded, "activity_df": activity_df})

	figure = PlotRegistry.build("activity-bar", scoped, scope=scope)

	assert {x for trace in figure.data for x in trace.x} == expected


def test_unknown_scope_is_rejected(context):
	"""A typo names a scope that would silently select nothing."""
	with pytest.raises(ValueError, match="scope must be one of"):
		context.scope_positions("cage")


def test_proportion_together_counts_only_the_scoped_positions(context):
	"""The scoped value is time together over phase duration, summed within the scope.

	At ``scope="cages"`` this is the arithmetic ``incohort_sociability`` stores (20/100),
	which is what lets the two agree while only one of them can see tunnels.
	"""
	rows = [("cage_1", 20.0), ("tunnel_1", 50.0)]

	assert scoped_proportion(context, "cages", rows) == pytest.approx(0.2)
	assert scoped_proportion(context, "tunnels", rows) == pytest.approx(0.5)
	assert scoped_proportion(context, "all", rows) == pytest.approx(0.7)


@pytest.mark.parametrize(
	("plot", "expected", "default"),
	[
		("time-alone-bar", ("all", "cages", "tunnels"), "all"),
		("cage-preference", ("all", "cages", "tunnels"), "all"),
		("cohort-heatmap", ("all", "cages", "tunnels"), "all"),
		("social-stability", ("all", "cages", "tunnels"), "all"),
		("network-sociability", ("all", "cages", "tunnels"), "all"),
		("time-per-cage-heatmap", ("cages", "tunnels"), "cages"),
		("cage-preference-evolution", ("cages", "tunnels"), "cages"),
		("sociability-heatmap", ("cages", "tunnels"), "cages"),
	],
)
def test_faceted_plots_offer_no_all_scope(plot, expected, default):
	"""A faceted heatmap's panels share one colour axis, so it shows one kind at a time.

	Cage dwell runs to hours and tunnel dwell to seconds, so mixing them on that shared
	scale renders the tunnel panels a uniform dark. Which plots take ``FacetScope`` and
	which take ``Scope`` is carried by the annotation alone, and a typo there would
	silently restore the unreadable option - so the split is pinned rather than reviewed.
	A faceted plot keeps ``"cages"`` as its default; every other scoped plot now opens
	on ``"all"``.
	"""
	scope = next(option for option in PlotRegistry.spec(plot).options if option.name == "scope")

	assert scope.choices == expected
	assert scope.default == default


# --- colours -----------------------------------------------------------------


def test_only_varying_attributes_are_offered(context):
	"""A cohort with one genotype should not offer to colour by genotype."""
	available = animals_module.available_attributes(context)

	assert available[0] == "animal_id"
	assert "sex" in available and "treatment" in available
	assert "genotype" not in available


def test_animal_colours_do_not_depend_on_the_animal_column(context):
	"""A tag keeps its colour whether the table calls it animal_id, chaser or winner."""
	base = animals_module.resolve_colors(context, "animal_id")
	chaser = animals_module.resolve_colors(context, "animal_id", animal_column="chaser")

	assert base.colors == chaser.colors
	assert chaser.column == "chaser"


def test_attribute_colours_are_shared_within_a_group(context):
	"""Two animals of the same sex get one colour, and the legend one entry."""
	mapping = animals_module.resolve_colors(context, "sex")

	assert mapping.categories == ["F", "M"]
	assert mapping.by_animal["0035A"] == mapping.by_animal["0035B"]
	assert mapping.by_animal["0035A"] != mapping.by_animal["0035C"]


def test_colours_survive_dropping_an_animal(context):
	"""Colours come from the cohort, so filtering must not recolour the rest."""
	full = animals_module.resolve_colors(context, "animal_id").colors

	smaller = PlotContext(
		_loaded=context._loaded,
		animal_ids=ANIMALS[:2],
		cages=context.cages,
		positions=context.positions,
		phases=context.phases,
		days_range=context.days_range,
		phase_range=context.phase_range,
		tunnels_map=context.tunnels_map,
	)
	subset = animals_module.resolve_colors(smaller, "animal_id").colors

	# The subset samples its own smaller palette; what must hold is that a plot
	# built from the whole cohort keeps every animal on its own colour.
	assert len(subset) == 2
	assert len(set(full.values())) == len(ANIMALS)


def test_unknown_colour_column_is_rejected(context):
	"""A typo names a column that does not exist, so it fails at the call."""
	with pytest.raises(ValueError, match="color_by"):
		animals_module.resolve_colors(context, "colour")


def test_ordering_stays_in_cohort_order(context):
	"""Colouring by an attribute recolours the plot; it never reorders the animals."""
	assert animals_module.resolve_colors(context, "sex").order == list(context.animal_ids)


def test_legend_collapses_to_one_entry_per_group(context):
	"""Per-animal traces stay, but the legend names each group once."""
	mapping = animals_module.resolve_colors(context, "sex")
	figure = go.Figure([go.Scatter(x=[0], y=[0], name=animal) for animal in ANIMALS])

	animals_module.collapse_legend(figure, mapping)

	assert [trace.name for trace in figure.data] == ["M", "M", "F", "F"]
	assert [bool(trace.showlegend) for trace in figure.data] == [True, False, True, False]
	# and the categories' colours are declared, for the recording page's palette swap
	assert list(figure.layout.colorway) == list(mapping.colors.values())


# --- registry ----------------------------------------------------------------


@pytest.fixture
def clean_registry():
	"""Register throwaway plots without leaking them into other tests."""
	saved = dict(PlotRegistry._specs)
	yield PlotRegistry
	PlotRegistry._specs.clear()
	PlotRegistry._specs.update(saved)


def test_option_without_a_default_is_rejected(clean_registry):
	"""Every option needs a default so a plot can be built with no arguments."""
	with pytest.raises(TypeError, match="no default"):

		@clean_registry.register("broken", title="Broken", requires=())
		def broken(context, *, mode) -> go.Figure:
			"""Broken."""
			return go.Figure()


def test_default_outside_its_literal_is_rejected(clean_registry):
	"""A default that no choice allows would fail on every build, so it fails here."""
	with pytest.raises(ValueError, match="not one of"):

		@clean_registry.register("broken", title="Broken", requires=())
		def broken(context, *, mode: Literal["a", "b"] = "c") -> go.Figure:
			"""Broken."""
			return go.Figure()


def test_resolver_for_an_unknown_option_is_rejected(clean_registry):
	"""A misspelt resolver key would silently never apply."""
	with pytest.raises(TypeError, match="unknown"):

		@clean_registry.register(
			"broken", title="Broken", requires=(), dynamic_choices={"colour_by": lambda c: ["x"]}
		)
		def broken(context, *, color_by: str = "animal_id") -> go.Figure:
			"""Broken."""
			return go.Figure()


def test_literal_and_resolver_on_one_option_is_rejected(clean_registry):
	"""The annotation would be discarded, which is certainly a mistake."""
	with pytest.raises(TypeError, match="Literal"):

		@clean_registry.register(
			"broken", title="Broken", requires=(), dynamic_choices={"mode": lambda c: ["x"]}
		)
		def broken(context, *, mode: Literal["a", "b"] = "a") -> go.Figure:
			"""Broken."""
			return go.Figure()


def test_resolved_default_reaches_the_builder(clean_registry, context):
	"""A narrowed option must pass its resolved value, not its declared one."""
	seen = {}

	@clean_registry.register(
		"demo",
		title="Demo",
		requires=("animals",),
		dynamic_choices={"color_by": animals_module.available_attributes},
	)
	def demo(context, *, color_by: str = "genotype") -> go.Figure:
		"""Demo."""
		seen["color_by"] = color_by
		return go.Figure()

	clean_registry.build("demo", context)

	# genotype does not vary in this cohort, so the resolver drops it.
	assert seen["color_by"] == "animal_id"


def test_value_outside_its_choices_is_rejected(clean_registry, context):
	"""The choices a spec advertises are enforced, not merely documented."""

	@clean_registry.register("demo", title="Demo", requires=("animals",))
	def demo(context, *, agg: Literal["sum", "mean"] = "sum") -> go.Figure:
		"""Demo."""
		return go.Figure()

	with pytest.raises(ValueError, match="must be one of"):
		clean_registry.build("demo", context, agg="median")


def test_missing_required_table_names_the_plot(clean_registry, context):
	"""A plot whose step has not run says so, rather than failing deep inside polars."""

	@clean_registry.register("demo", title="Demo", requires=("chasings_df",))
	def demo(context) -> go.Figure:
		"""Demo."""
		return go.Figure()

	with pytest.raises(ValueError, match="chasings_df"):
		clean_registry.build("demo", context)


def test_unknown_plot_raises(clean_registry, context):
	"""An unregistered name is an error, not an empty figure."""
	with pytest.raises(KeyError):
		clean_registry.build("nope", context)


def test_unit_option_flattens_its_literal_union():
	"""``unit: Unit | Literal["auto"]`` is a union of two Literals, not one."""
	option = next(o for o in PlotRegistry.spec("time-alone-bar").options if o.name == "unit")

	assert set(option.choices) == {"seconds", "minutes", "hours", "days", "auto"}
	assert option.default == "auto"


def test_phase_type_resolves_from_the_cohorts_own_phases(context):
	"""A multi-select option keeps its list default, narrowed to what still applies."""
	described = PlotRegistry.spec("time-alone-bar").options_for(context)
	option = next(o for o in described if o.name == "phase_type")

	assert option.choices == ("light_phase", "dark_phase")
	assert option.default == ["light_phase", "dark_phase"]


def test_hours_range_is_absent_from_whole_day_plots():
	"""Rankings, incohort_sociability and the phase_durations normaliser have no hour column."""
	for name in ("ranking-line", "cohort-heatmap", "social-stability", "network-sociability"):
		options = {option.name for option in PlotRegistry.spec(name).options}
		assert "hours_range" not in options, name

	for name in ("activity-bar", "activity-line", "metrics-polar-line"):
		options = {option.name for option in PlotRegistry.spec(name).options}
		assert "hours_range" in options, name


def test_hours_range_narrows_the_hourly_scaffold(context):
	"""A narrowed hours window drops those hours instead of zero-filling them."""
	frame = pl.DataFrame(
		{
			"animal_id": pl.Series(["0035A"], dtype=pl.Enum(ANIMALS)),
			"day": pl.Series([1], dtype=pl.Int16),
			"hour": pl.Series([5], dtype=pl.Int8),
		}
	)

	with_table = replace(context, _loaded={"t": frame})
	full = prepare.prep_hourly_line(with_table, (1, 1), "day", "t", "animal_id", pl.len())
	narrowed = prepare.prep_hourly_line(
		with_table, (1, 1), "day", "t", "animal_id", pl.len(), hours_range=(3, 6)
	)

	assert full["hour"].unique().sort().to_list() == list(range(24))
	assert narrowed["hour"].unique().sort().to_list() == [3, 4, 5, 6]


def test_polar_z_scores_within_the_selection_however_it_is_narrowed(context):
	"""Phase, hours and days all narrow the rows the z-scores are centred on."""
	rows = [
		(animal, day, hour, "dark_phase" if hour >= 12 else "light_phase", 2 * day - (hour < 12))
		for animal in ANIMALS[:2]
		for day in (1, 2)
		for hour in range(24)
	]
	frame = pl.DataFrame(
		rows, schema=["animal_id", "day", "hour", "phase", "phase_count"], orient="row"
	).with_columns(
		metric=pl.lit("activity"),
		value=pl.col("hour").cast(pl.Float64)
		* pl.col("day")
		* (1 + (pl.col("animal_id") == "0035B")),
		exposure=pl.lit(1.0),
	)
	with_table = replace(context, _loaded={"feature_df": frame})
	phases = ["light_phase", "dark_phase"]

	by_phase = prepare.prep_polar(with_table, (1, 1), ["dark_phase"], "day")
	by_hours = prepare.prep_polar(with_table, (1, 1), phases, "day", hours_range=(12, 23))

	assert by_phase.equals(by_hours)
	assert by_phase["mean"].sum() == pytest.approx(0)


# --- events ------------------------------------------------------------------


def bout_cells(cells: list[tuple[str, str | None, int, int]]) -> pl.DataFrame:
	"""An event_bouts table of ``(event, position, day, hour)`` cells."""
	return pl.DataFrame(
		cells,
		schema={
			"event": pl.Enum(["injection", "social"]),
			"position": pl.String,
			"day": pl.UInt16,
			"hour": pl.UInt8,
		},
		orient="row",
	)


def spans(
	context: PlotContext,
	bouts: pl.DataFrame | None,
	x: Literal["datetime", "hour", "day", "phase_count"] = "hour",
) -> list[tuple]:
	"""Event spans over days 1-2 of the window, sorted for comparison."""
	with_bouts = replace(context, _loaded={"event_bouts": bouts} if bouts is not None else {})

	return prepare.prep_event_spans(with_bouts, (1, 2), "day", x).sort("event", "x0").rows()


def test_phase_onsets_are_measured_from_the_start_onset():
	"""The hour axis counts from the start_from onset, so the onset lines must too."""
	recording = strategies.analysis_recording(
		start="2023-05-24 13:00:00",
		phases={"light_phase": dt.time(1, 0), "dark_phase": dt.time(13, 0)},
		start_from="dark_phase",
	)

	assert PlotContext.from_recording(recording).phases == {"light_phase": 12.0, "dark_phase": 0.0}


def test_only_the_phase_switch_gets_a_line():
	"""The hour axis opens on the start phase, so its onset is the axis edge."""
	figure = go.Figure()
	plot_factory._phase_markers(figure, {"light_phase": 13.0, "dark_phase": 0.0})

	assert [shape.x0 for shape in figure.layout.shapes] == [13.0]
	assert [shape.line.width for shape in figure.layout.shapes] == [1.5]
	assert figure.layout.annotations == ()


def test_consecutive_bins_merge_into_one_span(context):
	"""The same hour on several days folds onto the one hour axis."""
	bouts = bout_cells(
		[("social", "cage_1", 1, 13), ("social", "cage_1", 1, 14), ("social", "cage_1", 2, 13)]
	)

	assert spans(context, bouts) == [("social", "cage_1", 12.5, 14.5)]


def test_span_wrapping_past_midnight_splits_in_two(context):
	bouts = bout_cells([("injection", None, 1, 23), ("injection", None, 2, 0)])

	assert spans(context, bouts) == [
		("injection", None, -0.5, 0.5),
		("injection", None, 22.5, 23.5),
	]


def test_day_axis_spans_every_day_touched(context):
	bouts = bout_cells([("social", None, 1, 23), ("social", None, 2, 0)])

	assert spans(context, bouts, "day") == [("social", None, 0.5, 2.5)]


def test_bins_outside_the_window_are_dropped(context):
	assert spans(context, bout_cells([("social", None, 3, 5)])) == []


def test_recording_analysed_before_events_existed_has_no_spans(context):
	assert spans(context, None) == []


def test_datetime_axis_spans_the_bout_on_the_wall_clock(context):
	"""Plotly serializes a trace's datetimes without their zone, so spans drop it too."""
	start = dt.datetime(2023, 5, 24, 23, 30, tzinfo=ZoneInfo("Europe/Warsaw"))
	end = dt.datetime(2023, 5, 25, 0, 30, tzinfo=ZoneInfo("Europe/Warsaw"))
	bouts = bout_cells([("injection", None, 1, 23), ("injection", None, 2, 0)]).with_columns(
		start=pl.lit(start), end=pl.lit(end)
	)

	assert spans(context, bouts, "datetime") == [
		("injection", None, dt.datetime(2023, 5, 24, 23, 30), dt.datetime(2023, 5, 25, 0, 30))
	]


def test_faceted_heatmap_stacks_one_panel_per_row_in_order():
	"""A 2x2 wrap swapped titles between rows; one column keeps facet and row aligned."""
	heatmap = Heatmap(
		values=np.arange(3 * 2 * 4).reshape(3, 2, 4),
		text=None,
		label="Time spent",
		x=list(range(4)),
		y=["a", "b"],
		facets=["cage_1", "cage_2", "cage_3"],
	)

	figure = plot_factory._faceted_heatmap(heatmap, "T", "X", "Y", ("Hour", "Animal ID"))

	titles = [note.text for note in figure.layout.annotations]
	assert titles == ["<b>Cage 1</b>", "<b>Cage 2</b>", "<b>Cage 3</b>"]
	assert [trace.yaxis for trace in figure.data] == ["y", "y2", "y3"]
	assert [trace.z.tolist() for trace in figure.data] == [
		values.tolist() for values in heatmap.values
	]


def test_faceted_grid_heatmap_lays_panels_out_in_one_row():
	"""Pair matrices are square, so a wrapped grid left dead space under every row."""
	heatmap = Heatmap(
		values=np.arange(4 * 2 * 2).reshape(4, 2, 2),
		text=None,
		label="Time together",
		x=["a", "b"],
		y=["a", "b"],
		facets=["cage_1", "cage_2", "cage_3", "cage_4"],
	)

	figure = plot_factory._faceted_heatmap(heatmap, "T", "", "", ("X", "Y"), square=True, grid=True)

	assert [trace.xaxis for trace in figure.data] == ["x", "x2", "x3", "x4"]
	domains = {figure.layout[trace.yaxis.replace("y", "yaxis")].domain for trace in figure.data}
	assert len(domains) == 1


def test_positioned_event_is_drawn_only_on_its_cages_panel():
	heatmap = Heatmap(
		values=np.zeros((2, 1, 24)),
		text=None,
		label="Time spent",
		x=list(range(24)),
		y=["0035A"],
		facets=["cage_1", "cage_2"],
	)
	bouts = pl.DataFrame(
		{
			"event": ["social", "injection"],
			"position": ["cage_1", None],
			"x0": [12.5, -0.5],
			"x1": [13.5, 0.5],
		},
		schema_overrides={"event": pl.Enum(["injection", "social"])},
	)

	figure = plot_factory.plot_time_spent_per_cage(heatmap, "hourly", bouts)
	panels = {trace.xaxis: facet for facet, trace in zip(heatmap.facets, figure.data, strict=True)}
	drawn = sorted(
		(shape.label.text, panels[shape.xref])
		for shape in figure.layout.shapes
		if shape.name == "event-label"
	)

	assert drawn == [("injection", "cage_1"), ("injection", "cage_2"), ("social", "cage_1")]


def test_one_events_cages_share_a_span_on_a_plot_without_panels(context):
	"""Counterbalanced stimulus sides at the same hours would otherwise stack two labels."""
	ranks = pl.DataFrame({"animal_id": ANIMALS, "day": [1] * 4, "rank": [1.0, 2.0, 3.0, 4.0]})
	bouts = pl.DataFrame(
		{
			"event": ["social", "social"],
			"position": ["cage_3", "cage_1"],
			"x0": [0.5, 0.5],
			"x1": [1.5, 1.5],
		},
		schema_overrides={"event": pl.Enum(["injection", "social"])},
	)
	mapping = animals_module.resolve_colors(context, "animal_id")

	figure = plot_factory.plot_ranking_stability(ranks, mapping, "day", bouts)

	labels = [shape.label.text for shape in figure.layout.shapes if shape.name == "event-label"]
	assert labels == ["social (cage_1, cage_3)"]


def test_datetime_spans_are_written_like_the_trace_they_mark(context):
	"""Plotly writes a tz-aware trace as naive wall-clock time, so a span must be too.

	Should plotly or polars start writing the offset, spans and data would drift apart.
	"""
	moment = dt.datetime(2023, 5, 24, 13, 0, 30, tzinfo=ZoneInfo("Europe/Warsaw"))
	ranking = pl.DataFrame(
		{"animal_id": [ANIMALS[0]], "datetime": [moment], "ordinal": [1.0]},
		schema={
			"animal_id": pl.String,
			"datetime": pl.Datetime("us", "Europe/Warsaw"),
			"ordinal": pl.Float64,
		},
	)
	bouts = bout_cells([("injection", None, 1, 13)]).with_columns(
		start=pl.lit(moment), end=pl.lit(moment + dt.timedelta(minutes=10))
	)
	with_bouts = replace(context, _loaded={"event_bouts": bouts} if bouts is not None else {})
	mapping = animals_module.resolve_colors(context, "animal_id")

	figure = plot_factory.plot_ranking_line(
		ranking, mapping, prepare.prep_event_spans(with_bouts, (1, 2), "day", "datetime")
	)
	payload = json.loads(figure.to_json())

	assert payload["layout"]["shapes"][0]["x0"] == payload["data"][0]["x"][0]


def test_timeline_ships_wall_clock_numbers_and_reads_back_as_dates():
	"""The timeline's axes are typed arrays, but its hover and CSV still name dates and animals."""
	zone = "Europe/Warsaw"

	def at(hour: int) -> dt.datetime:
		return dt.datetime(2023, 5, 24, hour, tzinfo=ZoneInfo(zone))

	visits = pl.DataFrame(
		{
			"animal_id": ["0035B", "0035A", "0035A"],
			"position": ["cage_1", "cage_1", "tunnel_1"],
			"start": [at(1), at(2), at(4)],
			"end": [at(2), at(3), at(5)],
		},
		schema_overrides={"start": pl.Datetime("us", zone), "end": pl.Datetime("us", zone)},
	)
	no_spans = pl.DataFrame(schema={"event": pl.String, "position": pl.String})

	figure = plot_factory.plot_timeline(visits, ANIMALS[:2], ["cage_1", "tunnel_1"], no_spans)
	payload = json.loads(figure.to_json())

	assert [(t["name"], t["meta"], t["showlegend"]) for t in payload["data"]] == [
		("cage_1", "0035A", True),
		("cage_1", "0035B", False),
		("tunnel_1", "0035A", True),
	]
	assert all("bdata" in trace["x"] and "bdata" in trace["y"] for trace in payload["data"])
	assert payload["layout"]["xaxis"]["type"] == "date"

	csv = export.figure_data_csv(payload)
	assert csv is not None
	assert pl.read_csv(csv.encode()).rows() == [
		("cage_1", "2023-05-24T02:00:00.000", "0035A"),
		("cage_1", "2023-05-24T03:00:00.000", "0035A"),
		("cage_1", "2023-05-24T01:00:00.000", "0035B"),
		("cage_1", "2023-05-24T02:00:00.000", "0035B"),
		("tunnel_1", "2023-05-24T04:00:00.000", "0035A"),
		("tunnel_1", "2023-05-24T05:00:00.000", "0035A"),
	]


# --- quality -------------------------------------------------------------------


def test_quality_heatmap_pivots_miss_rate_by_animal_and_antenna(context):
	quality = pl.DataFrame(
		{
			"animal_id": [ANIMALS[0], ANIMALS[0], ANIMALS[1], ANIMALS[1]],
			"antenna": [1, 2, 1, 2],
			"detected": [10, 10, 10, 10],
			"missed": [0, 5, 2, 0],
			"miss_rate": [0.0, 33.3, 16.7, 0.0],
		}
	)
	with_quality = replace(context, _loaded={"recording_quality": quality})

	matrix, antennas = prepare.prep_quality_heatmap(with_quality, [ANIMALS[0], ANIMALS[1]])

	assert antennas == ["1", "2"]
	assert matrix.tolist() == [[0.0, 33.3], [16.7, 0.0]]


def test_quality_by_antenna_pools_counts_rather_than_averaging_rates():
	"""A pooled rate weighs by how much was actually seen, not by cell count."""
	quality = pl.DataFrame(
		{
			"animal_id": ["a", "a", "b", "b"],
			"antenna": [1, 2, 1, 2],
			# Antenna 1: 1 missed of 1001. Antenna 2: 1 missed of 2 - a high per-cell
			# rate that must not outweigh antenna 1's much larger sample.
			"detected": [1000, 1, 0, 1],
			"missed": [1, 0, 0, 1],
			"miss_rate": [0.1, 0.0, 0.0, 50.0],
		}
	)
	context = PlotContext(
		_loaded={"recording_quality": quality},
		animal_ids=["a", "b"],
		cages=[],
		positions=[],
		phases={},
		days_range=(1, 1),
		phase_range=(1, 1),
		tunnels_map={},
	)

	frame = prepare.prep_quality_by_antenna(context)

	assert frame.sort("antenna")["miss_rate"].to_list() == pytest.approx(
		[1 / 1001 * 100, 1 / 3 * 100]
	)


def test_ranking_distribution_is_the_same_for_a_window_in_days_or_phases(context):
	"""The window only picks which matches count, so its unit must not change the fit."""
	# One row per animal after each match, in replay order; phase 2 has no matches.
	ranking = pl.DataFrame(
		{
			"animal_id": ["0035A", "0035B"] * 3,
			"mu": [26.0, 24.0, 28.0, 22.0, 30.0, 20.0],
			"sigma": [8.0] * 6,
			"day": [1, 1, 2, 2, 2, 2],
			"phase_count": [1, 1, 3, 3, 4, 4],
		}
	)
	context = replace(context, _loaded={"ranking": ranking})

	def fit(days_range, granularity):
		return prepare.prep_ranking_distribution(context, days_range, granularity)

	assert fit((1, 2), "day").equals(fit((1, 4), "phase_count"))
	# The nearest phase with matches after the window must not stand in for its empty end.
	assert fit((1, 1), "day").equals(fit((1, 2), "phase_count"))


# --- network graphs ----------------------------------------------------------


def test_dominance_node_size_is_the_animals_own_ordinal():
	"""Sizes are looked up by animal id; the ranking table is in no particular order."""
	connections = pl.DataFrame({"source": ["a", "b"], "target": ["b", "c"], "chasings": [3.0, 1.0]})
	nodes = pl.DataFrame({"animal_id": ["c", "a", "b"], "ordinal": [10.0, 30.0, 20.0]})

	figure = plot_factory.plot_network_graph(
		connections, nodes, ["a", "b", "c"], ["#111", "#222", "#333"], "chasings", "circular"
	)

	assert figure.data[-1].marker.size == (30.0, 20.0, 10.0)


def test_sociability_nodes_are_uniform_without_a_ranking():
	"""An undirected graph carries no ranking, so every node takes the same size."""
	connections = pl.DataFrame({"source": ["a"], "target": ["b"], "proportion_together": [0.5]})

	figure = plot_factory.plot_network_graph(
		connections, None, ["a", "b"], ["#111", "#222"], "proportion_together", "circular"
	)

	assert figure.data[-1].marker.size == (30, 30)


# --- module boundaries -------------------------------------------------------


def test_core_does_not_import_plotting():
	"""The analysis pipeline must be usable without plotly installed."""
	probe = (
		"import sys;"
		"import deepecohab;"
		"import deepecohab.core.antenna_analysis;"
		"import deepecohab.core.recording_pipeline;"
		"print('plotly' in sys.modules, 'networkx' in sys.modules)"
	)
	result = subprocess.run(
		[sys.executable, "-c", probe], capture_output=True, text=True, check=True
	)

	assert result.stdout.strip() == "False False"


def test_importing_the_package_leaves_the_plotly_default_theme_alone():
	"""Importing a package should not restyle every other figure in the session."""
	probe = (
		"import plotly.io as pio;"
		"before = pio.templates.default;"
		"import deepecohab;"
		"print(before == pio.templates.default)"
	)
	result = subprocess.run(
		[sys.executable, "-c", probe], capture_output=True, text=True, check=True
	)

	assert result.stdout.strip() == "True"
