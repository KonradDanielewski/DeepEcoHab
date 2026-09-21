import datetime as dt
from urllib.parse import parse_qs, quote, urlencode

import dash
import dash_mantine_components as dmc
from dash import (
	ALL,
	MATCH,
	ClientsideFunction,
	Input,
	Output,
	State,
	callback,
	clientside_callback,
	ctx,
	dcc,
	html,
	no_update,
)
from dash.exceptions import PreventUpdate

from deepecohab.app import components, services
from deepecohab.app.components import icon, notify
from deepecohab.core.data_model import DataFrameRegistry
from deepecohab.plotting import PlotContext, PlotRegistry, available_attributes
from deepecohab.plotting.animals import resolve_colors
from deepecohab.plotting.theme import COLORSCALES, PALETTES

PATH = "/recording"

dash.register_page(
	__name__, path=PATH, name="Recording dashboard", order=1, icon="layout-dashboard"
)

PHASES = ("light_phase", "dark_phase")
#: Driven by the control bar rather than a per-card control.
_GLOBAL_OPTIONS = {
	"days_range",
	"granularity",
	"phase_type",
	"color_by",
	"order_by",
	"hours_range",
	"group_mean",
}
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
			("quality-missing", 12, 0),
		],
	),
	(
		"activity",
		"Activity",
		[
			("recording-timeline", 12, 340),
			("activity-line", 8, 340),
			("cage-preference", 4, 340),
			("activity-bar", 12, 320),
			("time-per-cage-heatmap", 7, 660),
			("cage-preference-evolution", 5, 660),
		],
	),
	(
		"social",
		"Social",
		[
			("sociability-heatmap", 6, 880, 2),
			("network-sociability", 6, 384),
			("cohort-heatmap", 6, 384),
			("time-alone-bar", 8, 384),
			("social-stability", 4, 384),
		],
	),
	(
		"dominance",
		"Dominance",
		[
			("ranking-line", 12, 360),
			("ranking-distribution-line", 6, 360),
			("chasings-line", 6, 360),
			("network-dominance", 6, 548),
			("chasings-heatmap", 6, 548),
		],
	),
]
_TAB_IDS = {section_id for section_id, *_ in _SECTIONS}


