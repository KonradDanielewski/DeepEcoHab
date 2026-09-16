"""Projects: the folders remembered in this browser, their recordings and analysis runs."""

import base64
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import dash
import dash_mantine_components as dmc
import polars as pl
from dash import (
	ALL,
	Input,
	Output,
	State,
	callback,
	clientside_callback,
	ctx,
	dcc,
	html,
	no_update,
	set_props,
)

from deepecohab import AnalysisParams, Project
from deepecohab.app import services
from deepecohab.app.components import icon, notify

dash.register_page(__name__, path="/", name="Projects", order=0, icon="folders")

_DEFAULTS = AnalysisParams()
_PROJECTS_HOME = Path.home() / "Documents" / "deepecohab" / "projects"


def _field(title: str, name: str, control, help_text: str) -> html.Div:
	return html.Div(
		[html.Span([title, " ", html.Code(name)]), control, html.P(help_text)],
		className="deh-field",
	)


def _seconds(control_id: str, value: float) -> html.Span:
	return html.Span(
		[
			dmc.NumberInput(
				id=control_id,
				value=value,
				min=0,
				step=0.5,
				allowNegative=False,
				w=96,
				classNames={"input": "deh-input"},
			),
			html.Span("seconds", className="deh-sub"),
		],
		className="deh-unit-input",
	)


_DIALOG_CLASSES = {
	"content": "deh-dialog",
	"header": "deh-dialog-head",
	"title": "deh-dialog-title",
	"body": "deh-dialog-content",
}

