import datetime as dt
import graphlib
import json
import logging
import queue
import shutil
import threading
import warnings
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations, pairwise, product
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, NamedTuple, overload
from zoneinfo import ZoneInfo

import polars as pl
from pydantic import (
	AwareDatetime,
	BaseModel,
	ConfigDict,
	Field,
	PastDate,
	PositiveInt,
	PrivateAttr,
	ValidationInfo,
	computed_field,
	field_serializer,
	model_validator,
)
from tqdm.auto import tqdm

CALENDAR_COLUMNS: Final = ("phase", "day", "phase_count", "hour")
"""The columns placing a row on the recording's calendar; every analysis table is keyed by them."""

LEAD_WARNING_THRESHOLD: Final = dt.timedelta(hours=1)
"""How far off a phase onset acquisition may start before adding a recording warns."""


def _elapsed(earlier: dt.datetime, later: dt.datetime) -> dt.timedelta:
	"""Real time between two aware datetimes.

	Both sides go through UTC first: subtracting two datetimes that share a tzinfo
	object gives the wall-clock difference rather than the elapsed one, and ZoneInfo
	instances are cached, so a span crossing a DST transition would come out an hour off.
	"""
	return later.astimezone(dt.UTC) - earlier.astimezone(dt.UTC)


class Cage(BaseModel):
	"""EcoHab habitat cage."""

	name: str
	cell_id: str
	cage_type: str
	antennas: list[str]


class Tunnel(BaseModel):
	"""EcoHab habitat tunnel."""

	name: str
	tunnel_no: int
	start_cell_id: str
	end_cell_id: str
	dead_end: bool
	antenna_count: int
	antennas: list[str]


class Layout(BaseModel):
	"""EcoHab habitat layout.

	Defines cages and tunnels within a recording and possible antenna pairs,
	as well as mapping of tunnels (directional to non-directional).
	"""

	UNDEFINED: ClassVar[str] = "undefined"

	cages: list[Cage]
	tunnels: list[Tunnel]
	antenna_combinations: dict[str, str]
	tunnels_map: dict[str, str]

	@computed_field
	@property
	def positions_directional(self) -> list[str]:
		"""All cage and tunnel names in directional format, plus the sentinel for unresolved positions."""
		return [*sorted(set(self.antenna_combinations.values())), self.UNDEFINED]

	@computed_field
	@property
	def positions_non_directional(self) -> list[str]:
		"""All cage and tunnel names in non-directional format, plus the sentinel for unresolved positions."""
		return [c.name for c in self.cages] + [t.name for t in self.tunnels] + [self.UNDEFINED]

	@property
	def cage_names(self) -> list[str]:
		"""Cage names, sorted."""
		return sorted(cage.name for cage in self.cages)

	@property
	def tunnel_names(self) -> list[str]:
		"""Undirected tunnel names, sorted."""
		return sorted(tunnel.name for tunnel in self.tunnels)

	@property
	def tunnel_names_directional(self) -> list[str]:
		"""Directional tunnel positions (e.g. ``c1_c2``), as they appear in ``main_df``.

		These are the keys of ``tunnels_map``: the positions before
		``transforms.remove_tunnel_directionality`` collapses a tunnel's two ends into one.
		"""
		return sorted(self.tunnels_map)


class Animal(BaseModel):
	"""EcoHab animal class.

	Stores information about animal from the cohort.
	"""

	tag: str
	mouse_line: str
	genotype: str
	subject_name: str
	sex: str
	date_of_birth: PastDate
	genetic_background: str
	treatment: str
	notes: str


class Cohort(BaseModel):
	"""EcoHab cohort of mice.

	Stores information about all animals in the cohort.
	"""

	n_mice: PositiveInt
	animals: list[Animal]

	@property
	def animal_names(self) -> list[str]:
		"""Contains animal names sorted alphanumerically."""
		return sorted(animal.subject_name for animal in self.animals)

	@property
	def animal_tags(self) -> list[str]:
		"""Contains animal RFID tags sorted alphanumerically."""
		return sorted(animal.tag for animal in self.animals)

	@property
	def animal_combinations(self) -> list[tuple[str, str]]:
		"""Unordered animal pairs (``a < b``), for symmetric measures.

		A meeting is one event whichever animal is named first, so ``pairwise_meetings``
		holds a single cell per pair.
		"""
		return list(combinations(self.animal_tags, 2))

	@property
	def animal_product(self) -> list[tuple[str, str]]:
		"""Ordered animal pairs (``a != b``, both directions), for directed measures.

		Chasings outcomes distinguish the two roles, so A-beats-B and
		B-beats-A are separate cells.
		"""
		return [(a, b) for a, b in product(self.animal_tags, self.animal_tags) if a != b]


