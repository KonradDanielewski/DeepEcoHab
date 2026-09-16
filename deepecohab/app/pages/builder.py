"""Plot builder screen: drag-and-drop ad-hoc plotting over the project table."""

import copy
import time
from urllib.parse import parse_qs

import dash
import dash_mantine_components as dmc
import polars as pl
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from deepecohab.app import services
from deepecohab.app.builder import catalog, figure, presets as presets_mod
from deepecohab.app.components import icon, notify

dash.register_page(__name__, path="/builder", name="Plot builder", order=2, icon="drag-drop")

#: Pseudo-shelves: the palette takes chips back, the filter rail turns them into controls.
PALETTE, FILTERS = "__palette__", "__filters__"

KIND_ICON = {"measure": "hash", "dimension": "tag", "time": "arrows-sort"}
GROUP_ORDER = ["Measure", "Time", "Events", "Animal", "Recording"]
GROUP_ICON = {
	"Measure": "hash",
	"Time": "clock",
	"Events": "bolt",
	"Animal": "paw",
	"Recording": "file-description",
}
PLOT_ICON = {
	"line": "chart-line",
	"scatter": "chart-dots",
	"bar": "chart-bar",
	"area": "chart-area",
	"box": "chart-candle",
	"violin": "chart-dots-2",
	"strip": "chart-dots-3",
	"histogram": "chart-histogram",
	"ecdf": "stairs",
	"density_heatmap": "chart-grid-dots",
	"scatter_polar": "chart-radar",
	"line_polar": "chart-radar",
	"bar_polar": "chart-donut",
	"sunburst": "chart-pie",
	"treemap": "chart-treemap",
}
#: Numeric time fields that offer a Range | Pick values toggle; others (age_days) are
#: range-only, and every dimension field is pick-only.
PICKABLE = frozenset({"day", "phase_count", "hour", "n_mice"})

_SCOPE = {
	"built-in": ("template", "built in"),
	"browser": ("bookmark", "saved in this browser"),
	"project": ("folders", "saved in project"),
}

_DIALOG_CLASSES = {
	"content": "deh-dialog",
	"header": "deh-dialog-head",
	"title": "deh-dialog-title",
	"body": "deh-dialog-content",
}

layout = html.Div(
	[
		dcc.Store(id="dnd-event"),
		dcc.Store(id="builder-project"),
		dcc.Store(id="builder-state"),
		dcc.Store(id="builder-last-preset"),
		dcc.Store(id="builder-presets-local", storage_type="local", data=[]),
		dcc.Store(id="builder-presets-bump", data=0),
		dcc.Store(id="export-source"),
		html.Div(id="builder-body"),
		dmc.Modal(
			id="preset-save-modal",
			title="Save preset",
			size=460,
			classNames=_DIALOG_CLASSES,
			children=[
				html.Div(
					[
						dmc.TextInput(
							id="preset-save-name",
							label="Name",
							autoComplete="off",
							className="deh-field",
							classNames={"input": "deh-input"},
						),
						dmc.TextInput(
							id="preset-save-description",
							label="Note",
							description="optional",
							autoComplete="off",
							className="deh-field",
							classNames={"input": "deh-input"},
						),
						dmc.RadioGroup(
							id="preset-save-scope",
							label="Keep it",
							value="browser",
							className="deh-field",
							children=dmc.Stack(
								[
									dmc.Radio(
										label="In this browser · only you, on this machine",
										value="browser",
									),
									dmc.Radio(
										label=(
											"In the project · written to builder_presets.json, "
											"shared with everyone who opens it"
										),
										value="project",
									),
								],
								gap=8,
							),
						),
					],
					className="deh-dialog-body",
				),
				html.Div(
					[
						html.Button(
							"Cancel", id="preset-save-cancel", className="deh-btn deh-btn-ghost"
						),
						html.Button(
							"Save preset",
							id="preset-save-submit",
							className="deh-btn deh-btn-primary",
						),
					],
					className="deh-dialog-foot",
				),
			],
		),
	]
)


def _placeholder(message: str) -> html.Div:
	return html.Div(
		[icon("info-circle", size=20), html.P(message)],
		className="deh-alert deh-alert-info",
		style={"maxWidth": "560px", "margin": "48px auto"},
	)


def _shelf_label(shelf: str) -> str:
	return "Filters" if shelf == FILTERS else figure.LABELS.get(shelf, shelf)


