import argparse
import sys
import webbrowser
from pathlib import Path
import json

import dash
import pandas as pd
from dash import dcc, html, ctx
from dash.dependencies import Input, Output, State, MATCH, ALL

from deepecohab.dash import dash_plotting
from deepecohab.dash import dash_layouts

import dash_bootstrap_components as dbc

from deepecohab.utils import auxfun_plots

def open_browser():
    webbrowser.open_new('http://127.0.0.1:8050/')
    
def parse_arguments():
    parser = argparse.ArgumentParser(description='Run DeepEcoHab Dashboard')
    parser.add_argument(
        '--results-path',
        type=str,
        required=True,
        help='h5 file path extracted from the config (examples/test_name2_2025-04-18/results/test_name2_data.h5)'
    )
    return parser.parse_args()

# Initialize the Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=["/assets/styles.css",
                                                                                   dbc.icons.FONT_AWESOME, 
                                                                                   dbc.themes.BOOTSTRAP])

import plotly.graph_objects as go
import plotly.io as pio

dark_dash_template = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e0e6f0"),
        xaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
        yaxis=dict(gridcolor="#2e3b53", linecolor="#4fc3f7"),
        legend=dict(bgcolor="rgba(0,0,0,0)")
    )
)

# register & set as default
pio.templates["dash_dark"] = dark_dash_template
pio.templates.default = "dash_dark"





app.title = 'EcoHAB Dashboard'
if __name__ == '__main__':
    args = parse_arguments()
    results_path = args.results_path

    if not Path(results_path).is_file():
        FileNotFoundError(f'{results_path} not found.')
        sys.exit(1)
    store = pd.HDFStore(results_path, mode='r')
    store = {key.replace('/', ''): store[key] for key in store.keys() if 'meta' not in key}
    
    _data = store['chasings']
    
    #TODO for now - because default value for mode switch is dark
    n_phases = _data.loc['dark_phase', :].index.get_level_values(0).unique().max()
    phases_range = [1, n_phases]


    # Dashboard layout
    dashboard_layout = dash_layouts.generate_graphs_layout(phases_range)

    comparison_tab = dash_layouts.generate_comparison_layout(phases_range)
    
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
            Output('position-plot', 'figure'),
            Output('activity-plot', 'figure'),
            Output('pairwise-heatmap', 'figure'),
            Output('chasings-heatmap', 'figure'),
            Output('sociability-heatmap', 'figure'),
            Output({'graph':'network'}, 'figure'),
            Output('chasings-plot', 'figure'),
            Output('ranking-time-plot', 'figure'),
            Output('ranking-distribution', 'figure'),
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
        
        # TODO: to be moved to auxfun_dashboard.py
        idx = pd.IndexSlice
        if mode == 'all':
            data_slice = idx[(slice(None), slice(phase_range[0], phase_range[-1])), :]
        else:
            data_slice = idx[(mode, slice(phase_range[0], phase_range[-1])), :]
            
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
        idx = pd.IndexSlice
        if mode == 'all':
            data_slice = idx[(slice(None), slice(phase_range[0], phase_range[-1])), :]
        else:
            data_slice = idx[(mode, slice(phase_range[0], phase_range[-1])), :]
            
        animals = store['main_df'].animal_id.cat.categories
        colors = auxfun_plots.color_sampling(animals)
        return dash_plotting.get_single_plot(store, mode, plot_type, data_slice, phase_range, aggregate_stats_switch, animals, colors)
    
    @app.callback(
        Output({'type': 'dropdown-visible', 'graph':MATCH}, "data"),
        [
            Input({'type': 'download-icon-button', 'graph': MATCH}, "n_clicks"),
            Input({'type': 'download-option', 'format': ALL, 'graph': MATCH}, 'n_clicks')
        ],
        State({'type': 'dropdown-visible', 'graph':MATCH}, "data"),
        prevent_initial_call=True
    )
    def toggle_dropdown(icon_clicks, download_clicks, visible):
            
        triggered_id = ctx.triggered_id

        if triggered_id['type']== 'download-icon-button' and icon_clicks is not None:
            return not visible
        elif isinstance(triggered_id, dict) and triggered_id['type'] == 'download-option':
            return False
        raise dash.exceptions.PreventUpdate

    
    
    @app.callback(
        Output({'type': 'dropdown-container', 'graph': MATCH}, "children"),
        Input({'type': 'dropdown-visible', 'graph': MATCH}, "data"),
    )
    def render_dropdown(visible):
        if visible:
            triggered_id = ctx.triggered_id
            graph_id = triggered_id['graph']
            return html.Div([
                html.Div([
                    html.Div("Download SVG", id={'type': 'download-option', 'format': 'svg', 'graph': graph_id},
                             n_clicks=0, className="dropdown-item", style={"cursor": "pointer"}),
                    html.Div("Download JSON", id={'type': 'download-option', 'format': 'json', 'graph': graph_id},
                             n_clicks=0, className="dropdown-item", style={"cursor": "pointer"})
                ], className="dropdown-menu show", style={"position": "absolute", "zIndex": 1000}),
            ])
        return None

    
    @app.callback(
        Output({'type': 'download-component', 'graph': MATCH}, 'data'),
        Input({'type': 'download-option', 'format': ALL, 'graph': MATCH}, 'n_clicks'),
        State({'graph':MATCH}, 'figure'),
        prevent_initial_call=True
    )
    def download_figure(n_clicks, figure):
        triggered_id = ctx.triggered_id
    
        plot_type = triggered_id['graph']
        fmt = triggered_id['format']
        
        figure = go.Figure(figure)

        if fmt == 'svg':
            svg_bytes = figure.to_image(format='svg')
            return dcc.send_bytes(svg_bytes, filename=f"{plot_type}.svg")
        elif fmt == 'json':
            return dcc.send_string(json.dumps(figure.to_plotly_json()), filename=f"{plot_type}.json")
        else:
            raise dash.exceptions.PreventUpdate
    
    
    # Run the app
    open_browser()
    app.run(debug=False, port=8050)
    