layout = html.Div(
	[
		dcc.Store(id="expanded", data=[]),
		dcc.Store(id="selection", data=[]),
		dcc.Store(id="analysis-params"),
		dcc.Store(id="run-progress"),
		dcc.Store(id="run-active", data=False),
		dcc.Store(id="run-failed", data={}),
		dcc.Store(id="data-changed"),
		dcc.Store(id="upload-target"),
		dcc.Store(id="remove-target"),
		html.Div(
			[
				html.Div([html.H2("Projects"), html.P(id="project-count")], className="deh-titles"),
				dmc.TextInput(
					id="project-search",
					placeholder="Filter projects and recordings",
					leftSection=icon("search", size=16),
					debounce=150,
					className="deh-search",
					classNames={"input": "deh-input"},
					**{"aria-label": "Filter projects and recordings"},  # ty: ignore[invalid-argument-type]
				),
				html.Button(
					[icon("plus", size=16), "Add project"],
					id="add-open",
					className="deh-btn",
				),
				html.Button(
					[icon("folder-plus", size=16), "New project"],
					id="create-open",
					className="deh-btn deh-btn-primary",
				),
			],
			className="deh-screen-head",
		),
		html.Div(id="project-table", className="deh-table-wrap"),
		html.Div(
			[
				html.Div(id="actionbar-message", className="deh-ab-msg"),
				html.Div(html.I(id="actionbar-meter"), className="deh-meter deh-when-running"),
				html.Button(
					[icon("adjustments-horizontal", size=16), "Parameters"],
					id="params-open",
					className="deh-btn deh-when-idle",
				),
				dmc.Switch(
					id="overwrite",
					checked=False,
					label="Overwrite existing tables",
					size="sm",
					className="deh-switch deh-when-idle",
				),
				html.Span(className="deh-grow"),
				html.Button(
					"Clear", id="selection-clear", className="deh-btn deh-btn-ghost deh-when-idle"
				),
				html.Button(
					[icon("player-play", size=16), "Run analysis"],
					id="run-start",
					className="deh-btn deh-btn-primary deh-when-idle",
				),
				html.Button("Cancel", id="run-cancel", className="deh-btn deh-when-running"),
			],
			id="actionbar",
			className="deh-actionbar",
			hidden=True,
		),
		dmc.Drawer(
			id="params-drawer",
			title="Analysis parameters",
			position="right",
			size="380px",
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					[
						_field(
							"Minimum meeting",
							"minimum_time",
							_seconds("params-minimum-time", _DEFAULTS.minimum_time),
							"Minimum continuous co-presence for a meeting to count. "
							"0 keeps every meeting.",
						),
						_field(
							"Minimum time alone",
							"minimum_time_alone",
							_seconds("params-minimum-alone", _DEFAULTS.minimum_time_alone),
							"Minimum solitary span. Discards the brief gaps left by animals "
							"arriving moments apart.",
						),
						_field(
							"Chasing window",
							"chasing_time_window",
							dmc.RangeSlider(
								id="params-chasing",
								value=list(_DEFAULTS.chasing_time_window),
								min=0,
								max=5,
								step=0.1,
								minRange=0.1,
								precision=1,
								marks=[
									{"value": second, "label": f"{second} s"} for second in range(6)
								],
								mb="lg",
							),
							"Shortest and longest chasing event, in seconds.",
						),
						html.Div(
							[
								icon("info-circle"),
								html.Span(
									[
										html.Code("prev_ranking"),
										" takes a table from an earlier recording, so it stays in "
										"notebooks for now.",
									]
								),
							],
							className="deh-alert deh-alert-info",
						),
					],
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button(
							"Reset to defaults",
							id="params-reset",
							className="deh-btn deh-btn-ghost",
						),
						html.Button(
							"Apply", id="params-apply", className="deh-btn deh-btn-primary"
						),
					],
					className="deh-dialog-foot",
				),
			],
		),
		dmc.Modal(
			id="add-modal",
			title="Add project",
			size=520,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					dmc.TextInput(
						id="add-path",
						label="Project folder",
						description=[
							"The folder that holds ",
							html.Code("project.json"),
							". The path is remembered in this browser only; files are never moved.",
						],
						placeholder=r"C:\Users\you\Documents\deepecohab\projects\my_project",
						autoComplete="off",
						inputWrapperOrder=["label", "input", "description", "error"],
						className="deh-field",
						classNames={"input": "deh-input deh-mono"},
					),
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button("Cancel", id="add-cancel", className="deh-btn deh-btn-ghost"),
						html.Button(
							"Add project", id="add-submit", className="deh-btn deh-btn-primary"
						),
					],
					className="deh-dialog-foot",
				),
			],
		),
		dmc.Modal(
			id="create-modal",
			title="New project",
			size=520,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					[
						dmc.TextInput(
							id="create-name",
							label="Project name",
							placeholder="my_project",
							className="deh-field",
							classNames={"input": "deh-input"},
						),
						dmc.TextInput(
							id="create-experimenter",
							label="Experimenter",
							placeholder="Who runs the experiment",
							className="deh-field",
							classNames={"input": "deh-input"},
						),
						dmc.TextInput(
							id="create-path",
							label="Folder",
							description="Created if it doesn't exist. Leave empty to use the folder shown.",
							placeholder=str(_PROJECTS_HOME / "<project name>"),
							autoComplete="off",
							inputWrapperOrder=["label", "input", "description", "error"],
							className="deh-field",
							classNames={"input": "deh-input deh-mono"},
						),
						dmc.Textarea(
							id="create-description",
							label="Description",
							placeholder="Optional: cohorts, treatment, what the project is for",
							autosize=True,
							minRows=2,
							className="deh-field",
						),
					],
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button(
							"Cancel", id="create-cancel", className="deh-btn deh-btn-ghost"
						),
						html.Button(
							"Create project",
							id="create-submit",
							className="deh-btn deh-btn-primary",
						),
					],
					className="deh-dialog-foot",
				),
			],
		),
		dmc.Modal(
			id="upload-modal",
			title="Add recordings",
			size=560,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					[
						dcc.Upload(
							id="upload-files",
							multiple=True,
							accept=".json,.parquet",
							className="deh-drop",
							className_active="deh-drop is-over",
							children=[
								icon("upload", size=22),
								html.B("Drop recordings here, or click to pick them"),
								html.Span(
									[
										"One ",
										html.Code("<name>.json"),
										" of metadata beside its ",
										html.Code("<name>.parquet"),
										" of registrations. Files are copied into the project "
										"under the name the metadata carries.",
									]
								),
							],
						),
						html.Div(id="upload-report"),
					],
					className="deh-dialog-body",
				),
				html.Div(
					html.Button("Close", id="upload-close", className="deh-btn"),
					className="deh-dialog-foot",
				),
			],
		),
		dmc.Modal(
			id="remove-modal",
			title="Remove recording",
			size=520,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					html.P(
						"Delisting takes the recording out of the project and leaves every file "
						"where it is, so adding it again brings it back. Deleting also removes "
						"the recording's folder — its config, raw registrations and results "
						"— for good."
					),
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button(
							"Cancel", id="remove-cancel", className="deh-btn deh-btn-ghost"
						),
						html.Button("Delist, keep files", id="remove-delist", className="deh-btn"),
						html.Button(
							[icon("trash", size=16), "Delete files"],
							id="remove-delete",
							className="deh-btn deh-btn-danger",
						),
					],
					className="deh-dialog-foot",
				),
			],
		),
	]
)


def _visible_recordings(project: dict, query: str) -> list[dict]:
	"""A project's recordings under the search; all of them when the project name matches."""
	if not query or query in project["name"].lower():
		return project["recordings"]
	return [recording for recording in project["recordings"] if query in recording["name"].lower()]