def _plain_filters(filters: dict) -> dict:
	"""``state["filters"]`` (mode/values, JSON-safe) as the plain shape figure.py wants."""
	plain: dict = {}
	for column, entry in filters.items():
		if entry["mode"] == "pick":
			if entry["values"]:
				plain[column] = list(entry["values"])
		else:
			plain[column] = {"lo": entry["lo"], "hi": entry["hi"]}
	return plain


def _plain_state(state: dict) -> dict:
	"""``state`` with filters in the shape ``figure.py``'s functions expect.

	``channels`` is not copied, so a mutation ``figure.py`` makes to it (``prune``,
	``seed_detail``, ``auto_facet_metric``) still lands on the caller's own state.
	"""
	return {**state, "filters": _plain_filters(state.get("filters", {}))}


def _default_filter(item: catalog.Field, frame: pl.LazyFrame) -> dict:
	if item.kind != "dimension" and frame.collect_schema()[item.name].is_numeric():
		lo, hi = catalog.value_range(frame, item.name)
		return {"mode": "range", "lo": lo, "hi": hi}
	return {"mode": "pick", "values": []}


def _apply_move(
	state: dict, by_name: dict, frame: pl.LazyFrame, field_name: str, source: str, target: str
) -> dict:
	"""Move one field from ``source`` to ``target``: the model behind drag-drop and the chip menu."""
	item = by_name.get(field_name)
	if item is None or target == source:
		return state

	if target == FILTERS:
		if item.kind == "measure":
			return state
		if source and source not in (PALETTE, FILTERS):
			held = state["channels"].get(source, [])
			state["channels"][source] = [name for name in held if name != field_name]
		state["filters"].setdefault(field_name, _default_filter(item, frame))
		return state

	plot = figure.plot_type(state["kind"])
	if target != PALETTE and (not figure.accepts(target, item.kind) or target not in plot.channels):
		return state

	if source == FILTERS:
		state["filters"].pop(field_name, None)
	elif source and source != PALETTE:
		held = state["channels"].get(source, [])
		state["channels"][source] = [name for name in held if name != field_name]

	if target != PALETTE:
		held = state["channels"].get(target, [])
		if target in figure.MULTI:
			state["channels"][target] = held if field_name in held else [*held, field_name]
		else:
			state["channels"][target] = [field_name]
		if field_name == catalog.VALUE:
			figure.auto_facet_metric(_plain_state(state))

	return state


# ------------------------------------------------------------------------- components


def _send_to_items(field: catalog.Field, source: str, plot: figure.PlotType) -> list:
	items = []
	for channel in plot.channels:
		if not figure.accepts(channel, field.kind) or channel == source:
			continue
		label = figure.LABELS.get(channel, channel)
		if channel in plot.required:
			label += " (required)"
		items.append(
			dmc.MenuItem(
				label,
				leftSection=icon("arrow-right", size=14),
				id={"type": "chip-send", "field": field.name, "from": source, "to": channel},
			)
		)

	if field.kind != "measure" and source != FILTERS:
		items.append(
			dmc.MenuItem(
				"Filters",
				leftSection=icon("filter", size=14),
				id={"type": "chip-send", "field": field.name, "from": source, "to": FILTERS},
			)
		)

	if source != PALETTE:
		items.append(dmc.MenuDivider())
		items.append(
			dmc.MenuItem(
				f"Remove from {_shelf_label(source)}",
				leftSection=icon("x", size=14),
				id={"type": "chip-send", "field": field.name, "from": source, "to": PALETTE},
				className="deh-danger",
			)
		)

	return items


def _chip(field: catalog.Field, source: str, plot: figure.PlotType) -> html.Div:
	remove = (
		None
		if source == PALETTE
		else html.Button(
			icon("x", size=13),
			className="deh-fchip-x",
			id={"type": "chip-x", "shelf": source, "field": field.name},
			title=f"Remove {field.label} from {_shelf_label(source)}",
		)
	)
	body = [
		icon(KIND_ICON[field.kind], size=15, color="var(--kind)"),
		dmc.Menu(
			[
				dmc.MenuTarget(html.Span(field.label, className="deh-fchip-label")),
				dmc.MenuDropdown(
					[dmc.MenuLabel(f"Send {field.label} to"), *_send_to_items(field, source, plot)]
				),
			],
			classNames={"dropdown": "deh-menu"},
			position="bottom-start",
			withinPortal=True,
		),
	]
	if remove is not None:
		body.append(remove)

	return html.Div(
		body,
		className="deh-fchip",
		draggable="true",
		title=f"{field.group} · {field.kind}",
		**{"data-field": field.name, "data-kind": field.kind, "data-from": source},  # ty: ignore[invalid-argument-type]
	)


