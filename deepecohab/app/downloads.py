import io
import json
import tempfile
import zipfile
from pathlib import Path

import plotly.graph_objects as go
import polars as pl
from flask import Blueprint, abort, request, send_file

from deepecohab.app import services
from deepecohab.core.data_model import DataFrameRegistry, Project, Recording, recording_status
from deepecohab.plotting.export import export_figure, figure_data_csv

bp = Blueprint("downloads", __name__)

_SPOOL = 32 * 1024 * 1024  #: zips this small stay in memory; bigger ones spill to disk


def _project(pid: str) -> Project:
	location = services.resolve_project_path(pid)
	if location is None:
		abort(404, "Unknown project id; open it from Projects first.")
	try:
		return services.load_project(location)
	except Exception as exc:
		abort(404, f"Project failed to load: {exc}")


def _recording(pid: str, name: str) -> Recording:
	project = _project(pid)
	try:
		return project[name]
	except KeyError:
		abort(404, "Unknown recording.")


def _computed_tables(recording: Recording) -> list[str]:
	done = recording_status(recording.root)
	return [name for name in DataFrameRegistry.list_available() if done.get(name)]


@bp.route("/download/project/<pid>/table.parquet")
def project_table_parquet(pid: str):
	"""The project table, unconverted."""
	project = _project(pid)
	path = project.project_location / Project.PROJECT_TABLE
	if not path.is_file():
		abort(404, "Generate the project table first.")
	return send_file(
		path, as_attachment=True, download_name=f"{project.project_name}__project_table.parquet"
	)


@bp.route("/download/project/<pid>/table.csv")
def project_table_csv(pid: str):
	"""The project table, converted with :func:`services.csv_ready`."""
	project = _project(pid)
	path = project.project_location / Project.PROJECT_TABLE
	if not path.is_file():
		abort(404, "Generate the project table first.")
	text = services.csv_ready(pl.read_parquet(path)).write_csv()
	return send_file(
		io.BytesIO(text.encode("utf-8")),
		as_attachment=True,
		download_name=f"{project.project_name}__project_table.csv",
		mimetype="text/csv",
	)


@bp.route("/download/project/<pid>/archive.zip")
def project_archive(pid: str):
	"""Every recording's config and results, and its raw data if ``?raw=1``, as one zip."""
	project = _project(pid)
	include_raw = request.args.get("raw") == "1"
	# Closed by send_file once the response is streamed, not here.
	buffer = tempfile.SpooledTemporaryFile(max_size=_SPOOL)  # noqa: SIM115

	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for recording in project.recordings:
			for path in recording.root.rglob("*"):
				relative = path.relative_to(recording.root)
				if path.is_dir() or (not include_raw and relative.parts[0] == "raw"):
					continue
				zf.write(path, str(Path(recording.name) / relative))

	buffer.seek(0)
	suffix = "_with_raw" if include_raw else ""
	return send_file(
		buffer,
		as_attachment=True,
		download_name=f"{project.project_name}__archive{suffix}.zip",
		mimetype="application/zip",
	)


@bp.route("/download/recording/<pid>/<recording_name>/tables.zip")
def recording_tables(pid: str, recording_name: str):
	"""Every table this recording has computed, as one zip, parquet or ``?format=csv``."""
	recording = _recording(pid, recording_name)
	as_csv = request.args.get("format") == "csv"
	buffer = tempfile.SpooledTemporaryFile(max_size=_SPOOL)  # noqa: SIM115 - closed by send_file

	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for name in _computed_tables(recording):
			path = recording.results_path / f"{name}.parquet"
			if as_csv:
				zf.writestr(f"{name}.csv", services.csv_ready(pl.read_parquet(path)).write_csv())
			else:
				zf.write(path, f"{name}.parquet")

	buffer.seek(0)
	suffix = "_csv" if as_csv else ""
	return send_file(
		buffer,
		as_attachment=True,
		download_name=f"{recording.name}__tables{suffix}.zip",
		mimetype="application/zip",
	)


@bp.route("/download/recording/<pid>/<recording_name>/table/<name>.parquet")
def recording_table(pid: str, recording_name: str, name: str):
	"""One computed analysis table, unconverted."""
	recording = _recording(pid, recording_name)
	if name not in _computed_tables(recording):
		abort(404, "That table has not been computed for this recording.")
	path = recording.results_path / f"{name}.parquet"
	return send_file(path, as_attachment=True, download_name=f"{recording.name}__{name}.parquet")


@bp.route("/download/recording/<pid>/<recording_name>/config.json")
def recording_config(pid: str, recording_name: str):
	"""This recording's config.json, as written by :meth:`Recording.update_notes` et al."""
	recording = _recording(pid, recording_name)
	return send_file(
		recording.root / "config.json",
		as_attachment=True,
		download_name=f"{recording.name}__config.json",
	)


@bp.route("/download/recording/<pid>/<recording_name>/raw.parquet")
def recording_raw(pid: str, recording_name: str):
	"""This recording's raw antenna registrations."""
	recording = _recording(pid, recording_name)
	path = recording.root / "raw" / "data.parquet"
	if not path.is_file():
		abort(404, "Raw data not found.")
	return send_file(path, as_attachment=True, download_name=f"{recording.name}__raw.parquet")


@bp.route("/download/recording/<pid>/<recording_name>/cohort.csv")
def recording_cohort(pid: str, recording_name: str):
	"""This recording's cohort, one row per animal."""
	recording = _recording(pid, recording_name)
	frame = pl.DataFrame([animal.model_dump(mode="json") for animal in recording.cohort.animals])
	return send_file(
		io.BytesIO(frame.write_csv().encode("utf-8")),
		as_attachment=True,
		download_name=f"{recording.name}__cohort.csv",
		mimetype="text/csv",
	)


def _safe_filename(name: str) -> str:
	cleaned = "".join(c if c.isalnum() or c in "-_." else "-" for c in name).strip("-")
	return cleaned or "plot"


@bp.route("/export", methods=["POST"])
def export_plot():
	"""Fit the posted figure to the requested export size and render it through kaleido."""
	try:
		figure = json.loads(request.form["figure"])
		form = json.loads(request.form["params"])
	except (KeyError, ValueError):
		abort(400, "Malformed export request.")

	fig = go.Figure(figure)
	if form.get("style") == "publication":
		fig.update_layout(template="publication")

	filename = _safe_filename(form.get("filename") or "plot")
	fmt = form.get("format", "svg")

	# Read the rendered image into memory before the temp dir cleans up, rather than
	# handing send_file a path inside it: on Windows the cleanup races the response
	# actually being streamed and fails to delete a file still open for reading.
	with tempfile.TemporaryDirectory() as tmp:
		image_path = Path(tmp) / f"{filename}.{fmt}"
		export_figure(
			fig,
			image_path,
			float(form["width_mm"]),
			float(form["height_mm"]),
			float(form["pt"]),
			fmt,
			int(form.get("dpi", 300)),
			form.get("title") or "" if form.get("title_on") else "",
			bool(form.get("legend", True)),
			bool(form.get("events", True)),
		)
		image_bytes = image_path.read_bytes()

	csv_text = figure_data_csv(figure) if form.get("csv") else None
	if csv_text is None:
		return send_file(
			io.BytesIO(image_bytes), as_attachment=True, download_name=f"{filename}.{fmt}"
		)

	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		zf.writestr(f"{filename}.{fmt}", image_bytes)
		zf.writestr(f"{filename}.csv", csv_text)
	buffer.seek(0)
	return send_file(
		buffer, as_attachment=True, download_name=f"{filename}.zip", mimetype="application/zip"
	)
