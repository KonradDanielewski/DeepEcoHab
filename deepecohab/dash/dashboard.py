import argparse
import sys
import io
import zipfile
from pathlib import Path
import json

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, ctx
from dash.dependencies import Input, Output, State, MATCH, ALL

from deepecohab.dash import dash_plotting
from deepecohab.dash import dash_layouts

import dash_bootstrap_components as dbc

from deepecohab.utils import (
    auxfun_plots,
    auxfun_dashboard,
)
    
def parse_arguments():
    parser = argparse.ArgumentParser(description='Run DeepEcoHab Dashboard')
    parser.add_argument(
        '--results-path',
        type=str,
        required=True,
        help='h5 file path extracted from the config (examples/test_name2_2025-04-18/results/test_name2_data.h5)'
    )
    parser.add_argument(
        '--config-path',
        type=str,
        required=True,
        help='path to the config file of the project'
    )
    return parser.parse_args()

# Initialize the Dash app
app = dash.Dash(
    __name__, 
    suppress_callback_exceptions=True, 
    external_stylesheets=[
        "/assets/styles.css",
        dbc.icons.FONT_AWESOME, 
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
        ]
    )

app.title = 'EcoHAB Dashboard'
if __name__ == '__main__':
    args = parse_arguments()
    results_path = args.results_path
    config_path = args.config_path

    if not Path(results_path).is_file():
        FileNotFoundError(f'{results_path} not found.')
        sys.exit(1)
    if not Path(config_path).is_file():
        FileNotFoundError(f'{config_path} not found.')
        sys.exit(1)
    
    store = pd.HDFStore(results_path, mode='r')
    store = {key.replace('/', ''): store[key] for key in store.keys() if 'meta' not in key} # and 'binary' not in key -- Avoid reading binary as not used  
    
    _data = store['chasings']
    n_phases = _data.index.get_level_values(1).max()
    phase_range = [1, n_phases]

    # Dashboard layout
    dashboard_layout = dash_layouts.generate_graphs_layout(phase_range)
    comparison_tab = dash_layouts.generate_comparison_layout(phase_range)
    
    app.layout = html.Div([
                dcc.Tabs(
                id='tabs',
                value='tab-dashboard',
                children=[
                    dcc.Tab(
                        label='Dashboard',
                        value='tab-dashboard',
                        children=dashboard_layout,
                        style={
                            'backgroundColor': '#5a6b8c',
                            'color': 'white',
                            'padding': '10px',
                            'fontWeight': 'bold',
                        },
                        selected_style={
                            'backgroundColor': '#2a3f5f',
                            'color': 'white',
                            'padding': '10px',
                            'fontWeight': 'bold',
                            'borderTop': '3px solid #5a6b8c'
                        }
                    ),
                    dcc.Tab(
                        label='Plots Comparison',
                        value='tab-other',
                        children=comparison_tab,
                        style={
                            'backgroundColor': '#5a6b8c',
                            'color': 'white',
                            'padding': '10px',
                            'fontWeight': 'bold',
                        },
                        selected_style={
                            'backgroundColor': '#2a3f5f',
                            'color': 'white',
                            'padding': '10px',
                            'fontWeight': 'bold',
                            'borderTop': '3px solid #5a6b8c'
                        }
                    ),
                ],
                style={
                    'backgroundColor': '#1f2c44',  # Tab bar background
                }
            )
        ])
    
    # Tabs callback
    @app.callback(Output('tabs-content', 'children'), [Input('tabs', 'value')])
    def render_content(tab):
        if tab == 'tab-dashboard':
            return dashboard_layout
        elif tab == 'tab-other':
            return comparison_tab

    # Plots update callback
    @app.callback(
        [
            Output({'graph':'position-plot'}, 'figure'),
            Output({'graph':'activity-plot'}, 'figure'),
            Output({'graph':'pairwise-heatmap'}, 'figure'),
            Output({'graph':'chasings-heatmap'}, 'figure'),
            Output({'graph':'sociability-heatmap'}, 'figure'),
            Output({'graph':'network'}, 'figure'),
            Output({'graph':'chasings-plot'}, 'figure'),
            Output({'graph':'ranking-time-plot'}, 'figure'),
            Output({'graph':'ranking-distribution'}, 'figure'),
            Output({'graph':'time-per-cage'}, 'figure'),
        ],
        [
            Input('phase-slider', 'value'),
            Input('mode-switch', 'value'),
            Input('aggregate-stats-switch', 'value'),
            Input('position-switch', 'value'),
            Input('pairwise-switch', 'value'),
        ]  
    )
    def update_plots(phase_range, mode, aggregate_stats_switch, position_switch, pairwise_switch):
        data_slice = auxfun_dashboard.get_data_slice(mode, phase_range)
            
        animals = store['main_df'].animal_id.cat.categories
        colors = auxfun_plots.color_sampling(animals)

        position_fig = dash_plotting.activity_bar(store, data_slice, position_switch, aggregate_stats_switch)
        activity_fig = dash_plotting.activity_line(store, phase_range, aggregate_stats_switch, animals, colors)
        pairwise_plot = dash_plotting.pairwise_sociability(store, data_slice,  pairwise_switch, aggregate_stats_switch)
        chasings_plot = dash_plotting.chasings(store, data_slice, aggregate_stats_switch)
        incohort_soc_plot = dash_plotting.within_cohort_sociability(store, data_slice)
        network_plot = dash_plotting.network_graph(store, mode, phase_range, animals, colors)
        chasing_line_plot = dash_plotting.chasings_line(store, phase_range, aggregate_stats_switch, animals, colors)
        ranking_line = dash_plotting.ranking_over_time(store, animals, colors)
        ranking_distribution = dash_plotting.ranking_distribution(store, data_slice, animals, colors)
        time_per_cage = dash_plotting.time_per_cage(store, phase_range, animals, colors)

        return [
            position_fig, 
            activity_fig, 
            pairwise_plot, 
            chasings_plot, 
            incohort_soc_plot, 
            network_plot, 
            chasing_line_plot, 
            ranking_line, 
            ranking_distribution,
            time_per_cage
        ]

    @app.callback(
        Output({'type': 'comparison-plot', 'side': MATCH}, 'figure'),
        [
            Input({'type': 'plot-dropdown', 'side': MATCH}, 'value'),
            Input({'type': 'mode-switch', 'side': MATCH}, 'value'),
            Input({'type': 'aggregate-switch', 'side': MATCH}, 'value'),
            Input({'type': 'phase-slider', 'side': MATCH}, 'value'),
        ]
    )
    def update_comparison_plot(plot_type, mode, aggregate_stats_switch, phase_range):
        data_slice = auxfun_dashboard.get_data_slice(mode, phase_range)
            
        animals = store['main_df'].animal_id.cat.categories
        colors = auxfun_plots.color_sampling(animals)
        return dash_plotting.get_single_plot(store, mode, plot_type, data_slice, phase_range, aggregate_stats_switch, animals, colors)

    @app.callback(
    Output("download-component", "data"),
    [
        Input("download-svg", "n_clicks"),
        Input("download-json", "n_clicks"),
        Input("download-csv", "n_clicks"),
    ],
    State("plot-checklist", "value"),
    [State({"type": "graph", "id": ALL}, "figure")],
    prevent_initial_call=True,
    )
    def download_selected(svg_click, json_click, csv_click, selected_plots, all_figures):
        triggered = ctx.triggered_id
        if not triggered or not selected_plots:
            raise dash.exceptions.PreventUpdate

        fmt_map = {
            "download-svg": "svg",
            "download-json": "json",
            "download-csv": "csv",
        }
        fmt = fmt_map.get(triggered)
        if not fmt:
            raise dash.exceptions.PreventUpdate

        files = []
        for plot_id_dict in selected_plots:
            plot_id = 'plot'
            figure = plot_id_dict['graph']
            if figure is None:
                continue

            if fmt == "svg":
                content = figure.to_image(format="svg")
                files.append((f"{plot_id}.svg", content))
            elif fmt == "json":
                content = json.dumps(figure.to_plotly_json()).encode("utf-8")
                files.append((f"{plot_id}.json", content))
            elif fmt == "csv":
                if figure.data:
                    dfs = [pd.DataFrame(trace) for trace in figure.data]
                    df = pd.concat(dfs, axis=1)
                else:
                    df = pd.DataFrame()
                csv_buf = io.StringIO()
                df.to_csv(csv_buf, index=False)
                files.append((f"{plot_id}.csv", csv_buf.getvalue().encode("utf-8")))

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
            raise dash.exceptions.PreventUpdate

    @app.callback(
        Output("modal", "is_open"),
        [Input("open-modal", "n_clicks"), Input("close-modal", "n_clicks")],
        [State("modal", "is_open")],
    )
    def toggle_modal(open_click, close_click, is_open):
        if open_click or close_click:
            return not is_open
        return is_open
        
    @app.callback(
        Output("download-dataframe", "data"),
        Input("download-data", "n_clicks"),
        State("data-keys-dropdown", "value"),
        State('mode-switch', "value"),
        State('phase-slider', "value"),
        prevent_initial_call=True,
    )
    def download_selected_data(n_clicks, selected_names, mode, phase_range,):
        if not selected_names:
            return None
        
        if len(selected_names) == 1:
            name = selected_names[0]
            data_slice = auxfun_dashboard.check_if_slice_applicable(name, mode, phase_range)
            if name in store:
                df = store[name].loc[data_slice]
                return dcc.send_data_frame(df.to_csv, f"{name}.csv")
            return None

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for name in selected_names:
                if name in store:
                    data_slice = auxfun_dashboard.check_if_slice_applicable(name, mode, phase_range)
                    df = store[name].loc[data_slice]
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    zf.writestr(f"{name}.csv", csv_bytes)

        zip_buffer.seek(0)
        
        return dcc.send_bytes(
            lambda b: b.write(zip_buffer.getvalue()),
            filename="selected_dataframes.zip"
        )
    
    # Run the app
    auxfun_plots.open_browser()
    app.run(debug=True, port=8050)
    