def _palette_children(fields: list[catalog.Field], state: dict, search: str) -> list:
	plot = figure.plot_type(state["kind"])
	legend = html.Div(
		[
			html.Span([html.I(style={"--k": "var(--k-measure)"}), "measure"]),
			html.Span([html.I(style={"--k": "var(--k-dim)"}), "category"]),
			html.Span([html.I(style={"--k": "var(--k-time)"}), "ordered"]),
		],
		className="deh-kind-legend",
	)
	query = (search or "").strip().lower()
	groups = []
	for group_name in GROUP_ORDER:
		items = [
			f for f in fields if f.group == group_name and (not query or query in f.label.lower())
		]
		if not items:
			continue
		groups.append(
			html.Div(
				[
					html.P(
						[
							icon(GROUP_ICON.get(group_name, "tag"), size=15),
							group_name,
							html.Span(str(len(items)), className="deh-sub"),
						],
						className="deh-group-title",
					),
					html.Div([_chip(item, PALETTE, plot) for item in items], className="deh-chips"),
				],
				className="deh-group",
			)
		)
	if not groups:
		return [legend, html.P(f"No field matches “{search}”.", className="deh-sub")]
	return [legend, *groups]


def _shelves_children(fields: list[catalog.Field], state: dict) -> list:
	by_name = {item.name: item for item in fields}
	plot = figure.plot_type(state["kind"])
	blocks = []
	for channel in plot.channels:
		held = state["channels"].get(channel, [])
		required = channel in plot.required
		accepts = " ".join(sorted(figure.ACCEPTS.get(channel, {"dimension", "time", "measure"})))
		hint = "groups, not drawn" if channel == figure.DETAIL else "drop here"
		body = [_chip(by_name[name], channel, plot) for name in held if name in by_name] or [
			html.Span(hint, className="deh-shelf-hint")
		]
		name_label: list = [figure.LABELS.get(channel, channel)]
		if required:
			name_label.append(html.I("*", title="Required"))
		blocks.append(
			html.Div(
				[
					html.Span(name_label, className="deh-shelf-name"),
					html.Div(body, className="deh-shelf-body"),
				],
				className="deh-shelf deh-shelf-required" if required else "deh-shelf",
				**{"data-shelf": channel, "data-accepts": accepts},  # ty: ignore[invalid-argument-type]
			)
		)
	return blocks


def _filter_block(
	name: str, value: dict, field: catalog.Field, frame: pl.LazyFrame, plot: figure.PlotType
) -> html.Div:
	chip = _chip(field, FILTERS, plot)
	numeric = field.kind != "dimension" and frame.collect_schema()[name].is_numeric()

	if not numeric:
		options = catalog.distinct_values(frame, name)
		body = dmc.CheckboxGroup(
			id={"type": "filter-pick", "field": name},
			value=list(value.get("values", [])),
			children=dmc.Stack(
				[dmc.Checkbox(value=option, label=option, size="xs") for option in options], gap=6
			),
			className="deh-value-list",
		)
	elif name in PICKABLE:
		lo, hi = catalog.value_range(frame, name)
		mode_row = html.Div(
			[
				html.Button(
					"Range",
					id={"type": "filter-mode", "field": name, "mode": "range"},
					className="deh-seg-btn" + (" is-active" if value["mode"] == "range" else ""),
				),
				html.Button(
					"Pick values",
					id={"type": "filter-mode", "field": name, "mode": "pick"},
					className="deh-seg-btn" + (" is-active" if value["mode"] == "pick" else ""),
				),
			],
			className="deh-seg-row",
		)
		if value["mode"] == "pick":
			control = dmc.ChipGroup(
				[dmc.Chip(str(v), value=str(v), size="xs") for v in range(int(lo), int(hi) + 1)],
				id={"type": "filter-pick", "field": name},
				value=[str(v) for v in value.get("values", [])],
				multiple=True,
			)
		else:
			control = dmc.RangeSlider(
				id={"type": "filter-range", "field": name},
				min=int(lo),
				max=int(hi),
				value=[value.get("lo", lo), value.get("hi", hi)],
			)
		body = html.Div([mode_row, control])
	else:
		lo, hi = catalog.value_range(frame, name)
		body = dmc.RangeSlider(
			id={"type": "filter-range", "field": name},
			min=lo,
			max=hi,
			value=[value.get("lo", lo), value.get("hi", hi)],
		)

	return html.Div([chip, body], className="deh-filter-block")


