import functools
import inspect
from collections.abc import Callable, Iterator, Sequence
from dataclasses import fields
from pathlib import Path
from typing import (
	Any,
)

import polars as pl

from deepecohab.utils.auxfun_plots import PlotConfig


class DataFrameRegistry:
	"""Registry of data-key builders and the dependency graph between them.

	Steps register either as bespoke data-structure builders (``register``)
	or as lifecycle-wrapped analysis steps with declared requirements
	(``register_step``); the latter define the dependency graph used to
	derive a topological run order.
	"""

	def __init__(self):
		self._registry: dict[str, Callable] = {}
		# name -> data keys the step reads. Only analysis steps (registered via
		# register_step) appear here; this is what defines the dependency graph.
		self._requires: dict[str, list[str]] = {}

	def register(self, name: str):
		"""Register a known data key and its builder, as-is.

		Used for the data-structure stage (main_df, padded_df, phase_durations):
		those have bespoke signatures, build several outputs at once and run
		before the analysis pipeline, so they are not lifecycle-wrapped and are
		not nodes in the analysis dependency graph. They are still listed in
		``list_available`` so they can be loaded by key.
		"""

		def wrapper(func: Callable):
			self._registry[name] = func
			return func

		return wrapper

	def register_step(self, name: str, requires: Sequence[str] = ()):
		"""Register an analysis pipeline step.

		The wrapped function becomes pure compute: it receives the resolved
		config dict and returns a LazyFrame. This decorator owns the shared
		lifecycle - cache short-circuit, results-path resolution and parquet
		sinking - and records ``requires`` so ``run_pipeline`` can derive a valid
		execution order by topological sort.

		Args:
			name: output key, also the ``results/<name>.parquet`` filename.
			requires: data keys this step reads via ``auxfun._get_data``. Keys
				that are themselves steps create dependency edges; keys produced
				by the data-structure stage (e.g. main_df) are treated as
				external prerequisites and create no edge.
		"""

		def wrapper(func: Callable):
			@functools.wraps(func)
			def lifecycle(
				config_path: str | Path | dict,
				*,
				overwrite: bool = False,
				save_data: bool = True,
				**kwargs,
			) -> pl.LazyFrame:
				from deepecohab.utils import auxfun

				cfg: dict[str, Any] = auxfun.read_config(config_path)

				if not overwrite:
					cached = auxfun.load_ecohab_data(config_path, name)
					if isinstance(cached, pl.LazyFrame):
						return cached

				result: pl.LazyFrame = func(cfg, **kwargs)

				if save_data:
					results_path = Path(cfg["project_location"]) / "results" / f"{name}.parquet"
					result.sink_parquet(results_path, compression="lz4", engine="streaming")

				return result

			self._registry[name] = lifecycle
			self._requires[name] = list(requires)
			return lifecycle

		return wrapper

	def list_available(self) -> list[str]:
		"""Returns a list of all registered data keys."""
		return list(self._registry.keys())

	def _resolve_order(self, targets: list[str] | None = None) -> list[str]:
		"""Topologically sort the analysis steps.

		Edges run from a step to each of its required keys that is itself a step.
		Required keys with no producing step are external prerequisites and are
		ignored here. If ``targets`` is given, only those steps and their
		transitive dependencies are returned.
		"""
		steps = set(self._requires)

		deps: dict[str, set[str]] = {
			name: {req for req in self._requires[name] if req in steps} for name in steps
		}

		if targets is not None:
			unknown = set(targets) - steps
			if unknown:
				raise KeyError(f"Unknown analysis step(s): {sorted(unknown)}")
			wanted: set[str] = set()
			stack = list(targets)
			while stack:
				step = stack.pop()
				if step in wanted:
					continue
				wanted.add(step)
				stack.extend(deps[step])
			deps = {name: (d & wanted) for name, d in deps.items() if name in wanted}

		# Kahn's algorithm; ready set kept sorted for a deterministic order.
		indegree = {name: len(d) for name, d in deps.items()}
		ready = sorted(name for name, n in indegree.items() if n == 0)
		order: list[str] = []
		while ready:
			node = ready.pop(0)
			order.append(node)
			for other, d in deps.items():
				if node in d:
					indegree[other] -= 1
					if indegree[other] == 0:
						ready.append(other)
			ready.sort()

		if len(order) != len(deps):
			raise ValueError(
				f"Cycle detected among analysis steps: {sorted(set(deps) - set(order))}"
			)

		return order

	@property
	def analysis_steps(self) -> list[str]:
		"""A valid topological execution order of all analysis steps."""
		return self._resolve_order()

	def run_pipeline(
		self, config: dict[str, Any], targets: list[str] | None = None, **kwargs
	) -> Iterator[tuple[str, int, int]]:
		"""Runs the pipeline in dependency order and yields status updates.

		Args:
			config: project config (path or dict).
			targets: if given, run only these steps and their dependencies;
				otherwise run every step.

		Yields:
			(step_name, current_index, total_steps)
		"""
		order = self._resolve_order(targets)
		total = len(order)
		for i, name in enumerate(order):
			self._registry[name](config, **kwargs)
			yield name, i + 1, total


class PlotRegistry:
	"""Registry for dashboard plots.

	A plot's dependencies are its function parameters: each parameter name must
	match a ``PlotConfig`` field, and the registry injects those fields by
	keyword at render time. The signature is therefore the single source of
	truth for what a plot needs - there is no separate dependency list to keep
	in sync, and parameters are annotated with their real (non-optional) types
	because the registry guarantees they are populated before dispatch.
	"""

	def __init__(self):
		self._registry: dict[str, Callable[..., Any]] = {}
		self._plot_dependencies: dict[str, list[str]] = {}
		self._config_fields = {f.name for f in fields(PlotConfig)}

	def register(self, name: str):
		"""Decorator to register a new plot type.

		The wrapped function's parameter names declare which ``PlotConfig``
		fields it consumes. Unknown parameter names raise at import time so a
		typo fails fast rather than at first render.
		"""

		def wrapper(func: Callable[..., Any]):
			deps = list(inspect.signature(func).parameters)
			unknown = set(deps) - self._config_fields
			if unknown:
				raise ValueError(
					f"Plot {name!r} requests non-PlotConfig field(s): {sorted(unknown)}"
				)
			self._registry[name] = func
			self._plot_dependencies[name] = deps
			return func

		return wrapper

	def get_dependencies(self, name: str) -> list[str]:
		"""Returns the list of PlotConfig attributes used by a specific plot."""
		return self._plot_dependencies.get(name, [])

	def get_plot(self, name: str, config: PlotConfig):
		"""Build the named plot from ``config``; returns ``{}`` if it is unregistered.

		Validates that every field the plot declares as a parameter was populated
		on ``config`` before dispatching, so a missing selection fails fast with a
		clear error instead of surfacing deep inside polars/plotly.
		"""
		plotter = self._registry.get(name)
		if not plotter:
			return {}
		values = {dep: getattr(config, dep) for dep in self._plot_dependencies[name]}
		missing = [key for key, value in values.items() if value is None]
		if missing:
			raise ValueError(
				f"Plot {name!r} requires PlotConfig field(s) {missing}, which are None."
			)
		return plotter(**values)

	def list_available(self) -> list[str]:
		"""Returns the names of all registered plots."""
		return list(self._registry.keys())


df_registry = DataFrameRegistry()
plot_registry = PlotRegistry()
