"""Recording dashboard: per-recording plots, controls and downloads."""

import datetime as dt
from urllib.parse import parse_qs, quote, urlencode

import dash
import dash_mantine_components as dmc
from dash import (
	ALL,
	MATCH,
	Input,
	Output,
	State,
	callback,
	ctx,
	dcc,
	html,
	no_update,
)
from dash.exceptions import PreventUpdate

from deepecohab.app import services
from deepecohab.app.components import icon, notify
from deepecohab.core.data_model import DataFrameRegistry
from deepecohab.plotting import PlotContext, PlotRegistry, available_attributes
from deepecohab.plotting.animals import resolve_colors

dash.register_page(
	__name__, path="/recording", name="Recording dashboard", order=1, icon="layout-dashboard"
)

PHASES = ["light_phase", "dark_phase"]
#: Driven by the control bar rather than a per-card control.
_GLOBAL_OPTIONS = {"days_range", "granularity", "phase_type", "color_by", "order_by", "hours_range"}
_OPTION_LABELS = {"agg": "Aggregate"}
#: (id, label, cells); a cell is (plot, column span of 12, height px[, grid rows]).
#: "cohort" and "quality-summary" are computed cards, not registered plots.
#: 548px is a half-width (span 6) card's rendered width at the common 1440px desktop
#: viewport this app is designed around, so a plot with that height there reads square.
_SECTIONS = [
	(
		"overview",
		"Overview",
		[
			("metrics-polar-line", 7, 500),
			("cohort", 5, 500),
		],
	),
	(
		"quality",
		"Quality",
		[
			("quality-summary", 12, 0),
			("quality-antenna", 7, 430),
			("quality-heatmap", 5, 430),
		],
	),
	(
		"activity",
		"Activity",
		[
			("recording-timeline", 12, 340),
			("activity-line", 8, 340),
			("cage-preference", 4, 340),
			("activity-bar", 6, 320),
			("time-alone-bar", 6, 320),
			("time-per-cage-heatmap", 7, 660),
			("cage-preference-evolution", 5, 660),
		],
	),
	(
		"social",
		"Social",
		[
			("sociability-heatmap", 6, 548),
			("cohort-heatmap", 6, 548),
			("network-sociability", 6, 548),
			("social-stability", 6, 548),
		],
	),
	(
		"dominance",
		"Dominance",
		[
			("ranking-line", 12, 360),
			("ranking-distribution-line", 6, 548),
			("chasings-line", 6, 548),
			("network-dominance", 6, 548),
			("chasings-heatmap", 6, 548),
		],
	),
]
_TAB_IDS = {section_id for section_id, *_ in _SECTIONS}

_DIALOG_CLASSES = {
	"content": "deh-dialog",
	"header": "deh-dialog-head",
	"title": "deh-dialog-title",
	"body": "deh-dialog-content",
}

layout = html.Div(
	[
		dcc.Store(id="rec-context"),
		dcc.Store(id="rec-controls"),
		dcc.Store(id="rec-notes"),
		dcc.Store(id="export-source"),
		html.Div(id="rec-body"),
		dmc.Modal(
			id="fullscreen-modal",
			title="",
			fullScreen=True,
			classNames={
				"content": "deh-dialog",
				"header": "deh-dialog-head",
				"title": "deh-dialog-title",
			},
			children=dcc.Graph(
				id="fullscreen-plot",
				config={"displayModeBar": False},
				style={"height": "calc(100vh - 120px)"},
			),
		),
		dmc.Modal(
			id="notes-modal",
			title="Notes",
			size=520,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					dmc.Textarea(
						id="notes-textarea",
						placeholder="No notes",
						autosize=True,
						minRows=6,
						className="deh-field",
					),
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button("Cancel", id="notes-cancel", className="deh-btn deh-btn-ghost"),
						html.Button("Save", id="notes-save", className="deh-btn deh-btn-primary"),
					],
					className="deh-dialog-foot",
				),
			],
		),
		dmc.Modal(
			id="animal-modal",
			title="",
			size=420,
			classNames=_DIALOG_CLASSES,
			children=html.Div(id="animal-modal-body", className="deh-dialog-body"),
		),
	]
)