def _filters_children(frame: pl.LazyFrame, fields: list[catalog.Field], state: dict):
	by_name = {item.name: item for item in fields}
	names = list(state.get("filters", {}))
	if not names:
		return html.Span("Drop any category or ordered field here.", className="deh-shelf-hint")
	plot = figure.plot_type(state["kind"])
	return [
		_filter_block(name, state["filters"][name], by_name[name], frame, plot)
		for name in names
		if name in by_name
	]


def _types_children(state: dict) -> list:
	return [
		html.Button(
			[icon(PLOT_ICON.get(plot.name, "chart-dots"), size=22), html.Span(plot.label)],
			id={"type": "builder-kind", "kind": plot.name},
			className="deh-type-btn",
			**{"aria-pressed": "true" if plot.name == state["kind"] else "false"},  # ty: ignore[invalid-argument-type]
		)
		for plot in figure.PLOTS
	]


def _mode_children(state: dict) -> list:
	return [
		html.Button(
			label.capitalize(),
			id={"type": "builder-mode", "mode": key},
			className="deh-seg-btn" + (" is-active" if key == state["measure_as"] else ""),
		)
		for key, label in figure.MEASURE_MODES.items()
	]


def _preset_card(pid: str, name: str, description: str, scope: str, active: bool) -> html.Button:
	scope_icon, scope_label = _SCOPE[scope]
	children = [
		html.B(name),
		html.Span(description, className="deh-sub"),
		html.Span([icon(scope_icon, size=12), scope_label], className="deh-preset-scope"),
	]
	if scope != "built-in":
		children.append(
			html.Button(
				icon("trash", size=14),
				className="deh-icon-btn sm deh-preset-x",
				id={"type": "preset-delete", "id": pid, "scope": scope},
				title=f"Delete {name}",
			)
		)
	return html.Button(
		children,
		id={"type": "preset-pick", "id": pid},
		className="deh-preset",
		**{"aria-pressed": "true" if active else "false"},  # ty: ignore[invalid-argument-type]
	)


def _slot_preset_card(
	preset: presets_mod.Preset, choices: list[str], counts: dict, active: bool
) -> dmc.Menu:
	items = [
		dmc.MenuItem(
			f"{choice} · {counts.get(choice, 0)} recordings",
			leftSection=icon("bolt", size=14),
			id={"type": "preset-slot", "id": preset.id, "choice": choice},
		)
		for choice in choices
	]
	trigger = html.Div(
		[
			html.B(preset.name),
			html.Span(preset.description, className="deh-sub"),
			html.Span([icon("template", size=12), "built in"], className="deh-preset-scope"),
		],
		className="deh-preset",
		**{"aria-pressed": "true" if active else "false"},  # ty: ignore[invalid-argument-type]
	)
	return dmc.Menu(
		[dmc.MenuTarget(trigger), dmc.MenuDropdown([dmc.MenuLabel(preset.slot_label), *items])],
		classNames={"dropdown": "deh-menu"},
	)


def _presets_children(
	project, location: str, state: dict, last_preset: dict | None, saved_local: list
) -> list:
	def matched(pid: str) -> bool:
		return (
			last_preset is not None
			and last_preset["id"] == pid
			and state == last_preset.get("state")
		)

	cards: list = []
	counts = None
	for preset in presets_mod.BUILTINS:
		if preset.slot_key:
			choices = services.event_names(project)
			if not choices:
				continue
			counts = counts or services.event_recording_counts(project)
			cards.append(_slot_preset_card(preset, choices, counts, matched(preset.id)))
		else:
			cards.append(
				_preset_card(
					preset.id, preset.name, preset.description, "built-in", matched(preset.id)
				)
			)
	for preset in services.load_saved_presets(location):
		cards.append(
			_preset_card(
				preset["id"],
				preset["name"],
				preset.get("description", ""),
				"project",
				matched(preset["id"]),
			)
		)
	for preset in saved_local or []:
		cards.append(
			_preset_card(
				preset["id"],
				preset["name"],
				preset.get("description", ""),
				"browser",
				matched(preset["id"]),
			)
		)
	cards.append(
		html.Button(
			[icon("bookmark-plus", size=16), "Save current"],
			id="builder-save-strip",
			className="deh-preset deh-preset-add",
		)
	)
	return cards


