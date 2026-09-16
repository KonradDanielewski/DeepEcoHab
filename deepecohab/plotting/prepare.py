import math
from dataclasses import dataclass
from itertools import combinations, product
from typing import Literal

import numpy as np
import polars as pl

from deepecohab.core.data_model import Layout
from deepecohab.plotting import durations
from deepecohab.plotting.context import Granularity, PlotContext, Scope

Aggregation = Literal["sum", "mean"]


@dataclass(frozen=True, eq=False)
class Heatmap:
	"""A faceted matrix and the labels it is drawn with.

	Attributes:
		values: ``(facet, row, column)`` values driving the colour scale.
		text: same shape, pre-formatted for hover, or ``None`` for plain numbers.
		label: colourbar title, including the unit.
		x: column labels.
		y: row labels.
		facets: one title per facet.
	"""

	values: np.ndarray
	text: np.ndarray | None
	label: str
	x: list[int] | list[str]
	y: list[str]
	facets: list[str]


def window_filter(
	days_range: tuple[int, int],
	granularity: Granularity,
	hours_range: tuple[int, int] | None = None,
) -> pl.Expr:
	"""The window predicate every prep function narrows its source table with.

	Args:
		days_range: first and last window unit (day or phase occurrence) to keep.
		granularity: which axis ``days_range`` measures.
		hours_range: first and last hour since the ``start_from`` onset to keep, or
			``None`` to keep every hour. Only tables carrying their own ``hour`` -
			not ``phase_durations``, or anything normalised against it - can take one.

	Returns:
		A boolean expression combining both bounds.
	"""
	expr = pl.col(granularity).is_between(days_range[0], days_range[1])

	if hours_range is not None:
		expr = expr & pl.col("hour").is_between(hours_range[0], hours_range[1])

	return expr


def _bins(days_range: tuple[int, int]) -> int:
	"""Number of window units the selection spans, for the SEM denominator."""
	return days_range[1] - days_range[0] + 1


def _matrix(
	frame: pl.DataFrame,
	on: str,
	index: str,
	values: str,
	animals: list[str],
) -> np.ndarray:
	"""Pivot a long pair table into a square animal-by-animal matrix."""
	return frame.pivot(on=on, index=index, values=values).drop(index).select(animals).to_numpy()


def prep_event_spans(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
	x: Literal["datetime", "hour", "day", "phase_count"],
	hours_range: tuple[int, int] | None = None,
) -> pl.DataFrame:
	"""Where each event falls on a plot's x axis, within the selected window.

	On a binned axis a span covers every bin the event overlaps, from half a bin before
	the first to half a bin after the last, since each point stands for its whole bin.

	Args:
		context: the context whose ``event_bouts`` table is read.
		days_range: first and last window unit to keep.
		granularity: the unit of the window.
		x: the ``event_bouts`` column the plot's x axis shows.
		hours_range: first and last hour to keep, matching the plot it is drawn on.

	Returns:
		One row per span, with ``event``, ``position``, ``x0`` and ``x1``; empty for a
		recording analysed before events existed.
	"""
	if "event_bouts" not in context:
		return pl.DataFrame(schema=["event", "position", "x0", "x1"])

	bouts = context.table("event_bouts").filter(window_filter(days_range, granularity, hours_range))

	# Plotly draws a trace's datetimes as naive wall-clock times, so the spans must be too.
	if x == "datetime":
		return bouts.select(
			"event",
			"position",
			pl.col("start").dt.replace_time_zone(None).alias("x0"),
			pl.col("end").dt.replace_time_zone(None).alias("x1"),
		).unique(maintain_order=True)

	return (
		bouts.select("event", "position", pl.col(x).cast(pl.Int64))
		.unique()
		.sort("event", "position", x)
		# A gap between neighbouring bins starts a new span.
		.with_columns(
			(pl.col(x).diff().over("event", "position") != 1)
			.fill_null(True)
			.cum_sum()
			.over("event", "position")
			.alias("run")
		)
		.group_by("event", "position", "run")
		.agg((pl.col(x).min() - 0.5).alias("x0"), (pl.col(x).max() + 0.5).alias("x1"))
		.drop("run")
	)


