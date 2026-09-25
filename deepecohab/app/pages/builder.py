import copy
import time
from pathlib import Path
from urllib.parse import parse_qs

import dash
import dash_mantine_components as dmc
import polars as pl
from dash import (
	ALL,
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
	set_props,
)
from dash.exceptions import PreventUpdate

from deepecohab import Project
from deepecohab.app import components, services
from deepecohab.app.builder import catalog, figure, presets as presets_mod
from deepecohab.app.components import icon, notify
from deepecohab.plotting.theme import PALETTES

PATH = "/builder"

dash.register_page(__name__, path=PATH, name="Plot builder", order=2, icon="drag-drop")

#: Pseudo-shelves: the palette takes chips back, the filter rail turns them into controls.
PALETTE, FILTERS = "__palette__", "__filters__"

KIND_ICON = {"measure": "hash", "dimension": "tag", "time": "arrows-sort"}
GROUP_ORDER = ["Measure", "Time", "Position", "Events", "Animal", "Recording"]
GROUP_ICON = {
	"Measure": "hash",
	"Time": "clock",
	"Position": "map-pin",
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
#: Format keys picked from a menu, empty as ``None`` rather than ``""``.
_SELECTS = ("colorscale", "palette")

_SCOPE = {
	"built-in": ("template", "built in"),
	"browser": ("bookmark", "saved in this browser"),
	"project": ("folders", "saved in project"),
}

layout = html.Div(
	[
		dcc.Store(id="dnd-event"),
		# Real clicks only, via deh.clickEvent: the buttons behind them are re-rendered on
		# every state change, which would otherwise fire their server callbacks each time.
		dcc.Store(id="builder-action"),
		dcc.Store(id="preset-delete-event"),
		dcc.Store(id="builder-save-strip-event"),
		dcc.Store(id="builder-kind"),
		dcc.Store(id="builder-project"),
		dcc.Store(id="builder-state"),
		dcc.Store(id="builder-last-preset"),
		dcc.Store(id="builder-presets-local", storage_type="local", data=[]),
		dcc.Store(id="builder-presets-bump", data=0),
		html.Div(id="builder-body"),
		dmc.Modal(
			id="preset-save-modal",
			title="Save preset",
			size=460,
			classNames=components.DIALOG_CLASSES,
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
	"""Move one field from ``source`` to ``target``: the model behind drag-drop and the chips."""
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


def _drop_unshelved_bins(state: dict) -> None:
	"""Forget the Blocks spec of every field no longer on a shelf.

	Run once before the trigger is applied rather than in each handler that can take a
	field off a shelf - the x button, a move to the palette or the filter rail, Clear, a
	plot type with fewer shelves - so a spec left behind by any of them cannot come back
	to life under the field when it is dropped again.
	"""
	held = {name for names in state["channels"].values() for name in names}
	bins = {name: spec for name, spec in state.get("bins", {}).items() if name in held}
	# No empty dict left behind, or a preset would read as edited after a reset.
	if bins:
		state["bins"] = bins
	else:
		state.pop("bins", None)


def _set_format(state: dict, key: str, value, auto: dict) -> dict:
	"""``state`` with Format ``key`` set to ``value``; empty, or the automatic text, clears it."""
	if key in figure.FORMAT_BOUNDS:
		value = value if isinstance(value, int | float) else None
	else:
		value = (value or "").strip() or None
	if value == auto.get(key):
		value = None
	fmt = state.get("format", {})
	if figure.live_format(fmt, auto).get(key) == value:
		raise PreventUpdate

	if value is None:
		fmt.pop(key, None)
	else:
		fmt[key] = {"on": auto[figure.FORMAT_BINDS[key]], "value": value}
	# No empty dict left behind, or a preset would read as edited after a reset.
	if fmt:
		state["format"] = fmt
	else:
		state.pop("format", None)
	return state


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


def _bin_items(field: catalog.Field, source: str, spec: str | None) -> list:
	"""The Blocks box for a numeric ordered field on a shelf; empty for anything else.

	Committed on Enter or on losing focus, never per keystroke: the shelves are rebuilt
	whenever the state changes, and a rebuild mid-edit would take the caret with it.
	"""
	if source in (PALETTE, FILTERS) or field.name not in catalog.ORDERED_COLUMNS:
		return []

	return [
		dmc.MenuDivider(),
		dmc.MenuLabel(f"Group {field.label} into blocks"),
		dmc.TextInput(
			id={"type": "chip-bin", "field": field.name},
			value=spec or "",
			placeholder=figure.BIN_HINT,
			description="both ends included; empty for one group per value",
			debounce=True,
			autoComplete="off",
			className="deh-field deh-bin-field",
			classNames={"input": "deh-input"},
		),
	]


def _chip(
	field: catalog.Field, source: str, plot: figure.PlotType, spec: str | None = None
) -> html.Div:
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
					[
						dmc.MenuLabel(f"Send {field.label} to"),
						*_send_to_items(field, source, plot),
						*_bin_items(field, source, spec),
					]
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


def _palette_children(fields: list[catalog.Field], kind: str, search: str) -> list:
	plot = figure.plot_type(kind)
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
		items.sort(key=lambda f: f.label.lower())
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
	bins = state.get("bins", {})
	plot = figure.plot_type(state["kind"])
	blocks = []
	for channel in plot.channels:
		held = state["channels"].get(channel, [])
		required = channel in plot.required
		accepts = " ".join(sorted(figure.ACCEPTS.get(channel, {"dimension", "time", "measure"})))
		hint = "groups, not drawn" if channel == figure.DETAIL else "drop here"
		body = [
			_chip(by_name[name], channel, plot, bins.get(name)) for name in held if name in by_name
		] or [html.Span(hint, className="deh-shelf-hint")]
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
				step=1,
				minRange=0,
				value=[value.get("lo", lo), value.get("hi", hi)],
			)
		body = html.Div([mode_row, control])
	else:
		lo, hi = catalog.value_range(frame, name)
		body = dmc.RangeSlider(
			id={"type": "filter-range", "field": name},
			min=lo,
			max=hi,
			step=(hi - lo) / 100 or 1,
			minRange=0,
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
		[dmc.MenuTarget(trigger), dmc.MenuDropdown([dmc.MenuLabel("Which event?"), *items])],
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
		if preset.needs_event:
			choices = project.event_names()
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


def _graph_title(state: dict, last_preset: dict | None) -> tuple[list, bool]:
	"""The graph card's title children, and whether Reset has nothing to reset to."""
	modified = last_preset is None or state != last_preset.get("state")
	title = last_preset["name"] if last_preset else "Untitled plot"
	head_label = [html.B(title)]
	if modified:
		tail = " · not saved as a preset" if last_preset is None else " (edited)"
		head_label.append(html.Span(tail, className="deh-sub"))
	return head_label, last_preset is None


def _format_props(state: dict, auto: dict) -> dict[str, dict]:
	"""Props for each Format field: its live override, and what empty falls back to.

	``auto`` is what ``builder-auto-titles`` holds: the automatic titles, plus how many
	categories the figure colours, which a palette must have colours enough for.
	"""
	live = figure.live_format(state.get("format", {}), auto)
	needed = auto["categories"]
	picked = PALETTES.get(live.get("palette"), [])
	props = {}
	for key, bind in figure.FORMAT_BINDS.items():
		element = auto[bind]
		if key in figure.FORMAT_BOUNDS:
			placeholder = "Auto"
		elif key in _SELECTS:
			placeholder = "Default"
		else:
			placeholder = element or ("No title" if element == "" else "Not on this plot")
		props[key] = {
			"value": live.get(key, None if key in _SELECTS else ""),
			"placeholder": placeholder,
			"disabled": element is None,
			"error": None,
		}
	for high, low in figure.FORMAT_PAIRS.items():
		if figure.inverted(live.get(low), live.get(high)):
			props[high]["error"] = "Must be above min"
	if 0 < len(picked) < needed:
		props["palette"]["error"] = f"{len(picked)} colours for {needed} categories"
	props["palette"]["data"] = [
		{"value": name, "label": f"{name} · {len(colors)}", "disabled": len(colors) < needed}
		for name, colors in PALETTES.items()
	]
	return props


def _graph_head(title_children: list, reset_disabled: bool) -> html.Div:
	"""The graph card's head: built once by ``_dashboard`` and never remounted.

	``_render`` updates ``builder-graph-title``/``builder-reset`` in place instead of
	replacing this whole block - Dash treats a remounted component as new, so a button
	here remounting on every state change fired its own callback with no real click
	behind it (the export dialog used to pop open on any edit).
	"""
	return html.Div(
		[
			html.Div(
				title_children,
				id="builder-graph-title",
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
				disabled=reset_disabled,
				title="Back to the last preset you loaded",
			),
			html.Button(
				[icon("bookmark-plus", size=15), "Save preset"],
				id="builder-save-head",
				className="deh-btn deh-btn-ghost sm",
			),
			html.Button(
				icon("format", size=15),
				id="builder-format",
				className="deh-icon-btn sm",
				title="Format this plot",
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


def _graph_children(
	frame: pl.LazyFrame,
	fields: list[catalog.Field],
	state: dict,
	theme: str,
):
	fig, note_texts = figure.build_figure(frame, _plain_state(state), fields)
	auto = {
		**figure.apply_format(fig, state.get("format", {})),
		"categories": len(fig.layout.colorway or ()),
	}
	# The top margin keeps room for a title set through Format.
	fig.update_layout(
		template=theme or "light",
		margin={"t": 48},
		title={"x": 0, "xref": "paper", "xanchor": "left"},
	)

	return fig, note_texts, auto


def _status_text(project, frame: pl.LazyFrame) -> str:
	rows = frame.select(pl.len()).collect().item()
	metrics = len(catalog.metric_names(frame))
	return f"{len(project.recordings)} recordings · {rows:,} rows · {metrics} metrics"


def _project_picker(paths: list[str] | None, pid: str | None) -> dmc.Select:
	return dmc.Select(
		id="builder-project-pick",
		data=[
			{"value": services.project_id(path), "label": services.project_name(path)}
			for path in paths or []
		],
		value=pid,
		placeholder="Pick a project",
		size="sm",
		w=240,
		allowDeselect=False,
		searchable=True,
		leftSection=icon("folders", size=16),
		classNames={"input": "deh-input"},
	)


def _bare(paths: list[str] | None, pid: str | None, message: str) -> html.Div:
	"""A placeholder under the project picker, so another project stays one pick away."""
	return html.Div(
		[
			html.Div(_project_picker(paths, pid), className="deh-b-toolbar"),
			components.placeholder(message),
		]
	)


def _dashboard(
	project, location, paths, frame, fields, state, last_preset, saved_local, theme, search=""
) -> html.Div:
	fig, note_texts, auto = _graph_children(frame, fields, state, theme)
	title_children, reset_disabled = _graph_title(state, last_preset)
	graph_card = html.Div(
		[
			dcc.Store(id="builder-auto-titles", data=auto),
			components.format_dialog(
				"builder",
				"Empty means automatic. Saved with the preset.",
				_format_props(state, auto),
			),
			_graph_head(title_children, reset_disabled),
			dcc.Graph(
				id="builder-graph",
				figure=fig,
				config={"displayModeBar": False, "responsive": True},
			),
		],
		id="builder-graph-card",
		className="deh-graph-card",
	)
	return html.Div(
		[
			html.Div(
				[
					_project_picker(paths, services.project_id(location)),
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
							dmc.TextInput(
								id="builder-search",
								placeholder="Search fields",
								leftSection=icon("search", size=16),
								debounce=150,
								classNames={"input": "deh-input"},
							),
							html.Div(
								_palette_children(fields, state["kind"], search),
								id="builder-palette",
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
							graph_card,
						],
						className="deh-canvas",
					),
					html.Div(
						[
							html.P("Filters", className="deh-rail-title"),
							html.Div(_filters_children(frame, fields, state), id="builder-filters"),
						],
						className="deh-rail deh-filters",
						**{"data-shelf": FILTERS, "data-accepts": "dimension time"},  # ty: ignore[invalid-argument-type]
					),
				],
				className="deh-builder",
			),
		]
	)


@callback(
	Output("builder-body", "children"),
	Output("builder-project", "data"),
	Output("builder-state", "data", allow_duplicate=True),
	Output("builder-last-preset", "data", allow_duplicate=True),
	Input("url", "pathname"),
	Input("url", "search"),
	State("plot-theme", "data"),
	State("project-paths", "data"),
	State("builder-project", "data"),
	State("builder-state", "data"),
	State("builder-last-preset", "data"),
	State("builder-presets-local", "data"),
	prevent_initial_call="initial_duplicate",
)
def _resolve(pathname, search, theme, paths, current, current_state, last_preset, saved_local):
	if pathname != PATH:
		raise PreventUpdate

	params = parse_qs((search or "").lstrip("?"))
	pid = (params.get("project") or [None])[0]

	if not pid:
		message = "Pick a project above, or open one from Projects."
		return _bare(paths, None, message), None, no_update, no_update

	location = services.resolve_project(paths, pid)
	if location is None:
		message = "This project is not in your browser's saved list. Open it from Projects."
		return _bare(paths, None, message), None, no_update, no_update

	table = Path(location) / Project.PROJECT_TABLE
	# A string: nanosecond mtimes lose precision as JSON numbers in the browser.
	opened = {
		"location": location,
		"stamp": str(table.stat().st_mtime_ns if table.is_file() else None),
		# A project added on Projects since shows up in the picker on the way back.
		"paths": paths,
	}
	if current_state and current == opened:
		raise PreventUpdate
	same_project = current and current.get("location") == location

	try:
		project = services.load_project(location)
		frame, fields = services.builder_frame(location)
	except FileNotFoundError as exc:
		message = f"{exc} Generate it from this project's row menu on the Projects screen."
		return _bare(paths, pid, message), opened, None, no_update
	except Exception as exc:
		return _bare(paths, pid, f"{type(exc).__name__}: {exc}"), None, no_update, no_update

	if same_project and current_state:
		state = current_state
	else:
		state = figure.seed_detail(figure.new_state(), fields)
		last_preset = None

	body = _dashboard(
		project, location, paths, frame, fields, state, last_preset, saved_local, theme
	)
	return body, opened, state, last_preset


@callback(
	Output("url", "search", allow_duplicate=True),
	Input("builder-project-pick", "value"),
	State("url", "search"),
	prevent_initial_call=True,
)
def _switch_project(pid, search):
	# The picker is rebuilt with the page, which fires this once with the project it shows.
	if not pid or pid == (parse_qs((search or "").lstrip("?")).get("project") or [None])[0]:
		raise PreventUpdate
	return f"?project={pid}"


clientside_callback(
	ClientsideFunction("deh", "builderKind"),
	Output("builder-kind", "data"),
	Input("builder-state", "data"),
	State("builder-kind", "data"),
	prevent_initial_call=True,
)


@callback(
	Output("builder-palette", "children"),
	Input("builder-search", "value"),
	Input("builder-kind", "data"),
	State("builder-project", "data"),
	prevent_initial_call=True,
)
def _render_palette(search, kind, project_data):
	if not project_data or not kind:
		raise PreventUpdate
	try:
		_frame, fields = services.builder_frame(project_data["location"])
	except FileNotFoundError:
		raise PreventUpdate from None
	return _palette_children(fields, kind, search)


@callback(
	Output("builder-shelves", "children"),
	Output("builder-filters", "children"),
	Output("builder-alerts", "children"),
	Output("builder-graph-title", "children"),
	Output("builder-reset", "disabled"),
	Output("builder-graph", "figure"),
	Output("builder-presets", "children"),
	Output("builder-types", "children"),
	Output("builder-mode-row", "children"),
	Output("builder-auto-titles", "data"),
	Input("builder-state", "data"),
	Input("plot-theme", "data"),
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

	fig, note_texts, auto = _graph_children(frame, fields, state, theme)
	title_children, reset_disabled = _graph_title(state, last_preset)
	return (
		_shelves_children(fields, state),
		_filters_children(frame, fields, state),
		_alerts_children(note_texts),
		title_children,
		reset_disabled,
		fig,
		_presets_children(project, location, state, last_preset, saved_local),
		_types_children(state),
		_mode_children(state),
		auto,
	)


@callback(
	Output("builder-format-modal", "opened"),
	Input("builder-format", "n_clicks"),
	prevent_initial_call=True,
)
def _open_format(clicks):
	if not clicks:
		raise PreventUpdate
	return True


@callback(
	Output({"type": "builder-fmt", "key": ALL}, "placeholder"),
	Output({"type": "builder-fmt", "key": ALL}, "disabled"),
	Output({"type": "builder-fmt", "key": ALL}, "error"),
	Output({"type": "builder-fmt", "key": "palette"}, "data"),
	Input("builder-auto-titles", "data"),
	State("builder-state", "data"),
	State({"type": "builder-fmt", "key": ALL}, "value"),
	prevent_initial_call=True,
)
def _render_format(auto, state, _values):
	"""Refill the Format form in place: remounting it would drop focus mid-edit."""
	if not auto or not state:
		raise PreventUpdate
	props = _format_props(state, auto)
	# Values are set, not declared as outputs: they are _reduce's inputs, so an output
	# here would close a loop through builder-state that Dash refuses to register.
	for field in ctx.states_list[1]:
		value = props[field["id"]["key"]]["value"]
		if field.get("value") != value:
			set_props(field["id"], {"value": value})
	keys = [output["id"]["key"] for output in ctx.outputs_list[0]]
	columns = ([props[key][prop] for key in keys] for prop in ("placeholder", "disabled", "error"))
	return *columns, props["palette"]["data"]


clientside_callback(
	ClientsideFunction("deh", "clickEvent"),
	Output("builder-action", "data"),
	Input({"type": "chip-x", "shelf": ALL, "field": ALL}, "n_clicks"),
	Input({"type": "chip-send", "field": ALL, "from": ALL, "to": ALL}, "n_clicks"),
	Input({"type": "builder-kind", "kind": ALL}, "n_clicks"),
	Input({"type": "builder-mode", "mode": ALL}, "n_clicks"),
	Input("builder-clear", "n_clicks"),
	Input("builder-reset", "n_clicks"),
	Input({"type": "preset-pick", "id": ALL}, "n_clicks"),
	Input({"type": "preset-slot", "id": ALL, "choice": ALL}, "n_clicks"),
	Input({"type": "filter-mode", "field": ALL, "mode": ALL}, "n_clicks"),
	prevent_initial_call=True,
)

clientside_callback(
	ClientsideFunction("deh", "clickEvent"),
	Output("preset-delete-event", "data"),
	Input({"type": "preset-delete", "id": ALL, "scope": ALL}, "n_clicks"),
	prevent_initial_call=True,
)

clientside_callback(
	ClientsideFunction("deh", "clickEvent"),
	Output("builder-save-strip-event", "data"),
	Input("builder-save-strip", "n_clicks"),
	prevent_initial_call=True,
)


@callback(
	Output("builder-state", "data"),
	Output("builder-last-preset", "data"),
	Input("dnd-event", "data"),
	Input("builder-action", "data"),
	Input({"type": "chip-bin", "field": ALL}, "value"),
	Input({"type": "filter-pick", "field": ALL}, "value"),
	Input({"type": "filter-range", "field": ALL}, "value"),
	Input({"type": "builder-fmt", "key": ALL}, "value"),
	Input("builder-fmt-reset", "n_clicks"),
	State("builder-state", "data"),
	State("builder-project", "data"),
	State("builder-last-preset", "data"),
	State("builder-presets-local", "data"),
	State("builder-auto-titles", "data"),
	prevent_initial_call=True,
)
def _reduce(
	event,
	action,
	_bin_specs,
	_pick_values,
	_range_values,
	_format_values,
	_format_reset,
	state,
	project_data,
	last_preset,
	saved_local,
	auto,
):
	# A button click arrives as builder-action's id - the one Dash would have triggered.
	trigger = action["id"] if ctx.triggered_id == "builder-action" else ctx.triggered_id
	if trigger is None or not project_data or not state:
		raise PreventUpdate

	location = project_data["location"]
	try:
		frame, fields = services.builder_frame(location)
	except FileNotFoundError:
		raise PreventUpdate from None
	by_name = {item.name: item for item in fields}
	state = copy.deepcopy(state)
	_drop_unshelved_bins(state)

	match trigger:
		case "builder-clear":
			state["channels"] = {}
			return state, no_update

		case {"type": "builder-fmt", "key": key}:
			return _set_format(state, key, ctx.triggered[0]["value"], auto), no_update

		case "builder-fmt-reset":
			if not ctx.triggered[0]["value"] or "format" not in state:
				raise PreventUpdate
			del state["format"]
			return state, no_update

		case "builder-reset":
			if not last_preset:
				raise PreventUpdate
			return copy.deepcopy(last_preset["state"]), no_update

		case {"type": "builder-kind", "kind": kind}:
			state["kind"] = kind
			state, _dropped = figure.prune(state, figure.plot_type(kind).channels)
			return figure.seed_detail(state, fields), no_update

		case {"type": "builder-mode", "mode": mode}:
			state["measure_as"] = mode
			return state, no_update

		case {"type": "chip-x", "shelf": shelf, "field": name}:
			if shelf == FILTERS:
				state["filters"].pop(name, None)
			else:
				held = state["channels"].get(shelf, [])
				state["channels"][shelf] = [held_name for held_name in held if held_name != name]
			return state, no_update

		case {"type": "chip-bin", "field": name}:
			text = (ctx.triggered[0]["value"] or "").strip()
			bins = state.setdefault("bins", {})
			if bins.get(name, "") == text:
				raise PreventUpdate
			if text:
				bins[name] = text
			else:
				bins.pop(name, None)
			return state, no_update

		case {"type": "chip-send", "field": name, "from": source, "to": target}:
			return _apply_move(state, by_name, frame, name, source, target), no_update

		case "dnd-event":
			if not event:
				raise PreventUpdate
			moved = _apply_move(
				state, by_name, frame, event["field"], event.get("from") or PALETTE, event["shelf"]
			)
			return moved, no_update

		case {"type": "preset-pick", "id": pid}:
			preset = presets_mod.BY_ID.get(pid)
			project = services.load_project(location)
			if preset is not None:
				entry = {
					"id": preset.id,
					"name": preset.name,
					"state": presets_mod.resolve(preset, project),
				}
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

		case {"type": "preset-slot", "id": pid, "choice": choice}:
			preset = presets_mod.BY_ID.get(pid)
			if preset is None:
				raise PreventUpdate
			resolved = presets_mod.resolve(preset, services.load_project(location), choice)
			entry = {"id": preset.id, "name": f"{preset.name}: {choice}", "state": resolved}
			return copy.deepcopy(resolved), entry

		case {"type": "filter-mode", "field": name, "mode": mode}:
			if state["filters"].get(name, {}).get("mode") == mode:
				raise PreventUpdate
			if mode == "pick":
				state["filters"][name] = {"mode": "pick", "values": []}
			else:
				lo, hi = catalog.value_range(frame, name)
				state["filters"][name] = {"mode": "range", "lo": lo, "hi": hi}
			return state, no_update

		case {"type": "filter-pick", "field": name}:
			current = state["filters"].get(name, {}).get("values", [])
			new_values = ctx.triggered[0]["value"] or []
			if list(new_values) == list(current):
				raise PreventUpdate
			state["filters"][name] = {"mode": "pick", "values": list(new_values)}
			return state, no_update

		case {"type": "filter-range", "field": name}:
			entry = state["filters"].get(name, {})
			new_value = ctx.triggered[0]["value"]
			if not new_value or [entry.get("lo"), entry.get("hi")] == list(new_value):
				raise PreventUpdate
			state["filters"][name] = {"mode": "range", "lo": new_value[0], "hi": new_value[1]}
			return state, no_update

		case _:
			raise PreventUpdate


@callback(
	Output("preset-save-modal", "opened"),
	Output("preset-save-name", "value"),
	Output("preset-save-name", "error"),
	Output("preset-save-description", "value"),
	Output("builder-presets-local", "data"),
	Output("builder-presets-bump", "data"),
	Input("builder-save-head", "n_clicks"),
	Input("builder-save-strip-event", "data"),
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

	if trigger in ("builder-save-head", "builder-save-strip-event"):
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
	Input("preset-delete-event", "data"),
	State("builder-presets-local", "data"),
	State("builder-project", "data"),
	State("builder-presets-bump", "data"),
	prevent_initial_call=True,
)
def _delete_preset(event, saved_local, project_data, bump):
	pid, scope = event["id"]["id"], event["id"]["scope"]

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
	if not _clicks or not fig:
		raise PreventUpdate
	title = (fig["layout"].get("title") or {}).get("text") or (
		last_preset["name"] if last_preset else "Untitled plot"
	)
	project_name = services.load_project(project_data["location"]).project_name
	filename = f"{project_name}__{title}".lower().replace(" ", "-")
	return True, {"figure": fig, "title": title}, filename