def _badge(kind: str, icon_name: str, *content, spin: bool = False, title: str = "") -> html.Span:
	return html.Span(
		[icon(icon_name, size=14, class_name="deh-spin" if spin else ""), *content],
		className=f"deh-badge deh-badge-{kind}",
		title=title,
	)


def _status(recording: dict, running: list | None, failure: str | None) -> html.Span:
	done, total = recording["done"], recording["total"]
	if running is not None:
		steps, _, building = running
		building = html.Span(building or "done", className="deh-mono")
		return _badge("run", "loader-2", f"{steps}/{total} · ", building, spin=True)
	if failure is not None:
		return _badge("bad", "circle-x", "Failed", title=failure)
	if done == total:
		return _badge("good", "circle-check", "Analysed", html.Small(f"{done}/{total}"))
	if done == 0:
		return _badge("neutral", "circle-dashed", "Not analysed", html.Small(f"0/{total}"))
	return _badge("warn", "alert-triangle", "Partial", html.Small(f"{done}/{total}"))


def _project_menu(project: dict) -> dmc.Menu:
	location, loadable = project["location"], project["error"] is None
	return dmc.Menu(
		[
			dmc.MenuTarget(
				html.Button(
					icon("dots-vertical"),
					className="deh-icon-btn",
					title=f"Actions for {project['name']}",
				)
			),
			dmc.MenuDropdown(
				[
					dmc.MenuLabel(project["name"]),
					dmc.MenuItem(
						"Open in plot builder",
						leftSection=icon("drag-drop", size=16),
						href=dash.get_relative_path(f"/builder?project={project['id']}"),
						disabled=not loadable,
					),
					dmc.MenuItem(
						"Add recordings…",
						leftSection=icon("upload", size=16),
						id={"type": "add-recordings", "place": "menu", "index": location},
						disabled=not loadable,
					),
					dmc.MenuItem(
						"Generate project table",
						leftSection=icon("database", size=16),
						id={"type": "generate-table", "index": location},
						disabled=not loadable,
					),
					*(
						[
							dmc.MenuDivider(),
							dmc.MenuLabel("Download"),
							*(
								dmc.MenuItem(
									label,
									leftSection=icon(icon_name, size=16),
									href=href,
									target="_blank",
								)
								for icon_name, label, href in _project_download_items(project["id"])
							),
						]
						if loadable
						else []
					),
					dmc.MenuItem(
						"Copy path",
						leftSection=icon("copy", size=16),
						id={"type": "copy-path", "place": "menu", "index": location},
					),
					dmc.MenuDivider(),
					dmc.MenuItem(
						"Remove from list",
						leftSection=icon("trash", size=16),
						id={"type": "remove-project", "index": location},
						className="deh-danger",
					),
				]
			),
		],
		position="bottom-end",
		classNames={"dropdown": "deh-menu"},
	)


def _project_download_items(pid: str) -> list[tuple[str, str, str]]:
	base = f"/download/project/{pid}"
	return [
		("table", "Project table · parquet", f"{base}/table.parquet"),
		("file-type-csv", "Project table · CSV", f"{base}/table.csv"),
		("file-zip", "Configs and results · zip", f"{base}/archive.zip"),
		("file-zip", "Configs, results and raw data · zip", f"{base}/archive.zip?raw=1"),
	]


def _download_menu(pid: str, name: str, loadable: bool) -> dmc.Menu:
	base = f"/download/recording/{pid}/{quote(name, safe='')}"
	files = [
		("file-zip", "All analysis tables · parquet", f"{base}/tables.zip"),
		("file-zip", "All analysis tables · CSV", f"{base}/tables.zip?format=csv"),
		("paw", "Cohort · CSV", f"{base}/cohort.csv"),
		("file-description", "Recording config · JSON", f"{base}/config.json"),
		("database", "Raw registrations · parquet", f"{base}/raw.parquet"),
	]
	return dmc.Menu(
		[
			dmc.MenuTarget(
				html.Button(
					icon("download", size=15),
					className="deh-icon-btn sm",
					title=f"Download data of {name}",
					disabled=not loadable,
				)
			),
			dmc.MenuDropdown(
				[
					dmc.MenuLabel(name),
					*(
						dmc.MenuItem(
							label, leftSection=icon(icon_name, size=16), href=href, target="_blank"
						)
						for icon_name, label, href in files
					),
				]
			),
		],
		position="bottom-end",
		classNames={"dropdown": "deh-menu"},
	)