def prep_timeline(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
	hours_range: tuple[int, int] | None = None,
) -> pl.DataFrame:
	"""Every animal's position intervals within the selected window, as timeline bars.

	Reads ``main_df`` directly rather than a downstream table, so each row is one real
	visit - a registration's ``time_spent`` is the gap since the animal's previous one,
	so it ran from ``datetime - time_spent`` to ``datetime``. Consecutive registrations
	at the same position - repeat triggers of one antenna pair mid-visit - are merged
	into a single bar, or the strip would carry orders of magnitude more bars than there
	were actual visits.
	"""
	return (
		context.table("main_df")
		.lazy()
		.filter(window_filter(days_range, granularity, hours_range))
		.with_columns(
			pl.col("position").cast(pl.String).replace(context.tunnels_map),
			(pl.col("datetime") - pl.col("time_spent")).alias("start"),
		)
		.filter(
			pl.col("position") != Layout.UNDEFINED,
			pl.col("time_spent") > pl.duration(microseconds=0),
		)
		.sort("animal_id", "start")
		.with_columns(
			(pl.col("position") != pl.col("position").shift(1))
			.over("animal_id")
			.fill_null(True)
			.cum_sum()
			.over("animal_id")
			.alias("run")
		)
		.group_by("animal_id", "position", "run")
		.agg(pl.col("start").min(), pl.col("datetime").max().alias("end"))
		.select("animal_id", "position", "start", "end")
		.sort("animal_id", "start")
		.collect(engine="in-memory")
	)


def prep_ranking_over_time(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
) -> pl.DataFrame:
	"""Aggregate animal ordinal rankings by window unit, hour, and datetime."""
	return (
		context.table("ranking")
		.lazy()
		.filter(window_filter(days_range, granularity))
		.sort("datetime")
		.group_by(granularity, "hour", "animal_id", "datetime", maintain_order=True)
		.agg(
			pl.when(pl.first(granularity) == 1)
			.then(pl.first("ordinal"))
			.otherwise(pl.last("ordinal"))
		)
		.collect(engine="in-memory")
	)


def prep_ranking_day_stability(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
) -> pl.DataFrame:
	"""Rank animals by their last ordinal in each window unit."""
	return (
		context.table("ranking")
		.lazy()
		.filter(window_filter(days_range, granularity))
		.group_by(granularity, "animal_id")
		.agg(pl.col("ordinal").last())
		.with_columns(
			pl.col("ordinal")
			.rank(method="average", descending=True)
			.over(granularity)
			.alias("rank")
		)
		.sort(granularity, "rank")
		.collect(engine="in-memory")
	)


def prep_ranking_distribution(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
) -> pl.DataFrame:
	"""Fit a normal probability density over each animal's latest ranking."""
	x_df = pl.LazyFrame({"ranking": np.arange(-10, 50, 0.1)})
	diff = (pl.col(granularity) - days_range[-1]).abs()
	pdf_expression = (1 / (pl.col("sigma") * math.sqrt(2 * math.pi))) * (
		-0.5 * ((pl.col("ranking") - pl.col("mu")) / pl.col("sigma")) ** 2
	).exp()

	return (
		context.table("ranking")
		.lazy()
		.filter(diff == diff.min())
		.group_by("animal_id")
		.agg(pl.last("mu"), pl.last("sigma"))
		.join(x_df, how="cross")
		.with_columns(pdf_expression.alias("probability_density"))
		.select("animal_id", "ranking", "probability_density")
		.sort("animal_id")
		.collect(engine="in-memory")
	)


