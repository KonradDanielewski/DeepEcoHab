"""DeepEcoHab GUI: a Dash + dash-mantine-components app.

``create_app()`` builds the app; nothing runs at import time so the module stays safe to
import from a WSGI server (``server = create_app().server``).
"""

import logging
from importlib.metadata import version

import dash
import dash_mantine_components as dmc
import diskcache
from dash import ALL, Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from deepecohab.app import downloads, services
from deepecohab.app.components import export_dialog, export_preview, icon

#: Shade 6 is the light-theme accent, shade 4 the dark one; the rest interpolate the tokens.
_ACCENT = [
	"#e0f1f3",
	"#c0e3e8",
	"#98d3dc",
	"#6fcbd9",
	"#45b5c8",
	"#2a9aad",
	"#1a7f91",
	"#146a79",
	"#0f5561",
	"#0a3f48",
]


def create_app() -> Dash:
	"""Build the Dash application; call once per process."""
	background_callback_manager = dash.DiskcacheManager(diskcache.Cache(services.CACHE_DIR))
	app = Dash(
		__name__,
		use_pages=True,
		suppress_callback_exceptions=True,
		background_callback_manager=background_callback_manager,
		title="DeepEcoHab",
	)
	app.layout = _layout()
	app.server.register_blueprint(downloads.bp)
	_register_callbacks(app)

	if not services.kaleido_ok():
		# ponytail: logs only, rather than threading a disabled-state into every export
		# button - kaleido.get_chrome_sync() fetches its own Chrome automatically, so a
		# real user hitting this needs a working network first anyway. Wire it into the
		# UI if that assumption stops holding.
		logging.getLogger(__name__).warning(
			"kaleido has no Chrome to render exports through; Download in the export "
			"dialog will fail until `kaleido.get_chrome_sync()` can fetch one."
		)

	return app


def _layout() -> dmc.MantineProvider:
	return dmc.MantineProvider(
		id="mantine-provider",
		defaultColorScheme="auto",
		# ty: DMC's stub types colors as dict-of-dicts; Mantine needs a list of 10 shades.
		theme={  # ty: ignore[invalid-argument-type]
			"primaryColor": "accent",
			"primaryShade": {"light": 6, "dark": 4},
			"colors": {"accent": _ACCENT},  # ty: ignore[invalid-argument-type]
			"fontFamily": "Geist, Segoe UI, system-ui, sans-serif",
			"fontFamilyMonospace": "Geist Mono, ui-monospace, Cascadia Mono, Consolas, monospace",
			"fontSizes": {"xs": "12px", "sm": "13px", "md": "14px", "lg": "16px", "xl": "20px"},
			"radius": {"xs": "4px", "sm": "6px", "md": "8px", "lg": "12px", "xl": "16px"},
			"defaultRadius": "md",
		},
		children=[
			dcc.Location(id="url", refresh=False),
			dcc.Store(id="theme-store", storage_type="local"),
			dcc.Store(id="nav-collapsed", storage_type="local", data=False),
			dcc.Store(id="project-paths", storage_type="local", data=[]),
			# Above Dash's debug bar (z-index 10000), which sits where toasts appear.
			dmc.NotificationContainer(id="notifications", zIndex=10001),
			# Shared by every page rather than duplicated per page: only one page is ever
			# mounted at a time, and each page's own "open" callback drives it by id.
			export_dialog(),
			dmc.AppShell(
				id="app-shell",
				layout="alt",
				navbar={"width": 232, "breakpoint": "sm", "collapsed": {"mobile": True}},
				header={"height": 56},
				padding=24,
				children=[
					dmc.AppShellNavbar(_navbar(), className="deh-nav", bg="var(--surface)"),
					dmc.AppShellHeader(_topbar(), bg="var(--surface)"),
					dmc.AppShellMain(dash.page_container),
				],
			),
		],
	)


def _nav_item(label: str, left_section, tip_index: str, tooltip: str = "", **kwargs) -> dmc.Tooltip:
	return dmc.Tooltip(
		dmc.NavLink(label=label, leftSection=left_section, className="deh-nav-item", **kwargs),
		id={"type": "nav-tip", "index": tip_index},
		label=tooltip or label,
		position="right",
		offset=12,
		disabled=True,
		boxWrapperProps={"w": "100%"},
		classNames={"tooltip": "deh-tooltip"},
	)


def _navbar() -> list:
	pages = [
		_nav_item(
			page["name"],
			icon(page["icon"], size=20),
			page["path"],
			id={"type": "nav-link", "index": page["path"]},
			href=page["relative_path"],
		)
		for page in dash.page_registry.values()
	]
	collapse = _nav_item(
		"Collapse",
		[
			icon("layout-sidebar-left-collapse", size=20, class_name="deh-when-expanded"),
			icon("layout-sidebar-left-expand", size=20, class_name="deh-when-collapsed"),
		],
		"collapse",
		tooltip="Expand sidebar",
		id="nav-collapse-btn",
	)
	brand_text = html.Span(
		[html.B("DeepEcoHab"), html.Br(), html.Small(f"{version('deepecohab')} · local")],
		className="deh-brand-text",
	)
	return [
		html.Div(
			[icon("brand", size=26, color="var(--accent)"), brand_text], className="deh-brand"
		),
		html.Div("Workspace", className="deh-nav-section"),
		*pages,
		html.Div(collapse, className="deh-nav-foot"),
	]