def _recording_row(
	project: dict, recording: dict, selected: set, progress: dict | None, failed: dict
) -> html.Tr:
	location, name = project["location"], recording["name"]
	loadable = project["error"] is None
	checked = (location, name) in selected
	opens = ["Open", icon("arrow-right", size=16)]
	return html.Tr(
		[
			html.Td(
				dmc.Checkbox(
					id={"type": "recording-check", "project": location, "index": name},
					checked=checked,
					disabled=not loadable or progress is not None,
					size="xs",
					radius="xs",
					**{"aria-label": f"Select {name}"},  # ty: ignore[invalid-argument-type]
				),
				className="c-check",
			),
			html.Td(html.Span(name, className="deh-mono deh-rec-name")),
			html.Td(
				[recording["window"], html.Div(recording["timezone"], className="deh-sub")]
				if loadable
				else "—"
			),
			html.Td(
				f"{recording['days']} · {recording['phases']}" if loadable else "—", className="num"
			),
			html.Td(recording["n_mice"] if loadable else "—", className="num"),
			html.Td(
				html.Div(
					[html.Span(trait, className="deh-tag") for trait in recording["traits"]],
					className="deh-tags",
				)
				if loadable
				else "—"
			),
			html.Td(recording["events"] if loadable else "—", className="num"),
			html.Td(
				_status(
					recording,
					(progress or {}).get(location, {}).get(name),
					failed.get(location, {}).get(name),
				)
			),
			html.Td(
				html.Div(
					[
						_download_menu(project["id"], name, loadable),
						dcc.Link(
							opens,
							href=dash.get_relative_path(
								f"/recording?project={project['id']}&recording={quote(name)}"
							),
							className="deh-btn deh-btn-ghost sm",
						)
						if loadable
						else html.Button(
							opens,
							className="deh-btn deh-btn-ghost sm",
							disabled=True,
							title="Opens once the configs load",
						),
						html.Button(
							icon("trash", size=15),
							id={"type": "remove-recording", "project": location, "index": name},
							className="deh-icon-btn sm deh-danger",
							title=f"Remove {name} from the project",
							disabled=not loadable or progress is not None,
						),
					],
					className="deh-card-actions",
				)
			),
		],
		className="is-selected" if checked else "",
	)


def _project_rows(
	project: dict,
	query: str,
	expanded: list[str],
	selected: set,
	progress: dict | None,
	failed: dict,
) -> list[html.Tr]:
	location, recordings = project["location"], project["recordings"]
	visible = _visible_recordings(project, query)
	name_hit = not query or query in project["name"].lower()
	if not (name_hit or visible):
		return []

	opened = location in expanded or not name_hit
	loadable = project["error"] is None
	analysed = sum(recording["done"] == recording["total"] for recording in recordings)
	partial = sum(0 < recording["done"] < recording["total"] for recording in recordings)
	share = round(100 * analysed / len(recordings)) if recordings else 0
	table_rows = project["table_rows"]

	rows = [
		html.Tr(
			[
				html.Td(
					html.Button(
						icon("chevron-right"),
						id={"type": "project-expand", "part": "chevron", "index": location},
						className=f"deh-icon-btn deh-exp{' is-open' if opened else ''}",
						title=f"Show recordings of {project['name']}",
					),
					className="c-exp",
				),
				html.Td(
					[
						html.Div(project["name"], className="deh-p-name"),
						html.Div(project["description"], className="deh-p-desc"),
					],
					id={"type": "project-expand", "part": "name", "index": location},
					className="deh-p-cell",
				),
				html.Td(project["experimenter"]),
				html.Td(len(recordings), className="num"),
				html.Td(
					html.Div(
						[
							html.Div(
								html.I(style={"width": f"{share}%"}),
								className="deh-meter full" if share == 100 else "deh-meter",
							),
							html.Span(
								f"{analysed} of {len(recordings)} analysed"
								+ (f" · {partial} partial" if partial else "")
							),
						],
						className="deh-an",
					)
				),
				html.Td(
					_badge("neutral", "database", f"{table_rows:,} rows")
					if table_rows is not None
					else _badge("neutral", "circle-dashed", "Not generated")
				),
				html.Td(
					html.Div(
						[
							html.Span(
								html.Bdi(location), className="deh-trunc deh-mono", title=location
							),
							html.Button(
								icon("copy", size=15),
								id={"type": "copy-path", "place": "row", "index": location},
								className="deh-icon-btn sm",
								title="Copy path",
							),
						],
						className="deh-loc",
					)
				),
				html.Td(_project_menu(project), className="c-menu"),
			],
			className="deh-project-row",
		)
	]
	if not opened:
		return rows

	keys = {(location, recording["name"]) for recording in visible}
	recordings_table = html.Table(
		[
			html.Thead(
				html.Tr(
					[
						html.Th(
							dmc.Checkbox(
								id={"type": "select-all", "index": location},
								checked=bool(keys) and keys <= selected,
								disabled=not loadable or progress is not None,
								size="xs",
								radius="xs",
								**{"aria-label": f"Select all recordings in {project['name']}"},  # ty: ignore[invalid-argument-type]
							),
							className="c-check",
						),
						html.Th("Recording"),
						html.Th("Window"),
						html.Th("Days · phases", className="num"),
						html.Th("Mice", className="num"),
						html.Th("Cohort"),
						html.Th("Events", className="num"),
						html.Th("Status"),
						html.Th(""),
					]
				)
			),
			html.Tbody(
				[
					_recording_row(project, recording, selected, progress, failed)
					for recording in visible
				]
				or html.Tr(
					html.Td(
						"No recordings match the filter." if recordings else "No recordings yet.",
						colSpan=9,
						className="deh-empty",
					)
				)
			),
			html.Tfoot(
				html.Tr(
					html.Td(
						html.Button(
							[icon("upload", size=16), "Add recordings"],
							id={"type": "add-recordings", "place": "table", "index": location},
							className="deh-btn sm",
							disabled=not loadable,
						),
						colSpan=9,
					)
				)
			),
		],
		className="deh-tbl deh-inner",
	)
	load_error = html.Div(
		[
			icon("circle-x"),
			html.Div(
				[
					html.B("Project.load"),
					" rejects this project, so the list comes from ",
					html.Code("project.json"),
					" and the results folders. Dashboards and runs open once the configs load.",
					html.Pre(project["error"]),
				]
			),
		],
		className="deh-alert deh-alert-bad",
	)
	rows.append(
		html.Tr(
			html.Td(
				html.Div(
					[recordings_table] if loadable else [load_error, recordings_table],
					className="deh-detail-in",
				),
				colSpan=8,
			),
			className="deh-detail",
		)
	)
	return rows