def prep_polar_df(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	granularity: Granularity,
	hours_range: tuple[int, int] | None = None,
) -> pl.DataFrame:
	"""Z-score every feature metric onto one comparable polar scale."""
	n_bins = _bins(days_range)
	# The hour filter has to apply before the day-level aggregation below, which sums
	# away the hour column entirely - window_filter can't reach it afterwards.
	hour_filter = (
		pl.col("hour").is_between(hours_range[0], hours_range[1])
		if hours_range is not None
		else pl.lit(True)
	)

	return (
		context.table("feature_df")
		.lazy()
		.filter(hour_filter)
		.group_by("animal_id", "metric", "phase", "day", "phase_count")
		.agg(pl.sum("value"), pl.sum("exposure"))
		.with_columns(
			pl.when(pl.col("exposure") > 0)
			.then(pl.col("value") / pl.col("exposure"))
			.otherwise(0.0)
			.alias("rate")
		)
		.with_columns(
			pl.when(pl.col("rate").std().fill_null(0) == 0)
			.then(pl.lit(0.0))
			.otherwise((pl.col("rate") - pl.col("rate").mean()) / pl.col("rate").std())
			.over("metric")
			.alias("z-score")
		)
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity),
		)
		.group_by("animal_id", "metric", granularity)
		.agg(pl.mean("z-score"))
		.group_by("animal_id", "metric")
		.agg(
			pl.mean("z-score").alias("mean"),
			(pl.std("z-score") / math.sqrt(n_bins)).alias("sem"),
		)
		.with_columns(
			(pl.col("mean") - pl.col("sem")).alias("lower"),
			(pl.col("mean") + pl.col("sem")).alias("upper"),
		)
		.sort("metric", "animal_id")
		.fill_null(0)
		.with_columns(
			pl.col("metric").str.to_titlecase().str.replace_all("_", " ").str.replace("N ", "# of ")
		)
		.collect(engine="streaming")
	)


def prep_network_dominance(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
) -> tuple[pl.DataFrame, pl.DataFrame]:
	"""Return chasing edges and the latest ranking per animal."""
	animals = context.animal_ids
	join_df = pl.LazyFrame(
		data=product(animals, animals),
		schema=[("target", pl.Enum(context.animal_ids)), ("source", pl.Enum(context.animal_ids))],
	)

	connections = (
		context.table("chasings_df")
		.lazy()
		.filter(window_filter(days_range, granularity))
		.group_by("chased", "chaser")
		.agg(pl.sum("chasings"))
		.join(join_df, left_on=["chaser", "chased"], right_on=["source", "target"], how="right")
		.fill_null(0)
		.sort("target", "source")  # necessary for deterministic output
		.collect(engine="in-memory")
	)

	diff = (pl.col(granularity) - days_range[-1]).abs()
	nodes = (
		context.table("ranking")
		.lazy()
		.filter(diff == diff.min())  # last window unit that updated the rank
		.group_by("animal_id")
		.agg(pl.last("ordinal"))
		.collect(engine="in-memory")
	)

	return connections, nodes


def _proportion_together(context: PlotContext, scope: Scope) -> pl.LazyFrame:
	"""Per-pair share of each phase spent together, over the positions in scope.

	``incohort_sociability`` stores this column for cages only, because the chance term it
	is compared against is built from cage occupancy. Every position shares one
	denominator, so summing the per-position ratios and dividing the summed time give the
	same number - which is what lets the scoped value be computed here and still agree
	exactly with the stored one at ``scope="cages"``.
	"""
	phase_seconds = pl.col("duration").dt.total_seconds(fractional=True)

	return (
		context.table("pairwise_meetings")
		.lazy()
		.filter(pl.col("position").is_in(context.scope_positions(scope)))
		.group_by("phase", "day", "phase_count", "animal_id", "animal_id_2")
		.agg(pl.sum("time_together"))
		.join(context.table("phase_durations").lazy(), on=["phase_count", "phase"], how="left")
		.select(
			"phase",
			"day",
			"phase_count",
			"animal_id",
			"animal_id_2",
			(pl.col("time_together").dt.total_seconds(fractional=True) / phase_seconds).alias(
				"proportion_together"
			),
		)
	)