def _human(value: str) -> str:
	return str(value).replace("_", " ")


def _placeholder(message: str) -> html.Div:
	return html.Div(
		[icon("info-circle", size=20), html.P(message)],
		className="deh-alert deh-alert-info",
		style={"maxWidth": "560px", "margin": "48px auto"},
	)


def _reads(tables: tuple[str, ...]) -> list:
	children = ["reads "]
	for index, table in enumerate(tables):
		if index:
			children.append(" ")
		children.append(html.Code(table))
	return children


def _available_attributes(context: PlotContext) -> list[str]:
	return available_attributes(context) if "animals" in context else ["animal_id"]


def _quality_badge(miss: float) -> html.Span:
	if miss < 1:
		kind, glyph, label = "good", "circle-check", "Good"
	elif miss < 2.5:
		kind, glyph, label = "warn", "alert-triangle", "Check"
	else:
		kind, glyph, label = "bad", "circle-x", "Poor"
	return html.Span([icon(glyph, size=14), label], className=f"deh-badge deh-badge-{kind}")


def _meta_strip(summary: dict) -> list:
	start = dt.datetime.fromisoformat(summary["start"])
	end = dt.datetime.fromisoformat(summary["end"])
	items = [
		html.Span(
			[icon("calendar", size=15), f"{start.day} {start:%b} → {end.day} {end:%b %Y}"],
			title=summary["timezone"],
		),
		html.Span(
			[
				icon("clock", size=15),
				f"{summary['days']} days · {summary['phases']} phases, "
				f"from {_human(summary['start_from'])}",
			]
		),
		html.Span([icon("users", size=15), f"{summary['n_mice']} mice"]),
		html.Span(
			[icon("grid-dots", size=15), f"{summary['cages']} cages · {summary['tunnels']} tunnels"]
		),
		html.Span(
			[icon("bolt", size=15), f"{len(summary['events'])} events"],
			title=", ".join(summary["events"]) or "No events",
		),
	]
	quality = summary["quality"]
	if quality is not None:
		items.append(
			html.Button(
				[f"{quality['miss']:.2f}% missed ", _quality_badge(quality["miss"])],
				id="rec-quality-jump",
				className="deh-btn deh-btn-ghost sm",
				title=(
					f"Worst antenna {quality['worst_antenna']['antenna']}: "
					f"{quality['worst_antenna']['miss']:.2f}% missed"
				),
			)
		)
	items.append(
		html.Button(
			[icon("notes", size=15), "Notes"],
			id="rec-notes-btn",
			className="deh-btn deh-btn-ghost sm",
		)
	)
	return items


def _download_menu(pid: str, name: str, tables: list[str]) -> dmc.Menu:
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
				html.Button([icon("download", size=16), "Download"], className="deh-btn sm")
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
					*([dmc.MenuDivider(), dmc.MenuLabel("One table · parquet")] if tables else []),
					*(
						dmc.MenuItem(
							html.Code(table),
							leftSection=icon("table", size=16),
							href=f"{base}/table/{table}.parquet",
							target="_blank",
						)
						for table in tables
					),
				]
			),
		],
		position="bottom-end",
		classNames={"dropdown": "deh-menu deh-menu-scroll"},
	)


def _window_marks(lo: int, hi: int) -> list[dmc.RangeSlider.Marks]:
	step = 2 if hi - lo + 1 > 12 else 1
	return [
		{"value": v, "label": str(v)} for v in range(lo, hi + 1) if (v - lo) % step == 0 or v == hi
	]


def _clock(summary: dict, hour: int) -> str:
	base_h, base_m = (int(part) for part in summary["onsets"][summary["start_from"]].split(":"))
	total = (base_h * 60 + base_m + hour * 60) % 1440
	return f"{total // 60:02d}:{total % 60:02d}"


def _hours_marks(summary: dict) -> list[dmc.RangeSlider.Marks]:
	return [{"value": hour, "label": _clock(summary, hour)} for hour in (0, 6, 12, 18, 23)]


def _cohort_rows(context: PlotContext, color_by: str):
	mapping = resolve_colors(context, color_by)
	animals = context.animals.sort("animal_id")
	return mapping, animals