@callback(
	Output("project-table", "children"),
	Output("project-count", "children"),
	Input("project-paths", "data"),
	Input("project-search", "value"),
	Input("expanded", "data"),
	Input("selection", "data"),
	Input("run-progress", "data"),
	Input("run-failed", "data"),
	Input("data-changed", "data"),
	Input("run-active", "data"),
)
def _render_projects(paths, search, expanded, selection, progress, failed, _written, active):
	# The last progress can land after the result, so it outlives the run unless gated.
	progress = progress if active else None
	paths = paths or []
	query = (search or "").strip().lower()
	selected = {tuple(key) for key in selection}
	rows = [
		row
		for location in paths
		for row in _project_rows(
			services.project_summary(location), query, expanded, selected, progress, failed
		)
	]
	if not rows:
		empty = (
			f"Nothing matches “{search.strip()}”."
			if paths
			else "No projects yet. Create one, or add a project folder to see its recordings."
		)
		rows = [html.Tr(html.Td(empty, colSpan=8, className="deh-empty"))]

	head = html.Thead(
		html.Tr(
			[
				html.Th(""),
				html.Th("Project"),
				html.Th("Experimenter"),
				html.Th("Recordings", className="num"),
				html.Th("Analysis"),
				html.Th("Project table"),
				html.Th("Location"),
				html.Th(""),
			]
		)
	)
	noun = "project" if len(paths) == 1 else "projects"
	return (
		html.Table([head, html.Tbody(rows)], className="deh-tbl"),
		f"{len(paths)} {noun} remembered in this browser",
	)


@callback(
	Output("actionbar", "hidden"),
	Output("actionbar", "className"),
	Output("actionbar-message", "children"),
	Output("actionbar-meter", "style"),
	Input("selection", "data"),
	Input("run-progress", "data"),
	Input("run-active", "data"),
)
def _render_actionbar(selection, progress, active):
	if active and progress:
		jobs = [job for recordings in progress.values() for job in recordings.values()]
		done = sum(steps for steps, _, _ in jobs)
		total = sum(steps for _, steps, _ in jobs)
		noun = "recording" if len(jobs) == 1 else "recordings"
		message = [
			icon("loader-2", class_name="deh-spin"),
			html.Span(["Analysing ", html.B(len(jobs)), f" {noun} · {done}/{total} steps"]),
		]
		return False, "deh-actionbar is-running", message, {"width": f"{100 * done // total}%"}

	noun = "recording" if len(selection) == 1 else "recordings"
	message = [html.B(len(selection)), f" {noun} selected"]
	return not selection, "deh-actionbar", message, no_update


