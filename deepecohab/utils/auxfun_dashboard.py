import datetime as dt
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Literal

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import polars as pl
from dash import dcc, exceptions, html

from deepecohab.core.registries import df_registry, plot_registry

COMMON_CFG = {"displayModeBar": False}


def generate_settings_block(
	phase_type_id: dict | str,
	aggregate_stats_id: dict | str,
	slider_id: dict | str,
	slider_switch_id: dict | str,
	days_range: list[int],
	position_switch_id: dict | str | None = None,
	pairwise_switch_id: dict | str | None = None,
	sociability_switch_id: dict | str | None = None,
	ranking_switch_id: dict | str | None = None,
	include_download: bool = False,
	comparison_layout: bool = False,
) -> html.Div:
	"""Generates settings block for the dashboard tabs"""
	block = html.Div(
		[
			html.Div(
				[
					html.Div(
						[
							dcc.RadioItems(
								id=phase_type_id,
								options=[
									{"label": "All", "value": "all"},
									{"label": "Dark", "value": "dark_phase"},
									{"label": "Light", "value": "light_phase"},
								],
								value="all",
								className="dash-radio",
							)
						],
					),
					html.Div(className="divider"),
					html.Div(
						[
							dcc.RadioItems(
								id=aggregate_stats_id,
								options=[
									{"label": "Sum", "value": "sum"},
									{"label": "Mean", "value": "mean"},
								],
								value="sum",
								className="dash-radio",
							)
						],
					),
					*(
						[
							html.Div(className="divider"),
							html.Div(
								dcc.RadioItems(
									id=slider_switch_id,
									options=[
										{"label": "Range", "value": f"{slider_id}_range"},
										{"label": "Single", "value": f"{slider_id}_single"},
									],
									value=f"{slider_id}_range",
									className="dash-radio",
								),
							),
						]
						if not comparison_layout
						else []
					),
					html.Div(className="divider"),
					html.Div(
						id=f"{slider_id}_range_container"
						if isinstance(slider_id, str)
						else slider_id[0],
						children=[
							html.Label("Days of experiment", className="slider-label"),
							dcc.RangeSlider(
								id=f"{slider_id}_range"
								if isinstance(slider_id, str)
								else slider_id[1],
								min=days_range[0],
								max=days_range[1],
								value=[*days_range],
								pushable=1,
								step=1,
								marks={i: str(i) for i in days_range},
								tooltip={
									"placement": "bottom",
									"always_visible": True,
								},
								updatemode="mouseup",
								included=True,
								vertical=False,
								persistence=True,
								persistence_type="session",
								allow_direct_input=False,
								className="dash-slider",
							),
						],
						className="flex-container",
						hidden=False,
					),
					html.Div(
						id=f"{slider_id}_single_container",
						children=[
							html.Label("Days of experiment", className="slider-label"),
							dcc.Slider(
								id=f"{slider_id}_single",
								min=days_range[0],
								max=days_range[1],
								value=days_range[0],
								step=1,
								marks={i: str(i) for i in days_range},
								tooltip={
									"placement": "bottom",
									"always_visible": True,
								},
								updatemode="mouseup",
								included=False,
								vertical=False,
								persistence=False,
								allow_direct_input=False,
								className="dash-slider",
							),
						],
						className="flex-container",
						hidden=True,
					),
					# Conditional block
					*(
						[
							html.Div(className="divider"),
							html.Div(
								[
									dbc.Container(
										[
											html.Button(
												[
													html.I(
														className="fa-solid fa-download fa-lg me-2"
													),
													"Downloads",
												],
												id="open-modal",
												n_clicks=0,
												className="DownloadButton",
											),
											generate_download_block(),
										]
									),
								],
								className="download-row",
							),
						]
						if include_download
						else []
					),
					*(
						[
							html.Div(className="divider"),
							generate_radio_switch(
								position_switch_id,
								[
									{"label": "Visits", "value": "visits"},
									{"label": "Time", "value": "time"},
								]
							),
							generate_radio_switch(
								pairwise_switch_id,
								[
									{"label": "Visits", "value": "pairwise_encounters"},
									{"label": "Time", "value": "time_together"},
								]
							),
							generate_radio_switch(
								sociability_switch_id,
								[
									{
										"label": "Time together",
										"value": "proportion_together",
									},
									{
										"label": "Incohort sociability",
										"value": "sociability",
									},
								]
							),
							generate_radio_switch(
								ranking_switch_id,
								[
									{"label": "In time", "value": "intime"},
									{"label": "Day stability", "value": "stability"},
								]
							)
						]
						if comparison_layout
						else []
					),
				],
				className="centered-container",
			),
		],
		className="header-bar",
	)

	return block