def _cohort_widgets(context: PlotContext, color_by: str) -> tuple[list, html.Div]:
	"""The cohort popover trigger's children and the popover body, for one colour attribute."""
	if "animals" not in context:
		empty = html.Div(html.P("Needs the animals table.", className="deh-sub"))
		return [f"Cohort · {len(context.animal_ids)}"], empty

	mapping, animals = _cohort_rows(context, color_by)
	strip = html.Span(
		[html.I(style={"background": mapping.by_animal[tag]}) for tag in context.animal_ids],
		className="deh-mini-strip",
	)
	rows = [
		html.Li(
			[
				html.Span(
					className="deh-dot", style={"background": mapping.by_animal[row["animal_id"]]}
				),
				html.Span(
					[
						html.Span(row["animal_id"], className="deh-mono"),
						html.Span(
							f" · {row['subject_name']} · {row['sex']} · {row['genotype']} · "
							f"{row['age'].days} d",
							className="deh-sub",
						),
					]
				),
			],
			id={"type": "animal-row", "scope": "popover", "tag": row["animal_id"]},
			n_clicks=0,
			style={"cursor": "pointer"},
			title="View notes",
		)
		for row in animals.iter_rows(named=True)
	]
	pop = html.Div(
		[
			html.P(["Colour follows ", html.B(_human(color_by)), "."], className="deh-sub"),
			html.Ul(rows, className="deh-cohort-list"),
		]
	)
	return [strip, f"Cohort · {len(context.animal_ids)}"], pop


def _option_control(plot: str, option) -> html.Div:
	control_id = {"type": "card-opt", "plot": plot, "option": option.name}
	label = _OPTION_LABELS.get(option.name, option.label)
	data = [{"value": str(choice), "label": _human(choice)} for choice in option.choices]
	control = (
		dmc.SegmentedControl(id=control_id, data=data, value=str(option.default), size="xs")
		if len(option.choices) <= 3
		else dmc.Select(
			id=control_id,
			data=data,
			value=str(option.default),
			size="xs",
			w=150,
			allowDeselect=False,
		)
	)
	return html.Div([html.Span(label, className="deh-opt-label"), control], className="deh-opt")


def _card_frame(
	children: list, span: int, rows: int, *, card_id: str | dict | None = None
) -> html.Article:
	attrs: dict[str, object] = {"data-span": str(span), "data-rows": str(rows)}
	if card_id is not None:
		attrs["id"] = card_id
	return html.Article(children, className="deh-card", **attrs)  # ty: ignore[invalid-argument-type]


def _plot_card(name: str, context: PlotContext, height: int) -> list:
	spec = PlotRegistry.spec(name)
	header = html.Div(
		[
			html.Div([html.H3(spec.title), html.P(spec.summary)], className="deh-card-titles"),
			html.Span(id={"type": "badge", "plot": name}, className="deh-card-badge"),
			html.Div(
				[
					html.Button(
						icon("download", size=16),
						id={"type": "card-export", "plot": name},
						className="deh-icon-btn sm",
						title=f"Export {spec.title}",
					),
					html.Button(
						icon("maximize", size=15),
						id={"type": "card-fullscreen", "plot": name},
						className="deh-icon-btn sm",
						title=f"Open {spec.title} full screen",
					),
				],
				className="deh-card-actions",
			),
		],
		className="deh-card-head",
	)

	missing = [table for table in spec.requires if table not in context]
	if missing:
		body = html.Div(
			[
				icon("database", size=22),
				html.Div(
					[
						html.B(["Needs ", *_reads(tuple(missing))[1:]]),
						html.P("Run analysis for this recording to build it."),
					]
				),
			],
			className="deh-missing-body",
		)
		return [header, body, html.Footer(_reads(spec.requires), className="deh-card-foot")]

	options = [option for option in spec.options if option.name not in _GLOBAL_OPTIONS]
	return [
		header,
		html.Div([_option_control(name, option) for option in options], className="deh-card-opts")
		if options
		else None,
		dcc.Loading(
			dcc.Graph(
				id={"type": "plot", "plot": name},
				figure={},
				config={"displayModeBar": False, "responsive": True},
				className="deh-plot",
				style={"height": f"{height}px"} if height else {},
			),
			custom_spinner=icon("loader-2", size=28, class_name="deh-spin"),
			delay_show=200,
		),
		html.Footer(_reads(spec.requires), className="deh-card-foot"),
	]