def _alerts_children(note_texts: list[str]) -> list:
	return [
		html.Div(
			[icon("alert-triangle", size=16), html.Span(text)], className="deh-alert deh-alert-warn"
		)
		for text in note_texts
	]


def _graph_children(
	frame: pl.LazyFrame,
	fields: list[catalog.Field],
	state: dict,
	last_preset: dict | None,
	theme: str,
):
	fig, note_texts = figure.build_figure(frame, _plain_state(state), fields)
	fig.update_layout(template=theme or "light", margin={"t": 30})

	modified = last_preset is None or state != last_preset.get("state")
	title = last_preset["name"] if last_preset else "Untitled plot"
	head_label = [html.B(title)]
	if modified:
		tail = " · not saved as a preset" if last_preset is None else " (edited)"
		head_label.append(html.Span(tail, className="deh-sub"))

	head = html.Div(
		[
			html.Div(
				head_label,
				style={
					"display": "flex",
					"flex": "1",
					"minWidth": "0",
					"alignItems": "baseline",
					"gap": "4px",
				},
			),
			html.Button(
				[icon("refresh", size=14), "Reset"],
				id="builder-reset",
				className="deh-btn deh-btn-ghost sm",
				disabled=last_preset is None,
				title="Back to the last preset you loaded",
			),
			html.Button(
				[icon("bookmark-plus", size=15), "Save preset"],
				id="builder-save-head",
				className="deh-btn deh-btn-ghost sm",
			),
			html.Button(
				icon("download", size=15),
				id="builder-export",
				className="deh-icon-btn sm",
				title="Export this plot",
			),
		],
		className="deh-graph-head",
	)
	graph = dcc.Graph(
		id="builder-graph",
		figure=fig,
		config={"displayModeBar": False, "responsive": True},
		style={"height": "420px"},
	)
	return [head, graph], note_texts


def _status_text(project, frame: pl.LazyFrame) -> str:
	rows = frame.select(pl.len()).collect().item()
	metrics = len(catalog.metric_names(frame))
	return (
		f"{project.project_name} · {len(project.recordings)} recordings · {rows:,} rows · "
		f"{metrics} metrics"
	)


def _dashboard(
	project, location, frame, fields, state, last_preset, saved_local, theme, search=""
) -> html.Div:
	graph_children, note_texts = _graph_children(frame, fields, state, last_preset, theme)
	return html.Div(
		[
			html.Div(
				[
					html.Div(_mode_children(state), id="builder-mode-row", className="deh-seg-row"),
					html.Button(
						[icon("eraser", size=15), "Clear shelves"],
						id="builder-clear",
						className="deh-btn deh-btn-ghost",
					),
					html.Span(className="deh-grow"),
					html.Span(
						_status_text(project, frame), id="builder-status", className="deh-b-status"
					),
				],
				className="deh-b-toolbar",
			),
			html.Div(
				_presets_children(project, location, state, last_preset, saved_local),
				id="builder-presets",
				className="deh-presets",
			),
			html.Div(_types_children(state), id="builder-types", className="deh-types"),
			html.Div(
				[
					html.Div(
						[
							html.P("Fields", className="deh-rail-title"),
							dcc.Input(
								id="builder-search",
								type="search",
								placeholder="Search fields",
								debounce=True,
								className="deh-input",
								style={"width": "100%", "height": "34px"},
							),
							html.Div(
								_palette_children(fields, state, search), id="builder-palette"
							),
						],
						className="deh-rail deh-palette",
						**{"data-shelf": PALETTE, "data-accepts": "dimension time measure"},  # ty: ignore[invalid-argument-type]
					),
					html.Div(
						[
							html.Div(
								_shelves_children(fields, state),
								id="builder-shelves",
								className="deh-shelves",
							),
							html.Div(_alerts_children(note_texts), id="builder-alerts"),
							html.Div(
								graph_children, id="builder-graph-card", className="deh-graph-card"
							),
						],
						className="deh-canvas",
					),
					html.Div(
						_filters_children(frame, fields, state),
						id="builder-filters",
						className="deh-rail deh-filters",
						**{"data-shelf": FILTERS, "data-accepts": "dimension time"},  # ty: ignore[invalid-argument-type]
					),
				],
				className="deh-builder",
			),
		]
	)