def generate_comparison_block(side: str, days_range: list[int]) -> html.Div:
	""" "Generates a side of a comparisons block"""
	return html.Div(
		[
			html.Label("Select Plot", style={"fontWeight": "bold"}),
			dcc.Dropdown(
				id={"type": "plot-dropdown", "side": side},
				options=get_options_from_ids(plot_registry.list_available()),
				value="ranking-line",
			),
			html.Div(
				[
					dcc.Graph(
						id={"figure": "comparison-plot", "side": side},
						config=COMMON_CFG,
						className="plot-600",
					),
				]
			),
			generate_settings_block(
				phase_type_id={"type": "phase_type", "side": side},
				aggregate_stats_id={"type": "agg_switch", "side": side},
				slider_id=[
					{"type": "days_range_container", "side": side},
					{"type": "days_range", "side": side},
				],
				slider_switch_id={"type": "slider_switch", "side": side},
				days_range=days_range,
				position_switch_id={"type": "position_switch", "side": side},
				pairwise_switch_id={"type": "pairwise_switch", "side": side},
				sociability_switch_id={"type": "sociability_switch", "side": side},
				ranking_switch_id={"type": "ranking_switch", "side": side},
				comparison_layout=True,
			),
			get_fmt_download_buttons(
				"download-btn-comparison",
				["svg", "png", "json"],
				side,
				is_vertical=False,
			),
			dcc.Download(id={"downloader": "download-component-comparison", "side": side}),
		],
		className="h-100 p-2",
	)


def generate_plot_download_tab() -> dcc.Tab:
	"""Generates Plots download tab in the Downloads modal component"""  # TODO: Add select all
	return dcc.Tab(
		id="download_tab",
		label="Plots",
		value="tab-plots",
		className="dash-tab",
		selected_className="dash-tab--selected",
		children=[
			dbc.Row(
				[
					dbc.Col(
						[
							dbc.Checkbox(
								id={"type": "select-all", "index": "plots"},
								label="Select All",
								value=False,
								className="mb-2 fw-bold",
							),
							dbc.Checklist(
								id={"type": "main-checklist", "index": "plots"},
								options=[],
								value=[],
								inline=False,
								className="download-dropdown",
							),
						],
						width=8,
					),
					dbc.Col(
						get_fmt_download_buttons("download-btn", ["svg", "png", "json"], "plots"),
						width=4,
						className="d-flex flex-column align-items-start",
					),
				],
				className="modal-download-content",
			)
		],
	)


def generate_csv_download_tab() -> dcc.Tab:
	"""Generates DataFrames download tab in the Downloads modal component"""
	options = get_options_from_ids(df_registry.list_available(), "_", delist=["binary_df"])

	return dcc.Tab(
		label="DataFrames",
		value="tab-dataframes",
		className="dash-tab",
		selected_className="dash-tab--selected",
		children=[
			dbc.Row(
				[
					dbc.Col(
						[
							dbc.Checkbox(
								id={"type": "select-all", "index": "dfs"},
								label="Select All",
								value=False,
								className="mb-2 fw-bold",
							),
							dbc.Checklist(
								id={"type": "main-checklist", "index": "dfs"},
								options=options,
								value=[],
								inline=False,
								className="download-dropdown",
							),
						],
						align="center",
						width=8,
					),
					dbc.Col(
						[
							dbc.Button(
								"Download DataFrame/s",
								id={
									"type": "download-btn",
									"fmt": "csv",
									"side": "dfs",
								},
								n_clicks=0,
								color="primary",
								className="ModalButton",
							)
						],
						width=4,
						align="center",
						className="d-flex flex-column align-items-start",
					),
				]
			)
		],
	)