def _quality_summary_children(context: PlotContext) -> list:
	header = html.Div(
		html.Div(
			[
				html.H3("Detection quality"),
				html.P(
					"Passes the antennas should have caught but did not. An animal that turns up "
					"at an antenna the layout does not join to its previous one crossed antennas "
					"that never fired."
				),
			],
			className="deh-card-titles",
		),
		className="deh-card-head",
	)
	if "recording_quality" not in context:
		body = html.Div(
			[
				icon("database", size=22),
				html.Div(html.B(["Needs ", html.Code("recording_quality")])),
			],
			className="deh-missing-body",
		)
		return [header, body]

	q = services.quality_summary(context)
	tiles = [
		("Missed passes", f"{q['miss']:.2f}%", _quality_badge(q["miss"])),
		(
			"Detections",
			f"{q['detected']:,}",
			html.Span(f"{q['missed']:,} missed", className="deh-sub"),
		),
		(
			"Worst antenna",
			f"Antenna {q['worst_antenna']['antenna']}",
			html.Span(f"{q['worst_antenna']['miss']:.2f}% missed", className="deh-sub"),
		),
		(
			"Worst animal",
			q["worst_animal"]["animal_id"],
			html.Span(f"{q['worst_animal']['miss']:.2f}% missed", className="deh-sub"),
		),
		(
			"Animal x antenna pairs without a miss",
			f"{q['clean_cells']} of {q['cells']}",
			html.Span(f"{q['antennas']} antennas", className="deh-sub"),
		),
	]
	body = html.Div(
		[
			html.Div(
				[
					html.Span(label, className="deh-tile-label"),
					html.Span(value, className="deh-tile-value"),
					aside,
				],
				className="deh-tile",
			)
			for label, value, aside in tiles
		],
		className="deh-tiles",
	)
	note = html.P(
		"Proposed bands, to confirm on more recordings: under 1% good, 1-2.5% check, 2.5% and "
		"over poor.",
		className="deh-q-note",
	)
	return [header, body, note]


def _card(cell: tuple, context: PlotContext, color_by: str) -> html.Article:
	name, span, height, *rest = cell
	rows = rest[0] if rest else 1
	if name == "cohort":
		# Baked in now rather than left for a reactive callback to fill on mount: a
		# MATCH-only-Output callback (no pattern-matched Input of its own) does not
		# reliably fire for a card that has never existed before, such as one behind an
		# inactive Tabs(keepMounted=False) panel.
		children = _cohort_card_children(context, color_by)
		return _card_frame(children, span, rows, card_id="cohort-card")
	if name == "quality-summary":
		return _card_frame(_quality_summary_children(context), span, rows)
	return _card_frame(_plot_card(name, context, height), span, rows)


