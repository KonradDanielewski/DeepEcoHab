from typing import (
	Any,
	Literal,
)

import dash
import plotly.graph_objects as go
import plotly.express as px
import polars as pl
from dash import (
	callback,
	clientside_callback,
	ctx,
	dcc,
	html,
	no_update
)
from dash.dependencies import (
	ALL,
	MATCH,
	Input,
	Output,
	State,
)

from deepecohab.app.page_layouts import cohort_dashboard_layout
from deepecohab.core.registries import plot_registry
from deepecohab.plotting import plot_catalog
from deepecohab.utils import (
	auxfun_dashboard,
	auxfun_plots,
	cache_config,
)

dash.register_page(__name__, path="/cohort_dashboard", name="Cohort Dashboard")

layout = html.Div(
	[
		dcc.Tabs(
			id="tabs",
			value="tab-dashboard",
			children=[
				dcc.Tab(
					label="Dashboard",
					value="tab-dashboard",
					className="dash-tab",
					selected_className="dash-tab--selected",
					children=html.Div(id="dynamic-graphs-container"),
				),
				dcc.Tab(
					label="Plots Comparison",
					value="tab-other",
					className="dash-tab",
					selected_className="dash-tab--selected",
					children=html.Div(id="dynamic-comparison-container"),
				),
			],
		)
	]
)


@callback(
	[
		Output("dynamic-graphs-container", "children"),
		Output("dynamic-comparison-container", "children"),
	],
	Input("project-config-store", "data"),
)
def render_graphs_layout(cfg: dict[str, Any]) -> tuple[html.Div, html.Div]:
	"""Render page layout for both tabs"""
	if not cfg:
		return html.Div("Please load a project to see graphs."), no_update

	current_days_range = cfg.get("days_range", [0, 1])

	dashboard_layout = cohort_dashboard_layout.generate_graphs_layout(current_days_range)
	comparison_tab = cohort_dashboard_layout.generate_comparison_layout(current_days_range)

	return dashboard_layout, comparison_tab

@callback(
	Output({"type": "graph", "name": MATCH}, "figure"),
	[
		Input("days_range", "value"),
		Input("days_single", "value"),
		Input("phase_type", "value"),
		Input("agg_switch", "value"),
		Input("position_switch", "value"),
		Input("pairwise_switch", "value"),
		Input("sociability_switch", "value"),
		Input("ranking_switch", "value"),
		Input("slider_switch", "value"),
		Input("cmap_dropdown", "value"),
	],
	State("project-config-store", "data"),
)
def update_plots(
	days_range: list[int],
	days_single: int,
	phase_type: str,
	agg_switch: str,
	pos_switch: str,
	pair_switch: str,
	sociability_switch: str,
	ranking_switch: str,
	slider_mode: Literal["days_single", "days_range"],
	scale: str, 
	cfg: dict[str, Any]
) -> tuple[go.Figure, dict]:
	(
		"""Performs selective plot update on the main layout

	Args:
		days_range: range of days selected on the RangeSlider.
		days_single: day selected on the single Slider.
		phase_type: type of phase chosed (light, dark or all).
		agg_switch: aggregation switch (sum or mean).
		pos_switch: activity bar/box plot switch (visits or time spent).
		pair_switch: pairwise meetings plot switch (encounters or time together).
		sociability_switch: sociability plot switch (proportion together or incohort sociability)
		ranking_switch: ranking switch (per hour update or per day rank)
		slider_mode: toogle for which slider type is visible
		cfg: config of the loaded project

	Returns:
		Figures affected by the activated switch/slider etc.
	"""
		""""""
	)
	plot_name: str = ctx.outputs_grouping["id"]["name"]
	plot_attributes = plot_registry.get_dependencies(plot_name)

	id_check = (
		"days_range"
		if ctx.triggered_id == "days_single"
		else None
		if ctx.triggered_id == "slider_switch"
		else ctx.triggered_id
	)

	if id_check is not None and id_check not in plot_attributes and id_check != 'cmap_dropdown':
		return no_update
	
	if slider_mode == "days_single":
		days_range = [days_single, days_single]

	phase_list: list[str] = [phase_type] if phase_type != "all" else ["dark_phase", "light_phase"]

	cfg_tuple = tuple(sorted(cfg.items())) if cfg else ()
	store = cache_config.get_project_data(cfg_tuple)

	store = cache_config.get_project_data(cfg)
	animals = cfg.get("animal_ids")
	animal_colors = auxfun_plots.color_sampling(animals, scale)
	positions = cfg.get("positions")
	positions_colors = auxfun_plots.color_sampling(positions, scale)
	cages = cfg.get("cages")
	ligt_dark_onset = {
		name: int(parts[0]) + int(parts[1]) / 60
		for name, time in cfg.get('phase').items()
		for parts in [time.split(":")]
	}

	plot_cfg = plot_catalog.PlotConfig(
		store=store,
		days_range=days_range,
		phase_type=phase_list,
		agg_switch=agg_switch,
		position_switch=pos_switch,
		pairwise_switch=pair_switch,
		sociability_switch=sociability_switch,
		ranking_switch=ranking_switch,
		animals=animals,
		animal_colors=animal_colors,
		cages=cages,
		positions=positions,
		position_colors=positions_colors,
		ligt_dark_onset=ligt_dark_onset,
	)

	fig = plot_registry.get_plot(plot_name, plot_cfg)

	return fig



