"""Server-side work for the app: cached projects, their table summaries and the analysis job.

Caches are keyed by path and file mtimes, never by user, so an entry retires itself when its
files change and nothing per-user outlives a request.
"""

import hashlib
import json
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import diskcache
import polars as pl
from dash import no_update

from deepecohab import AnalysisParams, Project, Recording, recording_status
from deepecohab.app.builder import catalog as builder_catalog
from deepecohab.app.components import notify
from deepecohab.core.data_model import DataFrameRegistry
from deepecohab.plotting import PlotContext
from deepecohab.plotting.export import ensure_chrome_available

BUILDER_PRESETS_FILE = "builder_presets.json"

CACHE_DIR = Path.home() / ".deepecohab" / "app-cache"


def project_id(location: str) -> str:
	"""A short, stable id for a project folder, so URLs never carry its path."""
	return hashlib.blake2b(location.encode(), digest_size=6).hexdigest()


def resolve_project(paths: list[str] | None, pid: str) -> str | None:
	"""The remembered project folder whose id is ``pid``, or None if it is not among ``paths``."""
	return next((path for path in paths or [] if project_id(path) == pid), None)


def remember_project(location: str) -> str:
	"""This project's id, and cache the id -> path mapping for the download routes.

	The browser's project list lives in local storage, which a plain Flask route
	cannot read, so every time a project is summarised for the Projects table this
	registers it; a download link's route then looks the path back up by id.
	"""
	pid = project_id(location)
	with diskcache.Cache(CACHE_DIR) as cache:
		cache.set(f"path:{pid}", location)
	return pid


def resolve_project_path(pid: str) -> str | None:
	"""The project folder last registered under ``pid`` by :func:`remember_project`."""
	with diskcache.Cache(CACHE_DIR) as cache:
		return cache.get(f"path:{pid}")


@lru_cache(maxsize=1)
def kaleido_ok() -> bool:
	"""Whether kaleido has a Chrome to render exports through, checked once per process."""
	return ensure_chrome_available()


def csv_ready(frame: pl.DataFrame) -> pl.DataFrame:
	"""``frame`` with every Duration column in seconds and every Enum/Categorical as a string.

	CSV has neither type, so a plain ``write_csv`` would otherwise dump raw microsecond
	integers for a duration and silently drop a category's declared order.
	"""
	exprs = []
	for name, dtype in frame.schema.items():
		if isinstance(dtype, pl.Duration):
			exprs.append((pl.col(name).dt.total_microseconds() / 1_000_000).alias(name))
		elif isinstance(dtype, (pl.Enum, pl.Categorical)):
			exprs.append(pl.col(name).cast(pl.String))
		else:
			exprs.append(pl.col(name))
	return frame.select(exprs)


def load_project(location: str) -> Project:
	"""The project at ``location``, loaded again only once its manifest or a config changes.

	Raises:
		Whatever ``Project.load`` raises for the folder.
	"""
	root = Path(location)
	configs = sorted(root.glob(f"*/{Project.CONFIG}"))
	stamp = tuple(path.stat().st_mtime_ns for path in [root / Project.MANIFEST, *configs])
	return _load_project(location, stamp)


@lru_cache(maxsize=16)
def _load_project(location: str, _stamp: tuple[int, ...]) -> Project:
	return Project.load(Path(location))


def project_summary(location: str) -> dict:
	"""Everything the Projects table shows for one folder.

	A project that ``Project.load`` rejects still lists its recordings, from ``project.json``
	and each recording's results folder, next to the error that stopped it.

	Args:
		location: the project folder, as remembered in the browser.

	Returns:
		The manifest fields, ``error`` (None when the project loads), ``table_rows`` (None
		until the project table is generated) and one dict per recording. A recording's
		window, cohort and events are there only when the project loads.
	"""
	root = Path(location)
	steps = len(DataFrameRegistry.step_order())
	table = root / Project.PROJECT_TABLE
	summary = {
		"location": location,
		"id": remember_project(location),
		"table_rows": (
			pl.scan_parquet(table).select(pl.len()).collect().item() if table.is_file() else None
		),
	}

	try:
		project = load_project(location)
	except Exception as exc:  # any unreadable folder still gets its row, with the reason
		try:
			manifest = json.loads((root / Project.MANIFEST).read_text(encoding="utf-8"))
		except (OSError, ValueError):
			manifest = {}
		return {
			**summary,
			"name": manifest.get("project_name", root.name),
			"experimenter": manifest.get("experimenter", ""),
			"description": manifest.get("description", ""),
			"error": f"{type(exc).__name__}: {exc}",
			"recordings": [
				{"name": name, "done": sum(recording_status(root / name).values()), "total": steps}
				for name in manifest.get("data_catalog", {})
			],
		}

	return {
		**summary,
		"name": project.project_name,
		"experimenter": project.experimenter,
		"description": project.description,
		"error": None,
		"recordings": [_recording_summary(recording, steps) for recording in project.recordings],
	}