def _controls_bar(summary: dict, controls: dict, context: PlotContext) -> html.Div:
	bound = summary["days"] if controls["granularity"] == "day" else summary["phases"]
	attrs = _available_attributes(context)
	color_by = controls["color_by"] if controls["color_by"] in attrs else "animal_id"
	cohort_children, cohort_pop = _cohort_widgets(context, color_by)

	return html.Div(
		[
			html.Div(
				[
					html.Span("Window", className="deh-ctl-label"),
					dmc.SegmentedControl(
						id="rec-granularity",
						data=[
							{"value": "day", "label": "Days"},
							{"value": "phase_count", "label": "Phases"},
						],
						value=controls["granularity"],
						size="xs",
					),
				],
				className="deh-ctl",
			),
			html.Div(
				dmc.RangeSlider(
					id="rec-window",
					min=1,
					max=bound,
					step=1,
					value=controls["window"],
					marks=_window_marks(1, bound),
					minRange=0,
					size="sm",
				),
				style={"flex": "1 1 260px", "minWidth": "220px"},
			),
			html.Div(
				dmc.RangeSlider(
					id="rec-hours",
					min=0,
					max=23,
					step=1,
					value=controls["hours"],
					marks=_hours_marks(summary),
					minRange=0,
					size="sm",
				),
				style={"flex": "1 1 260px", "minWidth": "220px"},
			),
			html.Div(
				[
					html.Span("Phases", className="deh-ctl-label"),
					dmc.ChipGroup(
						[
							dmc.Chip(
								[icon("sun", size=14), "Light"], value="light_phase", size="xs"
							),
							dmc.Chip(
								[icon("moon", size=14), "Dark"], value="dark_phase", size="xs"
							),
						],
						id="rec-phases",
						multiple=True,
						value=controls["phases"],
					),
				],
				className="deh-ctl",
			),
			html.Div(
				[
					html.Span("Animals by", className="deh-ctl-label"),
					dmc.Select(
						id="rec-animals-by",
						data=[{"value": a, "label": _human(a)} for a in attrs],
						value=color_by,
						size="xs",
						w=150,
						allowDeselect=False,
					),
				],
				className="deh-ctl",
			),
			dmc.Popover(
				[
					dmc.PopoverTarget(
						html.Button(cohort_children, id="rec-cohort-btn", className="deh-btn sm")
					),
					dmc.PopoverDropdown(html.Div(cohort_pop, id="rec-cohort-pop")),
				],
				position="bottom-end",
				width=320,
				classNames={"dropdown": "deh-menu"},
			),
		],
		className="deh-controls",
	)


def _dashboard(
	pid: str,
	names: list[str],
	name: str,
	summary: dict,
	context: PlotContext,
	controls: dict,
	tab: str,
) -> list:
	header = html.Div(
		[
			html.Div(
				[
					html.Button(
						icon("chevron-left", size=16),
						id="rec-prev",
						className="deh-icon-btn",
						title="Previous recording",
						disabled=len(names) < 2,
					),
					dmc.Select(
						id="rec-select",
						data=[{"value": n, "label": n} for n in names],
						value=name,
						size="sm",
						w=280,
						allowDeselect=False,
						searchable=True,
						classNames={"input": "deh-mono"},
					),
					html.Button(
						icon("chevron-right", size=16),
						id="rec-next",
						className="deh-icon-btn",
						title="Next recording",
						disabled=len(names) < 2,
					),
				],
				className="deh-rec-pick",
			),
			html.Div(_meta_strip(summary), className="deh-rec-meta"),
			html.Span(className="deh-grow"),
			_download_menu(
				pid,
				name,
				[table for table in DataFrameRegistry.list_available() if table in context],
			),
		],
		className="deh-rec-head",
	)
	tabs = dmc.Tabs(
		[
			dmc.TabsList(
				[dmc.TabsTab(label, value=section_id) for section_id, label, _ in _SECTIONS]
			),
			*(
				dmc.TabsPanel(
					html.Div(
						[_card(cell, context, controls["color_by"]) for cell in cells],
						className="deh-cards",
					),
					value=section_id,
				)
				for section_id, _, cells in _SECTIONS
			),
		],
		id="rec-tabs",
		value=tab,
		keepMounted=False,
		className="deh-tabs-gap",
	)
	return [header, _controls_bar(summary, controls, context), tabs]