def prep_network_sociability(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
	scope: Scope = "cages",
) -> pl.DataFrame:
	"""Return edges weighted by the time each pair spent together."""
	animals = context.animal_ids
	join_df = pl.LazyFrame(
		data=combinations(animals, 2),
		schema=[("source", pl.Enum(context.animal_ids)), ("target", pl.Enum(context.animal_ids))],
	)

	return (
		_proportion_together(context, scope)
		.filter(window_filter(days_range, granularity))
		.group_by("animal_id", "animal_id_2")
		.agg(pl.sum("proportion_together"))
		.join(
			join_df,
			left_on=["animal_id", "animal_id_2"],
			right_on=["source", "target"],
			how="right",
		)
		.sort("source", "target")  # order fixes the node positions
		.fill_null(0)
		.collect(engine="in-memory")
	)


def prep_directed_heatmap(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	agg: Aggregation,
	granularity: Granularity,
	animals: list[str],
	table: str,
	value: str,
	column: str,
	row: str,
	hours_range: tuple[int, int] | None = None,
) -> np.ndarray:
	"""Pivot a directed pair count into a ``column``-versus-``row`` matrix.

	Args:
		table: the pair table to read, such as ``chasings_df``.
		value: the count column in ``table``, such as ``chasings``.
		column: the animal column laid along the matrix columns, such as ``chaser``.
		row: the animal column laid along the matrix rows, such as ``chased``.
	"""
	join_df = pl.LazyFrame(
		product(animals, animals),
		schema=[(row, pl.Enum(context.animal_ids)), (column, pl.Enum(context.animal_ids))],
	)

	match agg:
		case "sum":
			agg_func = pl.sum(value).alias("sum")
		case "mean":
			agg_func = pl.mean(value).round(2).alias("mean")

	frame = (
		context.table(table)
		.lazy()
		.sort(row, column)
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity, hours_range),
		)
		.group_by(granularity, column, row)
		.agg(pl.sum(value))
		.group_by(column, row, maintain_order=True)
		.agg(agg_func)
		.join(join_df, on=[column, row], how="right")
		.collect(engine="in-memory")
	)

	return _matrix(frame, on=column, index=row, values=agg, animals=animals)


def prep_hourly_line(
	context: PlotContext,
	days_range: tuple[int, int],
	granularity: Granularity,
	table: str,
	animal_column: str,
	count: pl.Expr,
	hours_range: tuple[int, int] | None = None,
) -> pl.DataFrame:
	"""Hourly totals per animal, with the mean and SEM across window units.

	Args:
		table: the table to read, such as ``main_df``.
		animal_column: the animal column to total by, such as ``chaser``.
		count: what the rows of one animal, hour and window unit add up to, such as
			``pl.len()`` for antenna detections.
		hours_range: first and last hour to keep; the zero-fill scaffold is narrowed
			to match, so a dropped hour is absent rather than a zero bar.
	"""
	n_bins = _bins(days_range)
	hours = range(24) if hours_range is None else range(hours_range[0], hours_range[1] + 1)

	join_df = pl.LazyFrame(
		product(context.animal_ids, range(days_range[0], days_range[1] + 1), hours),
		schema=[
			(animal_column, pl.Enum(context.animal_ids)),
			(granularity, pl.Int16()),
			("hour", pl.Int8()),
		],
	)

	return (
		context.table(table)
		.lazy()
		.filter(window_filter(days_range, granularity, hours_range))
		.group_by(granularity, "hour", animal_column)
		.agg(count.alias("count"))
		.join(join_df, on=[animal_column, "hour", granularity], how="right")
		.fill_null(0)
		.group_by("hour", animal_column)
		.agg(
			pl.sum("count").alias("total"),
			pl.mean("count").alias("mean").round(2),
			(pl.std("count") / math.sqrt(n_bins)).alias("sem"),
		)
		.with_columns(
			(pl.col("mean") - pl.col("sem")).alias("lower"),
			(pl.col("mean") + pl.col("sem")).alias("upper"),
		)
		.sort(animal_column, "hour")
		.collect(engine="in-memory")
	)