def _recording_summary(recording: Recording, steps: int) -> dict:
	timeline = recording.timeline
	zone = timeline.recording_timezone
	start = timeline.start_datetime.astimezone(zone)
	end = timeline.end_datetime.astimezone(zone)
	animals = recording.cohort.animals
	return {
		"name": recording.name,
		"done": sum(recording_status(recording.root).values()),
		"total": steps,
		"window": f"{start.day} {start:%b} → {end.day} {end:%b %Y}",
		"timezone": str(zone),
		"days": timeline.days_range[1] - timeline.days_range[0] + 1,
		"phases": timeline.phase_range[1] - timeline.phase_range[0] + 1,
		"n_mice": recording.cohort.n_mice,
		"traits": [
			value
			for field in ("mouse_line", "genotype", "sex")
			for value in dict.fromkeys(getattr(animal, field) for animal in animals)
		],
		"events": len(recording.events),
	}


def plot_context(location: str, name: str) -> PlotContext:
	"""The plot context for one recording, rebuilt only once its results change.

	Args:
		location: the project folder.
		name: the recording's name.
	"""
	recording = load_project(location)[name]
	results = recording.results_path
	stamp = (
		tuple(sorted((path.name, path.stat().st_mtime_ns) for path in results.glob("*.parquet")))
		if results.is_dir()
		else ()
	)
	return _plot_context(location, name, stamp)


@lru_cache(maxsize=8)
def _plot_context(location: str, name: str, _stamp: tuple[tuple[str, int], ...]) -> PlotContext:
	return PlotContext.from_recording(load_project(location)[name])


def recording_summary(location: str, name: str) -> dict:
	"""Everything the recording dashboard header and control bar show.

	Args:
		location: the project folder.
		name: the recording's name.
	"""
	recording = load_project(location)[name]
	timeline = recording.timeline
	zone = timeline.recording_timezone
	context = plot_context(location, name)

	return {
		"name": recording.name,
		"project": recording.project_name,
		"timezone": str(zone),
		"start": timeline.start_datetime.astimezone(zone).isoformat(),
		"end": timeline.end_datetime.astimezone(zone).isoformat(),
		"days": timeline.days_range[1] - timeline.days_range[0] + 1,
		"phases": timeline.phase_range[1] - timeline.phase_range[0] + 1,
		"start_from": timeline.start_from,
		"onsets": {phase: onset.isoformat("minutes") for phase, onset in timeline.phases.items()},
		"n_mice": recording.cohort.n_mice,
		"cages": len(recording.layout.cages),
		"tunnels": len(recording.layout.tunnels),
		"events": [event.name for event in recording.events],
		"notes": recording.notes,
		"quality": quality_summary(context) if "recording_quality" in context else None,
	}


def update_notes(location: str, name: str, notes: str) -> None:
	"""Persist new notes for one recording; the next `load_project` picks them up from disk."""
	load_project(location)[name].update_notes(notes)


def quality_summary(context: PlotContext) -> dict:
	"""Pooled detection-quality stats for the header and the quality tab's tiles."""
	frame = context.table("recording_quality").with_columns(pl.col("animal_id").cast(pl.String))
	rate = 100 * pl.col("missed") / (pl.col("missed") + pl.col("detected"))

	overall = frame.select(pl.col("missed").sum(), pl.col("detected").sum()).row(0, named=True)
	by_antenna = (
		frame.group_by("antenna")
		.agg(pl.col("missed").sum(), pl.col("detected").sum())
		.with_columns(rate.alias("miss_rate"))
		.sort("miss_rate", descending=True)
	)
	by_animal = (
		frame.group_by("animal_id")
		.agg(pl.col("missed").sum(), pl.col("detected").sum())
		.with_columns(rate.alias("miss_rate"))
		.sort("miss_rate", descending=True)
	)
	worst_antenna = by_antenna.row(0, named=True)
	worst_animal = by_animal.row(0, named=True)
	missed, detected = overall["missed"], overall["detected"]

	return {
		"miss": 100 * missed / (missed + detected) if missed + detected else 0.0,
		"detected": detected,
		"missed": missed,
		"worst_antenna": {"antenna": worst_antenna["antenna"], "miss": worst_antenna["miss_rate"]},
		"worst_animal": {"animal_id": worst_animal["animal_id"], "miss": worst_animal["miss_rate"]},
		"clean_cells": frame.filter(pl.col("missed") == 0).height,
		"cells": frame.height,
		"antennas": by_antenna.height,
	}


def event_names(project: Project) -> list[str]:
	"""Every event name the project declares anywhere, plus "Any event"."""
	names = sorted({event.name for recording in project.recordings for event in recording.events})
	return [*names, "Any event"] if names else []


def event_recording_counts(project: Project) -> dict[str, int]:
	"""How many recordings declare each event, "Any event" counting recordings with any."""
	counts = dict.fromkeys(event_names(project), 0)
	for recording in project.recordings:
		declared = {event.name for event in recording.events}
		for name in declared:
			counts[name] += 1
		if declared:
			counts["Any event"] += 1
	return counts