@callback(
	Output("rec-body", "children"),
	Output("rec-context", "data"),
	Output("rec-controls", "data", allow_duplicate=True),
	Output("rec-notes", "data"),
	Input("url", "search"),
	State("project-paths", "data"),
	State("rec-context", "data"),
	prevent_initial_call="initial_duplicate",
)
def _resolve(search, paths, current):
	params = parse_qs((search or "").lstrip("?"))
	pid = (params.get("project") or [None])[0]
	requested = (params.get("recording") or [None])[0]
	tab = (params.get("tab") or ["overview"])[0]
	tab = tab if tab in _TAB_IDS else "overview"

	if not pid:
		return (
			_placeholder("Open a recording from a project to see its dashboard here."),
			None,
			no_update,
			no_update,
		)

	location = services.resolve_project(paths, pid)
	if location is None:
		message = "This project is not in your browser's saved list. Open it from Projects."
		return _placeholder(message), None, no_update, no_update

	try:
		project = services.load_project(location)
	except Exception as exc:
		return _placeholder(f"{type(exc).__name__}: {exc}"), None, no_update, no_update

	names = [recording.name for recording in project.recordings]
	if not names:
		return (
			_placeholder(f"{project.project_name} has no recordings yet."),
			None,
			no_update,
			no_update,
		)

	name = requested if requested in names else names[0]

	if current and (current.get("location"), current.get("recording")) == (location, name):
		raise PreventUpdate

	try:
		summary = services.recording_summary(location, name)
		context = services.plot_context(location, name)
	except Exception as exc:
		return _placeholder(f"{type(exc).__name__}: {exc}"), None, no_update, no_update

	controls = {
		"window": [1, summary["days"]],
		"granularity": "day",
		"hours": [0, 23],
		"phases": list(PHASES),
		"color_by": "animal_id",
	}
	body = _dashboard(pid, names, name, summary, context, controls, tab)
	return body, {"location": location, "recording": name}, controls, summary["notes"]


def _merge_search(search: str, **updates: str) -> str:
	params = {key: values[0] for key, values in parse_qs((search or "").lstrip("?")).items()}
	params.update(updates)
	return "?" + urlencode(params, quote_via=quote)


@callback(
	Output("url", "search", allow_duplicate=True),
	Input("rec-select", "value"),
	Input("rec-prev", "n_clicks"),
	Input("rec-next", "n_clicks"),
	State("rec-context", "data"),
	State("url", "search"),
	prevent_initial_call=True,
)
def _switch_recording(selected, _prev, _next, context_data, search):
	# All three inputs are rebuilt into rec-body on every recording switch, so they fire this
	# once with no click and no trigger behind them (see _notes_modal). Unguarded, that lands
	# in the step branch as step -1 and walks to the previous recording on its own, which
	# rebuilds the body and fires it again.
	if not context_data or not ctx.triggered[0]["value"]:
		raise PreventUpdate

	location = context_data["location"]
	names = [recording.name for recording in services.load_project(location).recordings]
	current = context_data["recording"]

	if ctx.triggered_id == "rec-select":
		name = selected
	else:
		step = 1 if ctx.triggered_id == "rec-next" else -1
		name = names[(names.index(current) + step) % len(names)]

	if name == current:
		raise PreventUpdate

	return _merge_search(search, recording=name)


@callback(
	Output("url", "search", allow_duplicate=True),
	Input("rec-tabs", "value"),
	State("url", "search"),
	prevent_initial_call=True,
)
def _switch_tab(tab, search):
	if (parse_qs((search or "").lstrip("?")).get("tab") or [None])[0] == tab:
		raise PreventUpdate
	return _merge_search(search, tab=tab)


@callback(
	Output("rec-window", "min"),
	Output("rec-window", "max"),
	Output("rec-window", "marks"),
	Output("rec-window", "value"),
	Output("rec-controls", "data", allow_duplicate=True),
	Input("rec-granularity", "value"),
	Input("rec-window", "value"),
	State("rec-context", "data"),
	State("rec-controls", "data"),
	prevent_initial_call=True,
)
def _window_control(granularity, window, context_data, controls):
	if not context_data:
		raise PreventUpdate

	summary = services.recording_summary(context_data["location"], context_data["recording"])
	bound = summary["days"] if granularity == "day" else summary["phases"]
	value = [1, bound] if ctx.triggered_id == "rec-granularity" else window
	merged = {**(controls or {}), "granularity": granularity, "window": value}
	return 1, bound, _window_marks(1, bound), value, merged


@callback(
	Output("rec-controls", "data", allow_duplicate=True),
	Input("rec-hours", "value"),
	Input("rec-phases", "value"),
	Input("rec-animals-by", "value"),
	State("rec-controls", "data"),
	prevent_initial_call=True,
)
def _filter_controls(hours, phases, color_by, controls):
	return {**(controls or {}), "hours": hours, "phases": phases or [], "color_by": color_by}


