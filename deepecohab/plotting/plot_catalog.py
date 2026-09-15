from typing import Literal

import plotly.graph_objects as go
import polars as pl

from deepecohab.plotting import plot_factory, prepare
from deepecohab.plotting.animals import (
	available_attributes,
	order_by_attribute,
	resolve_colors,
)
from deepecohab.plotting.context import (
	SCOPE_NOUN,
	FacetScope,
	Granularity,
	PlotContext,
	Scope,
)
from deepecohab.plotting.durations import Unit
from deepecohab.plotting.registry import PlotRegistry
from deepecohab.plotting.theme import sample_palette

PHASES = ["light_phase", "dark_phase"]
BY_COHORT = {"color_by": available_attributes}
ORDERED_BY_COHORT = {"order_by": available_attributes}


def _window(
	context: PlotContext,
	days_range: tuple[int, int] | None,
	granularity: Granularity,
) -> tuple[int, int]:
	"""Fall back to the whole recording when no window is selected."""
	return context.axis_range(granularity) if days_range is None else days_range


@PlotRegistry.register(
	"activity-bar",
	title="Activity per position",
	requires=("activity_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def activity(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	metric: Literal["visits", "time"] = "time",
	agg: Literal["sum", "mean"] = "sum",
	color_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""Visits to each position, or time spent there.

	Quantifies behaviour either by the number of visits to specific locations or
	the total time spent in those locations.
	"""
	window = _window(context, days_range, granularity)
	frame, rendered = prepare.prep_activity(context, window, phase_type, granularity, agg, unit)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_activity(
		frame, context.positions, mapping, metric, agg, granularity, rendered.label
	)


@PlotRegistry.register(
	"time-alone-bar",
	title="Time spent alone",
	requires=("activity_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def time_alone(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	scope: Scope = "cages",
	color_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""Time each animal spent without any other animal present.

	Shows the duration each animal spent alone, segmented by the position where that
	happened - cages, tunnels, or both.
	"""
	window = _window(context, days_range, granularity)
	positions = context.scope_positions(scope)
	frame, rendered = prepare.prep_time_alone(
		context, window, phase_type, granularity, agg, positions, unit
	)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_time_alone(
		frame, positions, mapping, agg, granularity, rendered.label, SCOPE_NOUN[scope]
	)


@PlotRegistry.register(
	"cage-preference",
	title="Cage preference",
	requires=("activity_df",),
)
def cage_preference(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	scope: Scope = "cages",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""Distribution of time the cohort spends in each position."""
	window = _window(context, days_range, granularity)
	positions = context.scope_positions(scope)
	frame, rendered = prepare.prep_cage_preference(
		context, window, phase_type, granularity, positions, unit
	)

	return plot_factory.plot_cage_preference(
		frame,
		positions,
		sample_palette(len(positions)),
		granularity,
		rendered.label,
		SCOPE_NOUN[scope],
	)


@PlotRegistry.register(
	"cage-preference-evolution",
	title="Cage preference over time",
	requires=("activity_df", "animals"),
	dynamic_choices=ORDERED_BY_COHORT,
)
def cage_preference_evolution(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	agg: Literal["sum", "mean"] = "sum",
	scope: FacetScope = "cages",
	order_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""Time spent in each cage, or each tunnel, across days or phases."""
	window = _window(context, days_range, granularity)
	heatmap = prepare.prep_time_per_position(
		context,
		window,
		agg,
		granularity,
		granularity,
		context.scope_positions(scope),
		order_by_attribute(context, order_by),
		unit,
	)

	spans = prepare.prep_event_spans(context, window, granularity, granularity)

	return plot_factory.plot_time_spent_per_cage(heatmap, "daily", spans, SCOPE_NOUN[scope])


@PlotRegistry.register(
	"time-per-cage-heatmap",
	title="Time per cage by hour",
	requires=("activity_df", "animals"),
	dynamic_choices=ORDERED_BY_COHORT,
)
def time_per_cage(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	agg: Literal["sum", "mean"] = "sum",
	scope: FacetScope = "cages",
	order_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""Position occupancy across the 24 hours of the experiment day.

	One panel per cage, or per tunnel, showing when and for how long each animal
	occupies it.
	"""
	window = _window(context, days_range, granularity)
	heatmap = prepare.prep_time_per_position(
		context,
		window,
		agg,
		granularity,
		"hour",
		context.scope_positions(scope),
		order_by_attribute(context, order_by),
		unit,
	)

	spans = prepare.prep_event_spans(context, window, granularity, "hour")

	return plot_factory.plot_time_spent_per_cage(heatmap, "hourly", spans, SCOPE_NOUN[scope])


@PlotRegistry.register(
	"activity-line",
	title="Activity per hour",
	requires=("main_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def activity_line(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	agg: Literal["sum", "mean"] = "sum",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Antenna detections per hour, showing the circadian rhythm.

	For the mean, a shaded band shows the standard error across the selected
	window units.
	"""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_hourly_line(context, window, granularity, "main_df", "animal_id", pl.len())
	spans = prepare.prep_event_spans(context, window, granularity, "hour")
	mapping = resolve_colors(context, color_by)

	builder = (
		plot_factory.plot_sum_line_per_hour
		if agg == "sum"
		else plot_factory.plot_mean_line_per_hour
	)

	return builder(frame, mapping, "activity", context.phases, spans)


@PlotRegistry.register(
	"chasings-line",
	title="Chasings per hour",
	requires=("chasings_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def chasings_line(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	agg: Literal["sum", "mean"] = "sum",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Chasing frequency per hour, showing the diurnal rhythm of aggression.

	For the mean, a shaded band shows the standard error across the selected
	window units.
	"""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_hourly_line(
		context, window, granularity, "chasings_df", "chaser", pl.sum("chasings")
	)
	spans = prepare.prep_event_spans(context, window, granularity, "hour")
	mapping = resolve_colors(context, color_by, animal_column="chaser")

	builder = (
		plot_factory.plot_sum_line_per_hour
		if agg == "sum"
		else plot_factory.plot_mean_line_per_hour
	)

	return builder(frame, mapping, "chasings", context.phases, spans)


@PlotRegistry.register(
	"ranking-line",
	title="Dominance ranking",
	requires=("ranking", "animals"),
	dynamic_choices=BY_COHORT,
)
def ranking_over_time(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	mode: Literal["intime", "stability"] = "intime",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Ranking over time, or its day-to-day stability."""
	window = _window(context, days_range, granularity)
	mapping = resolve_colors(context, color_by)

	match mode:
		case "intime":
			frame = prepare.prep_ranking_over_time(context, window, granularity)
			spans = prepare.prep_event_spans(context, window, granularity, "datetime")

			return plot_factory.plot_ranking_line(frame, mapping, spans)
		case "stability":
			frame = prepare.prep_ranking_day_stability(context, window, granularity)
			spans = prepare.prep_event_spans(context, window, granularity, granularity)

			return plot_factory.plot_ranking_stability(frame, mapping, granularity, spans)


@PlotRegistry.register(
	"ranking-distribution-line",
	title="Ranking distribution",
	requires=("ranking", "animals"),
	dynamic_choices=BY_COHORT,
)
def ranking_distribution(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Probability density of each animal's ranking on the latest day in range."""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_ranking_distribution(context, window, granularity)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_ranking_distribution(frame, mapping)


@PlotRegistry.register(
	"metrics-polar-line",
	title="Feature overview",
	requires=("feature_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def polar_metrics(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	color_by: str = "animal_id",
) -> go.Figure:
	"""Z-scored dominance, activity and proximity metrics on one polar scale.

	A polar overlay of metrics in different units is unreadable raw, so each is
	z-scored for display only.
	"""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_polar_df(context, window, phase_type, granularity)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_metrics_polar(frame, mapping)


@PlotRegistry.register(
	"chasings-heatmap",
	title="Chasings matrix",
	requires=("chasings_df", "animals"),
	dynamic_choices=ORDERED_BY_COHORT,
)
def chasings_heatmap(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	order_by: str = "animal_id",
) -> go.Figure:
	"""Chaser-versus-chased matrix of agonistic interactions.

	Columns are chasers and rows are chased.
	"""
	window = _window(context, days_range, granularity)
	animals = order_by_attribute(context, order_by)
	img = prepare.prep_directed_heatmap(
		context,
		window,
		phase_type,
		agg,
		granularity,
		animals,
		table="chasings_df",
		value="chasings",
		column="chaser",
		row="chased",
	)

	return plot_factory.plot_heatmap(
		img, animals, "<b>Chasings</b>", ("Chaser", "Chased", "Number")
	)


@PlotRegistry.register(
	"tube-test-heatmap",
	title="Tube-test matrix",
	requires=("tube_test_df",),
	dynamic_choices=ORDERED_BY_COHORT,
)
def tube_test_heatmap(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	order_by: str = "animal_id",
) -> go.Figure:
	"""Winner-versus-loser matrix of spontaneous tube-test outcomes."""
	window = _window(context, days_range, granularity)
	animals = order_by_attribute(context, order_by)
	img = prepare.prep_directed_heatmap(
		context,
		window,
		phase_type,
		agg,
		granularity,
		animals,
		table="tube_test_df",
		value="tube_test",
		column="winner",
		row="loser",
	)

	return plot_factory.plot_heatmap(
		img, animals, "<b>Spontaneous tube-test</b>", ("Winner", "Loser", "Number")
	)


@PlotRegistry.register(
	"sociability-heatmap",
	title="Pairwise sociability",
	requires=("pairwise_meetings", "animals"),
	dynamic_choices=ORDERED_BY_COHORT,
)
def pairwise_sociability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	metric: Literal["time_together", "pairwise_encounters"] = "time_together",
	scope: FacetScope = "cages",
	order_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
) -> go.Figure:
	"""How often pairs meet, or how long they spend together, per cage or per tunnel."""
	window = _window(context, days_range, granularity)
	heatmap = prepare.prep_pairwise_sociability(
		context,
		window,
		phase_type,
		agg,
		metric,
		granularity,
		context.scope_positions(scope),
		order_by_attribute(context, order_by),
		unit,
	)

	return plot_factory.plot_sociability_heatmap(heatmap, metric)


@PlotRegistry.register(
	"cohort-heatmap",
	title="Within-cohort sociability",
	requires=("incohort_sociability", "pairwise_meetings", "phase_durations", "animals"),
	dynamic_choices=ORDERED_BY_COHORT,
)
def within_cohort_sociability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	metric: Literal["proportion_together", "sociability"] = "sociability",
	scope: Scope = "cages",
	order_by: str = "animal_id",
) -> go.Figure:
	"""Mean sociability index between every pair in the cohort.

	``scope`` applies to ``proportion_together`` only: ``sociability`` is measured against
	a cage-only chance expectation, so it ignores the selection.
	"""
	window = _window(context, days_range, granularity)
	animals = order_by_attribute(context, order_by)
	img = prepare.prep_within_cohort_sociability(
		context, window, phase_type, metric, granularity, animals, scope
	)

	title = (
		"<b>Proportional time spent together</b>"
		if metric == "proportion_together"
		else "<b>Within-cohort sociability</b>"
	)

	return plot_factory.plot_heatmap(img, animals, title, ("X", "Y", "Sociability"))


@PlotRegistry.register(
	"social-stability",
	title="Relationship stability",
	requires=("pairwise_meetings", "phase_durations", "animals"),
	dynamic_choices=BY_COHORT,
)
def social_stability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: list[str] = PHASES,
	scope: Scope = "cages",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Stability of every pair's relationship against how much time they share."""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_social_stability(context, window, phase_type, granularity, scope)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_social_stability(frame, mapping)


@PlotRegistry.register(
	"network-dominance",
	title="Dominance network",
	requires=("chasings_df", "ranking", "animals"),
	dynamic_choices=BY_COHORT,
)
def network_dominance(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	layout: Literal["spring", "circular"] = "spring",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Directed network of chasing, with node size showing ranking."""
	window = _window(context, days_range, granularity)
	connections, nodes = prepare.prep_network_dominance(context, window, granularity)
	mapping = resolve_colors(context, color_by)
	colors = [mapping.by_animal[animal] for animal in context.animal_ids]

	return plot_factory.plot_network_graph(
		connections, nodes, context.animal_ids, colors, "chasings", layout
	)


@PlotRegistry.register(
	"network-sociability",
	title="Sociability network",
	requires=("pairwise_meetings", "phase_durations", "animals"),
	dynamic_choices=BY_COHORT,
)
def network_sociability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	layout: Literal["spring", "circular"] = "spring",
	scope: Scope = "cages",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Undirected network weighted by the time each pair spends together."""
	window = _window(context, days_range, granularity)
	connections = prepare.prep_network_sociability(context, window, granularity, scope)
	mapping = resolve_colors(context, color_by)
	colors = [mapping.by_animal[animal] for animal in context.animal_ids]

	return plot_factory.plot_network_graph(
		connections, None, context.animal_ids, colors, "proportion_together", layout
	)