def prep_activity(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	granularity: Granularity,
	agg: Aggregation,
	unit: durations.Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> tuple[pl.DataFrame, durations.DurationDisplay]:
	"""Visits and time spent per position and animal.

	A summed plot draws one row per animal and position; a mean plot keeps the
	window units so the box has a distribution to show. Aggregating here rather
	than in the plot is what keeps the hover text describing the value on screen.
	"""
	per_unit = (
		context.table("activity_df")
		.lazy()
		.with_columns(pl.col("position").cast(pl.String))
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity, hours_range),
		)
		.group_by(granularity, "animal_id", "position")
		.agg(
			pl.sum("visits_to_position").alias("visits"),
			pl.sum("time_in_position").alias("time"),
		)
	)

	if agg == "sum":
		per_unit = per_unit.group_by("animal_id", "position").agg(pl.sum("visits"), pl.sum("time"))

	frame = per_unit.sort("animal_id", "position").collect(engine="in-memory")

	return durations.to_display(frame, "time", unit, "Time spent")


def prep_time_alone(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	granularity: Granularity,
	agg: Aggregation,
	positions: list[str],
	unit: durations.Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> tuple[pl.DataFrame, durations.DurationDisplay]:
	"""Time each animal spent alone, per position."""
	per_unit = (
		context.table("activity_df")
		.lazy()
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity, hours_range),
			pl.col("position").is_in(positions),
		)
		.group_by(granularity, "animal_id", "position")
		.agg(pl.sum("time_alone"))
	)

	if agg == "sum":
		per_unit = per_unit.group_by("animal_id", "position").agg(pl.sum("time_alone"))

	frame = per_unit.sort("animal_id", "position").collect(engine="in-memory")

	return durations.to_display(frame, "time_alone", unit, "Time alone")


def _facet_matrices(
	frame: pl.DataFrame,
	facet: str,
	row: str,
	column: str,
	values: str,
	facets: list[str],
	rows: list[str],
	columns: list,
) -> np.ndarray:
	"""Pivot a long table into one ``(row, column)`` matrix per facet."""
	wide = (
		frame.pivot(on=column, index=[facet, row], values=values)
		.with_columns(pl.col(facet).cast(pl.String), pl.col(row).cast(pl.String))
		.sort(
			pl.col(facet).replace_strict(facets, range(len(facets)), return_dtype=pl.Int32),
			pl.col(row).replace_strict(rows, range(len(rows)), return_dtype=pl.Int32),
		)
		.select([str(label) for label in columns])
	)

	return wide.to_numpy().reshape(len(facets), len(rows), len(columns))


