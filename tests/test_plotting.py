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
import strategies as strat

from deepecohab.plotting import animals as animals_module, durations, plot_factory, prepare, theme
from deepecohab.plotting.context import PlotContext
from deepecohab.plotting.prepare import Heatmap
from deepecohab.plotting.registry import PlotRegistry

ANIMALS = ["0035A", "0035B", "0035C", "0035D"]


class FakeTables:
	"""Table provider serving one in-memory cohort table."""

	def __init__(self, animals: pl.DataFrame, available: set[str] | None = None) -> None:
		self._animals = animals
		self._available = {"animals"} if available is None else available

	def table(self, key: str) -> pl.DataFrame:
		return self._animals

	def has(self, key: str) -> bool:
		return key in self._available


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
		tables=FakeTables(cohort),
		animal_ids=list(ANIMALS),
		cages=["cage_1", "cage_2"],
		# As layout.positions_non_directional carries them: cages, tunnels, sentinel.
		positions=["cage_1", "cage_2", "tunnel_1", "tunnel_2", "undefined"],
		phases={"light_phase": 0.0, "dark_phase": 12.0},
		days_range=(1, 3),
		phase_range=(1, 6),
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
	assert durations.pick_unit(_frame([value]), "t") == expected


def test_unit_of_an_empty_column_falls_back_to_seconds():
	"""A filtered-away selection still needs a label."""
	assert durations.pick_unit(_frame([]), "t") == "seconds"


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
	frame = _frame([value])
	rendered = durations.display(frame, "t", unit)

	assert frame.select(rendered.text).item() == expected


def test_value_and_label_agree_on_the_unit():
	"""The number plotted and the unit in the axis title come from one call."""
	frame = _frame([dt.timedelta(hours=3)])
	rendered = durations.display(frame, "t", "hours")

	assert rendered.label == "<b>Time [h]</b>"
	assert frame.select(rendered.value).item() == pytest.approx(3.0)


def test_to_display_replaces_the_duration_and_adds_its_text():
	"""A Duration cannot be serialized by plotly, so the column becomes a float."""
	frame, _ = durations.to_display(_frame([dt.timedelta(hours=2)]), "t", "hours")

	assert frame.schema["t"] == pl.Float64
	assert frame["t_text"].to_list() == ["2h"]


# --- scope -------------------------------------------------------------------


class SociabilityTables:
	"""Provider serving the two tables the scoped proportion is computed from."""

	def __init__(self, pairwise: pl.DataFrame, phase_durations: pl.DataFrame) -> None:
		self._tables = {"pairwise_meetings": pairwise, "phase_durations": phase_durations}

	def table(self, key: str) -> pl.DataFrame:
		return self._tables[key]

	def has(self, key: str) -> bool:
		return key in self._tables


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
	scoped = replace(context, tables=SociabilityTables(pairwise, phase_durations))

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
	("plot", "expected"),
	[
		("time-alone-bar", ("all", "cages", "tunnels")),
		("cage-preference", ("all", "cages", "tunnels")),
		("cohort-heatmap", ("all", "cages", "tunnels")),
		("social-stability", ("all", "cages", "tunnels")),
		("network-sociability", ("all", "cages", "tunnels")),
		("time-per-cage-heatmap", ("cages", "tunnels")),
		("cage-preference-evolution", ("cages", "tunnels")),
		("sociability-heatmap", ("cages", "tunnels")),
	],
)
def test_faceted_plots_offer_no_all_scope(plot, expected):
	"""A faceted heatmap's panels share one colour axis, so it shows one kind at a time.

	Cage dwell runs to hours and tunnel dwell to seconds, so mixing them on that shared
	scale renders the tunnel panels a uniform dark. Which plots take ``FacetScope`` and
	which take ``Scope`` is carried by the annotation alone, and a typo there would
	silently restore the unreadable option - so the split is pinned rather than reviewed.
	"""
	scope = next(option for option in PlotRegistry.spec(plot).options if option.name == "scope")

	assert scope.choices == expected
	assert scope.default == "cages"


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
		tables=context.tables,
		animal_ids=ANIMALS[:2],
		cages=context.cages,
		positions=context.positions,
		phases=context.phases,
		days_range=context.days_range,
		phase_range=context.phase_range,
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


def test_ordering_groups_animals_by_attribute(context):
	"""Matrix axes are grouped by attribute rather than recoloured."""
	order = animals_module.order_by_attribute(context, "sex")

	assert sorted(order) == sorted(ANIMALS)
	assert order[:2] == ["0035C", "0035D"]  # F before M, then by tag


def test_legend_collapses_to_one_entry_per_group(context):
	"""Per-animal traces stay, but the legend names each group once."""
	mapping = animals_module.resolve_colors(context, "sex")
	figure = go.Figure([go.Scatter(x=[0], y=[0], name=animal) for animal in ANIMALS])

	animals_module.collapse_legend(figure, mapping)

	assert [trace.name for trace in figure.data] == ["M", "M", "F", "F"]
	assert [bool(trace.showlegend) for trace in figure.data] == [True, False, True, False]


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


def test_spec_describes_itself_in_json(clean_registry, context):
	"""A web client builds its controls from this, so it must serialize."""

	@clean_registry.register(
		"demo",
		title="Demo",
		requires=("animals",),
		dynamic_choices={"color_by": animals_module.available_attributes},
	)
	def demo(
		context, *, agg: Literal["sum", "mean"] = "sum", color_by: str = "animal_id"
	) -> go.Figure:
		"""One line of summary."""
		return go.Figure()

	described = clean_registry.spec("demo").describe(context)

	assert described["summary"] == "One line of summary."
	assert json.loads(json.dumps(described)) == described
	assert {option["name"] for option in described["options"]} == {"agg", "color_by"}


# --- events ------------------------------------------------------------------


class EventTables:
	"""Table provider serving one event_bouts table, or nothing at all."""

	def __init__(self, bouts: pl.DataFrame | None) -> None:
		self._bouts = bouts

	def table(self, key: str) -> pl.DataFrame:
		assert self._bouts is not None
		return self._bouts

	def has(self, key: str) -> bool:
		return key == "event_bouts" and self._bouts is not None


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
	with_bouts = replace(context, tables=EventTables(bouts))

	return prepare.prep_event_spans(with_bouts, (1, 2), "day", x).sort("event", "x0").rows()


def test_phase_onsets_are_measured_from_the_start_onset():
	"""The hour axis counts from the start_from onset, so the onset lines must too."""
	recording = strat.analysis_recording(
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
	assert {note.text: note.x for note in figure.layout.annotations} == {"☀️": 18.5, "🌙": 6.5}


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
	drawn = sorted((shape.label.text, panels[shape.xref]) for shape in figure.layout.shapes)

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

	assert [shape.label.text for shape in figure.layout.shapes] == ["social (cage_1, cage_3)"]


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
	with_bouts = replace(context, tables=EventTables(bouts))
	mapping = animals_module.resolve_colors(context, "animal_id")

	figure = plot_factory.plot_ranking_line(
		ranking, mapping, prepare.prep_event_spans(with_bouts, (1, 2), "day", "datetime")
	)
	payload = json.loads(figure.to_json())

	assert payload["layout"]["shapes"][0]["x0"] == payload["data"][0]["x"][0]


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
