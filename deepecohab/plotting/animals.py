from dataclasses import dataclass, field

import plotly.graph_objects as go
import polars as pl

from deepecohab.plotting import theme
from deepecohab.plotting.context import PlotContext

COLOR_COLUMNS: tuple[str, ...] = (
	"animal_id",
	"subject_name",
	"sex",
	"genotype",
	"treatment",
	"mouse_line",
	"genetic_background",
)


@dataclass(frozen=True, eq=False)
class ColorMapping:
	"""Which column drives colour, and the colour every category gets.

	Attributes:
		column: the column plots pass to plotly's ``color``.
		animal_column: the frame's animal key column, such as ``chaser``.
		categories: category order, covering the whole cohort.
		colors: one colour per category.
		category_by_animal: the category each cohort tag belongs to.
		legend_title: heading for the colour legend.
		animal_order: cohort tags grouped into contiguous blocks by attribute value,
			then by tag - the axis/trace order for a per-animal plot.
		group_mean: whether traces average their animals into one line per group,
			set by :func:`resolve_colors` only when ``color_by`` is an attribute.
	"""

	column: str
	animal_column: str
	categories: list[str]
	colors: dict[str, str]
	category_by_animal: dict[str, str]
	legend_title: str
	animal_order: list[str] = field(default_factory=list)
	group_mean: bool = False

	@property
	def by_animal(self) -> dict[str, str]:
		"""Colour for each cohort tag, so a trace stays per animal.

		Colouring by an attribute still draws one trace per animal; they simply
		share their group's colour, and :func:`collapse_legend` folds the repeated
		entries into one per group.
		"""
		return {tag: self.colors[category] for tag, category in self.category_by_animal.items()}

	@property
	def trace_column(self) -> str:
		"""The frame column driving one trace per group when averaging, else per animal."""
		return self.column if self.group_mean else self.animal_column

	@property
	def trace_colors(self) -> dict[str, str]:
		"""Colour per value of :attr:`trace_column`."""
		return self.colors if self.group_mean else self.by_animal

	@property
	def order(self) -> list[str]:
		"""Trace/category order matching :attr:`trace_column`."""
		return self.categories if self.group_mean else self.animal_order


def available_attributes(context: PlotContext) -> list[str]:
	"""``animal_id`` plus every attribute taking more than one distinct value."""
	animals = context.animals
	varying = [
		column
		for column in COLOR_COLUMNS
		if column != "animal_id" and column in animals.columns and animals[column].n_unique() > 1
	]

	return ["animal_id", *varying]


def _categories(context: PlotContext, color_by: str) -> list[str]:
	"""Every value ``color_by`` takes across the cohort, in legend order."""
	if color_by == "animal_id":
		return list(context.animal_ids)

	return context.animals[color_by].drop_nulls().unique().sort().to_list()


def resolve_colors(
	context: PlotContext,
	color_by: str,
	cmap: str = "Phase",
	animal_column: str = "animal_id",
	group_mean: bool = False,
) -> ColorMapping:
	"""Map every category of ``color_by`` to a colour.

	Categories come from the whole cohort rather than the plotted frame, so an
	animal keeps its colour when a selection drops some of its cohort.

	Args:
		color_by: ``animal_id`` or any cohort attribute.
		cmap: colorscale the categories are sampled from.
		animal_column: the frame's own animal column, such as ``chaser``, used when
			colouring by animal rather than by attribute.
		group_mean: average traces within each colour group, only meaningful when
			``color_by`` is an attribute - colouring by animal keeps one trace per
			animal regardless.

	Raises:
		ValueError: ``color_by`` is not a colourable column.
	"""
	if color_by not in COLOR_COLUMNS:
		raise ValueError(f"color_by must be one of {COLOR_COLUMNS}, got {color_by!r}")

	categories = _categories(context, color_by)
	colors = theme.sample_palette(len(categories), cmap)
	title = animal_column if color_by == "animal_id" else color_by

	if color_by == "animal_id":
		category_by_animal = {tag: tag for tag in context.animal_ids}
	else:
		category_by_animal = dict(
			context.animals.select(
				pl.col("animal_id").cast(pl.String), pl.col(color_by).cast(pl.String)
			).iter_rows()
		)

	return ColorMapping(
		column=animal_column if color_by == "animal_id" else color_by,
		animal_column=animal_column,
		categories=categories,
		colors=dict(zip(categories, colors, strict=True)),
		category_by_animal=category_by_animal,
		legend_title=f"<b>{title.replace('_', ' ').capitalize()}</b>",
		animal_order=order_by_attribute(context, color_by),
		group_mean=group_mean and color_by != "animal_id",
	)