def builder_frame(location: str) -> tuple[pl.LazyFrame, list[builder_catalog.Field]]:
	"""The prepared project table and its field catalog for the plot builder.

	Raises:
		FileNotFoundError: the project table has not been generated yet.
	"""
	project = load_project(location)
	frame = builder_catalog.project_frame(project)
	return builder_catalog.prepare(frame, event_names(project))


def load_saved_presets(location: str) -> list[dict]:
	"""Builder presets saved to ``<project>/builder_presets.json``, empty if there are none."""
	path = Path(location) / BUILDER_PRESETS_FILE
	if not path.is_file():
		return []
	return json.loads(path.read_text(encoding="utf-8"))


def save_preset(location: str, preset: dict) -> None:
	"""Add or replace one preset in ``<project>/builder_presets.json``."""
	path = Path(location) / BUILDER_PRESETS_FILE
	presets = [p for p in load_saved_presets(location) if p["id"] != preset["id"]]
	presets.append(preset)
	path.write_text(json.dumps(presets, indent=2), encoding="utf-8")


def delete_saved_preset(location: str, preset_id: str) -> None:
	"""Remove one preset from ``<project>/builder_presets.json``."""
	path = Path(location) / BUILDER_PRESETS_FILE
	presets = [p for p in load_saved_presets(location) if p["id"] != preset_id]
	path.write_text(json.dumps(presets, indent=2), encoding="utf-8")


def request_cancel(location: str) -> None:
	"""Ask a running analysis of ``location`` to stop once its steps in flight land."""
	with diskcache.Cache(CACHE_DIR) as flags:
		flags.set(f"cancel:{location}", True, expire=3600)


def run_analysis(
	set_progress: Callable[[dict], None],
	_clicks: int,
	selection: list[list[str]],
	params: dict | None,
	overwrite: bool,
	failed: dict[str, dict[str, str]],
) -> tuple:
	"""The Run analysis background callback: the selected recordings, project by project.

	Progress goes out as ``{location: {recording: [steps done, steps, step building]}}``.
	A watcher thread turns :func:`request_cancel` into the pipeline's cancel event, so the
	steps in flight still land. Recordings left incomplete by a project that raised are
	marked failed.

	Returns:
		The failed-recordings store and the selection, cleared after a clean run. The outcome
		goes out as a notification.
	"""
	order = DataFrameRegistry.step_order()
	todo: dict[str, list[str]] = {}
	for location, name in selection:
		if overwrite or not _analysed(location, name):
			todo.setdefault(location, []).append(name)

	if not todo:
		message = (
			f"Nothing to build: the selected recordings already have all {len(order)} tables. "
			"Turn on Overwrite to rebuild them."
		)
		notify("warn", message)
		return no_update, no_update

	progress = {
		location: {name: [0, len(order), order[0]] for name in names}
		for location, names in todo.items()
	}
	started = time.perf_counter()
	cancel, finished = threading.Event(), threading.Event()
	errors: dict[str, Exception] = {}

	with diskcache.Cache(CACHE_DIR) as flags:
		keys = [f"cancel:{location}" for location in todo]
		for key in keys:
			flags.delete(key)
		# Cancel shows once progress does, so a click can no longer land before this reset.
		set_progress(progress)

		def watch() -> None:
			while not finished.wait(0.5):
				if any(flags.get(key) for key in keys):
					cancel.set()

		threading.Thread(target=watch, daemon=True).start()
		try:
			for location, names in todo.items():
				if cancel.is_set():
					break
				try:
					with Project.load(Path(location)) as project:
						events = project._analyze_project(
							AnalysisParams(**(params or {})),
							names,
							overwrite=overwrite,
							cancel=cancel,
						)
						for event in events:
							project._log.info("%s: built %s", event.recording, event.step)
							building = (
								order[event.step_index] if event.step_index < len(order) else ""
							)
							progress[location][event.recording] = [
								event.step_index,
								len(order),
								building,
							]
							set_progress(progress)
				except Exception as exc:  # the project's other recordings still finished
					errors[location] = exc
		finally:
			finished.set()

	failed = dict(failed or {})
	for location, names in todo.items():
		kept = {
			name: reason for name, reason in failed.get(location, {}).items() if name not in names
		}
		if location in errors:
			kept |= {name: str(errors[location]) for name in names if not _analysed(location, name)}
		failed[location] = kept

	if errors:
		notify("bad", f"Analysis failed: {next(iter(errors.values()))}")
		return failed, no_update
	if cancel.is_set():
		notify(
			"warn",
			"Cancelled. Recordings in flight finished their current step first, and their "
			"finished tables stay on disk.",
		)
		return failed, no_update

	count = sum(map(len, todo.values()))
	noun = "recording" if count == 1 else "recordings"
	notify("good", f"Analysed {count} {noun} in {time.perf_counter() - started:.1f} s")
	return failed, []


def _analysed(location: str, name: str) -> bool:
	return all(recording_status(Path(location) / name).values())