def generate_download_block() -> dbc.Modal:
	"""Generate Downloads modal component"""
	modal = dbc.Modal(
		[
			dbc.ModalHeader([dbc.ModalTitle("Downloads", className="fw-bold")]),
			dbc.ModalBody(
				dcc.Tabs(
					id="download-tabs",
					value="tab-plots",
					children=[
						generate_plot_download_tab(),
						generate_csv_download_tab(),
					],
					className="modal-tabs-size",
				),
			),
			dcc.Download(id="download-component"),
		],
		id="modal",
		is_open=False,
	)

	return modal


def generate_sidebar(icon_map: dict[str, str], page_registry: dict[str, str], tooltips: list[str]) -> html.Div:
	return html.Div(
		[
			html.Div("MENU", className="sidebar-label"),
			html.Div(
				[
					dcc.Link(
						html.Button(
							html.I(className=icon_map.get(page["relative_path"], "fas fa-file")),
							title=tooltip,
							className="icon-btn",
						),
						href=page["relative_path"],
						className="nav-link-wrapper",
					)
					for page, tooltip in zip(page_registry.values(), tooltips)
				],
				className="tab-buttons",
			),
		],
		id="sidebar",
	)

def generate_radio_switch(switch_id: dict, switch_options: list[dict]) -> html.Div:
	return html.Div(
		id={
			"container": switch_id["type"],
			"side": switch_id["side"],
		},
		hidden=True,
		className="flex-container",
		children=[
			html.Div(
				dcc.RadioItems(
					id=switch_id,
					inline=True,
					options=switch_options,
					value=switch_options[0]['value'],
					className="dash-radio",
				),
			),
		],
	)


def generate_standard_graph(graph_id: str, css_class: str = "plot-450", **kwargs) -> html.Div:
	"""Generate Div that contains graph and corresponding data"""
	animate = kwargs.get("animate", False)
	return html.Div(
		[
			dcc.Graph(
				id={"type": "graph", "name": graph_id},
				animate=animate,
				className=css_class,
				config=COMMON_CFG,
			),
		],
		className=css_class,
	)


def get_options_from_ids(
	obj_ids: list[str], sep: str = "-", delist: list[str] = []
) -> list[dict[str, str]]:
	"""Generate options in the Downloads -> Plots tab from available IDs"""
	return [
		{"label": get_display_name(obj_id, sep), "value": obj_id}
		for obj_id in obj_ids
		if obj_id not in delist
	]


def get_display_name(name: str, sep: str = "-") -> str:
	"""Helper to beautify option names for Downloads -> Plots tab"""
	return " ".join(word.capitalize() for word in name.split(sep))


def get_fmt_download_buttons(type: str, fmts: list, side: str, is_vertical: bool = True) -> dbc.Row:
	"""Generate buttons for Downloads -> Plot tab"""
	buttons: list[dbc.Col] = []
	width_col = 12
	if not is_vertical:
		width_col = 12 // len(fmts)
	for fmt in fmts:
		btn = dbc.Button(
			f"Download {fmt.upper()}",
			id={"type": type, "fmt": fmt, "side": side},
			n_clicks=0,
			color="primary",
			className="ModalButton",
		)
		buttons.append(dbc.Col(btn, width=width_col))
	return dbc.Row(buttons)