def mean_by_group(frame: pl.DataFrame, mapping: ColorMapping, values: list[str]) -> pl.DataFrame:
	"""Average per-animal ``values`` across each colour group's animals.

	A no-op unless ``mapping.group_mean``. Otherwise the animal column is relabelled
	to its group and renamed to ``mapping.column``, every other column stays a
	grouping key, and ``values`` are averaged within each group. A ``"mean"`` value
	gets its ``sem``/``lower``/``upper`` recomputed from the spread across the
	group's animals, replacing whatever per-animal band those columns held.

	Args:
		frame: a per-animal frame keyed on ``mapping.animal_column``.
		mapping: the colour mapping driving the grouping.
		values: value columns to average.

	Returns:
		``frame`` unchanged, or one row per group and remaining key instead of per animal.
	"""
	if not mapping.group_mean:
		return frame

	keys = [
		column
		for column in frame.columns
		if column not in {mapping.animal_column, *values, "sem", "lower", "upper"}
	]
	aggs = [pl.mean(value).alias(value) for value in values]
	if "mean" in values:
		aggs.append(
			(pl.col("mean").std() / pl.col("mean").count().sqrt()).fill_null(0.0).alias("sem")
		)

	grouped = (
		frame.with_columns(
			pl.col(mapping.animal_column)
			.cast(pl.String)
			.replace(mapping.category_by_animal)
			.alias(mapping.column)
		)
		.group_by([mapping.column, *keys], maintain_order=True)
		.agg(*aggs)
		.sort([mapping.column, *keys])
	)

	if "mean" in values:
		grouped = grouped.with_columns(
			(pl.col("mean") - pl.col("sem")).alias("lower"),
			(pl.col("mean") + pl.col("sem")).alias("upper"),
		)

	return grouped


def collapse_legend(figure: go.Figure, mapping: ColorMapping) -> None:
	"""Fold per-animal traces into one legend entry per colour category.

	The categories' colours also become the figure's ``colorway``, which is how the
	recording page's Format tells them apart from any other colour to swap a palette.

	Args:
		figure: a figure whose traces are named after animals.
		mapping: the colour mapping those traces were built from.
	"""
	figure.update_layout(colorway=list(mapping.colors.values()))
	seen: set[str] = set()

	for trace in figure.data:
		category = mapping.category_by_animal.get(trace.name, trace.name)
		trace.legendgroup = category
		trace.name = category

		# An explicitly hidden trace, such as an error band, stays hidden and does
		# not claim the category its visible sibling still needs.
		if trace.showlegend is False:
			continue

		trace.showlegend = category not in seen
		seen.add(category)


def order_by_attribute(context: PlotContext, color_by: str) -> list[str]:
	"""Cohort tags grouped into contiguous blocks by attribute value.

	Matrix plots colour by their metric, so an attribute reorders their axes
	instead of recolouring them.

	Args:
		color_by: the attribute to group by; ``animal_id`` keeps cohort order.

	Returns:
		Every cohort tag, ordered by attribute value then by tag.
	"""
	if color_by == "animal_id":
		return list(context.animal_ids)

	return (
		context.animals.sort(color_by, "animal_id")
		.get_column("animal_id")
		.cast(pl.String)
		.to_list()
	)