# ------------------------------------------------------------------------- callbacks


@callback(
	Output("builder-body", "children"),
	Output("builder-project", "data"),
	Output("builder-state", "data", allow_duplicate=True),
	Output("builder-last-preset", "data", allow_duplicate=True),
	Input("url", "search"),
	State("theme-store", "data"),
	State("project-paths", "data"),
	State("builder-project", "data"),
	State("builder-state", "data"),
	State("builder-last-preset", "data"),
	State("builder-presets-local", "data"),
	prevent_initial_call="initial_duplicate",
)
def _resolve(search, theme, paths, current, current_state, last_preset, saved_local):
	params = parse_qs((search or "").lstrip("?"))
	pid = (params.get("project") or [None])[0]

	if not pid:
		message = "Open a project from Projects, then use its row menu to open it here."
		return _placeholder(message), None, no_update, no_update

	location = services.resolve_project(paths, pid)
	if location is None:
		message = "This project is not in your browser's saved list. Open it from Projects."
		return _placeholder(message), None, no_update, no_update

	same_project = current and current.get("location") == location

	try:
		project = services.load_project(location)
		frame, fields = services.builder_frame(location)
	except FileNotFoundError as exc:
		message = f"{exc} Generate it from this project's row menu on the Projects screen."
		return _placeholder(message), {"location": location}, no_update, no_update
	except Exception as exc:
		return _placeholder(f"{type(exc).__name__}: {exc}"), None, no_update, no_update

	if same_project and current_state:
		state = current_state
	else:
		state = figure.seed_detail(figure.new_state(), fields)
		last_preset = None

	body = _dashboard(project, location, frame, fields, state, last_preset, saved_local, theme)
	return body, {"location": location}, state, last_preset


@callback(
	Output("builder-palette", "children"),
	Input("builder-search", "value"),
	Input("builder-state", "data"),
	State("builder-project", "data"),
	prevent_initial_call=True,
)
def _render_palette(search, state, project_data):
	if not project_data or not state:
		raise PreventUpdate
	try:
		_frame, fields = services.builder_frame(project_data["location"])
	except FileNotFoundError:
		raise PreventUpdate from None
	return _palette_children(fields, state, search)


@callback(
	Output("builder-shelves", "children"),
	Output("builder-filters", "children"),
	Output("builder-alerts", "children"),
	Output("builder-graph-card", "children"),
	Output("builder-presets", "children"),
	Output("builder-types", "children"),
	Output("builder-mode-row", "children"),
	Output("builder-status", "children"),
	Input("builder-state", "data"),
	Input("theme-store", "data"),
	Input("builder-presets-bump", "data"),
	State("builder-project", "data"),
	State("builder-presets-local", "data"),
	State("builder-last-preset", "data"),
	prevent_initial_call=True,
)
def _render(state, theme, _bump, project_data, saved_local, last_preset):
	if not project_data or not state:
		raise PreventUpdate
	location = project_data["location"]
	try:
		project = services.load_project(location)
		frame, fields = services.builder_frame(location)
	except FileNotFoundError:
		raise PreventUpdate from None

	graph_children, note_texts = _graph_children(frame, fields, state, last_preset, theme)
	return (
		_shelves_children(fields, state),
		_filters_children(frame, fields, state),
		_alerts_children(note_texts),
		graph_children,
		_presets_children(project, location, state, last_preset, saved_local),
		_types_children(state),
		_mode_children(state),
		_status_text(project, frame),
	)