@callback(
	Output("expanded", "data"),
	Input({"type": "project-expand", "part": ALL, "index": ALL}, "n_clicks"),
	State("expanded", "data"),
	prevent_initial_call=True,
)
def _toggle_project(_clicks, expanded):
	if not ctx.triggered[0]["value"]:
		return no_update
	location = ctx.triggered_id["index"]
	if location in expanded:
		return [path for path in expanded if path != location]
	return [*expanded, location]


@callback(
	Output("selection", "data", allow_duplicate=True),
	Input({"type": "recording-check", "project": ALL, "index": ALL}, "checked"),
	Input({"type": "select-all", "index": ALL}, "checked"),
	Input("selection-clear", "n_clicks"),
	State("selection", "data"),
	State("project-search", "value"),
	prevent_initial_call=True,
)
def _select_recordings(_checks, _all, _clear, selection, search):
	trigger = ctx.triggered_id
	if trigger == "selection-clear":
		return []
	if trigger is None:
		return no_update

	selected = {tuple(key) for key in selection}
	if trigger["type"] == "select-all":
		project = services.project_summary(trigger["index"])
		query = (search or "").strip().lower()
		keys = {
			(trigger["index"], recording["name"])
			for recording in _visible_recordings(project, query)
		}
	else:
		keys = {(trigger["project"], trigger["index"])}

	changed = selected | keys if ctx.triggered[0]["value"] else selected - keys
	return no_update if changed == selected else sorted(map(list, changed))


@callback(
	Output("add-modal", "opened"),
	Output("add-path", "value"),
	Output("add-path", "error"),
	Input("add-open", "n_clicks"),
	Input("add-cancel", "n_clicks"),
	Input("add-submit", "n_clicks"),
	Input("add-path", "n_submit"),
	State("add-path", "value"),
	State("project-paths", "data"),
	prevent_initial_call=True,
)
def _add_project(_open, _cancel, _submit, _enter, value, paths):
	if ctx.triggered_id == "add-open":
		return True, "", None
	if ctx.triggered_id == "add-cancel":
		return False, no_update, None

	folder = Path((value or "").strip().strip('"'))
	if folder.name == Project.MANIFEST:
		folder = folder.parent
	if not str(folder).strip(". "):
		return no_update, no_update, "Enter the folder that holds project.json."
	if not (folder.expanduser() / Project.MANIFEST).is_file():
		error = (
			f"No project.json in {folder}. Pick the folder that holds it; it sits next to one "
			"folder per recording."
		)
		return no_update, no_update, error

	location = str(folder.expanduser().resolve())
	project = services.project_summary(location)
	if location in paths:
		return no_update, no_update, f"{project['name']} is already in your list."

	set_props("project-paths", {"data": [*paths, location]})
	notify("good", f"Added {project['name']}: {len(project['recordings'])} recordings")
	return False, "", None


@callback(
	Output("create-modal", "opened"),
	Output("create-name", "value"),
	Output("create-experimenter", "value"),
	Output("create-path", "value"),
	Output("create-description", "value"),
	Output("create-name", "error"),
	Output("create-experimenter", "error"),
	Output("create-path", "error"),
	Input("create-open", "n_clicks"),
	Input("create-cancel", "n_clicks"),
	Input("create-submit", "n_clicks"),
	State("create-name", "value"),
	State("create-experimenter", "value"),
	State("create-path", "value"),
	State("create-description", "value"),
	State("project-paths", "data"),
	prevent_initial_call=True,
)
def _create_project(_open, _cancel, _submit, name, experimenter, folder, description, paths):
	unchanged = (no_update,) * 4
	if ctx.triggered_id == "create-open":
		return True, "", "", "", "", None, None, None
	if ctx.triggered_id == "create-cancel":
		return False, *unchanged, None, None, None

	name, experimenter = (name or "").strip(), (experimenter or "").strip()
	if not name or not experimenter:
		name_error = None if name else "Enter the project name."
		experimenter_error = None if experimenter else "Enter who runs the experiment."
		return no_update, *unchanged, name_error, experimenter_error, None

	location = Path((folder or "").strip().strip('"') or _PROJECTS_HOME / name).expanduser()
	try:
		project = Project.create(name, experimenter, location, (description or "").strip())
	except FileExistsError:
		error = "This folder already holds a project; open it with Add project."
		return no_update, *unchanged, None, None, error
	except OSError as exc:
		return no_update, *unchanged, None, None, f"Can't create this folder: {exc.strerror or exc}"

	project.close()
	set_props("project-paths", {"data": [*paths, str(project.project_location)]})
	notify("good", f"Created {name} in {project.project_location}")
	return False, *unchanged, None, None, None


