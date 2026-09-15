from importlib import import_module
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from deepecohab.core import (
	# Imported for their side effect: defining the steps of the analysis pipeline.
	antenna_analysis as antenna_analysis,
	recording_pipeline as recording_pipeline,
)
from deepecohab.core.data_model import (
	AnalysisParams as AnalysisParams,
	Project as Project,
	Recording as Recording,
)

if TYPE_CHECKING:
	from deepecohab.plotting import (
		PlotContext as PlotContext,
		PlotRegistry as PlotRegistry,
		available_attributes as available_attributes,
		plot as plot,
		plot_specs as plot_specs,
		set_default_theme as set_default_theme,
	)

__version__ = version("deepecohab")

_LAZY_EXPORTS = {
	"PlotContext": "deepecohab.plotting",
	"PlotRegistry": "deepecohab.plotting",
	"available_attributes": "deepecohab.plotting",
	"plot": "deepecohab.plotting",
	"plot_specs": "deepecohab.plotting",
	"set_default_theme": "deepecohab.plotting",
}


def __getattr__(name: str) -> Any:
	"""Resolve the plotting exports on first access."""
	module = _LAZY_EXPORTS.get(name)

	if module is None:
		raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

	return getattr(import_module(module), name)


def __dir__() -> list[str]:
	"""List the eager and lazy exports together."""
	return sorted({*globals(), *_LAZY_EXPORTS})
