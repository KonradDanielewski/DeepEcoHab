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
from deepecohab.plotting.context import PlotContext as PlotContext
from deepecohab.plotting.export import (
	export_figure as export_figure,
	fit_for_export as fit_for_export,
)
from deepecohab.plotting.registry import (
	Option as Option,
	PlotRegistry as PlotRegistry,
	PlotSpec as PlotSpec,
)

if TYPE_CHECKING:
	from deepecohab.core.data_model import Recording


def plot(name: str, target: "Recording | PlotContext", **options: Any) -> go.Figure:
	"""Build one plot from a recording or a context.

	Hold a :class:`PlotContext` when making several plots: it caches the analysis
	tables it has already read, which a recording passed here cannot do.

	Args:
		name: registry key, as listed by :meth:`PlotRegistry.list_available`.
		**options: overrides for the plot's keyword arguments.
	"""
	context = target if isinstance(target, PlotContext) else PlotContext.from_recording(target)
	return PlotRegistry.build(name, context, **options)