@callback(
	Output("selection", "data", allow_duplicate=True),
	Input({"type": "remove-project", "index": ALL}, "n_clicks"),
	State("project-paths", "data"),
	State("selection", "data"),
	prevent_initial_call=True,
)
def _remove_project(_clicks, paths, selection):
	if not ctx.triggered[0]["value"]:
		return no_update
	location = ctx.triggered_id["index"]
	set_props("project-paths", {"data": [path for path in paths if path != location]})
	notify(
		"info",
		f"Removed {services.project_summary(location)['name']} from this browser's list. Its "
		"files stay on disk; add the folder again to bring it back.",
	)
	return [key for key in selection if key[0] != location]


@callback(
	Output("data-changed", "data"),
	Input({"type": "generate-table", "index": ALL}, "n_clicks"),
	prevent_initial_call=True,
)
def _generate_table(_clicks):
	if not ctx.triggered[0]["value"]:
		return no_update
	project = services.load_project(ctx.triggered_id["index"])
	try:
		rows = project.generate_project_table().select(pl.len()).collect().item()
	except (FileNotFoundError, ValueError) as exc:
		notify("bad", str(exc))
		return no_update
	notify("good", f"Wrote {Project.PROJECT_TABLE}: {rows:,} rows from {len(project)} recordings")
	return time.time()


def _pair_uploads(files: list[Path]) -> tuple[list[tuple[Path, Path]], list[str]]:
	"""Match every ``<name>.json`` of metadata to the ``<name>.parquet`` dropped with it.

	Returns:
		The (metadata, data) pairs, and one line for each file left without a partner.
	"""
	metadata = {path.stem: path for path in files if path.suffix.lower() == ".json"}
	data = {path.stem: path for path in files if path.suffix.lower() == ".parquet"}
	pairs, lonely = [], []
	for path in files:
		suffix = path.suffix.lower()
		if suffix == ".json" and path.stem in data:
			pairs.append((path, data[path.stem]))
		elif suffix == ".json":
			lonely.append(f"{path.name}: no {path.stem}.parquet came with it")
		elif suffix == ".parquet" and path.stem not in metadata:
			lonely.append(f"{path.name}: no {path.stem}.json came with it")
		elif suffix != ".parquet":
			lonely.append(f"{path.name}: neither metadata (.json) nor registrations (.parquet)")
	return pairs, lonely


@callback(
	Output("upload-modal", "opened"),
	Output("upload-modal", "title"),
	Output("upload-target", "data"),
	Output("upload-report", "children"),
	Output("upload-files", "contents"),
	Output("data-changed", "data", allow_duplicate=True),
	Input({"type": "add-recordings", "place": ALL, "index": ALL}, "n_clicks"),
	Input("upload-files", "contents"),
	Input("upload-close", "n_clicks"),
	State("upload-files", "filename"),
	State("upload-target", "data"),
	prevent_initial_call=True,
)
def _add_recordings(_clicks, contents, _close, filenames, location):
	unchanged = (no_update,) * 6
	if ctx.triggered_id == "upload-close":
		return False, no_update, no_update, None, None, no_update
	if ctx.triggered_id != "upload-files":
		if not ctx.triggered[0]["value"]:
			return unchanged
		location = ctx.triggered_id["index"]
		title = f"Add recordings to {services.project_summary(location)['name']}"
		return True, title, location, None, None, no_update
	if not contents:  # our own reset of the drop zone comes back through this Input
		return unchanged

	project = services.load_project(location)
	with tempfile.TemporaryDirectory(prefix="deh-upload-") as staging:
		files = []
		for name, blob in zip(filenames, contents, strict=True):
			path = Path(staging) / Path(name).name
			path.write_bytes(base64.b64decode(blob.split(",", 1)[1]))
			files.append(path)

		pairs, lonely = _pair_uploads(files)
		added, failed = project.add_recordings(pairs) if pairs else ([], [])

	problems = lonely + [
		f"{source.metadata_path.name}: {type(source.error).__name__}: {source.error}"
		for source in failed
	]
	if not problems:
		noun = "recording" if len(added) == 1 else "recordings"
		notify("good", f"Added {len(added)} {noun} to {project.project_name}")
		return False, no_update, no_update, None, None, time.time()

	notify("warn", f"Added {len(added)}; {len(problems)} could not be added")
	report = html.Div(
		[
			icon("circle-x"),
			html.Div([html.B("Not added"), html.Pre("\n".join(problems))]),
		],
		className="deh-alert deh-alert-bad",
	)
	return True, no_update, no_update, report, None, time.time()