def prep_time_per_position(
	context: PlotContext,
	days_range: tuple[int, int],
	agg: Aggregation,
	granularity: Granularity,
	x: Literal["hour", "day", "phase_count"],
	positions: list[str],
	animals: list[str],
	unit: durations.Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> Heatmap:
	"""Time spent per position, as one animal-by-``x`` matrix per position.

	Args:
		x: the matrix columns - ``"hour"`` for the hours of the day, or the
			granularity for its window units. When it is ``"hour"``, ``hours_range``
			narrows the columns themselves rather than just which rows contribute.
	"""
	if x == "hour":
		x_values = list(
			range(24) if hours_range is None else range(hours_range[0], hours_range[1] + 1)
		)
	else:
		x_values = list(range(days_range[0], days_range[1] + 1))

	join_df = pl.LazyFrame(
		product(x_values, positions, animals),
		schema=[
			(x, pl.Int16()),
			("position", pl.String()),
			("animal_id", pl.Enum(context.animal_ids)),
		],
	)

	match agg:
		case "sum":
			agg_func = pl.sum("time_in_position")
		case "mean":
			agg_func = pl.mean("time_in_position")

	frame = (
		context.table("activity_df")
		.lazy()
		.with_columns(pl.col("position").cast(pl.String))
		.filter(
			window_filter(days_range, granularity, hours_range),
			pl.col("position").is_in(positions),
		)
		.group_by([x, "animal_id", "position"])
		.agg(agg_func)
		.join(join_df, on=[x, "position", "animal_id"], how="right")
		.collect(engine="in-memory")
	)

	frame, rendered = durations.to_display(frame, "time_in_position", unit, "Time spent")
	shape = ("position", "animal_id", x)

	return Heatmap(
		values=_facet_matrices(frame, *shape, "time_in_position", positions, animals, x_values),
		text=_facet_matrices(frame, *shape, "time_in_position_text", positions, animals, x_values),
		label=rendered.label,
		x=x_values,
		y=animals,
		facets=positions,
	)


def prep_cage_preference(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	granularity: Granularity,
	positions: list[str],
	unit: durations.Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> tuple[pl.DataFrame, durations.DurationDisplay]:
	"""Time spent per position, per animal and window unit."""
	frame = (
		context.table("activity_df")
		.lazy()
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity, hours_range),
		)
		.with_columns(pl.col("position").cast(pl.String))
		.group_by(granularity, "animal_id", "position")
		.agg(pl.sum("time_in_position"))
		.filter(pl.col("position").is_in(positions))
		.sort("position")
		.collect(engine="in-memory")
	)

	return durations.to_display(frame, "time_in_position", unit, "Time spent")


def prep_pairwise_sociability(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	agg: Aggregation,
	metric: Literal["time_together", "pairwise_encounters"],
	granularity: Granularity,
	positions: list[str],
	animals: list[str],
	unit: durations.Unit | Literal["auto"] = "auto",
	hours_range: tuple[int, int] | None = None,
) -> Heatmap:
	"""Pivot pairwise meetings into one animal-by-animal matrix per position."""
	join_df = pl.LazyFrame(
		product(positions, animals, animals),
		schema=[
			("position", pl.Categorical()),
			("animal_id", pl.Enum(context.animal_ids)),
			("animal_id_2", pl.Enum(context.animal_ids)),
		],
	)

	frame = (
		context.table("pairwise_meetings")
		.lazy()
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity, hours_range),
		)
		.group_by(["animal_id", "animal_id_2", "position"], maintain_order=True)
		.agg(
			pl.sum(metric).alias("sum"),
			pl.mean(metric).alias("mean"),
		)
		.join(join_df, on=["position", "animal_id", "animal_id_2"], how="right")
		.collect(engine="in-memory")
	)

	shape = ("position", "animal_id", "animal_id_2")

	if metric == "pairwise_encounters":
		return Heatmap(
			values=_facet_matrices(frame, *shape, agg, positions, animals, animals),
			text=None,
			label="<b>Number</b>",
			x=animals,
			y=animals,
			facets=positions,
		)

	frame, rendered = durations.to_display(frame, agg, unit, "Time together")

	return Heatmap(
		values=_facet_matrices(frame, *shape, agg, positions, animals, animals),
		text=_facet_matrices(frame, *shape, f"{agg}_text", positions, animals, animals),
		label=rendered.label,
		x=animals,
		y=animals,
		facets=positions,
	)


