import argparse
import sys
import io
import zipfile
from pathlib import Path

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
                        className='dash-tab',
                        selected_className='dash-tab--selected',
                        children=dashboard_layout,
                    ),
                    dcc.Tab(
                        label='Plots Comparison',
                        value='tab-other',
                        className='dash-tab',
                        selected_className='dash-tab--selected',
                        children=comparison_tab,
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
        [Output("modal", "is_open"), Output("plot-checklist", "options")],
        [Input("open-modal", "n_clicks"), Input("close-modal", "n_clicks")],
        [State("modal", "is_open"),
         State({"graph" : ALL}, "id")],
    )
    def toggle_modal(open_click, close_click, is_open, graph_ids):
        if open_click or close_click:
            return not is_open, auxfun_dashboard.get_options_from_ids([g["graph"] for g in graph_ids])
        return is_open, []
        
    @app.callback(
        Output("download-component", "data"),
        [
            Input({"type":"download-btn", "fmt": ALL, "tab":ALL}, "n_clicks"),
        ],
        [
            State("data-keys-checklist", "value"),
            State("plot-checklist", "value"),
            State('mode-switch', "value"),
            State('phase-slider', "value"),
            State({"graph" : ALL}, "figure"),
            State({"graph" : ALL}, "id"),
            State({"store" : ALL}, "data"),
            State({"store" : ALL}, "id")
        ],
        prevent_initial_call=True,
    )
    def download_selected_data(btn_clicks, 
                               selected_dfs, 
                               selected_plots,
                               mode, 
                               phase_range,
                               all_figures, 
                               all_ids, 
                               all_stores, 
                               store_ids
                               ):
        
        triggered = ctx.triggered_id
        if not triggered:
            raise dash.exceptions.PreventUpdate
        
        if triggered["tab"] == "dfs":
            return auxfun_dashboard.download_dataframes(selected_dfs,
                                                        mode,
                                                        phase_range,
                                                        store)
        elif triggered["tab"] == "plots":
            return auxfun_dashboard.download_plots(selected_plots,
                                            triggered["fmt"],
                                            all_figures, 
                                            all_ids, 
                                            all_stores, 
                                            store_ids
                                            )
        else:
            raise dash.exceptions.PreventUpdate
        

    auxfun_plots.open_browser()
    app.run(debug=True, port=8050)
    