def _topbar() -> html.Div:
	return html.Div(
		[
			dmc.Burger(id="burger", opened=False, size="sm", hiddenFrom="sm"),
			html.Div(id="crumbs", className="deh-crumbs"),
			html.Button(
				[icon("moon", class_name="deh-moon"), icon("sun", class_name="deh-sun")],
				id="theme-toggle",
				className="deh-icon-btn",
				**{"aria-label": "Toggle colour theme"},  # ty: ignore[invalid-argument-type]
			),
		],
		className="deh-topbar",
	)


def _register_callbacks(app: Dash) -> None:
	app.clientside_callback(
		"""function () {
			const dark = document.documentElement.getAttribute("data-mantine-color-scheme") === "dark";
			return dark ? "light" : "dark";
		}""",
		Output("theme-store", "data"),
		Input("theme-toggle", "n_clicks"),
		prevent_initial_call=True,
	)

	app.clientside_callback(
		"function (theme) { return theme || window.dash_clientside.no_update; }",
		Output("mantine-provider", "forceColorScheme"),
		Input("theme-store", "data"),
	)

	app.clientside_callback(
		"function (nClicks, collapsed) { return !collapsed; }",
		Output("nav-collapsed", "data"),
		Input("nav-collapse-btn", "n_clicks"),
		State("nav-collapsed", "data"),
		prevent_initial_call=True,
	)

	app.clientside_callback(
		"""function (collapsed, mobileOpened) {
			const tips = window.dash_clientside.callback_context.outputs_list[2];
			return [
				{width: collapsed ? 64 : 232, breakpoint: "sm", collapsed: {mobile: !mobileOpened}},
				collapsed ? "nav-collapsed" : null,
				tips.map(() => !collapsed),
			];
		}""",
		Output("app-shell", "navbar"),
		Output("app-shell", "mod"),
		Output({"type": "nav-tip", "index": ALL}, "disabled"),
		Input("nav-collapsed", "data"),
		Input("burger", "opened"),
	)

	@app.callback(
		Output({"type": "nav-link", "index": ALL}, "active"),
		Output("crumbs", "children"),
		Output("burger", "opened"),
		Input("url", "pathname"),
	)
	def _sync_page(pathname):
		page = next((p for p in dash.page_registry.values() if p["path"] == pathname), None)
		active = [output["id"]["index"] == pathname for output in dash.ctx.outputs_list[0]]
		return active, html.B(page["name"] if page else "Not found"), False

	# The export dialog is shared shell UI (see _layout above); its behaviour does not
	# depend on which page opened it, so it registers once here rather than once per
	# page - only the "which plot" open callback differs, and lives on each page.
	@app.callback(
		Output("export-width", "value"),
		Input("export-width-preset", "value"),
		prevent_initial_call=True,
	)
	def _export_width_preset(preset):
		if preset == "custom":
			raise PreventUpdate
		return int(preset)

	@app.callback(
		Output("export-dialog", "opened", allow_duplicate=True),
		Input("export-cancel", "n_clicks"),
		prevent_initial_call=True,
	)
	def _close_export(_clicks):
		return False

	@app.callback(
		Output("export-preview", "figure"),
		Output("export-dims", "children"),
		Output("export-warnings", "children"),
		Output("export-dpi-field", "style"),
		Output("export-events", "disabled"),
		Output("export-csv", "disabled"),
		Output("export-submit", "children"),
		Output("export-field-figure", "value"),
		Output("export-field-params", "value"),
		Input("export-source", "data"),
		Input("export-style", "value"),
		Input("export-format", "value"),
		Input("export-width", "value"),
		Input("export-height", "value"),
		Input("export-pt", "value"),
		Input("export-dpi", "value"),
		Input("export-legend", "checked"),
		Input("export-title-toggle", "checked"),
		Input("export-events", "checked"),
		Input("export-csv", "checked"),
		Input("export-filename", "value"),
		prevent_initial_call=True,
	)
	def _render_export(
		source, style, fmt, width, height, pt, dpi, legend, title_on, events, csv, filename
	):
		if not source:
			raise PreventUpdate
		form = {
			"style": style,
			"format": fmt,
			"width_mm": float(width or 85),
			"height_mm": float(height or 64),
			"pt": float(pt or 8),
			"dpi": int(dpi or 300),
			"legend": bool(legend),
			"title_on": bool(title_on),
			"events": bool(events),
			"csv": bool(csv),
			"filename": filename or "plot",
		}
		result = export_preview(source["figure"], source["title"], form)
		label = [
			icon("download", size=15),
			f"Download {fmt.upper()}{' + CSV' if form['csv'] and result['has_csv'] else ''}",
		]
		return (
			result["figure"],
			result["dims"],
			result["warnings"],
			{} if fmt == "png" else {"display": "none"},
			not result["has_events"],
			not result["has_csv"],
			label,
			result["payload_figure"],
			result["payload_params"],
		)