def get_plot_file(
	figure: go.Figure,
	fmt: Literal["json", "png", "svg"],
	plot_name: str,
) -> bytes:
	"""Helper for content download"""
	match fmt:
		case "svg":
			content = figure.to_image(format="svg")
			return (f"{plot_name}.svg", content)
		case "png":
			content = figure.to_image(format="png")
			return (f"{plot_name}.png", content)
		case "json":
			content = json.dumps(figure.to_plotly_json()).encode("utf-8")
			return (f"{plot_name}.json", content)
		case _:
			raise exceptions.PreventUpdate


def download_plots(
	selected_plots: list[str],
	fmt: str,
	all_figures: list[go.Figure],
	all_ids: list[dict],
) -> dict[str, Any | None]:
	"""Downloads chosen plot/s related object via the browser"""
	if not selected_plots or not fmt:
		raise exceptions.PreventUpdate

	files: list[bytes] = []

	for fig_id, fig in zip(all_ids, all_figures):
		plot_id = fig_id["name"]
		if plot_id not in selected_plots or fig is None:
			continue
		figure = go.Figure(fig)
		plot_name = f"plot_{plot_id}"
		plt_file = get_plot_file(figure, fmt, plot_name)
		files.append(plt_file)

	if len(files) == 1:
		fname, content = files[0]
		return dcc.send_bytes(lambda b: b.write(content), filename=fname)

	elif len(files) > 1:
		zip_buffer = io.BytesIO()
		with zipfile.ZipFile(zip_buffer, "w") as zf:
			for fname, content in files:
				zf.writestr(fname, content)
		zip_buffer.seek(0)
		return dcc.send_bytes(lambda b: b.write(zip_buffer.read()), filename=f"plots_{fmt}.zip")

	else:
		raise exceptions.PreventUpdate


def build_filter_expr(
	columns: list[str],
	days_range: list[int] = None,
	phase_type: list[str] = None,
) -> pl.Expr:
	"Builds filtering expressions for DF download by checking column presence"
	exprs: list[pl.Expr] = []

	if days_range is not None and "day" in columns:
		exprs.append(pl.col("day").is_between(*days_range, closed="both"))

	if phase_type is not None and "phase" in columns:
		exprs.append(pl.col("phase").is_in(phase_type))

	if not exprs:
		return None

	return exprs


def download_dataframes(
	selected_dfs: list[pl.DataFrame],
	phase_type: list[str],
	days_range: list[int],
	store: dict,
) -> dict[str, Any | None]:
	"""Downloads the selected DataFrame/s via the browser"""
	if not selected_dfs:
		raise exceptions.PreventUpdate

	phase_type = [phase_type] if not phase_type == "all" else ["dark_phase", "light_phase"]

	if len(selected_dfs) == 1:
		name = selected_dfs[0]
		if name in store:
			df = store[name]
			expr = build_filter_expr(df.schema, days_range, phase_type)
			df = df.filter(expr) if expr is not None else df
			return dcc.send_string(df.write_csv, f"{name}.csv")
		return None

	zip_buffer = io.BytesIO()
	with zipfile.ZipFile(zip_buffer, "w") as zf:
		for name in selected_dfs:
			if name in store:
				df = store[name]
				expr = build_filter_expr(df.schema, days_range, phase_type)
				df = df.filter(expr) if expr is not None else df
				csv_bytes = df.write_csv().encode("utf-8")
				zf.writestr(f"{name}.csv", csv_bytes)

	zip_buffer.seek(0)

	return dcc.send_bytes(
		lambda b: b.write(zip_buffer.getvalue()), filename="selected_dataframes.zip"
	)

def _is_valid_time(time_str: str) -> bool:
	"""Helper to check if provided time a valid time."""
	try:
		dt.datetime.strptime(time_str, "%H:%M")
		return True
	except (ValueError, TypeError):
		return False


def _get_status(idx: str, input: str) -> bool:
	"""Helper to validate required inputs."""
	if not (input and input.strip()):
		return False

	if idx == "proj-loc":
		try:
			Path(input)
			return True
		except OSError:
			return False

	if idx == "data-loc":
		return Path(input).is_dir()

	if idx in ["light-start", "dark-start"]:
		return _is_valid_time(input)

	return True