def prep_within_cohort_sociability(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	metric: Literal["proportion_together", "sociability"],
	granularity: Granularity,
	animals: list[str],
	scope: Scope = "cages",
) -> np.ndarray:
	"""Pivot mean cohort sociability into an animal-by-animal matrix.

	``scope`` applies to ``proportion_together`` only. ``sociability`` is measured against
	a cage-only chance expectation, so it is read from ``incohort_sociability`` as stored.
	"""
	join_df = pl.LazyFrame(
		product(animals, animals),
		schema=[
			("animal_id", pl.Enum(context.animal_ids)),
			("animal_id_2", pl.Enum(context.animal_ids)),
		],
	)

	source = (
		_proportion_together(context, scope)
		if metric == "proportion_together"
		else context.table("incohort_sociability").lazy()
	)

	frame = (
		source.with_columns(pl.col(metric).round(3))
		.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity),
		)
		.group_by(["animal_id", "animal_id_2"], maintain_order=True)
		.agg(pl.mean(metric).round(2).alias("mean"))
		.join(join_df, on=["animal_id", "animal_id_2"], how="right")
		.collect(engine="in-memory")
	)

	return _matrix(frame, on="animal_id_2", index="animal_id", values="mean", animals=animals)


def prep_social_stability(
	context: PlotContext,
	days_range: tuple[int, int],
	phase_type: list[str],
	granularity: Granularity,
	scope: Scope = "cages",
) -> pl.DataFrame:
	"""Median time together per pair, with a stability score from its dispersion."""
	mad = (pl.col("proportion_together") - pl.median("proportion_together")).abs().median()

	frame = _proportion_together(context, scope)
	frame = pl.concat(
		[frame, frame.rename({"animal_id": "animal_id_2", "animal_id_2": "animal_id"})]
	)

	return (
		frame.filter(
			pl.col("phase").is_in(phase_type),
			window_filter(days_range, granularity),
		)
		.group_by(granularity, "animal_id", "animal_id_2")
		.agg(pl.mean("proportion_together"))
		.sort("animal_id", "animal_id_2", granularity)
		.group_by("animal_id", "animal_id_2")
		.agg(
			# +1e-10 avoids a division by zero turning stability into NaN
			(1 - (mad / (pl.median("proportion_together") + 1e-10)))
			.clip(0, 1)
			.round(2)
			.alias("stability"),
			pl.median("proportion_together").round(2),
		)
		.sort("animal_id")
		.collect(engine="in-memory")
	)


def prep_quality_heatmap(context: PlotContext, animals: list[str]) -> tuple[np.ndarray, list[str]]:
	"""Miss rate per animal and antenna, as an animal-by-antenna matrix.

	``recording_quality`` already has one row per animal and antenna - it is built
	from a cross join - so no zero-filling scaffold is needed here, unlike the pair
	matrices.

	Returns:
		The matrix, its rows in ``animals`` order, and the antenna column labels in
		antenna order.
	"""
	frame = context.table("recording_quality")
	antennas = [str(antenna) for antenna in sorted(frame["antenna"].unique().to_list())]

	wide = (
		frame.pivot(on="antenna", index="animal_id", values="miss_rate")
		.with_columns(pl.col("animal_id").cast(pl.String))
		.sort(
			pl.col("animal_id").replace_strict(animals, range(len(animals)), return_dtype=pl.Int32)
		)
		.select(antennas)
	)

	return wide.to_numpy(), antennas


def prep_quality_by_antenna(context: PlotContext) -> pl.DataFrame:
	"""Miss rate per antenna, pooled across the cohort.

	A pooled rate is ``missed.sum() / (missed + detected).sum()``, never the mean of
	the per-animal cell rates, so a lightly-sampled animal cannot skew an antenna's
	rate as much as a heavily-sampled one.
	"""
	detected, missed = pl.col("detected"), pl.col("missed")

	return (
		context.table("recording_quality")
		.lazy()
		.group_by("antenna")
		.agg(detected.sum(), missed.sum())
		.with_columns(
			pl.when(detected + missed > 0)
			.then(100 * missed / (detected + missed))
			.otherwise(0.0)
			.alias("miss_rate")
		)
		.sort("antenna")
		.collect(engine="in-memory")
	)
