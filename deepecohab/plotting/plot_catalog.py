from collections.abc import Sequence
from typing import Literal

import plotly.graph_objects as go
import polars as pl

from deepecohab.core.data_model import Layout
from deepecohab.plotting import durations, plot_factory, prepare
from deepecohab.plotting.animals import (
	available_attributes,
	mean_by_group,
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

PHASES = ("light_phase", "dark_phase")
BY_COHORT = {"color_by": available_attributes}
#: ``Timeline.phases`` need not carry both keys, so a plot's phase_type choices are
#: resolved from the cohort's own phases rather than assumed to always be the pair.
PHASE_TYPE = {"phase_type": lambda context: list(context.phases)}
BY_COHORT_AND_PHASE = {**BY_COHORT, **PHASE_TYPE}

#: The count-line builder each aggregation draws with.
LINE_BY_AGG = {
	"sum": plot_factory.plot_sum_line,
	"mean": plot_factory.plot_mean_line,
}


def _window(
	context: PlotContext,
	days_range: tuple[int, int] | None,
	granularity: Granularity,
) -> tuple[int, int]:
	"""Fall back to the whole recording when no window is selected."""
	return context.axis_range(granularity) if days_range is None else days_range


@PlotRegistry.register(
	"recording-timeline",
	title="Position timeline",
	requires=("main_df", "animals"),
)
def recording_timeline(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Every animal's position over time, as a compact Gantt-style strip."""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_timeline(context, window, granularity, hours_range)
	spans = prepare.prep_event_spans(context, window, granularity, "datetime", hours_range)

	return plot_factory.plot_timeline(
		frame, sorted(context.animal_ids), context.scope_positions("all"), spans
	)


@PlotRegistry.register(
	"activity-bar",
	title="Activity per position",
	requires=("activity_df", "animals"),
	dynamic_choices=BY_COHORT_AND_PHASE,
)
def activity(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	metric: Literal["visits", "time"] = "time",
	agg: Literal["sum", "mean"] = "sum",
	scope: Scope = "all",
	color_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
	group_mean: bool = False,
) -> go.Figure:
	"""Visits to each position, or time spent there.

	Quantifies behaviour either by the number of visits to specific locations or
	the total time spent in those locations. ``"all"`` keeps the undefined position,
	so the time no antenna could place stays visible.
	"""
	window = _window(context, days_range, granularity)
	positions = context.positions if scope == "all" else context.scope_positions(scope)
	frame = prepare.prep_activity(
		context, window, phase_type, granularity, agg, positions, hours_range
	)
	mapping = resolve_colors(context, color_by, group_mean=group_mean)
	frame = mean_by_group(frame, mapping, ["visits", "time"])
	frame, label = durations.to_display(frame, "time", unit, "Time spent")

	return plot_factory.plot_activity(
		frame, positions, mapping, metric, agg, granularity, label, SCOPE_NOUN[scope]
	)


@PlotRegistry.register(
	"time-alone-bar",
	title="Time spent alone",
	requires=("activity_df", "animals"),
	dynamic_choices=BY_COHORT_AND_PHASE,
)
def time_alone(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	scope: Scope = "all",
	color_by: str = "animal_id",
	unit: Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
	group_mean: bool = False,
) -> go.Figure:
	"""Time each animal spent without any other animal present.

	Shows the duration each animal spent alone, segmented by the position where that
	happened - cages, tunnels, or both.
	"""
	window = _window(context, days_range, granularity)
	positions = context.scope_positions(scope)
	frame = prepare.prep_time_alone(
		context, window, phase_type, granularity, agg, positions, hours_range
	)
	mapping = resolve_colors(context, color_by, group_mean=group_mean)
	frame = mean_by_group(frame, mapping, ["time_alone"])
	frame, label = durations.to_display(frame, "time_alone", unit, "Time alone")

	return plot_factory.plot_time_alone(
		frame, positions, mapping, agg, granularity, label, SCOPE_NOUN[scope]
	)


@PlotRegistry.register(
	"cage-preference",
	title="Position preference",
	requires=("activity_df",),
	dynamic_choices=PHASE_TYPE,
)
def cage_preference(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	scope: Scope = "all",
	unit: Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Distribution of time the cohort spends in each position."""
	window = _window(context, days_range, granularity)
	positions = context.scope_positions(scope)
	frame, label = prepare.prep_cage_preference(
		context, window, phase_type, granularity, positions, unit, hours_range
	)

	return plot_factory.plot_cage_preference(
		frame,
		positions,
		sample_palette(len(positions)),
		granularity,
		label,
		SCOPE_NOUN[scope],
	)


@PlotRegistry.register(
	"cage-preference-evolution",
	title="Position preference over time",
	requires=("activity_df", "animals"),
)
def cage_preference_evolution(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	timescale: Literal["days", "hours"] = "days",
	agg: Literal["sum", "mean"] = "sum",
	scope: FacetScope = "cages",
	unit: Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Time spent in each cage, or each tunnel, across the window or the hours of the day.

	``"days"`` steps through the window's days or phases, following ``granularity``;
	``"hours"`` folds the window onto the 24 hours of the experiment day.
	"""
	window = _window(context, days_range, granularity)
	x = granularity if timescale == "days" else "hour"
	heatmap = prepare.prep_time_per_position(
		context,
		window,
		agg,
		granularity,
		x,
		context.scope_positions(scope),
		context.animal_ids,
		unit,
		hours_range,
	)

	spans = prepare.prep_event_spans(context, window, granularity, x, hours_range)
	kind = "daily" if timescale == "days" else "hourly"

	return plot_factory.plot_time_spent_per_cage(
		heatmap, kind, spans, SCOPE_NOUN[scope], granularity
	)


@PlotRegistry.register(
	"activity-line",
	title="Activity over time",
	requires=("main_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def activity_line(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	timescale: Literal["days", "hours"] = "hours",
	agg: Literal["sum", "mean"] = "sum",
	color_by: str = "animal_id",
	hours_range: tuple[int, int] | None = None,
	group_mean: bool = False,
) -> go.Figure:
	"""Antenna detections per hour of the day, or per day of the window.

	``"hours"`` folds the window onto the 24 hours of the experiment day, showing the
	circadian rhythm; ``"days"`` steps through the window's days or phases, following
	``granularity``. For the mean, a shaded band shows the standard error across the axis
	folded away.
	"""
	window = _window(context, days_range, granularity)
	x = granularity if timescale == "days" else "hour"
	frame = prepare.prep_count_line(
		context, window, granularity, x, "main_df", "animal_id", pl.len(), hours_range
	)
	spans = prepare.prep_event_spans(context, window, granularity, x, hours_range)
	mapping = resolve_colors(context, color_by, group_mean=group_mean)
	frame = mean_by_group(frame, mapping, ["total", "mean"])

	return LINE_BY_AGG[agg](frame, mapping, "activity", x, context.phases, spans)


@PlotRegistry.register(
	"chasings-line",
	title="Chasings over time",
	requires=("chasings_df", "animals"),
	dynamic_choices=BY_COHORT,
)
def chasings_line(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	timescale: Literal["days", "hours"] = "hours",
	agg: Literal["sum", "mean"] = "sum",
	scope: Literal["chaser", "chased"] = "chaser",
	color_by: str = "animal_id",
	hours_range: tuple[int, int] | None = None,
	group_mean: bool = False,
) -> go.Figure:
	"""Chasings per hour of the day, or per day of the window.

	Counts each animal's chasings as the chaser, or as the chased. ``timescale`` works as
	for ``activity-line``. For the mean, a shaded band shows the standard error across the
	axis folded away.
	"""
	window = _window(context, days_range, granularity)
	x = granularity if timescale == "days" else "hour"
	frame = prepare.prep_count_line(
		context, window, granularity, x, "chasings_df", scope, pl.sum("chasings"), hours_range
	)
	spans = prepare.prep_event_spans(context, window, granularity, x, hours_range)
	mapping = resolve_colors(context, color_by, animal_column=scope, group_mean=group_mean)
	frame = mean_by_group(frame, mapping, ["total", "mean"])

	return LINE_BY_AGG[agg](frame, mapping, "chasings", x, context.phases, spans)


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
	"""Probability density of each animal's ranking after the last match in range."""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_ranking_distribution(context, window, granularity)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_ranking_distribution(frame, mapping)


@PlotRegistry.register(
	"metrics-polar-line",
	title="Feature overview",
	requires=("feature_df", "animals"),
	dynamic_choices=BY_COHORT_AND_PHASE,
)
def polar_metrics(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	color_by: str = "animal_id",
	hours_range: tuple[int, int] | None = None,
	group_mean: bool = False,
) -> go.Figure:
	"""Z-scored dominance, activity and proximity metrics on one polar scale.

	A polar overlay of metrics in different units is unreadable raw, so each is
	z-scored for display only.
	"""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_polar(context, window, phase_type, granularity, hours_range)
	mapping = resolve_colors(context, color_by, group_mean=group_mean)
	frame = mean_by_group(frame, mapping, ["mean"])

	return plot_factory.plot_metrics_polar(frame, mapping)


@PlotRegistry.register(
	"chasings-heatmap",
	title="Chasings matrix",
	requires=("chasings_df", "animals"),
	dynamic_choices=PHASE_TYPE,
)
def chasings_heatmap(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Chaser-versus-chased matrix of agonistic interactions.

	Columns are chasers and rows are chased.
	"""
	window = _window(context, days_range, granularity)
	animals = context.animal_ids
	matrix = prepare.prep_directed_heatmap(
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
		hours_range=hours_range,
	)

	return plot_factory.plot_heatmap(
		matrix, animals, "<b>Chasings</b>", ("Chaser", "Chased", "Number")
	)


@PlotRegistry.register(
	"tube-test-heatmap",
	title="Tube-test matrix",
	requires=("tube_test_df",),
	dynamic_choices=PHASE_TYPE,
)
def tube_test_heatmap(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Winner-versus-loser matrix of spontaneous tube-test outcomes."""
	window = _window(context, days_range, granularity)
	animals = context.animal_ids
	matrix = prepare.prep_directed_heatmap(
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
		hours_range=hours_range,
	)

	return plot_factory.plot_heatmap(
		matrix, animals, "<b>Spontaneous tube-test</b>", ("Winner", "Loser", "Number")
	)


@PlotRegistry.register(
	"sociability-heatmap",
	title="Pairwise sociability",
	requires=("pairwise_meetings", "animals"),
	dynamic_choices=PHASE_TYPE,
)
def pairwise_sociability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	agg: Literal["sum", "mean"] = "sum",
	metric: Literal["time_together", "pairwise_encounters"] = "time_together",
	scope: FacetScope = "cages",
	unit: Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
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
		context.animal_ids,
		unit,
		hours_range,
	)

	return plot_factory.plot_sociability_heatmap(heatmap, metric)


@PlotRegistry.register(
	"cohort-heatmap",
	title="Within-cohort sociability",
	requires=("incohort_sociability", "pairwise_meetings", "phase_durations", "animals"),
	dynamic_choices=PHASE_TYPE,
)
def within_cohort_sociability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	metric: Literal["proportion_together", "sociability"] = "proportion_together",
	scope: Scope = "all",
) -> go.Figure:
	"""Mean sociability index between every pair in the cohort.

	``scope`` applies to ``proportion_together`` only: ``sociability`` is measured against
	a cage-only chance expectation, so it ignores the selection.
	"""
	window = _window(context, days_range, granularity)
	animals = context.animal_ids
	matrix = prepare.prep_within_cohort_sociability(
		context, window, phase_type, metric, granularity, animals, scope
	)

	title = (
		"<b>Proportional time spent together</b>"
		if metric == "proportion_together"
		else "<b>Within-cohort sociability</b>"
	)

	return plot_factory.plot_heatmap(matrix, animals, title, ("X", "Y", "Sociability"))


@PlotRegistry.register(
	"social-stability",
	title="Relationship stability",
	requires=("pairwise_meetings", "phase_durations", "animals"),
	dynamic_choices=BY_COHORT_AND_PHASE,
)
def social_stability(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	phase_type: Sequence[str] = PHASES,
	scope: Scope = "all",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Stability of every pair's relationship against how much time they share."""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_social_stability(context, window, phase_type, granularity, scope)
	mapping = resolve_colors(context, color_by)

	return plot_factory.plot_social_stability(frame, mapping)


@PlotRegistry.register(
	"quality-heatmap",
	title="Missed passes by animal and antenna",
	requires=("recording_quality",),
)
def quality_heatmap(context: PlotContext) -> go.Figure:
	"""Share of each animal's passes over each antenna that went unrecorded."""
	animals = context.animal_ids
	matrix, antennas = prepare.prep_quality_heatmap(context, animals)

	return plot_factory.plot_quality_heatmap(matrix, animals, antennas)


@PlotRegistry.register(
	"quality-antenna",
	title="Missed passes per antenna",
	requires=("recording_quality",),
)
def quality_by_antenna(context: PlotContext) -> go.Figure:
	"""Pooled over the cohort, so a marginal antenna stands out first."""
	return plot_factory.plot_quality_by_antenna(prepare.prep_quality_by_antenna(context))


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
	edge_cutoff: float = 0,
	color_by: str = "animal_id",
) -> go.Figure:
	"""Directed network of chasing, with node size showing ranking.

	``edge_cutoff`` drops edges weaker than that percentage of the strongest before the
	layout is fitted, so the network is recomputed from what remains.
	"""
	window = _window(context, days_range, granularity)
	connections, nodes = prepare.prep_network_dominance(context, window, granularity)
	mapping = resolve_colors(context, color_by)
	colors = [mapping.by_animal[animal] for animal in context.animal_ids]

	figure = plot_factory.plot_network_graph(
		connections, nodes, context.animal_ids, colors, "chasings", layout, edge_cutoff
	)
	return figure.update_layout(colorway=list(mapping.colors.values()))


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
	edge_cutoff: float = 0,
	scope: Scope = "all",
	color_by: str = "animal_id",
) -> go.Figure:
	"""Undirected network weighted by the time each pair spends together.

	``edge_cutoff`` works as for ``network-dominance``.
	"""
	window = _window(context, days_range, granularity)
	connections = prepare.prep_network_sociability(context, window, granularity, scope)
	mapping = resolve_colors(context, color_by)
	colors = [mapping.by_animal[animal] for animal in context.animal_ids]

	figure = plot_factory.plot_network_graph(
		connections,
		None,
		context.animal_ids,
		colors,
		"proportion_together",
		layout,
		edge_cutoff,
	)
	return figure.update_layout(colorway=list(mapping.colors.values()))


@PlotRegistry.register(
	"recording-pulse",
	title="Recording pulse",
	requires=("activity_df",),
)
def recording_pulse(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Cohort visits per hour, one row per experiment day, outlined where an event ran.

	Rows stay experiment days whichever granularity the window is in, since a phase
	covers half a day: a phase window narrows which hours of those days are drawn.
	"""
	window = _window(context, days_range, granularity)
	heatmap, cells = prepare.prep_actogram(context, window, granularity, hours_range)

	return plot_factory.plot_actogram(heatmap, cells, context.phases)


@PlotRegistry.register(
	"habitat-occupancy",
	title="Habitat occupancy",
	requires=("activity_df",),
)
def habitat_occupancy(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	hours_range: tuple[int, int] | None = None,
) -> go.Figure:
	"""Share of the cohort's time each place held, across the window.

	Position preference collapsed over time answers where the group lived; this keeps
	the time axis, so a cohort abandoning a cage shows up as the move it was.
	"""
	window = _window(context, days_range, granularity)
	frame = prepare.prep_occupancy_share(context, window, granularity, hours_range)
	spans = prepare.prep_event_spans(context, window, granularity, granularity, hours_range)

	# Cages take the palette cage-preference gives them at cages-only scope, so a cage
	# keeps one colour across the dashboard. Tunnels and undefined are not cages and stay
	# out of the hue budget: one neutral band for transit, a hatched one for no place.
	colors = dict(zip(context.cages, sample_palette(len(context.cages)), strict=True))
	colors |= {"tunnels": "rgba(123, 137, 136, 0.5)", Layout.UNDEFINED: "rgba(123, 137, 136, 0.22)"}
	order = [*context.cages, "tunnels", Layout.UNDEFINED]

	return plot_factory.plot_occupancy_ribbon(frame, order, colors, granularity, spans)


@PlotRegistry.register(
	"cohort-phenotype",
	title="Cohort phenotype map",
	requires=("activity_df", "chasings_df", "ranking", "animals"),
	dynamic_choices=BY_COHORT,
)
def cohort_phenotype(
	context: PlotContext,
	*,
	days_range: tuple[int, int] | None = None,
	granularity: Granularity = "day",
	hours_range: tuple[int, int] | None = None,
	color_by: str = "animal_id",
) -> go.Figure:
	"""One marker per animal, carrying locomotion, sociality, chasing and rank at once.

	Marker area is chases won and colour the dominance rating, so an animal that sits
	apart from the cloud is the one to open the Social or Dominance tab for.
	"""
	window = _window(context, days_range, granularity)
	# Colour is the rating, so the animals-by choice only decides the name on each marker.
	label = "subject_name" if color_by == "subject_name" else "animal_id"
	mapping = resolve_colors(context, color_by)
	return plot_factory.plot_phenotype_map(
		prepare.prep_phenotype(context, window, granularity, hours_range), mapping, label
	)
