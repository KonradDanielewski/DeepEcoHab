from typing import TYPE_CHECKING, Any

import plotly.graph_objects as go

from deepecohab.plotting import (
	# Imported for its side effect: registering every plot in the catalog.
	plot_catalog as plot_catalog,
)
from deepecohab.plotting.animals import (
	COLOR_COLUMNS as COLOR_COLUMNS,
	ColorMapping as ColorMapping,
	available_attributes as available_attributes,
)
from deepecohab.plotting.context import (
	PlotContext as PlotContext,
	TableProvider as TableProvider,
)
from deepecohab.plotting.durations import DurationDisplay as DurationDisplay
from deepecohab.plotting.registry import (
	Option as Option,
	PlotRegistry as PlotRegistry,
	PlotSpec as PlotSpec,
)
from deepecohab.plotting.theme import set_default_theme as set_default_theme

if TYPE_CHECKING:
	from deepecohab.core.data_model import Recording


def _as_context(target: "Recording | PlotContext") -> PlotContext:
	"""Accept either a recording or an already-built context."""
	return target if isinstance(target, PlotContext) else PlotContext.from_recording(target)


def plot(name: str, target: "Recording | PlotContext", **options: Any) -> go.Figure:
	"""Build one plot from a recording or a context.

	Hold a :class:`PlotContext` when making several plots: it caches the analysis
	tables it has already read, which a recording passed here cannot do.

	Args:
		name: registry key, as listed by :meth:`PlotRegistry.list_available`.
		target: the recording to plot, or a context built from one.
		**options: overrides for the plot's keyword arguments.

	Returns:
		The figure.
	"""
	return PlotRegistry.build(name, _as_context(target), **options)


def plot_specs(target: "Recording | PlotContext | None" = None) -> list[dict[str, Any]]:
	"""Describe every registered plot, for a GUI to build controls from.

	Args:
		target: resolve cohort-dependent choices against this recording or context.

	Returns:
		One serializable description per plot.
	"""
	context = None if target is None else _as_context(target)

	return [spec.describe(context) for spec in PlotRegistry.specs()]