@callback(
	[
		Output({"figure": "comparison-plot", "side": MATCH}, "figure"),
		Output({"container": "position_switch", "side": MATCH}, "hidden"),
		Output({"container": "pairwise_switch", "side": MATCH}, "hidden"),
		Output({"container": "sociability_switch", "side": MATCH}, "hidden"),
		Output({"container": "ranking_switch", "side": MATCH}, "hidden"),
	],
	Input({"type": ALL, "side": MATCH}, "value"),
	State("project-config-store", "data"),
)
def update_comparison_plot(switches: list[Any], cfg: dict[str, Any]) -> tuple[go.Figure, dict]:
	"""Render plots in the comparisons tab"""
	input_dict: dict[str, Any] = {
		item["id"]["type"]: val for item, val in zip(ctx.inputs_list[0], switches)
	}

	plot_attributes = plot_catalog.plot_registry.get_dependencies(input_dict["plot-dropdown"])

	phase_type: list[str] = (
		[input_dict["phase_type"]]
		if not input_dict["phase_type"] == "all"
		else ["dark_phase", "light_phase"]
	)

	store = cache_config.get_project_data(cfg)
	animals = cfg["animal_ids"]
	animal_colors = auxfun_plots.color_sampling(animals)
	cages = cfg["cages"]
	positions = cfg["positions"]
	positions_colors = auxfun_plots.color_sampling(animals)
	ligt_dark_onset = {
		name: int(parts[0]) + int(parts[1]) / 60
		for name, time in cfg.get('phase').items()
		for parts in [time.split(":")]
	}

	plot_cfg = plot_catalog.PlotConfig(
		store=store,
		days_range=input_dict["days_range"],
		phase_type=phase_type,
		agg_switch=input_dict["agg_switch"],
		position_switch=input_dict["position_switch"],
		pairwise_switch=input_dict["pairwise_switch"],
		sociability_switch=input_dict["sociability_switch"],
		ranking_switch=input_dict["ranking_switch"],
		animals=animals,
		animal_colors=animal_colors,
		cages=cages,
		positions=positions,
		position_colors=positions_colors,
		ligt_dark_onset=ligt_dark_onset,
	)

	fig = plot_catalog.plot_registry.get_plot(input_dict["plot-dropdown"], plot_cfg)

	pairwise_hidden = "pairwise_switch" not in plot_attributes
	position_hidden = "position_switch" not in plot_attributes
	sociability_hidden = "sociability_switch" not in plot_attributes
	ranking_hidden = "ranking_switch" not in plot_attributes

	return (
		fig,
		position_hidden,
		pairwise_hidden,
		sociability_hidden,
		ranking_hidden,
	)


