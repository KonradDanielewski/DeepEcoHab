from typing import Literal
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
    days_range = cfg['days_range']
    cages = cfg['cages']
    animals = cfg['animal_ids']
    colors = auxfun_plots.color_sampling(animals)

    # Dashboard layout
    dashboard_layout = dash_layouts.generate_graphs_layout(days_range)
    comparison_tab = dash_layouts.generate_comparison_layout(days_range)

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

    # Plots update callback
    @app.callback(
        [
            Output({"graph": "position-plot"}, "figure"),
            Output({"store": "position-plot"}, "data"),
            Output({"graph": "activity-plot"}, "figure"),
            Output({"store": "activity-plot"}, "data"),
            Output({"graph": "pairwise-heatmap"}, "figure"),
            Output({"store": "pairwise-heatmap"}, "data"),
            Output({"graph": "chasings-heatmap"}, "figure"),
            Output({"store": "chasings-heatmap"}, "data"),
            Output({"graph": "sociability-heatmap"}, "figure"),
            Output({"store": "sociability-heatmap"}, "data"),
            Output({"graph": "network"}, "figure"),
            Output({"store": "network"}, "data"),
            Output({"graph": "chasings-plot"}, "figure"),
            Output({"store": "chasings-plot"}, "data"),
            Output({"graph": "ranking-time-plot"}, "figure"),
            Output({"store": "ranking-time-plot"}, "data"),
            Output({"graph": "ranking-distribution"}, "figure"),
            Output({"store": "ranking-distribution"}, "data"),
            Output({"graph": "time-per-cage"}, "figure"),
            Output({"store": "time-per-cage"}, "data"),
            Output({"graph": "metrics"}, "figure"),
            Output({"store": "metrics"}, "data"),
            Output({"graph": "time-alone"}, "figure"),
            Output({"store": "time-alone"}, "data"),
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
        days_range, phase_type, aggregate_stats_switch, position_switch, pairwise_switch
    ):       
        phase_type = ([phase_type] if not phase_type == 'all' else ['dark_phase', 'light_phase'])
       
        position_fig, position_data = dash_plotting.activity(
            store, days_range, phase_type, str(position_switch), str(aggregate_stats_switch)
        )
        activity_fig, activity_data = dash_plotting.activity_line(
            store, days_range, str(aggregate_stats_switch), animals, colors
        )
        pairwise_plot, pairwise_data = dash_plotting.pairwise_sociability(
            store, days_range, phase_type, str(pairwise_switch), str(aggregate_stats_switch), animals, cages,
        )
        chasings_plot, chasings_data = dash_plotting.chasings_heatmap(
            store, days_range, phase_type, str(aggregate_stats_switch), animals,
        )
        incohort_soc_plot, incohort_soc_data = dash_plotting.within_cohort_sociability(
            store, days_range, phase_type, animals,
        )
        network_plot, network_plot_data = dash_plotting.network_graph(
            store, days_range, animals, colors
        )
        chasing_line_plot, chasing_line_data = dash_plotting.chasings_line(
            store, days_range, str(aggregate_stats_switch), animals, colors
        )
        ranking_line, ranking_data = dash_plotting.ranking_over_time(
            store, animals, colors
        )
        ranking_distribution, ranking_distribution_data = dash_plotting.ranking_distribution(
            store, days_range, animals, colors
        )
        time_per_cage, time_per_cage_data = dash_plotting.time_per_cage(
            store, days_range, str(aggregate_stats_switch), animals, cages,
        )
        metrics_fig, metrics_data = dash_plotting.polar_metrics(
            store, days_range, phase_type, animals, colors
        )
        time_alone_fig, time_alone_data = dash_plotting.time_alone(
            store, days_range, phase_type, cages
        )

        return [
            position_fig,
            auxfun_plots.to_store_json(position_data),
            activity_fig,
            auxfun_plots.to_store_json(activity_data),
            pairwise_plot,
            auxfun_plots.to_store_json(pairwise_data),
            chasings_plot,
            auxfun_plots.to_store_json(chasings_data),
            incohort_soc_plot,
            auxfun_plots.to_store_json(incohort_soc_data),
            network_plot,
            auxfun_plots.to_store_json(network_plot_data),
            chasing_line_plot,
            auxfun_plots.to_store_json(chasing_line_data),
            ranking_line,
            auxfun_plots.to_store_json(ranking_data),
            ranking_distribution,
            auxfun_plots.to_store_json(ranking_distribution_data),
            time_per_cage,
            auxfun_plots.to_store_json(time_per_cage_data),
            metrics_fig,
            auxfun_plots.to_store_json(metrics_data),
            time_alone_fig,
            auxfun_plots.to_store_json(time_alone_data),
        ]

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
        ],
    )
    def update_comparison_plot(
        plot_type: str, 
        phase_type: str,
        days_range: list[int, int], 
        aggregate_stats_switch: Literal['sum', 'mean'], 
    ) -> tuple[go.Figure, str]:
        phase_type = ([phase_type] if not phase_type == 'all' else ['dark_phase', 'light_phase'])

        plt, df = dash_plotting.get_single_plot(
            store,
            days_range,
            phase_type,
            plot_type,
            aggregate_stats_switch,
            animals,
            colors,
            cages
        )
        return plt, auxfun_plots.to_store_json(df)

    @app.callback(
        [Output("modal", "is_open"), Output("plot-checklist", "options")],
        [Input("open-modal", "n_clicks")],
        [State("modal", "is_open"), State({"graph": ALL}, "id")],
    )
    def toggle_modal(open_click, is_open, graph_ids):
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
        btn_clicks,
        selected_dfs,
        selected_plots,
        phase_type,
        days_range,
        all_figures,
        all_ids,
        all_stores,
        store_ids,
    ):
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
    def download_comparison_data(btn_click, figure, fig_id, data_store, plot_type):
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