@callback(
	Output("remove-modal", "opened"),
	Output("remove-modal", "title"),
	Output("remove-target", "data"),
	Output("data-changed", "data", allow_duplicate=True),
	Output("selection", "data", allow_duplicate=True),
	Input({"type": "remove-recording", "project": ALL, "index": ALL}, "n_clicks"),
	Input("remove-cancel", "n_clicks"),
	Input("remove-delist", "n_clicks"),
	Input("remove-delete", "n_clicks"),
	State("remove-target", "data"),
	State("selection", "data"),
	prevent_initial_call=True,
)
def _remove_recording(_clicks, _cancel, _delist, _delete, target, selection):
	if isinstance(ctx.triggered_id, dict):
		if not ctx.triggered[0]["value"]:
			return (no_update,) * 5
		location, name = ctx.triggered_id["project"], ctx.triggered_id["index"]
		return True, f"Remove {name}?", [location, name], no_update, no_update
	if ctx.triggered_id == "remove-cancel":
		return False, no_update, no_update, no_update, no_update

	location, name = target
	delete_files = ctx.triggered_id == "remove-delete"
	services.load_project(location).remove_recording(name, delete_files=delete_files)
	notify(
		"info",
		f"Deleted {name} and its files" if delete_files else f"Delisted {name}; its files stay",
	)
	kept = [key for key in selection if key != [location, name]]
	return False, no_update, no_update, time.time(), kept


@callback(
	Output("params-drawer", "opened"),
	Output("analysis-params", "data"),
	Output("params-minimum-time", "error"),
	Output("params-minimum-alone", "error"),
	Input("params-open", "n_clicks"),
	Input("params-apply", "n_clicks"),
	State("params-minimum-time", "value"),
	State("params-minimum-alone", "value"),
	State("params-chasing", "value"),
	prevent_initial_call=True,
)
def _apply_params(_open, _apply, minimum_time, minimum_time_alone, chasing_time_window):
	if ctx.triggered_id == "params-open":
		return True, no_update, None, None

	errors = [
		None if isinstance(value, int | float) else "A number of seconds, 0 or more."
		for value in (minimum_time, minimum_time_alone)
	]
	if any(errors):
		return no_update, no_update, *errors

	params = {
		"minimum_time": minimum_time,
		"minimum_time_alone": minimum_time_alone,
		"chasing_time_window": chasing_time_window,
	}
	notify("info", "Parameters apply to the next run.")
	return False, params, None, None


@callback(
	Output("params-minimum-time", "value"),
	Output("params-minimum-alone", "value"),
	Output("params-chasing", "value"),
	Input("params-reset", "n_clicks"),
	prevent_initial_call=True,
)
def _reset_params(_clicks):
	return (
		_DEFAULTS.minimum_time,
		_DEFAULTS.minimum_time_alone,
		list(_DEFAULTS.chasing_time_window),
	)


callback(
	Output("run-failed", "data"),
	Output("selection", "data", allow_duplicate=True),
	Input("run-start", "n_clicks"),
	State("selection", "data"),
	State("analysis-params", "data"),
	State("overwrite", "checked"),
	State("run-failed", "data"),
	background=True,
	progress=Output("run-progress", "data"),
	running=[
		(Output("run-start", "disabled"), True, False),
		(Output("run-active", "data"), True, False),
	],
	prevent_initial_call=True,
)(services.run_analysis)

clientside_callback(
	"function () { return null; }",
	Output("run-progress", "data", allow_duplicate=True),
	Input("run-start", "n_clicks"),
	prevent_initial_call=True,
)


@callback(Input("run-cancel", "n_clicks"), State("selection", "data"), prevent_initial_call=True)
def _cancel_run(_clicks, selection):
	for location in {location for location, _ in selection}:
		services.request_cancel(location)
	notify("info", "Cancelling: recordings in flight finish their current step first.")


clientside_callback(
	"""function () {
		const dc = window.dash_clientside;
		const trigger = dc.callback_context.triggered[0];
		if (!trigger || !trigger.value) return dc.no_update;
		const toast = (kind, message) => dc.set_props("notifications", {sendNotifications: [{
			action: "show", message, className: `deh-toast deh-toast-${kind}`,
			withCloseButton: false, autoClose: 5200,
		}]});
		const path = dc.callback_context.triggered_id.index;
		(navigator.clipboard ? navigator.clipboard.writeText(path) : Promise.reject()).then(
			() => toast("info", "Path copied"),
			() => toast("warn", "The browser blocked clipboard access; select the path instead."),
		);
		return dc.no_update;
	}""",
	Output("notifications", "sendNotifications", allow_duplicate=True),
	Input({"type": "copy-path", "place": ALL, "index": ALL}, "n_clicks"),
	prevent_initial_call=True,
)
