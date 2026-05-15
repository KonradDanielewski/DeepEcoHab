from typing import (
	Any,
	Callable,
	Iterator,
)
from deepecohab.utils.auxfun_plots import PlotConfig

class DataFrameRegistry:
	def __init__(self):
		self._registry: dict[str, Callable] = {}
		self.analysis_steps: list[str] = [
			"activity_df",
			"cage_occupancy",
			"chasings_df",
			"tube_test_df",
			"ranking",
			"pairwise_meetings",
			"incohort_sociability",
			"time_alone",
			"feature_df",
		]

	def register(self, name: str):
		"""Decorator to register a new plot type."""

		def wrapper(func: Callable):
			self._registry[name] = func
			return func

		return wrapper

	def list_available(self) -> list[str]:
		"""Returns a list of all registered function names."""
		return list(self._registry.keys())

	def run_pipeline(
		self, config: dict[str, Any], **kwargs
	) -> Iterator[tuple[str, int, list[int]]]:
		"""Runs the pipeline and yields status updates.

		Yields:
			(step_name, current_index, total_steps)
		"""
		total = len(self.analysis_steps)
		for i, name in enumerate(self.analysis_steps):	
			func = self._registry[name]
			func(config, **kwargs)
			yield name, i + 1, total


class PlotRegistry:
	"""Registry for dashboard plots."""

	def __init__(self):
		self._registry: dict[str, Callable[[PlotConfig], Any]] = {}
		self._plot_dependencies: dict[str, list[str]] = {}

	def register(self, name: str, dependencies: list[str] = None):
		"""Decorator to register a new plot type."""

		def wrapper(func: Callable[[PlotConfig], Any]):
			self._registry[name] = func
			self._plot_dependencies[name] = dependencies
			return func

		return wrapper

	def get_dependencies(self, name: str) -> list[str]:
		"""Returns the list of PlotConfig attributes used by a specific plot."""
		return self._plot_dependencies.get(name, list())

	def get_plot(self, name: str, config: PlotConfig):
		plotter = self._registry.get(name)
		if not plotter:
			return {}
		return plotter(config)

	def list_available(self) -> list[str]:
		return list(self._registry.keys())


df_registry = DataFrameRegistry()
plot_registry = PlotRegistry()