@callback(
	Output("download-component", "data"),
	Input({"type": "download-btn", "fmt": ALL, "side": ALL}, "n_clicks"),
	[
		State({"type": "main-checklist", "index": "dfs"}, "value"),
		State({"type": "main-checklist", "index": "plots"}, "value"),
		State("phase_type", "value"),
		State("days_range", "value"),
		State({"type": "graph", "name": ALL}, "figure"),
		State({"type": "graph", "name": ALL}, "id"),
		State("project-config-store", "data"),
	],
	prevent_initial_call=True,
)
def download_selected_data(
	btn_clicks: int,
	selected_dfs: list[pl.DataFrame],
	selected_plots: list[str],
	phase_type: str,
	days_range: list[int],
	all_figures: list[dict],
	all_ids: list[dict],
	cfg: dict[str, Any],
) -> dict[str, Any | None]:
	"""Triggers download from the Downloads modal component"""
	triggered = ctx.triggered_id
	if not triggered:
		raise dash.exceptions.PreventUpdate

	if triggered["side"] == "dfs":
		store = cache_config.get_project_data(cfg)
		return auxfun_dashboard.download_dataframes(selected_dfs, phase_type, days_range, store)
	elif triggered["side"] == "plots":
		return auxfun_dashboard.download_plots(
			selected_plots,
			triggered["fmt"],
			all_figures,
			all_ids,
		)
	else:
		raise dash.exceptions.PreventUpdate

@callback(
	Output("color-settings-modal", "is_open"),
	Input("open-color-settings", "n_clicks"),
	State("color-settings-modal", "is_open"),
	prevent_initial_call=True,
)
def toggle_color_settings(n_clicks, is_open):
	return not is_open


@callback(
	Output({"downloader": "download-component-comparison", "side": MATCH}, "data"),
	Input({"type": "download-btn-comparison", "fmt": ALL, "side": MATCH}, "n_clicks"),
	[
		State({"figure": "comparison-plot", "side": MATCH}, "figure"),
		State({"type": "plot-dropdown", "side": MATCH}, "value"),
	],
	prevent_initial_call=True,
)
def download_comparison_data(btn_click: int, figure: dict, plot_type: str) -> dict[str, Any | None]:
	"""Triggers download from the comparisons tab"""
	triggered = ctx.triggered_id
	if not triggered:
		raise dash.exceptions.PreventUpdate

	figure = go.Figure(figure)
	if figure is None:
		raise dash.exceptions.PreventUpdate

	plot_name = f"comparison_{plot_type}"
	fname, content = auxfun_dashboard.get_plot_file(figure, triggered["fmt"], plot_name)
	return dcc.send_bytes(lambda b: b.write(content), filename=fname)


clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="handle_slider_mode"),
	[
		Output("days_range_container", "hidden"),
		Output("days_single_container", "hidden"),
		Output("agg_switch", "value"),
		Output("agg_switch", "disabled"),
		Output("agg_switch", "className"),
	],
	Input("slider_switch", "value"),
)

clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="sync_select_all"),
	[
		Output({"type": "main-checklist", "index": MATCH}, "value"),
		Output({"type": "select-all", "index": MATCH}, "value"),
	],
	[
		Input({"type": "select-all", "index": MATCH}, "value"),
		Input({"type": "main-checklist", "index": MATCH}, "value"),
	],
	State({"type": "main-checklist", "index": MATCH}, "options"),
)

clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="toggle_modal"),
	[
		Output("modal", "is_open"),
		Output({"type": "main-checklist", "index": "plots"}, "options"),
	],
	Input("open-modal", "n_clicks"),
	[
		State("modal", "is_open"),
		State({"type": "graph", "name": ALL}, "id"),
	],
	prevent_initial_call=True,
)
