from typing import Any, Literal
import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import polars as pl
import plotly.graph_objects as go
from dash import ctx, dcc, html
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
    results_path = args.results_path
    config_path = args.config_path
    
    cfg = auxfun.read_config(config_path)

    if not Path(results_path).is_dir():
        FileNotFoundError(f"{results_path} not found.")
        sys.exit(1)
    if not Path(config_path).is_file():
        FileNotFoundError(f"{config_path} not found.")
        sys.exit(1)

    store = {file.stem: pl.read_parquet(file) for file in Path(results_path).glob('*.parquet') if 'binary' not in str(file)}
    
    DAYS_RANGE = cfg['days_range']
    CAGES = cfg['cages']
    POSITIONS = sorted(store['activity_df']['position'].unique().to_list())
    ANIMALS = cfg['animal_ids']
    ANIMAL_COLORS = auxfun_plots.color_sampling(ANIMALS)
    POSITION_COLORS = auxfun_plots.color_sampling(POSITIONS)

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
                style={
                    "backgroundColor": "#1f2c44",  # Tab bar background
                },
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
            Output({"graph": "ranking-line"}, "figure"),
            Output({"store": "ranking-line"}, "data"),
            Output({"graph": "metrics-polar-line"}, "figure"),
            Output({"store": "metrics-polar-line"}, "data"),
            Output({"graph": "ranking-distribution-line"}, "figure"),
            Output({"store": "ranking-distribution-line"}, "data"),
            Output({"graph": "network-graph"}, "figure"),
            Output({"store": "network-graph"}, "data"),           
            Output({"graph": "chasings-heatmap"}, "figure"),
            Output({"store": "chasings-heatmap"}, "data"),
            Output({"graph": "chasings-line"}, "figure"),
            Output({"store": "chasings-line"}, "data"),
            Output({"graph": "activity-bar"}, "figure"),
            Output({"store": "activity-bar"}, "data"),
            Output({"graph": "activity-line"}, "figure"),
            Output({"store": "activity-line"}, "data"),
            Output({"graph": "time-per-cage-heatmap"}, "figure"),
            Output({"store": "time-per-cage-heatmap"}, "data"),
            Output({"graph": "sociability-heatmap"}, "figure"),
            Output({"store": "sociability-heatmap"}, "data"),
            Output({"graph": "cohort-heatmap"}, "figure"),
            Output({"store": "cohort-heatmap"}, "data"),
            Output({"graph": "time-alone-bar"}, "figure"),
            Output({"store": "time-alone-bar"}, "data"),
        ],
        [
            Input("phase-slider", "value"),
            Input("mode-switch", "value"),
            Input("aggregate-stats-switch", "value"),
            Input("position-switch", "value"),
            Input("pairwise-switch", "value"),
        ],
    )
    def update_plots(
        days_range: list[int, int], 
        phase_type: Literal['dark_phase', 'light_phase', 'all'], 
        aggregate_stats_switch: Literal['mean', 'sum'], 
        position_switch: Literal['time', 'visits'], 
        pairwise_switch: Literal['time_together', 'pairwise_encounters'],
    ) -> list[go.Figure, dict]:
        """Render plots in the main dashboard tab"""       
        phase_type = ([phase_type] if not phase_type == 'all' else ['dark_phase', 'light_phase'])

        plot_cfg = auxfun_plots.PlotConfig(
            store, days_range, phase_type, aggregate_stats_switch,
            position_switch, pairwise_switch, ANIMALS, ANIMAL_COLORS, CAGES, POSITIONS,
            POSITION_COLORS,
        )
        
        plot_names = list(dash_plotting.plot_registry._registry.keys())
        
        output = []
        
        for name in plot_names:
            fig, data = dash_plotting.plot_registry.get_plot(name, plot_cfg)
            output.extend([fig, auxfun_plots.to_store_json(data)])

        return output

        

    @app.callback(
        [
            Output({"type": "comparison-plot", "side": MATCH}, "figure"),
            Output({"store": "comparison-plot", "side": MATCH}, "data"),
        ],
        [
            Input({"type": "plot-dropdown", "side": MATCH}, "value"),
            Input({"type": "mode-switch", "side": MATCH}, "value"),
            Input({"type": "phase-slider", "side": MATCH}, "value"),
            Input({"type": "aggregate-switch", "side": MATCH}, "value"),
            Input({"type": "position-switch", "side": MATCH}, "value"),
            Input({"type": "pairwise-switch", "side": MATCH}, "value"),
        ],
    )
    def update_comparison_plot(
        plot_type: str, 
        phase_type: str,
        days_range: list[int, int], 
        aggregate_stats_switch: Literal['mean', 'sum'], 
        position_switch: Literal["time", "visits"],
        pairwise_switch: Literal["time_together", "pairwise_encounters"],
    ) -> tuple[go.Figure, dict]:
        """Render plots in the comparisons tab"""
        phase_type = ([phase_type] if not phase_type == 'all' else ['dark_phase', 'light_phase'])
           
        plot_cfg = auxfun_plots.PlotConfig(
          store, days_range, phase_type, aggregate_stats_switch,
          position_switch, pairwise_switch, ANIMALS, ANIMAL_COLORS, CAGES, POSITIONS,
          POSITION_COLORS,
        )
        plt, df = dash_plotting.plot_registry.get_plot(plot_type, plot_cfg)

    
        return plt, auxfun_plots.to_store_json(df)

    @app.callback(
        [Output("modal", "is_open"), Output("plot-checklist", "options")],
        [Input("open-modal", "n_clicks")],
        [State("modal", "is_open"), State({"graph": ALL}, "id")],
    )
    def toggle_modal(open_click: bool, is_open: bool, graph_ids: list[dict]) -> tuple[bool, list]:
        """Opens and closes Downloads modal component"""
        if open_click:
            return not is_open, auxfun_dashboard.get_options_from_ids(
                [g["graph"] for g in graph_ids]
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
            State("mode-switch", "value"),
            State("phase-slider", "value"),
            State({"graph": ALL}, "figure"),
            State({"graph": ALL}, "id"),
            State({"store": ALL}, "data"),
            State({"store": ALL}, "id"),
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
        store_ids: list[dict],
    ) -> dict[str, Any | None]:
        """Triggers download from the Downloads modal component"""
        triggered = ctx.triggered_id
        if not triggered:
            raise dash.exceptions.PreventUpdate

        if triggered["side"] == "dfs":
            return auxfun_dashboard.download_dataframes(
                selected_dfs, phase_type, days_range, store
            )
        elif triggered["side"] == "plots":
            return auxfun_dashboard.download_plots(
                selected_plots,
                triggered["fmt"],
                all_figures,
                all_ids,
                all_stores,
                store_ids,
            )
        else:
            raise dash.exceptions.PreventUpdate

    @app.callback(
        Output({"type": "download-component-comparison", "side": MATCH}, "data"),
        Input(
            {"type": "download-btn-comparison", "fmt": ALL, "side": MATCH}, "n_clicks"
        ),
        State({"type": "comparison-plot", "side": MATCH}, "figure"),
        State({"type": "comparison-plot", "side": MATCH}, "id"),
        State({"store": "comparison-plot", "side": MATCH}, "data"),
        State({"type": "plot-dropdown", "side": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def download_comparison_data(btn_click: int, figure: dict, fig_id: str, data_store: dict, plot_type: str) -> dict[str, Any | None]:
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

    auxfun_plots.open_browser()
    app.run(debug=True, port=8050)
