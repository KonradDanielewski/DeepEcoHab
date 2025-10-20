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
            Output({'store':'position-plot'}, 'data'),
            Output({'graph':'activity-plot'}, 'figure'),
            Output({'store':'activity-plot'}, 'data'),
            Output({'graph':'pairwise-heatmap'}, 'figure'),
            Output({'store':'pairwise-heatmap'}, 'data'),
            Output({'graph':'chasings-heatmap'}, 'figure'),
            Output({'store':'chasings-heatmap'}, 'data'),
            Output({'graph':'sociability-heatmap'}, 'figure'),
            Output({'store':'sociability-heatmap'}, 'data'),
            Output({'graph':'network'}, 'figure'),
            Output({'store':'network'}, 'data'),
            Output({'graph':'chasings-plot'}, 'figure'),
            Output({'store':'chasings-plot'}, 'data'),
            Output({'graph':'ranking-time-plot'}, 'figure'),
            Output({'store':'ranking-time-plot'}, 'data'),
            Output({'graph':'ranking-distribution'}, 'figure'),
            Output({'store':'ranking-distribution'}, 'data'),
            Output({'graph':'time-per-cage'}, 'figure'),
            Output({'store':'time-per-cage'}, 'data'),
            Output({'graph':'metrics'}, 'figure'),
            Output({'store':'metrics'}, 'data'),
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

        position_fig, position_data = dash_plotting.activity_bar(store, data_slice, position_switch, aggregate_stats_switch)
        activity_fig, activity_data = dash_plotting.activity_line(store, phase_range, aggregate_stats_switch, animals, colors)
        pairwise_plot, pairwise_data = dash_plotting.pairwise_sociability(store, data_slice,  pairwise_switch, aggregate_stats_switch)
        chasings_plot, chasings_data = dash_plotting.chasings(store, data_slice, aggregate_stats_switch)
        incohort_soc_plot, incohort_soc_data = dash_plotting.within_cohort_sociability(store, data_slice)
        network_plot, network_plot_data = dash_plotting.network_graph(store, mode, phase_range, animals, colors)
        chasing_line_plot, chasing_line_data = dash_plotting.chasings_line(store, phase_range, aggregate_stats_switch, animals, colors)
        ranking_line, ranking_data = dash_plotting.ranking_over_time(store, animals, colors)
        ranking_distribution, ranking_distribution_data = dash_plotting.ranking_distribution(store, data_slice, animals, colors)
        time_per_cage, time_per_cage_data = dash_plotting.time_per_cage(store=store, phase_range=phase_range, agg_switch=aggregate_stats_switch, animals=animals, colors=colors)
        metrics_fig, metrics_data = dash_plotting.metrics(store, data_slice, animals, colors)

        return [
            position_fig, auxfun_plots.to_store_json(position_data),
            activity_fig, auxfun_plots.to_store_json(activity_data),
            pairwise_plot, auxfun_plots.to_store_json(pd.DataFrame()),
            chasings_plot, auxfun_plots.to_store_json(chasings_data),
            incohort_soc_plot, auxfun_plots.to_store_json(incohort_soc_data),
            network_plot, auxfun_plots.to_store_json(network_plot_data),
            chasing_line_plot, auxfun_plots.to_store_json(chasing_line_data),
            ranking_line, auxfun_plots.to_store_json(ranking_data),
            ranking_distribution, auxfun_plots.to_store_json(ranking_distribution_data),
            time_per_cage, auxfun_plots.to_store_json(time_per_cage_data),
            metrics_fig, auxfun_plots.to_store_json(metrics_data)
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
        return dash_plotting.get_single_plot(store, mode, plot_type, data_slice, phase_range, aggregate_stats_switch, animals, colors)[0]

    @app.callback(
    Output("download-component", "data"),
    [
        Input("download-svg", "n_clicks"),
        Input("download-json", "n_clicks"),
        Input("download-csv", "n_clicks"),
    ],
    State("plot-checklist", "value"),
    [State({"graph" : ALL}, "figure"),
    State({"graph" : ALL}, "id"),
    State({"store" : ALL}, "data"),
    State({"store" : ALL}, "id")],
    prevent_initial_call=True,
    )
    def download_selected(svg_click, json_click, csv_click, selected_plots, all_figures, all_ids, all_stores, store_ids):
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

        fig_dict = {id_dict["graph"]: fig for id_dict, fig in zip(all_ids, all_figures)}
        state_dict = {id_dict["store"]: data for id_dict, data in zip(store_ids, all_stores)}

        files = []
        for plot_id_dict in selected_plots:
            plot_id = plot_id_dict['graph']
            plot_name = f'plot_{plot_id}'
            figure = go.Figure(fig_dict[plot_id])
            if figure is None:
                continue

            if fmt == "svg":
                content = figure.to_image(format="svg")
                files.append((f"{plot_name}.svg", content))
            elif fmt == "json":
                content = json.dumps(figure.to_plotly_json()).encode("utf-8")
                files.append((f"{plot_name}.json", content))
            elif fmt == "csv":
                df_data = state_dict[plot_id]
                if df_data is None:
                    continue
                df = pd.read_json(df_data, orient="split")
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                files.append((f"{plot_name}.csv", csv_bytes))

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

    auxfun_plots.open_browser()
    app.run(debug=True, port=8050)
    