@callback(
	Output("rec-cohort-btn", "children"),
	Output("rec-cohort-pop", "children"),
	Input("rec-context", "data"),
	Input("rec-controls", "data"),
	prevent_initial_call=True,
)
def _update_cohort_widgets(context_data, controls):
	if not context_data or not controls:
		raise PreventUpdate
	context = services.plot_context(context_data["location"], context_data["recording"])
	return _cohort_widgets(context, controls.get("color_by", "animal_id"))


@callback(
	Output("cohort-card", "children"),
	Input("rec-context", "data"),
	Input("rec-controls", "data"),
	prevent_initial_call=True,
)
def _update_cohort_card(context_data, controls):
	if not context_data or not controls:
		raise PreventUpdate
	context = services.plot_context(context_data["location"], context_data["recording"])
	return _cohort_card_children(context, controls.get("color_by", "animal_id"))


def _cohort_card_children(context: PlotContext, color_by: str) -> list:
	header = html.Div(
		html.Div(
			[
				html.H3("Cohort"),
				html.P(
					[
						f"{len(context.animal_ids)} animals. Colour follows ",
						html.B(_human(color_by)),
						" on every plot here.",
					]
				),
			],
			className="deh-card-titles",
		),
		className="deh-card-head",
	)
	if "animals" not in context:
		body = html.Div(
			[icon("database", size=22), html.Div(html.B(["Needs ", html.Code("animals")]))],
			className="deh-missing-body",
		)
		return [header, body]

	mapping, animals = _cohort_rows(context, color_by)
	table = html.Table(
		[
			html.Thead(
				html.Tr(
					[
						html.Th(""),
						html.Th("Tag"),
						html.Th("Subject"),
						html.Th("Sex"),
						html.Th("Genotype"),
						html.Th("Mouse line"),
						html.Th("Genetic background"),
						html.Th("Treatment"),
						html.Th("Age", className="num"),
					]
				)
			),
			html.Tbody(
				[
					html.Tr(
						[
							html.Td(
								html.Span(
									className="deh-dot",
									style={"background": mapping.by_animal[row["animal_id"]]},
								)
							),
							html.Td(row["animal_id"], className="deh-mono"),
							html.Td(row["subject_name"]),
							html.Td(row["sex"]),
							html.Td(row["genotype"]),
							html.Td(row["mouse_line"]),
							html.Td(row["genetic_background"]),
							html.Td(row["treatment"]),
							html.Td(f"{row['age'].days} d", className="num"),
						],
						id={"type": "animal-row", "scope": "table", "tag": row["animal_id"]},
						n_clicks=0,
						style={"cursor": "pointer"},
						title="View notes",
					)
					for row in animals.iter_rows(named=True)
				]
			),
		],
		className="deh-tbl mini",
	)
	return [
		header,
		html.Div(table, className="deh-cohort-table"),
		html.Footer(_reads(("animals",)), className="deh-card-foot"),
	]


@callback(
	Output({"type": "plot", "plot": MATCH}, "figure"),
	Output({"type": "badge", "plot": MATCH}, "children"),
	Input("rec-context", "data"),
	Input("rec-controls", "data"),
	Input({"type": "card-opt", "plot": MATCH, "option": ALL}, "value"),
	Input("theme-store", "data"),
	State({"type": "card-opt", "plot": MATCH, "option": ALL}, "id"),
)
def _update_plot(context_data, controls, opt_values, theme, opt_ids):
	if not context_data or not controls:
		raise PreventUpdate

	name = ctx.outputs_list[0]["id"]["plot"]
	context = services.plot_context(context_data["location"], context_data["recording"])
	spec = PlotRegistry.spec(name)
	if any(table not in context for table in spec.requires):
		raise PreventUpdate

	accepted = {option.name for option in spec.options}
	values = {opt_id["option"]: value for opt_id, value in zip(opt_ids, opt_values, strict=True)}
	values.update(
		days_range=controls["window"],
		granularity=controls["granularity"],
		phase_type=controls["phases"],
		color_by=controls["color_by"],
		order_by=controls["color_by"],
		# None for the untouched full day, matching every builder's own default: some
		# prepare.* steps aggregate away the hour column before applying this filter and
		# only skip that filter when it is exactly None (e.g. prep_polar_df).
		hours_range=None if list(controls["hours"]) == [0, 23] else controls["hours"],
	)
	values = {key: value for key, value in values.items() if key in accepted}

	figure = PlotRegistry.build(name, context, **values)
	# The card header already carries the title; the figure's own would double it up.
	# Plotly still reserves top margin for it, so that's trimmed back too.
	figure.update_layout(title=None, margin={"t": 30}, template=theme or "light")

	whole_day = "hours_range" not in accepted and list(controls["hours"]) != [0, 23]
	badge = (
		html.Span(
			[icon("clock", size=14), "Whole day"],
			className="deh-badge deh-badge-neutral",
			title="This card has no hourly breakdown; the hours window does not apply to it.",
		)
		if whole_day
		else None
	)
	return figure, badge