@callback(
	Output("builder-state", "data"),
	Output("builder-last-preset", "data"),
	Input("dnd-event", "data"),
	Input({"type": "chip-x", "shelf": ALL, "field": ALL}, "n_clicks"),
	Input({"type": "chip-send", "field": ALL, "from": ALL, "to": ALL}, "n_clicks"),
	Input({"type": "builder-kind", "kind": ALL}, "n_clicks"),
	Input({"type": "builder-mode", "mode": ALL}, "n_clicks"),
	Input("builder-clear", "n_clicks"),
	Input("builder-reset", "n_clicks"),
	Input({"type": "preset-pick", "id": ALL}, "n_clicks"),
	Input({"type": "preset-slot", "id": ALL, "choice": ALL}, "n_clicks"),
	Input({"type": "filter-pick", "field": ALL}, "value"),
	Input({"type": "filter-range", "field": ALL}, "value"),
	Input({"type": "filter-mode", "field": ALL, "mode": ALL}, "n_clicks"),
	State("builder-state", "data"),
	State("builder-project", "data"),
	State("builder-last-preset", "data"),
	State("builder-presets-local", "data"),
	prevent_initial_call=True,
)
def _reduce(
	event,
	_chip_x,
	_chip_send,
	_kind_clicks,
	_mode_clicks,
	_clear,
	_reset,
	_preset_clicks,
	_slot_clicks,
	_pick_values,
	_range_values,
	_mode_toggle,
	state,
	project_data,
	last_preset,
	saved_local,
):
	trigger = ctx.triggered_id
	if trigger is None or not project_data or not state:
		raise PreventUpdate

	location = project_data["location"]
	try:
		frame, fields = services.builder_frame(location)
	except FileNotFoundError:
		raise PreventUpdate from None
	by_name = {item.name: item for item in fields}
	state = copy.deepcopy(state)

	if trigger == "builder-clear":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		state["channels"] = {}
		return state, no_update

	if trigger == "builder-reset":
		if not ctx.triggered[0]["value"] or not last_preset:
			raise PreventUpdate
		return copy.deepcopy(last_preset["state"]), no_update

	if isinstance(trigger, dict) and trigger.get("type") == "builder-kind":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		state["kind"] = trigger["kind"]
		state, _dropped = figure.prune(state, figure.plot_type(state["kind"]).channels)
		state = figure.seed_detail(state, fields)
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "builder-mode":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		state["measure_as"] = trigger["mode"]
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "chip-x":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		shelf, field_name = trigger["shelf"], trigger["field"]
		if shelf == FILTERS:
			state["filters"].pop(field_name, None)
		else:
			held = state["channels"].get(shelf, [])
			state["channels"][shelf] = [name for name in held if name != field_name]
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "chip-send":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		state = _apply_move(state, by_name, frame, trigger["field"], trigger["from"], trigger["to"])
		return state, no_update

	if trigger == "dnd-event":
		if not event:
			raise PreventUpdate
		state = _apply_move(
			state, by_name, frame, event["field"], event.get("from") or PALETTE, event["shelf"]
		)
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "preset-pick":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		pid = trigger["id"]
		preset = presets_mod.BY_ID.get(pid)
		project = services.load_project(location)
		if preset is not None:
			resolved = presets_mod.resolve(preset, project)
			entry = {"id": preset.id, "name": preset.name, "state": resolved}
		else:
			saved = next(
				(
					item
					for item in [*(saved_local or []), *services.load_saved_presets(location)]
					if item["id"] == pid
				),
				None,
			)
			if saved is None:
				raise PreventUpdate
			entry = {"id": saved["id"], "name": saved["name"], "state": saved["state"]}
		return copy.deepcopy(entry["state"]), entry

	if isinstance(trigger, dict) and trigger.get("type") == "preset-slot":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		preset = presets_mod.BY_ID.get(trigger["id"])
		if preset is None:
			raise PreventUpdate
		project = services.load_project(location)
		choice = trigger["choice"]
		resolved = presets_mod.resolve(preset, project, choice)
		entry = {"id": preset.id, "name": f"{preset.name}: {choice}", "state": resolved}
		return copy.deepcopy(resolved), entry

	if isinstance(trigger, dict) and trigger.get("type") == "filter-mode":
		if not ctx.triggered[0]["value"]:
			raise PreventUpdate
		name, mode = trigger["field"], trigger["mode"]
		if state["filters"].get(name, {}).get("mode") == mode:
			raise PreventUpdate
		if mode == "pick":
			state["filters"][name] = {"mode": "pick", "values": []}
		else:
			lo, hi = catalog.value_range(frame, name)
			state["filters"][name] = {"mode": "range", "lo": lo, "hi": hi}
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "filter-pick":
		name = trigger["field"]
		current = state["filters"].get(name, {}).get("values", [])
		new_values = ctx.triggered[0]["value"] or []
		if list(new_values) == list(current):
			raise PreventUpdate
		state["filters"][name] = {"mode": "pick", "values": list(new_values)}
		return state, no_update

	if isinstance(trigger, dict) and trigger.get("type") == "filter-range":
		name = trigger["field"]
		entry = state["filters"].get(name, {})
		new_value = ctx.triggered[0]["value"]
		if not new_value or [entry.get("lo"), entry.get("hi")] == list(new_value):
			raise PreventUpdate
		state["filters"][name] = {"mode": "range", "lo": new_value[0], "hi": new_value[1]}
		return state, no_update

	raise PreventUpdate


