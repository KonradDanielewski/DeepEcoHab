from typing import Any
import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import polars as pl
import plotly.graph_objects as go
from dash import ctx, dcc, html, no_update
from dash.dependencies import ALL, MATCH, Input, Output, State

from deepecohab.dash import dash_layouts, dash_plotting
from deepecohab.utils import (
	auxfun,
	auxfun_dashboard,
	auxfun_plots,
)


# Initialize the Dash app
app = dash.Dash(
	__name__,
	suppress_callback_exceptions=True,
	external_stylesheets=[
		"/assets/styles.css",
		dbc.icons.FONT_AWESOME,
		dbc.themes.BOOTSTRAP,
		"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
	],
)

app.title = "EcoHAB Dashboard"
if __name__ == "__main__":
	args = auxfun_dashboard.parse_arguments()
	results_path: str = args.results_path
	config_path: str = args.config_path

	cfg: dict[str, Any] = auxfun.read_config(config_path)

	if not Path(results_path).is_dir():
		FileNotFoundError(f"{results_path} not found.")
		sys.exit(1)
	if not Path(config_path).is_file():
		FileNotFoundError(f"{config_path} not found.")
		sys.exit(1)

	store = {
		file.stem: pl.read_parquet(file)
		for file in Path(results_path).glob("*.parquet")
		if "binary" not in str(file)
	}

	DAYS_RANGE: list[int, int] = cfg["days_range"]
	CAGES: list[str] = cfg["cages"]
	POSITIONS: list[str] = sorted(store["activity_df"]["position"].unique().to_list())
	ANIMALS: list[str] = cfg["animal_ids"]
	ANIMAL_COLORS: list[str] = auxfun_plots.color_sampling(ANIMALS)
	POSITION_COLORS: list[str] = auxfun_plots.color_sampling(POSITIONS)

	# Dashboard layout
	dashboard_layout = dash_layouts.generate_graphs_layout(DAYS_RANGE)
	comparison_tab = dash_layouts.generate_comparison_layout(DAYS_RANGE)

	app.layout = html.Div(
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
						children=dashboard_layout,
					),
					dcc.Tab(
						label="Plots Comparison",
						value="tab-other",
						className="dash-tab",
						selected_className="dash-tab--selected",
						children=comparison_tab,
					),
				],
			)
		]
	)

	# Tabs callback
	@app.callback(Output("tabs-content", "children"), [Input("tabs", "value")])
	def render_content(tab):
		if tab == "tab-dashboard":
			return dashboard_layout
		elif tab == "tab-other":
			return comparison_tab

	@app.callback(
		[
			Output({"type": "graph", "name": MATCH}, "figure"),
			Output({"type": "store", "name": MATCH}, "data"),
		],
		[
			Input("days_range", "value"),
			Input("phase_type", "value"),
			Input("agg_switch", "value"),
			Input("position_switch", "value"),
			Input("pairwise_switch", "value"),
			input("ranking_switch", "value"),
		],
	)
	def update_plots(
		days_range, phase_type, agg_switch, pos_switch, pair_switch, ranking_switch,
	) -> tuple[go.Figure, dict]:
		plot_name: str = ctx.outputs_grouping[0]["id"]["name"]
		plot_attributes = dash_plotting.plot_registry.get_dependencies(plot_name)

		if ctx.triggered_id is not None and ctx.triggered_id not in plot_attributes:
			return no_update, no_update

		phase_list: list[str] = (
			[phase_type] if phase_type != "all" else ["dark_phase", "light_phase"]
		)

		plot_cfg = auxfun_plots.PlotConfig(
			store=store,
			days_range=days_range,
			phase_type=phase_list,
			agg_switch=agg_switch,
			position_switch=pos_switch,
			pairwise_switch=pair_switch,
			ranking_switch=ranking_switch,
			animals=ANIMALS,
			animal_colors=ANIMAL_COLORS,
			cages=CAGES,
			positions=POSITIONS,
			position_colors=POSITION_COLORS,
		)

		fig, data = dash_plotting.plot_registry.get_plot(plot_name, plot_cfg)

		return fig, auxfun_dashboard.to_store_json(data)

	@app.callback(
		[
			Output({"figure": "comparison-plot", "side": MATCH}, "figure"),
			Output({"store": "comparison-plot", "side": MATCH}, "data"),
			Output({"container": "position_switch", "side": MATCH}, "hidden"),
			Output({"container": "pairwise_switch", "side": MATCH}, "hidden"),
		],
		Input({"type": ALL, "side": MATCH}, "value"),
	)
	def update_comparison_plot(switches: list[Any]) -> tuple[go.Figure, dict]:
		"""Render plots in the comparisons tab"""
		input_dict: dict[str, Any] = {
			item["id"]["type"]: val for item, val in zip(ctx.inputs_list[0], switches)
		}
		plot_attributes = dash_plotting.plot_registry.get_dependencies(input_dict["plot-dropdown"])

		phase_type: list[str] = (
			[input_dict["phase_type"]]
			if not input_dict["phase_type"] == "all"
			else ["dark_phase", "light_phase"]
		)

		plot_cfg = auxfun_plots.PlotConfig(
			store=store,
			days_range=input_dict["days_range"],
			phase_type=phase_type,
			agg_switch=input_dict["agg_switch"],
			position_switch=input_dict["position_switch"],
			pairwise_switch=input_dict["pairwise_switch"],
			animals=ANIMALS,
			animal_colors=ANIMAL_COLORS,
			cages=CAGES,
			positions=POSITIONS,
			position_colors=POSITION_COLORS,
		)

		fig, data = dash_plotting.plot_registry.get_plot(input_dict["plot-dropdown"], plot_cfg)

		pairwise_hidden = "pairwise_switch" not in plot_attributes
		position_hidden = "position_switch" not in plot_attributes

		return (
			fig,
			auxfun_dashboard.to_store_json(data),
			position_hidden,
			pairwise_hidden,
		)

	@app.callback(
		[Output("modal", "is_open"), Output("plot-checklist", "options")],
		[Input("open-modal", "n_clicks")],
		[State("modal", "is_open"), State({"type": "graph", "name": ALL}, "id")],
	)
	def toggle_modal(
		open_click: bool, is_open: bool, graph_ids: list[dict[str, str]]
	) -> tuple[bool, list]:
		"""Opens and closes Downloads modal component"""
		if open_click:
			return not is_open, auxfun_dashboard.get_options_from_ids(
				[g["name"] for g in graph_ids]
			)
		return is_open, []

	@app.callback(
		Output("download-component", "data"),
		[
			Input({"type": "download-btn", "fmt": ALL, "side": ALL}, "n_clicks"),
		],
		[
			State("data-keys-checklist", "value"),
			State("plot-checklist", "value"),
			State("phase_type", "value"),
			State("days_range", "value"),
			State({"type": "graph", "name": ALL}, "figure"),
			State({"type": "graph", "name": ALL}, "id"),
			State({"type": "store", "name": ALL}, "data"),
		],
		prevent_initial_call=True,
	)
	def download_selected_data(
		btn_clicks: int,
		selected_dfs: list[pl.DataFrame],
		selected_plots: list[str],
		phase_type: str,
		days_range: list[int, int],
		all_figures: list[dict],
		all_ids: list[dict],
		all_stores: list[dict],
	) -> dict[str, Any | None]:
		"""Triggers download from the Downloads modal component"""
		triggered = ctx.triggered_id
		if not triggered:
			raise dash.exceptions.PreventUpdate

		if triggered["side"] == "dfs":
			return auxfun_dashboard.download_dataframes(selected_dfs, phase_type, days_range, store)
		elif triggered["side"] == "plots":
			return auxfun_dashboard.download_plots(
				selected_plots,
				triggered["fmt"],
				all_figures,
				all_ids,
				all_stores,
			)
		else:
			raise dash.exceptions.PreventUpdate

	@app.callback(
		Output({"downloader": "download-component-comparison", "side": MATCH}, "data"),
		Input({"type": "download-btn-comparison", "fmt": ALL, "side": MATCH}, "n_clicks"),
		[
			State({"figure": "comparison-plot", "side": MATCH}, "figure"),
			# State({"figure": "comparison-plot", "side": MATCH}, "id"),
			State({"store": "comparison-plot", "side": MATCH}, "data"),
			State({"type": "plot-dropdown", "side": MATCH}, "value"),
		],
		prevent_initial_call=True,
	)
	def download_comparison_data(
		btn_click: int, figure: dict, data_store: dict, plot_type: str
	) -> dict[str, Any | None]:
		"""Triggers download from the comparisons tab"""
		triggered = ctx.triggered_id
		if not triggered:
			raise dash.exceptions.PreventUpdate

		figure = go.Figure(figure)
		if (figure is None) or (data_store is None):
			raise dash.exceptions.PreventUpdate

		plot_name = f"comparison_{plot_type}"
		fname, content = auxfun_dashboard.get_plot_file(
			data_store, figure, triggered["fmt"], plot_name
		)
		return dcc.send_bytes(lambda b: b.write(content), filename=fname)

	auxfun_dashboard.open_browser()
	app.run(debug=True, port=8050)
