from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, get_args

import plotly.graph_objects as go
import polars as pl

from deepecohab.core.data_model import Layout
from deepecohab.plotting.registry import PlotRegistry

if TYPE_CHECKING:
	from deepecohab.core.data_model import Recording

Granularity = Literal["day", "phase_count"]

Scope = Literal["all", "cages", "tunnels"]
"""Which positions a plot covers. Cages and tunnels carry the same measures."""

FacetScope = Literal["cages", "tunnels"]
"""``Scope`` without ``"all"``, for the plots that draw one panel per position.

Faceted heatmaps share a single colour axis across their panels, and cage dwell runs to
hours where tunnel dwell runs to seconds - so mixing the two renders the tunnel panels a
uniform dark. Those plots offer one kind at a time instead.
"""

SCOPE_NOUN: Final[dict[str, str]] = {"cages": "cage", "tunnels": "tunnel", "all": "position"}
"""The word a scope goes by in a title or an axis label."""


class TableProvider(Protocol):
	"""Source of the analysis tables a plot reads."""

	def table(self, key: str) -> pl.DataFrame:
		"""Return the analysis table registered under ``key``."""
		...

	def has(self, key: str) -> bool:
		"""Whether ``key`` has been computed and can be read."""
		...


@dataclass(eq=False)
class RecordingTables:
	"""Table provider backed by one recording's results directory.

	Args:
		recording: the recording whose parquets are read.
	"""

	recording: "Recording"
	_loaded: dict[str, pl.DataFrame] = field(default_factory=dict, repr=False)

	def table(self, key: str) -> pl.DataFrame:
		"""Load and cache the analysis table registered under ``key``."""
		if key not in self._loaded:
			self._loaded[key] = self.recording.load_results(key, eager=True)

		return self._loaded[key]

	def has(self, key: str) -> bool:
		"""Whether the step producing ``key`` has run for this recording."""
		return key in self._loaded or (self.recording.results_path / f"{key}.parquet").is_file()


@dataclass(eq=False)
class PlotContext:
	"""Everything a plot needs that is not a user selection.

	Attributes:
		tables: source of the analysis tables.
		animal_ids: every cohort tag, sorted; the order colours are assigned in.
		cages: cage names.
		positions: cages and tunnels.
		phases: phase onsets in hours since the ``start_from`` onset, where the hour axis
			begins.
		days_range: first and last experiment day.
		phase_range: first and last phase occurrence.
	"""

	tables: TableProvider
	animal_ids: list[str]
	cages: list[str]
	positions: list[str]
	phases: dict[str, float]
	days_range: tuple[int, int]
	phase_range: tuple[int, int]

	@classmethod
	def from_recording(cls, recording: "Recording") -> "PlotContext":
		"""Build a context from an analysed recording.

		Args:
			recording: a recording whose pipeline has been run.

		Returns:
			A context reading that recording's results.
		"""
		timeline = recording.timeline
		onsets = {
			name: onset.hour + onset.minute / 60 + onset.second / 3600
			for name, onset in timeline.phases.items()
		}

		return cls(
			tables=RecordingTables(recording),
			animal_ids=recording.cohort.animal_tags,
			cages=recording.layout.cage_names,
			positions=recording.layout.positions_non_directional,
			phases={
				name: (hours - onsets[timeline.start_from]) % 24 for name, hours in onsets.items()
			},
			days_range=timeline.days_range,
			phase_range=timeline.phase_range,
		)

	@cached_property
	def animals(self) -> pl.DataFrame:
		"""Cohort metadata, one row per animal."""
		return self.table("animals")

	@property
	def tunnels(self) -> list[str]:
		"""Tunnel names: the positions that are neither cages nor the undefined sentinel.

		Derived rather than stored, since ``positions`` already holds cages, tunnels and
		the sentinel, and a context built by hand would otherwise have to repeat itself.
		"""
		known = {*self.cages, Layout.UNDEFINED}
		return [position for position in self.positions if position not in known]

	def scope_positions(self, scope: Scope) -> list[str]:
		"""The positions a scope selection covers.

		Args:
			scope: ``"cages"``, ``"tunnels"`` or ``"all"``.

		Raises:
			ValueError: ``scope`` is not one of the three.

		Returns:
			Cage and/or tunnel names. The ``undefined`` sentinel is never among them: it
			is not a place, and no measure is attributed to it.
		"""
		match scope:
			case "cages":
				return self.cages
			case "tunnels":
				return self.tunnels
			case "all":
				return [*self.cages, *self.tunnels]
			case _:
				raise ValueError(f"scope must be one of {get_args(Scope)}, got {scope!r}")

	def table(self, key: str) -> pl.DataFrame:
		"""Return the analysis table registered under ``key``."""
		return self.tables.table(key)

	def __contains__(self, key: str) -> bool:
		"""Whether the analysis table ``key`` is available to read."""
		return self.tables.has(key)

	def axis_range(self, granularity: Granularity) -> tuple[int, int]:
		"""Full range of the day or phase axis, for an unset selection.

		Args:
			granularity: which axis to measure.

		Raises:
			ValueError: ``granularity`` is not one of the two axis columns.

		Returns:
			The first and last value of that axis.
		"""
		if granularity not in get_args(Granularity):
			raise ValueError(
				f"granularity must be one of {get_args(Granularity)}, got {granularity!r}"
			)

		return self.phase_range if granularity == "phase_count" else self.days_range

	def available_plots(self, computed_only: bool = False) -> list[str]:
		"""Names of the plots that can be built.

		Args:
			computed_only: keep only plots whose required tables have been computed.

		Returns:
			The registered plot names.
		"""
		names = PlotRegistry.list_available()

		if not computed_only:
			return names

		return [
			name
			for name in names
			if all(table in self for table in PlotRegistry.spec(name).requires)
		]

	def plot(self, name: str, **options: Any) -> go.Figure:
		"""Build a plot against this context.

		Args:
			name: registry key.
			**options: overrides for the plot's keyword arguments.

		Returns:
			The figure.
		"""
		return PlotRegistry.build(name, self, **options)