@callback(
	Output("fullscreen-modal", "opened"),
	Output("fullscreen-modal", "title"),
	Output("fullscreen-plot", "figure"),
	Input({"type": "card-fullscreen", "plot": ALL}, "n_clicks"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	prevent_initial_call=True,
)
def _fullscreen(_clicks, figures, ids):
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	name = ctx.triggered_id["plot"]
	figure = next((f for f, i in zip(figures, ids, strict=True) if i["plot"] == name), None)
	if figure is None:
		raise PreventUpdate
	return True, PlotRegistry.spec(name).title, figure


@callback(
	Output("export-dialog", "opened", allow_duplicate=True),
	Output("export-source", "data", allow_duplicate=True),
	Output("export-filename", "value", allow_duplicate=True),
	Input({"type": "card-export", "plot": ALL}, "n_clicks"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State("rec-context", "data"),
	prevent_initial_call=True,
)
def _open_export(_clicks, figures, ids, rec_context):
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	name = ctx.triggered_id["plot"]
	figure = next((f for f, i in zip(figures, ids, strict=True) if i["plot"] == name), None)
	if not figure:
		raise PreventUpdate
	recording = (rec_context or {}).get("recording", "recording")
	filename = f"{recording}__{name}".lower().replace(" ", "-")
	return True, {"figure": figure, "title": PlotRegistry.spec(name).title}, filename


@callback(
	Output("notes-modal", "opened"),
	Output("notes-textarea", "value"),
	Output("rec-notes", "data", allow_duplicate=True),
	Input("rec-notes-btn", "n_clicks"),
	Input("notes-cancel", "n_clicks"),
	Input("notes-save", "n_clicks"),
	State("notes-textarea", "value"),
	State("rec-context", "data"),
	State("rec-notes", "data"),
	prevent_initial_call=True,
)
def _notes_modal(_open, _cancel, _save, text, context_data, notes):
	# rec-notes-btn is rebuilt into rec-body on every recording switch, and notes-cancel /
	# notes-save live in the page's static layout, which mounts fresh whenever this page is
	# routed to - both cases fire this callback once with no real click behind them.
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	if ctx.triggered_id == "rec-notes-btn":
		return True, notes or "", no_update
	if ctx.triggered_id == "notes-cancel":
		return False, no_update, no_update

	if not context_data:
		raise PreventUpdate
	text = (text or "").strip()
	services.update_notes(context_data["location"], context_data["recording"], text)
	notify("good", "Notes saved")
	return False, no_update, text


@callback(
	Output("animal-modal", "opened"),
	Output("animal-modal", "title"),
	Output("animal-modal-body", "children"),
	Input({"type": "animal-row", "scope": ALL, "tag": ALL}, "n_clicks"),
	State("rec-context", "data"),
	prevent_initial_call=True,
)
def _animal_modal(_clicks, context_data):
	if not context_data or not ctx.triggered[0]["value"]:
		raise PreventUpdate
	tag = ctx.triggered_id["tag"]
	context = services.plot_context(context_data["location"], context_data["recording"])
	animal = next(row for row in context.animals.iter_rows(named=True) if row["animal_id"] == tag)
	body = html.P(animal["notes"] or "No notes", className="deh-notes")
	return True, f"{animal['subject_name']} · {tag}", body