layout = html.Div(
	[
		dcc.Store(id="rec-context"),
		dcc.Store(id="rec-controls"),
		# rec-tabs is built into rec-body, so a callback that also takes an input from this
		# static layout would be dispatched before it exists ("a nonexistent object was used
		# in an Input"). switchTab mirrors the tab here, where plotRequest can always see it.
		dcc.Store(id="rec-tab"),
		# What the cohort cards were drawn for: _dashboard bakes them for animal_id.
		dcc.Store(id="rec-color-by", data="animal_id"),
		dcc.Store(id="notes-target"),
		dcc.Store(id="rec-format", storage_type="session"),
		dcc.Store(id="rec-format-target"),
		dcc.Store(id="rec-colors", data={"colorscale": COLORSCALES, "palette": PALETTES}),
		components.format_dialog(
			"rec", "Empty means automatic. Applies to this plot on every recording."
		),
		html.Div(id="rec-body"),
		dmc.Modal(
			id="fullscreen-modal",
			title="",
			fullScreen=True,
			classNames=components.DIALOG_CLASSES,
			children=dcc.Graph(
				id="fullscreen-plot",
				figure=components.EMPTY_FIGURE,
				config={"displayModeBar": False},
				style={"height": "calc(100vh - 120px)"},
			),
		),
		dmc.Modal(
			id="notes-modal",
			title="Notes",
			size=520,
			classNames=components.DIALOG_CLASSES,
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
	]
)


def _human(value: str) -> str:
	return str(value).replace("_", " ")


def _reads(tables: tuple[str, ...]) -> list:
	children = ["reads "]
	for index, table in enumerate(tables):
		if index:
			children.append(" ")
		children.append(html.Code(table))
	return children


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


def _cohort_widgets(context: PlotContext, color_by: str) -> tuple[list, html.Div]:
	"""The cohort popover trigger's children and the popover body, for one colour attribute."""
	if "animals" not in context:
		empty = html.Div(html.P("Needs the animals table.", className="deh-sub"))
		return [f"Cohort · {len(context.animal_ids)}"], empty

	mapping, animals = resolve_colors(context, color_by), context.animals.sort("animal_id")
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
			title="Edit notes",
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


def _plot_card(name: str, context: PlotContext, height: int, tab: str) -> list:
	spec = PlotRegistry.spec(name)
	header = html.Div(
		[
			html.Div(
				[
					html.H3(spec.title, id={"type": "card-title", "plot": name}),
					html.P(spec.summary),
				],
				className="deh-card-titles",
			),
			html.Span(id={"type": "badge", "plot": name}, className="deh-card-badge"),
			html.Div(
				[
					html.Button(
						icon("adjustments-horizontal", size=15),
						id={"type": "card-format", "plot": name},
						className="deh-icon-btn sm",
						title=f"Format {spec.title}",
					),
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
		dcc.Store(id={"type": "plot-req", "plot": name}, data={"tab": tab}),
		dcc.Loading(
			dcc.Graph(
				id={"type": "plot", "plot": name},
				figure=components.EMPTY_FIGURE,
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

	quality = services.quality_summary(context)
	tiles = [
		("Missed passes", f"{quality['miss']:.2f}%", _quality_badge(quality["miss"])),
		(
			"Detections",
			f"{quality['detected']:,}",
			html.Span(f"{quality['missed']:,} missed", className="deh-sub"),
		),
		(
			"Worst antenna",
			f"Antenna {quality['worst_antenna']['antenna']}",
			html.Span(f"{quality['worst_antenna']['miss']:.2f}% missed", className="deh-sub"),
		),
		(
			"Worst animal",
			quality["worst_animal"]["animal_id"],
			html.Span(f"{quality['worst_animal']['miss']:.2f}% missed", className="deh-sub"),
		),
		(
			"Animal x antenna pairs without a miss",
			f"{quality['clean_cells']} of {quality['cells']}",
			html.Span(f"{quality['antennas']} antennas", className="deh-sub"),
		),
	]
	if "activity_df" in context and "phase_durations" in context:
		missing = services.missing_time(context)
		worst = missing["rows"][0]
		tiles.append(
			(
				"Position unknown",
				f"{missing['mean_share']:.2f}%",
				html.Span(
					f"Worst: {worst['animal_id']} {worst['share']:.2f}%", className="deh-sub"
				),
			)
		)
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


def _quality_missing_children(context: PlotContext, color_by: str) -> list:
	header = html.Div(
		html.Div(
			[
				html.H3("Position unknown"),
				html.P("Time each animal spent at a position antennas could not resolve."),
			],
			className="deh-card-titles",
		),
		className="deh-card-head",
	)
	needed = ("activity_df", "phase_durations")
	missing = [table for table in needed if table not in context]
	if missing:
		body = html.Div(
			[icon("database", size=22), html.Div(html.B(["Needs ", *_reads(tuple(missing))[1:]]))],
			className="deh-missing-body",
		)
		return [header, body, html.Footer(_reads(needed), className="deh-card-foot")]

	result = services.missing_time(context)
	subjects = (
		{row["animal_id"]: row["subject_name"] for row in context.animals.iter_rows(named=True)}
		if "animals" in context
		else {}
	)
	colors = resolve_colors(context, color_by).by_animal
	rows = [
		html.Tr(
			[
				html.Td(
					html.Span(className="deh-dot", style={"background": colors[row["animal_id"]]})
				),
				html.Td(row["animal_id"], className="deh-mono"),
				html.Td(subjects.get(row["animal_id"], "—")),
				html.Td(row["time_in_position_text"]),
				html.Td(f"{row['share']:.2f}%", className="num"),
			]
		)
		for row in result["rows"]
	]
	rows.append(
		html.Tr(
			[
				html.Td("Cohort mean", colSpan=4),
				html.Td(f"{result['mean_share']:.2f}%", className="num"),
			]
		)
	)
	table = html.Table(
		[
			html.Thead(
				html.Tr(
					[
						html.Th(""),
						html.Th("Tag"),
						html.Th("Subject"),
						html.Th("Time unknown"),
						html.Th("% of recording", className="num"),
					]
				)
			),
			html.Tbody(rows),
		],
		className="deh-tbl mini",
	)
	return [
		header,
		html.Div(table, className="deh-cohort-table"),
		html.Footer(_reads(needed), className="deh-card-foot"),
	]


def _card(cell: tuple, context: PlotContext, color_by: str, tab: str) -> html.Article:
	name, span, height, *rest = cell
	rows = rest[0] if rest else 1
	if name == "cohort":
		# Baked in now rather than left for a reactive callback to fill on mount, so the
		# card is right from its first paint.
		children = _cohort_card_children(context, color_by)
		return _card_frame(children, span, rows, card_id="cohort-card")
	if name == "quality-summary":
		return _card_frame(_quality_summary_children(context), span, rows)
	if name == "quality-missing":
		children = _quality_missing_children(context, color_by)
		return _card_frame(children, span, rows, card_id="quality-missing-card")
	return _card_frame(_plot_card(name, context, height, tab), span, rows)


def _controls_bar(summary: dict, controls: dict, context: PlotContext) -> html.Div:
	bound = summary["days"] if controls["granularity"] == "day" else summary["phases"]
	attrs = available_attributes(context) if "animals" in context else ["animal_id"]
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
			dmc.Switch(
				id="rec-group-mean",
				label="Group mean",
				checked=controls.get("group_mean", False),
				disabled=color_by in ("animal_id", "subject_name"),
				size="xs",
			),
			dmc.Switch(
				id="rec-events",
				label="Events",
				checked=True,
				disabled=not summary["events"],
				size="xs",
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
			components.download_menu(
				pid,
				name,
				html.Button([icon("download", size=16), "Download"], className="deh-btn sm"),
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
						[_card(cell, context, controls["color_by"], section_id) for cell in cells],
						className="deh-cards",
					),
					value=section_id,
				)
				for section_id, _, cells in _SECTIONS
			),
		],
		id="rec-tabs",
		value=tab,
		# Dash 4 rebuilds a remounted panel from the layout its parent first rendered,
		# which drops every figure a callback has filled in since.
		keepMounted=True,
		className="deh-tabs-gap",
	)
	return [header, _controls_bar(summary, controls, context), tabs]


@callback(
	Output("rec-body", "children"),
	Output("rec-context", "data"),
	Output("rec-controls", "data", allow_duplicate=True),
	Input("url", "pathname"),
	Input("url", "search"),
	State("project-paths", "data"),
	State("rec-context", "data"),
	prevent_initial_call="initial_duplicate",
)
def _resolve(pathname, search, paths, current):
	if pathname != PATH:
		raise PreventUpdate

	params = parse_qs((search or "").lstrip("?"))
	pid = (params.get("project") or [None])[0]
	requested = (params.get("recording") or [None])[0]
	tab = (params.get("tab") or ["overview"])[0]
	tab = tab if tab in _TAB_IDS else "overview"

	if not pid:
		return (
			components.placeholder("Open a recording from a project to see its dashboard here."),
			None,
			no_update,
		)

	location = services.resolve_project(paths, pid)
	if location is None:
		message = "This project is not in your browser's saved list. Open it from Projects."
		return components.placeholder(message), None, no_update

	try:
		project = services.load_project(location)
	except Exception as exc:
		return components.placeholder(f"{type(exc).__name__}: {exc}"), None, no_update

	names = [recording.name for recording in project.recordings]
	if not names:
		return (
			components.placeholder(f"{project.project_name} has no recordings yet."),
			None,
			no_update,
		)

	name = requested if requested in names else names[0]
	# A string: nanosecond mtimes lose precision as JSON numbers in the browser.
	stamp = str(services.results_stamp(location, name))

	identity = {"location": location, "recording": name, "stamp": stamp}
	if current and all(current.get(key) == value for key, value in identity.items()):
		raise PreventUpdate

	try:
		summary = services.recording_summary(location, name)
		context = services.plot_context(location, name)
	except Exception as exc:
		return components.placeholder(f"{type(exc).__name__}: {exc}"), None, no_update

	controls = {
		"window": [1, summary["days"]],
		"granularity": "day",
		"hours": [0, 23],
		"phases": list(PHASES),
		"color_by": "animal_id",
		"group_mean": False,
	}
	body = _dashboard(pid, names, name, summary, context, controls, tab)
	# days/phases ride along so the window slider can re-axis itself clientside.
	context_data = {**identity, "days": summary["days"], "phases": summary["phases"]}
	return body, context_data, controls


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


clientside_callback(
	ClientsideFunction("deh", "switchTab"),
	Output("url", "search", allow_duplicate=True),
	Output("rec-tab", "data"),
	Input("rec-tabs", "value"),
	State("url", "search"),
	prevent_initial_call=True,
)


clientside_callback(
	ClientsideFunction("deh", "windowControl"),
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


clientside_callback(
	ClientsideFunction("deh", "filterControls"),
	Output("rec-controls", "data", allow_duplicate=True),
	Output("rec-group-mean", "disabled"),
	Input("rec-hours", "value"),
	Input("rec-phases", "value"),
	Input("rec-animals-by", "value"),
	Input("rec-group-mean", "checked"),
	State("rec-controls", "data"),
	prevent_initial_call=True,
)


clientside_callback(
	ClientsideFunction("deh", "toggleEvents"),
	Input("rec-events", "checked"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	prevent_initial_call=True,
)


clientside_callback(
	ClientsideFunction("deh", "colorBy"),
	Output("rec-color-by", "data"),
	Input("rec-controls", "data"),
	State("rec-color-by", "data"),
	prevent_initial_call=True,
)


@callback(
	Output("rec-cohort-btn", "children"),
	Output("rec-cohort-pop", "children"),
	Output("cohort-card", "children"),
	Output("quality-missing-card", "children"),
	Input("rec-color-by", "data"),
	State("rec-context", "data"),
	prevent_initial_call=True,
)
def _update_cohort(color_by, context_data):
	if not context_data:
		raise PreventUpdate
	context = services.plot_context(context_data["location"], context_data["recording"])
	return (
		*_cohort_widgets(context, color_by),
		_cohort_card_children(context, color_by),
		_quality_missing_children(context, color_by),
	)


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

	mapping, animals = resolve_colors(context, color_by), context.animals.sort("animal_id")
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
						title="Edit notes",
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


clientside_callback(
	ClientsideFunction("deh", "plotRequest"),
	Input("rec-context", "data"),
	Input("rec-controls", "data"),
	Input("rec-tab", "data"),
	Input("plot-theme", "data"),
	Input({"type": "card-opt", "plot": ALL, "option": ALL}, "value"),
	State({"type": "plot-req", "plot": ALL}, "data"),
)


@callback(
	Output({"type": "plot", "plot": MATCH}, "figure"),
	Output({"type": "badge", "plot": MATCH}, "children"),
	Input({"type": "plot-req", "plot": MATCH}, "data"),
	State("rec-events", "checked"),
	# The request mounts as {tab} alone; deh.plotRequest fills it once the tab shows.
	prevent_initial_call=True,
)
def _update_plot(request, events_on):
	if not request or "context" not in request:
		raise PreventUpdate

	context_data, controls, theme = request["context"], request["controls"], request["theme"]
	name = ctx.outputs_list[0]["id"]["plot"]
	context = services.plot_context(context_data["location"], context_data["recording"])
	spec = PlotRegistry.spec(name)
	if any(table not in context for table in spec.requires):
		raise PreventUpdate

	accepted = {option.name for option in spec.options}
	values = dict(request["opts"])
	values.update(
		days_range=controls["window"],
		granularity=controls["granularity"],
		phase_type=controls["phases"],
		color_by=controls["color_by"],
		order_by=controls["color_by"],
		group_mean=controls.get("group_mean", False),
		# None for the untouched full day, matching every builder's own default: some
		# prepare.* steps aggregate away the hour column before applying this filter and
		# only skip that filter when it is exactly None (e.g. prep_polar).
		hours_range=None if list(controls["hours"]) == [0, 23] else controls["hours"],
	)
	values = {key: value for key, value in values.items() if key in accepted}

	figure = PlotRegistry.build(name, context, **values)
	# The card header already carries the title; the figure's own would double it up.
	# Plotly still reserves top margin for it, so that's trimmed back too.
	figure.update_layout(title=None, margin={"t": 30}, template=theme or "light")
	if not events_on:
		# A newly mounted or rebuilt card starts respecting the toggle without being an
		# Input of its own; deh.toggleEvents keeps an already-loaded figure in sync.
		figure.update_shapes(visible=False, selector={"name": "event-span"})
		figure.update_annotations(visible=False, selector={"name": "event-label"})

	badges = []
	if "hours_range" not in accepted and list(controls["hours"]) != [0, 23]:
		badges.append(
			html.Span(
				[icon("clock", size=14), "Whole day"],
				className="deh-badge deh-badge-neutral",
				title="This card has no hourly breakdown; the hours window does not apply to it.",
			)
		)
	if controls.get("group_mean") and "color_by" in accepted and "group_mean" not in accepted:
		badges.append(
			html.Span(
				[icon("users", size=14), "Per animal"],
				className="deh-badge deh-badge-neutral",
				title="Group mean does not apply here; this card shows one line per animal.",
			)
		)
	return figure, badges or None


# Clientside: every figure on the tab is already in the browser, so picking one is not
# worth uploading them all to the server and sending one back.
clientside_callback(
	ClientsideFunction("deh", "fullscreen"),
	Output("fullscreen-modal", "opened"),
	Output("fullscreen-modal", "title"),
	Output("fullscreen-plot", "figure"),
	Input({"type": "card-fullscreen", "plot": ALL}, "n_clicks"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State({"type": "card-title", "plot": ALL}, "children"),
	State({"type": "card-title", "plot": ALL}, "id"),
	prevent_initial_call=True,
)


# Clientside for the same reason as the fullscreen callback above. The export-source store
# still feeds the server preview, so one figure goes up - not all of them.
clientside_callback(
	ClientsideFunction("deh", "openExport"),
	Output("export-dialog", "opened", allow_duplicate=True),
	Output("export-source", "data", allow_duplicate=True),
	Output("export-filename", "value", allow_duplicate=True),
	Input({"type": "card-export", "plot": ALL}, "n_clicks"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State({"type": "card-title", "plot": ALL}, "children"),
	State({"type": "card-title", "plot": ALL}, "id"),
	State("rec-context", "data"),
	prevent_initial_call=True,
)


# Format only rewrites layout the browser already holds, so none of it reaches the server.
clientside_callback(
	ClientsideFunction("deh", "openFormat"),
	Output("rec-format-modal", "opened"),
	Output("rec-format-modal", "title"),
	Output("rec-format-target", "data"),
	Output({"type": "rec-fmt", "key": ALL}, "value"),
	Output({"type": "rec-fmt", "key": ALL}, "placeholder"),
	Output({"type": "rec-fmt", "key": ALL}, "disabled"),
	Output({"type": "rec-fmt", "key": "palette"}, "data"),
	Input({"type": "card-format", "plot": ALL}, "n_clicks"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State({"type": "card-title", "plot": ALL}, "children"),
	State({"type": "card-title", "plot": ALL}, "id"),
	State("rec-format", "data"),
	State("rec-colors", "data"),
	prevent_initial_call=True,
)


clientside_callback(
	ClientsideFunction("deh", "editFormat"),
	Output("rec-format", "data"),
	Input({"type": "rec-fmt", "key": ALL}, "value"),
	Input("rec-fmt-reset", "n_clicks"),
	State("rec-format-target", "data"),
	State("rec-format", "data"),
	State({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State("rec-colors", "data"),
	prevent_initial_call=True,
)


clientside_callback(
	ClientsideFunction("deh", "applyFormat"),
	Input("rec-format", "data"),
	Input({"type": "plot", "plot": ALL}, "figure"),
	State({"type": "plot", "plot": ALL}, "id"),
	State("rec-colors", "data"),
	prevent_initial_call=True,
)


@callback(
	Output("notes-modal", "opened"),
	Output("notes-modal", "title"),
	Output("notes-textarea", "value"),
	Output("notes-target", "data"),
	Input("rec-notes-btn", "n_clicks"),
	Input({"type": "animal-row", "scope": ALL, "tag": ALL}, "n_clicks"),
	Input("notes-cancel", "n_clicks"),
	Input("notes-save", "n_clicks"),
	State("notes-textarea", "value"),
	State("rec-context", "data"),
	State("notes-target", "data"),
	prevent_initial_call=True,
)
def _notes_modal(_open, _rows, _cancel, _save, text, context_data, target):
	# rec-notes-btn and the animal rows are rebuilt into rec-body on every recording
	# switch, and notes-cancel / notes-save live in the page's static layout, which
	# mounts fresh whenever this page is routed to - all fire this callback once with
	# no real click behind them.
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	trigger = ctx.triggered_id
	if trigger == "notes-cancel":
		return False, no_update, no_update, no_update

	if not context_data:
		raise PreventUpdate
	location, name = context_data["location"], context_data["recording"]

	if trigger == "notes-save":
		if not target:
			raise PreventUpdate
		services.update_notes(location, name, (text or "").strip(), target.get("tag"))
		notify("good", "Notes saved")
		return False, no_update, no_update, no_update

	# Read fresh from disk rather than context.animals, the analysed parquet, which
	# would go stale the moment notes are saved without a re-analysis.
	recording = services.load_project(location)[name]
	if trigger == "rec-notes-btn":
		return True, "Notes", recording.notes, {"tag": None}

	tag = trigger["tag"]
	animal = next(a for a in recording.cohort.animals if a.tag == tag)
	return True, f"{animal.subject_name} · {tag}", animal.notes, {"tag": tag}