class Timeline(BaseModel):
	"""Timeline of the experiment.

	Contains all information related to the start and end of the experiment, the
	timezone of the computer that recorded the data, the onset of each circadian
	phase, and the ranges of days and phases present in the recording.
	"""

	start_datetime: AwareDatetime
	end_datetime: AwareDatetime
	recording_timezone: ZoneInfo
	phases: dict[Literal["light_phase", "dark_phase"], dt.time]
	start_from: Literal["light_phase", "dark_phase"]

	@model_validator(mode="after")
	def _check_timeline(self) -> "Timeline":
		if self.end_datetime <= self.start_datetime:
			raise ValueError("end_datetime must be after start_datetime")

		if self.start_from not in self.phases:
			raise ValueError(
				f"start_from is {self.start_from!r} but phases only defines {sorted(self.phases)}."
			)

		if self.experiment_start >= self.end_datetime:
			raise ValueError(
				f"The recording ends before {self.start_from!r} first starts, at "
				f"{self.experiment_start}, so it holds no experiment to analyse."
			)
		return self

	@computed_field
	@property
	def experiment_start(self) -> dt.datetime:
		"""When the experiment proper begins: the ``start_from`` onset nearest acquisition.

		Days and hours are counted from here, so the same day and hour mark the same
		point of the experiment in every recording however acquisition happened to be
		timed. The nearest onset can fall a little before recording began, which leaves
		the first phase short rather than discarding a whole cycle of data.
		"""
		start = self.start_datetime.astimezone(self.recording_timezone)
		onset = self.phases[self.start_from]

		candidates = [
			dt.datetime.combine(
				start.date() + dt.timedelta(days=offset), onset, tzinfo=self.recording_timezone
			)
			for offset in (-1, 0, 1)
		]
		return min(candidates, key=lambda moment: abs(_elapsed(start, moment)))

	@property
	def discarded_lead(self) -> dt.timedelta:
		"""Data recorded before :attr:`experiment_start`, which the analysis leaves out."""
		return max(_elapsed(self.start_datetime, self.experiment_start), dt.timedelta(0))

	@property
	def unrecorded_lead(self) -> dt.timedelta:
		"""Time between :attr:`experiment_start` and the start of recording, never captured.

		The first phase is short by this much, and no data is dropped.
		"""
		return max(_elapsed(self.experiment_start, self.start_datetime), dt.timedelta(0))

	@computed_field
	@property
	def days_range(self) -> tuple[int, int]:
		"""Range of experiment days present in the recording."""
		start, end = self.local_span
		return (1, _elapsed(start, end) // dt.timedelta(days=1) + 1)

	@computed_field
	@property
	def phase_range(self) -> tuple[int, int]:
		"""Range of phases present in the recording."""
		return (1, len(self._boundaries()) + 1)

	@property
	def local_span(self) -> tuple[dt.datetime, dt.datetime]:
		"""The analysed window - experiment start to recording end - in the recording timezone.

		Everything downstream takes its bounds from here, so the lead-in before
		:attr:`experiment_start` is trimmed once, in one place.
		"""
		return self.experiment_start, self.end_datetime.astimezone(self.recording_timezone)

	def _boundaries(self) -> list[dt.datetime]:
		"""Phase switch instants strictly inside the recording, in order."""
		start, end = self.local_span
		candidates = (
			dt.datetime.combine(
				start.date() + dt.timedelta(days=n), hhmm, tzinfo=self.recording_timezone
			)
			for n in range((end.date() - start.date()).days + 1)
			for hhmm in set(self.phases.values())
		)
		return sorted(b for b in candidates if start < b < end and self._wall_clock_exists(b))

	@staticmethod
	def _wall_clock_exists(moment: dt.datetime) -> bool:
		"""False for wall-clock times skipped by a DST jump forward."""
		return moment.astimezone(dt.UTC).astimezone(moment.tzinfo) == moment


class Bout(BaseModel):
	"""One stretch of an event, from ``start`` up to but not including ``end``.

	``position`` names the cage or tunnel it was applied in; a bout without one applies
	to the whole habitat.
	"""

	model_config = ConfigDict(extra="forbid")

	start: AwareDatetime
	end: AwareDatetime
	position: str | None = None

	@model_validator(mode="after")
	def _check_bout(self) -> "Bout":
		if self.end <= self.start:
			raise ValueError(f"a bout must end after it starts, got {self.start} to {self.end}")
		return self


class Event(BaseModel):
	"""Something the experimenter did during the recording, and every bout of it.

	A stimulus presentation, an injection or a cage swap. Different events may overlap -
	two stimuli presented at once in different cages - but the bouts of one event may
	not, so an entry typed twice fails rather than counting double.
	"""

	model_config = ConfigDict(extra="forbid")

	name: str
	description: str
	bouts: list[Bout] = Field(min_length=1)

	@model_validator(mode="after")
	def _check_event(self) -> "Event":
		ordered = sorted(self.bouts, key=lambda bout: bout.start)
		for earlier, later in pairwise(ordered):
			if later.start < earlier.end:
				raise ValueError(
					f"bouts of {self.name!r} overlap: {earlier.start} to {earlier.end} "
					f"and {later.start} to {later.end}"
				)
		return self


class AnalysisParams(BaseModel):
	"""Tuning knobs for the analysis steps.

	Args:
		minimum_time: minimum continuous co-presence, in seconds, for a meeting to count.
		minimum_time_alone: minimum continuous solitary time, in seconds, for a span to
			count as time alone. Discards the brief gaps left by animals travelling as a
			group and arriving moments apart.
		chasing_time_window: min and max length, in seconds, of a chasing event.
		prev_ranking: starting ratings from an earlier recording of the same animals.
	"""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	minimum_time: float = 2
	minimum_time_alone: float = 10.0
	chasing_time_window: tuple[float, float] = (0.1, 1.2)
	prev_ranking: pl.DataFrame | pl.LazyFrame | None = None


class StepProgress(NamedTuple):
	"""One finished pipeline step within a recording."""

	step: str
	step_index: int
	step_total: int


class Progress(NamedTuple):
	"""One finished pipeline step, located in both the recording and step loops."""

	recording: str
	recording_index: int
	recording_total: int
	step: str
	step_index: int
	step_total: int


class DataFrameRegistry:
	"""The analysis pipeline: which tables exist, what each needs, and how to build them.

	Steps register at import time via :meth:`register`, so the graph belongs to the
	class; an instance is that graph bound to one recording. The registry works out
	the run order and builds each table, so every step is a plain
	``(recording, params) -> LazyFrame``.
	"""

	_builders: ClassVar[dict[str, Callable[["Recording", AnalysisParams], pl.LazyFrame]]] = {}
	_requires: ClassVar[dict[str, list[str]]] = {}

	def __init__(self, recording: "Recording") -> None:
		self._recording = recording

	@classmethod
	def register(cls, name: str, requires: Sequence[str] = ()) -> Callable:
		"""Register a pipeline step under ``name``.

		Args:
			name: output key, also the ``results/<name>.parquet`` filename.
			requires: data keys this step reads via ``Recording.load_results``; each
				is an edge in the graph :meth:`step_order` sorts.

		Returns:
			The function unchanged, so it stays directly callable.
		"""

		def wrapper(func: Callable) -> Callable:
			cls._builders[name] = func
			cls._requires[name] = list(requires)
			return func

		return wrapper

	@classmethod
	def list_available(cls) -> list[str]:
		"""Every registered data key."""
		return list(cls._builders)

	@classmethod
	def step_order(cls, targets: list[str] | None = None) -> list[str]:
		"""Sort the steps so each one runs after the steps it requires.

		Args:
			targets: run only these steps and their transitive dependencies;
				``None`` covers every registered step.

		Returns:
			Step names in a valid execution order, deterministic between runs.

		Raises:
			KeyError: a target, or a declared requirement, is not registered.
			ValueError: the requirements form a cycle.
		"""
		unknown = {req for reqs in cls._requires.values() for req in reqs} - set(cls._builders)
		if unknown:
			raise KeyError(
				f"Steps declare requirements that no step produces: {sorted(unknown)}. "
				"The module defining them may not have been imported."
			)

		deps: dict[str, set[str]] = {name: set(reqs) for name, reqs in cls._requires.items()}

		if targets is not None:
			if missing := set(targets) - set(deps):
				raise KeyError(f"Unknown analysis step(s): {sorted(missing)}")
			wanted: set[str] = set()
			stack = list(targets)
			while stack:
				step = stack.pop()
				if step in wanted:
					continue
				wanted.add(step)
				stack.extend(deps[step])
			deps = {name: (d & wanted) for name, d in deps.items() if name in wanted}

		# Fed in sorted, so the order is the same between runs.
		sorter = graphlib.TopologicalSorter({name: deps[name] for name in sorted(deps)})
		try:
			return list(sorter.static_order())
		except graphlib.CycleError as cycle:
			raise ValueError(
				f"Cycle detected among analysis steps: {sorted(set(cycle.args[1]))}"
			) from None

	def run(
		self,
		params: AnalysisParams | None = None,
		targets: list[str] | None = None,
		*,
		overwrite: bool = False,
	) -> Iterator[StepProgress]:
		"""Build every step in dependency order, yielding progress as each one lands.

		Args:
			params: tuning knobs; defaults are used when omitted.
			targets: run only these steps and their dependencies.
			overwrite: rebuild steps whose parquet already exists.

		Yields:
			One :class:`StepProgress` per finished step.
		"""
		order = self.step_order(targets)
		params = params or AnalysisParams()

		for index, name in enumerate(order, start=1):
			self._build(name, params, overwrite=overwrite)
			yield StepProgress(name, index, len(order))

	def _build(self, name: str, params: AnalysisParams, *, overwrite: bool) -> None:
		"""Compute one step and sink it, unless its parquet is already there."""
		path = self._recording.results_path / f"{name}.parquet"

		if path.is_file() and not overwrite:
			return

		path.parent.mkdir(parents=True, exist_ok=True)
		self._builders[name](self._recording, params).sink_parquet(
			path, compression="lz4", engine="streaming"
		)


def recording_status(root: Path) -> dict[str, bool]:
	"""Which pipeline steps a recording has already computed, read straight off disk.

	Reads ``results/`` directly rather than going through a ``Recording``, so a
	project whose ``config.json`` fails validation can still report status for that
	recording from the manifest and results folder alone.

	Args:
		root: the recording's own directory, e.g. ``<project_location>/<name>``.

	Returns:
		Every registered step name mapped to whether its parquet exists.
	"""
	results = root / "results"
	return {
		step: (results / f"{step}.parquet").is_file() for step in DataFrameRegistry.step_order()
	}


class Recording(BaseModel):
	"""Recording class."""

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	name: str
	project_name: str
	recording_location: str
	timeline: Timeline
	cohort: Cohort
	layout: Layout
	events: list[Event] = Field(default_factory=list)
	notes: str
	data: pl.LazyFrame = Field(exclude=True, repr=False)

	_root: Path | None = PrivateAttr(default=None)
	_registry: DataFrameRegistry | None = PrivateAttr(default=None)

	@property
	def data_schema(self) -> pl.Schema:
		"""Expected input data schema."""
		return pl.Schema(
			{
				"datetime": pl.Datetime("us", time_zone=self.timeline.recording_timezone.key),
				"antenna": pl.Int8,
				"time_under": pl.Duration("us"),
				"animal_id": pl.Enum(self.cohort.animal_tags),
			}
		)

	@property
	def root(self) -> Path:
		"""This recording's directory inside its project.

		Raises:
			ValueError: the recording is not attached to a project, so it has nowhere
				to read or write results.
		"""
		if self._root is None:
			raise ValueError(
				f"Recording {self.name!r} is not attached to a project and so has no "
				"directory. Add it with Project.add_recording(), or open the project "
				"with Project.load()."
			)
		return self._root

	@property
	def results_path(self) -> Path:
		"""Where this recording's analysis tables are written."""
		return self.root / "results"

	@property
	def registry(self) -> DataFrameRegistry:
		"""The analysis DAG, bound to this recording."""
		if self._registry is None:
			self._registry = DataFrameRegistry(self)
		return self._registry

	@overload
	def load_results(self, key: str, *, eager: Literal[False] = False) -> pl.LazyFrame: ...
	@overload
	def load_results(self, key: str, *, eager: Literal[True]) -> pl.DataFrame: ...
	def load_results(self, key: str, *, eager: bool = False) -> pl.LazyFrame | pl.DataFrame:
		"""Load an analysis table this recording has already produced.

		Args:
			key: registered data key, e.g. ``"main_df"``, or the name of any other table
				written into ``results/`` - an auxiliary analysis sunk there by hand.
			eager: collect the table instead of scanning it lazily.

		Raises:
			KeyError: nothing produces ``key`` - no registered step, no parquet on disk.
			FileNotFoundError: a registered step produces it but has not run yet.

		Returns:
			The table, lazy by default.
		"""
		path = self.results_path / f"{key}.parquet"

		if not path.is_file():
			available_dfs = DataFrameRegistry.list_available()
			if key not in available_dfs:
				raise KeyError(f"{key!r} is not a registered data key. Available: {available_dfs}")
			raise FileNotFoundError(
				f"{key!r} has not been computed for recording {self.name!r}. "
				"Run Project.run_analysis() first."
			)

		return pl.read_parquet(path) if eager else pl.scan_parquet(path)

	def _analyze_recording(
		self,
		params: AnalysisParams | None = None,
		targets: list[str] | None = None,
		*,
		overwrite: bool = False,
	) -> Iterator[StepProgress]:
		"""Run this recording's pipeline, yielding progress as each step lands."""
		yield from self.registry.run(params, targets, overwrite=overwrite)

	def to_config(self) -> dict[str, Any]:
		"""JSON-ready snapshot of the metadata; the frame itself is not included."""
		return self.model_dump(mode="json")

	def update_notes(self, notes: str) -> None:
		"""Set this recording's notes and persist them to its config.json.

		Raises:
			ValueError: the recording is not attached to a project (see `root`).
		"""
		self.notes = notes
		(self.root / "config.json").write_text(
			json.dumps(self.to_config(), indent=2), encoding="utf-8"
		)

	@classmethod
	def from_config(cls, config: dict[str, Any], data_path: Path) -> "Recording":
		"""Rebuild a recording from to_config() output, reattaching its parquet."""
		return cls.model_validate(config, context={"data_path": data_path})

	@model_validator(mode="before")
	@classmethod
	def _scan_frame(cls, values: Any, info: ValidationInfo) -> Any:
		ctx = info.context or {}
		if isinstance(values, dict) and "data" not in values and "data_path" in ctx:
			values = {**values, "data": pl.scan_parquet(ctx["data_path"])}
		return values

	@model_validator(mode="after")
	def _check_schema(self, info: ValidationInfo) -> "Recording":
		path = (info.context or {}).get("data_path", "<data>")
		found = self.data.collect_schema()
		expected = self.data_schema

		if found != expected:
			raise ValueError(
				f"{path}: schema mismatch\n  expected: {expected}\n  found:    {found}"
			)
		return self

	@model_validator(mode="after")
	def _check_events(self) -> "Recording":
		names = [event.name for event in self.events]
		if duplicates := sorted({name for name in names if names.count(name) > 1}):
			raise ValueError(f"event names must be unique, got duplicates of {duplicates}")

		start, end = self.timeline.local_span
		positions = self.layout.cage_names + self.layout.tunnel_names

		for event in self.events:
			for bout in event.bouts:
				if bout.start < start or bout.end > end:
					raise ValueError(
						f"a bout of {event.name!r}, {bout.start} to {bout.end}, falls outside the "
						f"analysed window {start} to {end}"
					)
				if bout.position is not None and bout.position not in positions:
					raise ValueError(
						f"a bout of {event.name!r} is in {bout.position!r}, which the layout does "
						f"not have; its positions are {positions}"
					)
		return self


class FailedRecording(NamedTuple):
	"""A recording that could not be added, with the exception that stopped it."""

	metadata_path: Path
	data_path: Path
	error: Exception


class AddReport(NamedTuple):
	"""Outcome of a batch add: names that went in, sources that didn't."""

	added: list[str]
	failed: list[FailedRecording]


class Project(BaseModel):
	"""Project class.

	Contains all recordings related to a specific project and info about the:
	project name, experimenter, list of recordings and their location in the catalog.

	The project is persisted as <project_location>/project.json, which maps each
	recording name to its config.json relative to the manifest. Each recording
	owns <project_location>/<recording_name>/, holding config.json, raw/ and
	results/. Data is reattached from raw/data.parquet on load.
	"""

	MANIFEST: ClassVar[str] = "project.json"
	CONFIG: ClassVar[str] = "config.json"
	LOGFILE: ClassVar[str] = "project.log"
	PROJECT_TABLE: ClassVar[str] = "project_table.parquet"

	project_name: str
	experimenter: str
	project_location: Path = Field(exclude=True)
	created_at: dt.datetime
	description: str = ""
	data_catalog: dict[str, Recording] = Field(default_factory=dict)

	_logger: logging.Logger | None = PrivateAttr(default=None)

	@field_serializer("data_catalog")
	def _catalog_as_pointers(self, catalog: dict[str, Recording]) -> dict[str, str]:
		"""The manifest records where each config.json is, not what's in it."""
		return {name: f"{name}/{self.CONFIG}" for name in catalog}

	@classmethod
	def create(
		cls,
		project_name: str,
		experimenter: str,
		location: Path,
		description: str = "",
	) -> "Project":
		"""Creates the project at specified location and writes its manifest."""
		location = Path(location).expanduser().resolve()
		location.mkdir(parents=True, exist_ok=True)
		if (location / cls.MANIFEST).exists():
			raise FileExistsError(
				f"A project already exists at {location}; use Project.load() to open it."
			)

		project = cls(
			project_name=project_name,
			experimenter=experimenter,
			project_location=location,
			created_at=dt.datetime.now(dt.UTC),
			description=description,
		)
		project._log.info("created project %r by %s", project_name, experimenter)
		project._save()
		return project

	@classmethod
	def load(cls, location: Path) -> "Project":
		"""Reopen a project written by _save(), following the manifest's pointers."""
		location = Path(location).expanduser().resolve()
		raw = json.loads((location / cls.MANIFEST).read_text(encoding="utf-8"))

		raw["data_catalog"] = {
			name: cls._read_config(location / rel)
			for name, rel in raw.get("data_catalog", {}).items()
		}

		project = cls.model_validate({**raw, "project_location": location})
		project._log.info("opened project (%d recordings)", len(project.data_catalog))
		return project

	def close(self) -> None:
		"""Release the log file handle."""
		if self._logger is not None:
			for handler in list(self._logger.handlers):
				self._logger.removeHandler(handler)
				handler.close()
			self._logger = None

	def __enter__(self) -> "Project":
		return self

	def __exit__(self, *exc_info: object) -> None:
		self.close()

	def __getitem__(self, name: str) -> Recording:
		try:
			return self.data_catalog[name]
		except KeyError:
			raise KeyError(
				f"No recording named {name!r} in project {self.project_name!r}. "
				f"Available: {sorted(self.data_catalog)}"
			) from None

	def __len__(self) -> int:
		return len(self.data_catalog)

	@property
	def recordings(self) -> list[Recording]:
		"""Every recording in the project, in the order they were added."""
		return list(self.data_catalog.values())

	def add_recording(self, metadata_path: Path, data_path: Path) -> Recording:
		"""Adds a recording to the project and updates the manifest."""
		recording = self._add_one(Path(metadata_path), Path(data_path))
		self._save()
		return recording

	def add_recordings(self, sources: Iterable[tuple[Path, Path]]) -> AddReport:
		"""Adds several recordings, matched pairwise as (metadata_path, data_path).

		Recordings are added independently: a failure on one is logged and
		warned about, and the rest still go in. The manifest is written once,
		after the batch.

		Returns:
			AddReport with the names added and the sources that failed.
		"""
		added: list[str] = []
		failed: list[FailedRecording] = []

		for metadata_path, data_path in sources:
			metadata_path, data_path = Path(metadata_path), Path(data_path)
			try:
				added.append(self._add_one(metadata_path, data_path).name)
			except Exception as exc:
				failed.append(FailedRecording(metadata_path, data_path, exc))
				self._log.exception("failed to add recording from %s", metadata_path)

		if added:
			self._save()
		self._log.info("batch add: %d added, %d failed", len(added), len(failed))

		if failed:
			details = "\n".join(
				f"  {f.metadata_path}: {type(f.error).__name__}: {f.error}" for f in failed
			)
			warnings.warn(
				f"{len(failed)} of {len(failed) + len(added)} recordings could not be "
				f"added:\n{details}",
				stacklevel=2,
			)

		return AddReport(added, failed)

	def remove_recording(self, name: str, *, delete_files: bool = False) -> None:
		"""Removes recording from project.

		By default a soft delete - delists from the catalog, leaving config.json
		and the data on disk.

		Args:
			name: name of the recording to be deleted
			delete_files: whether to delete the files related to recording as well.
				Defaults to False.
		"""
		if name not in self.data_catalog:
			raise KeyError(f"No recording named {name!r} in project {self.project_name!r}.")

		del self.data_catalog[name]
		if delete_files:
			shutil.rmtree(self.project_location / name, ignore_errors=True)

		self._log.warning(
			"removed recording %r (files %s)",
			name,
			"deleted" if delete_files else "kept",
		)
		self._save()

	def run_analysis(
		self,
		params: AnalysisParams | None = None,
		names: Iterable[str] | None = None,
		targets: list[str] | None = None,
		*,
		overwrite: bool = False,
		workers: int | None = None,
	) -> None:
		"""Run the analysis pipeline for every recording, showing one progress bar.

		Recordings are analysed concurrently, so the bar counts every step of every
		recording and names the one that landed most recently; with several recordings
		in flight at once there is no single inner loop left to nest a second bar on.
		Steps whose parquet already exists are skipped, so re-running is cheap and
		resumes where an interrupted run left off.

		A recording that fails does not stop the others - the error is raised once the
		rest have finished.

		Args:
			params: tuning knobs for the steps; defaults are used when omitted.
			names: run only these recordings; ``None`` runs all of them.
			targets: run only these steps and their dependencies.
			overwrite: rebuild tables that already exist on disk.
			workers: how many recordings to analyse at once; ``None`` takes a quarter
				of polars' thread pool, capped at the number of recordings.
		"""
		# Exact, not an estimate: a step that is skipped still reports itself.
		total = len(self._select(names)) * len(DataFrameRegistry.step_order(targets))
		events = self._analyze_project(params, names, targets, overwrite=overwrite, workers=workers)

		# Logging stays on this side: the workers only emit events, so the lazily attached
		# file handler is never raced for.
		bar = tqdm(events, total=total, desc="analysis", unit="step")
		for progress in bar:
			bar.set_postfix_str(f"{progress.recording}: {progress.step}")
			self._log.info("%s: built %s", progress.recording, progress.step)

	def generate_project_table(self, names: Iterable[str] | None = None) -> pl.LazyFrame:
		"""Combine every recording's features into one table on a shared timeline.

		Each recording's features are joined to its cohort metadata and tagged with the
		recording they came from, so results can be grouped by genotype, sex, treatment
		or any other recorded attribute across the whole project. Days and hours already
		count from each recording's own experiment start, so the same day and hour mark
		the same point of the experiment in every row.

		Recordings of different lengths contribute the days they have; nothing is padded
		or truncated to match.

		The table also gains one column per event name declared anywhere in the
		project, plus ``"Any event"``: "During" / "Same hours, other days" / "Other
		hours" for a recording that declares that event, null for one that does not.
		See :func:`recording_pipeline.event_status`.

		Args:
			names: aggregate only these recordings; ``None`` covers the whole project.

		Raises:
			ValueError: the project has no recordings to aggregate.
			FileNotFoundError: a recording has not been analysed yet.

		Returns:
			The table, which is also written to ``project_table.parquet``.
		"""
		# Deferred: recording_pipeline imports grids, which imports this module.
		from deepecohab.core.recording_pipeline import event_status

		recordings = self._select(names)
		if not recordings:
			raise ValueError(f"Project {self.project_name!r} has no recordings to aggregate.")

		all_events = sorted({event.name for recording in recordings for event in recording.events})
		event_columns = [*all_events, "Any event"] if all_events else []

		frames = []
		for recording in recordings:
			frame = recording.load_results("feature_df").join(
				recording.load_results("animals"), on="animal_id", how="left"
			)

			if event_columns:
				frame = frame.join(
					event_status(recording, event_columns), on=["day", "hour"], how="left"
				)

			frames.append(
				frame.with_columns(
					pl.lit(recording.name).alias("recording"),
					pl.lit(recording.cohort.n_mice).cast(pl.UInt16).alias("n_mice"),
					# Both enums are built per recording, so a cohort or a light cycle that
					# differs gives them different categories; strings concatenate cleanly.
					pl.col("animal_id").cast(pl.String),
					pl.col("phase").cast(pl.String),
				).select("recording", "n_mice", pl.exclude("recording", "n_mice"))
			)

		path = self.project_location / self.PROJECT_TABLE
		pl.concat(frames, how="vertical").sink_parquet(path, compression="lz4", engine="streaming")
		self._log.info("wrote project table from %d recordings", len(frames))
		return pl.scan_parquet(path)

	@overload
	def load_project_table(self, *, eager: Literal[False] = False) -> pl.LazyFrame: ...
	@overload
	def load_project_table(self, *, eager: Literal[True]) -> pl.DataFrame: ...
	def load_project_table(self, *, eager: bool = False) -> pl.LazyFrame | pl.DataFrame:
		"""Load the table written by :meth:`generate_project_table`.

		Args:
			eager: collect the table instead of scanning it lazily.

		Raises:
			FileNotFoundError: the table has not been generated yet.

		Returns:
			The table, lazy by default.
		"""
		path = self.project_location / self.PROJECT_TABLE
		if not path.is_file():
			raise FileNotFoundError(
				f"Project {self.project_name!r} has no project table yet. "
				"Run Project.generate_project_table() first."
			)

		return pl.read_parquet(path) if eager else pl.scan_parquet(path)

	def _analyze_project(
		self,
		params: AnalysisParams | None = None,
		names: Iterable[str] | None = None,
		targets: list[str] | None = None,
		*,
		overwrite: bool = False,
		workers: int | None = None,
		cancel: threading.Event | None = None,
	) -> Iterator[Progress]:
		"""Run the pipeline across recordings as one flat event stream.

		Recordings are analysed side by side, sharing nothing but the read-only step graph,
		so events arrive interleaved, each tagged with the recording it came from. One
		recording's own steps stay in dependency order.

		A recording that raises does not stop the others; the error surfaces here once the
		rest have finished, as it does in :meth:`add_recordings`.

		Internal: :meth:`run_analysis` is the public entry point.

		Args:
			workers: how many recordings to analyse at once; ``None`` takes a quarter
				of polars' thread pool, capped at the number of recordings.
			cancel: once set, every recording stops before its next step, so the steps in
				flight still land and recordings not yet started never begin.
		"""
		recordings = self._select(names)
		if not recordings:
			return

		workers = workers or min(len(recordings), max(1, pl.thread_pool_size() // 4))
		cancel = cancel or threading.Event()

		# An executor reports whole recordings, so workers hand back steps as they land.
		events: queue.Queue[Progress | None] = queue.Queue()

		def analyse(index: int, recording: Recording) -> None:
			# Lazy: each next() builds one step, so the check runs before every build.
			steps = recording._analyze_recording(params, targets, overwrite=overwrite)
			try:
				while not cancel.is_set() and (step := next(steps, None)) is not None:
					events.put(Progress(recording.name, index, len(recordings), *step))
			finally:
				events.put(None)  # this recording is done, however it ended

		# Abandoning the generator without setting cancel blocks until every recording
		# finishes.
		with ThreadPoolExecutor(workers) as pool:
			futures = [
				pool.submit(analyse, index, recording)
				for index, recording in enumerate(recordings, start=1)
			]
			pending = len(futures)

			while pending:
				if (event := events.get()) is None:
					pending -= 1
				else:
					yield event

			for future in futures:
				future.result()  # a worker that raised does so here

	def _select(self, names: Iterable[str] | None) -> list[Recording]:
		"""The recordings a run covers; the one place that decides which of them run."""
		return [self[name] for name in names] if names is not None else self.recordings

	def _add_one(self, metadata_path: Path, data_path: Path) -> Recording:
		"""Validate, write, and catalog one recording. Raises on any failure."""
		metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
		recording = Recording.from_config(metadata["recording"], data_path)
		root = self.project_location / recording.name

		if recording.name in self.data_catalog or root.exists():
			self._log.error("rejected duplicate recording %r", recording.name)
			raise FileExistsError(
				f"Recording {recording.name!r} is already in project {self.project_name!r}."
			)

		target = root / "raw" / "data.parquet"
		try:
			target.parent.mkdir(parents=True)
			(root / "results").mkdir(parents=True)
			recording.data.sink_parquet(target)
			recording.data = pl.scan_parquet(target)  # our copy, not the caller's
			(root / self.CONFIG).write_text(
				json.dumps(recording.to_config(), indent=2), encoding="utf-8"
			)
		except Exception:
			shutil.rmtree(root, ignore_errors=True)  # only ours; root didn't exist above
			raise

		recording._root = root
		self.data_catalog[recording.name] = recording
		self._log.info(
			"added recording %r from %s (%d animals)",
			recording.name,
			metadata_path,
			recording.cohort.n_mice,
		)

		line = recording.timeline
		if discarded := line.discarded_lead:
			lead = discarded
			offset = f"{discarded} of data recorded before it is left out of the analysis"
		elif unrecorded := line.unrecorded_lead:
			lead = unrecorded
			offset = (
				f"recording started {unrecorded} into it, so that first phase is short by "
				"as much and no data is dropped"
			)
		else:
			lead, offset = dt.timedelta(0), ""

		if offset:
			note = (
				f"the experiment starts at {line.experiment_start}, the nearest "
				f"{line.start_from} onset; {offset}"
			)
			self._log.warning("%r: %s", recording.name, note)
			if lead > LEAD_WARNING_THRESHOLD:
				warnings.warn(f"Recording {recording.name!r}: {note}.", stacklevel=2)

		return recording

	@classmethod
	def _read_config(cls, config_path: Path) -> Recording:
		"""Load one recording from its config.json, reattaching the sibling parquet."""
		if not config_path.is_file():
			raise FileNotFoundError(f"{config_path} is listed in the manifest but is missing.")

		recording = Recording.from_config(
			json.loads(config_path.read_text(encoding="utf-8")),
			config_path.parent / "raw" / "data.parquet",
		)
		recording._root = config_path.parent
		return recording

	def _save(self) -> Path:
		"""Write the pointer manifest to <project_location>/project.json."""
		path = self.project_location / self.MANIFEST
		tmp = path.with_suffix(".json.tmp")
		tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
		tmp.replace(path)
		self._log.info("saved manifest (%d recordings)", len(self.data_catalog))
		return path

	@property
	def _log(self) -> logging.Logger:
		"""Logger writing to <project_location>/project.log."""
		if self._logger is None:
			path = self.project_location / self.LOGFILE
			logger = logging.getLogger(f"deepecohab.project.{path}")  # unique per project
			if not logger.handlers:
				logger.setLevel(logging.INFO)
				handler = logging.FileHandler(path, encoding="utf-8")
				handler.setFormatter(
					logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
				)
				logger.addHandler(handler)
			self._logger = logger
		return self._logger