@callback(
	Output("preset-save-modal", "opened"),
	Output("preset-save-name", "value"),
	Output("preset-save-name", "error"),
	Output("preset-save-description", "value"),
	Output("builder-presets-local", "data"),
	Output("builder-presets-bump", "data"),
	Input("builder-save-head", "n_clicks"),
	Input("builder-save-strip", "n_clicks"),
	Input("preset-save-cancel", "n_clicks"),
	Input("preset-save-submit", "n_clicks"),
	State("preset-save-name", "value"),
	State("preset-save-description", "value"),
	State("preset-save-scope", "value"),
	State("builder-state", "data"),
	State("builder-project", "data"),
	State("builder-presets-local", "data"),
	State("builder-presets-bump", "data"),
	prevent_initial_call=True,
)
def _save_preset_modal(
	_head,
	_strip,
	_cancel,
	_submit,
	name,
	description,
	scope,
	state,
	project_data,
	saved_local,
	bump,
):
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	trigger = ctx.triggered_id

	if trigger in ("builder-save-head", "builder-save-strip"):
		return True, "", None, "", no_update, no_update
	if trigger == "preset-save-cancel":
		return False, no_update, None, no_update, no_update, no_update

	name = (name or "").strip()
	existing = {preset.name.lower() for preset in presets_mod.BUILTINS}
	existing |= {preset["name"].lower() for preset in saved_local or []}
	existing |= {
		preset["name"].lower() for preset in services.load_saved_presets(project_data["location"])
	}
	if not name:
		return True, no_update, "Give the preset a name.", no_update, no_update, no_update
	if name.lower() in existing:
		error = f"A preset called “{name}” already exists."
		return True, no_update, error, no_update, no_update, no_update

	preset = {
		"id": f"saved-{int(time.time() * 1000)}",
		"name": name,
		"description": (description or "").strip(),
		"state": state,
		"scope": scope or "browser",
	}
	if preset["scope"] == "project":
		services.save_preset(project_data["location"], preset)
		notify("good", f"Saved “{name}” to builder_presets.json.")
		return False, no_update, None, no_update, no_update, (bump or 0) + 1

	notify("good", f"Saved “{name}” in this browser.")
	return False, no_update, None, no_update, [*(saved_local or []), preset], (bump or 0) + 1


@callback(
	Output("builder-presets-local", "data", allow_duplicate=True),
	Output("builder-presets-bump", "data", allow_duplicate=True),
	Input({"type": "preset-delete", "id": ALL, "scope": ALL}, "n_clicks"),
	State("builder-presets-local", "data"),
	State("builder-project", "data"),
	State("builder-presets-bump", "data"),
	prevent_initial_call=True,
)
def _delete_preset(_clicks, saved_local, project_data, bump):
	if not ctx.triggered[0]["value"]:
		raise PreventUpdate
	trigger = ctx.triggered_id
	pid, scope = trigger["id"], trigger["scope"]

	if scope == "project":
		services.delete_saved_preset(project_data["location"], pid)
		notify("info", "Deleted from builder_presets.json.")
		return no_update, (bump or 0) + 1

	notify("info", "Deleted from this browser.")
	return [preset for preset in saved_local or [] if preset["id"] != pid], (bump or 0) + 1


@callback(
	Output("export-dialog", "opened", allow_duplicate=True),
	Output("export-source", "data", allow_duplicate=True),
	Output("export-filename", "value", allow_duplicate=True),
	Input("builder-export", "n_clicks"),
	State("builder-graph", "figure"),
	State("builder-last-preset", "data"),
	State("builder-project", "data"),
	prevent_initial_call=True,
)
def _open_export(_clicks, fig, last_preset, project_data):
	if not fig:
		raise PreventUpdate
	title = last_preset["name"] if last_preset else "Untitled plot"
	project_name = services.load_project(project_data["location"]).project_name
	filename = f"{project_name}__{title}".lower().replace(" ", "-")
	return True, {"figure": fig, "title": title}, filename
