import argparse
import sys
import webbrowser
from pathlib import Path

import dash
import pandas as pd
from dash import dcc, html
import dash_daq as daq
from dash.dependencies import Input, Output

from deepecohab.utils import auxfun_plots
from deepecohab.dash.plots import (
    plot_ranking_in_time,
    plot_position_fig,
    plot_pairwise_plot,
    plot_chasings,
    plot_in_cohort_sociability,
    plot_network_grah
)


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
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=["/assets/styles.css"])

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
    dash_data = auxfun_plots.load_dashboard_data(store)
    _data = dash_data['time_per_position_df']
    n_phases_dark = _data['phase_count'][_data['phase'] == 'dark_phase'].max()
    n_phases_light = _data['phase_count'][_data['phase'] == 'light_phase'].max()
    n_phases = min(n_phases_dark, n_phases_light)
    phases = list(range(1, n_phases + 1))

    # Dashboard layout
    dashboard_layout = html.Div([
    html.Div([
        html.Div([
            html.Div([
                # Left: vertical radio items
                html.Div([
                    dcc.RadioItems(
                        id='mode-switch',
                        options=[
                            {'label': 'Dark', 'value': 'dark'},
                            {'label': 'Light', 'value': 'light'},
                            {'label': 'All', 'value': 'all'},
                        ],
                        value='dark',
                        labelStyle={'display': 'block', 'marginBottom': '5px'},
                        inputStyle={'marginRight': '6px'},
                    )
                ], style={
                    'marginRight': '20px',
                    'minWidth': '70px',
                    'textAlign': 'left',
                }),
                html.Div(style={
                    'width': '1px',
                    'backgroundColor': '#5a6b8c',
                    'height': '40px',
                    'margin': '0 20px'
                }),
                html.Div([
                    dcc.RadioItems(
                        id='aggregate-stats-switch',
                        options=[
                            {'label': 'Sum', 'value': 'sum'},
                            {'label': 'Mean', 'value': 'mean'},
                        ],
                        value='sum',
                        labelStyle={'display': 'block', 'marginBottom': '5px'},
                        inputStyle={'marginRight': '6px'},
                    )
                ], style={
                    'marginRight': '20px',
                    'minWidth': '70px',
                    'textAlign': 'left',
                }),
                html.Div(style={
                    'width': '1px',
                    'backgroundColor': '#5a6b8c',
                    'height': '40px',
                    'margin': '0 20px'
                }),
                # Right: slider
                html.Div([
                    html.Label('Phases', style={
                        'fontWeight': 'bold',
                        'textAlign': 'left',
                        'marginRight': '10px',
                        'whiteSpace': 'nowrap'
                    }),
                    dcc.RangeSlider(
                        id='phase-slider',
                        min=min(phases),
                        max=max(phases),
                        value=[1,1],
                        count=1,
                        step=1,
                        tooltip={'placement': 'bottom', 'always_visible': True},
                        updatemode='drag',
                        included=True,
                        vertical=False,
                        persistence=True,
                        className='slider',
                    )
                ], style={'flex': '1'})  # let it take remaining space
            ],
            style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center',
                'width': '100%',
                'gap': '20px',
            })
        ],
        style={
            'padding': '10px',
            'textAlign': 'center',
            'backgroundColor': "#1f2c44",
            'position': 'sticky',
            'top': '0',
            'zIndex': '1000',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
        })
        ], style={
        'position': 'sticky',
        'top': '0',
        'padding': '10px',
        'z-index': '1000',
        'textAlign': 'center',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
        'background-color': "#1f2c44",
    }),
            
        html.Div([
            dcc.Graph(id='ranking-time-plot', figure=plot_ranking_in_time(dash_data)),
            dcc.RadioItems(
                id='position-switch',
                options=[
                    {'label': 'Visits', 'value': 'visits'},
                    {'label': 'Time', 'value': 'time'}
                    ],
                value='visits',
                labelStyle={'display': 'inline-block'}
            ),
            dcc.Graph(id='position-plot'),
            dcc.RadioItems(
                id='pairwise-switch',
                options=[{'label': 'Visits', 'value': 'visits'}, {'label': 'Time', 'value': 'time'}],
                value='visits',
                labelStyle={'display': 'inline-block'}
            ),
            dcc.Graph(id='pairwise-heatmap'),
        html.Div([
            html.Div([
                dcc.Graph(id='chasings-heatmap')
            ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            html.Div([
                dcc.Graph(id='sociability-heatmap')
            ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                ], style={'width': '80%', 'margin': 'auto'}),
                        dcc.Graph(id='network-graph')
                    ], style={'padding': '20px'})
    ])

    comparison_tab = html.Div([
        html.H2('Plots Comparison', style={'textAlign': 'center', 'margin-bottom': '40px'}),

        html.Div([
            # Left panel
            html.Div([
                html.Label('Select Plot', style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='dropdown-plot-left',
                    options=[
                        {'label': 'Visits to compartments Dark', 'value': 'position_dark_visits'},
                        {'label': 'Visits to compartments Light', 'value': 'position_light_visits'},
                        {'label': 'Time spent in compartments Dark', 'value': 'position_dark_time'},
                        {'label': 'Time spent in compartments Light', 'value': 'position_light_time'},
                        {'label': 'Pairwise Encounters Dark', 'value': 'pairwise_encounters_dark'},
                        {'label': 'Pairwise Encounters Light', 'value': 'pairwise_encounters_light'},
                        {'label': 'Pairwise Time Dark', 'value': 'pairwise_time_dark'},
                        {'label': 'Pairwise Time Light', 'value': 'pairwise_time_light'},
                        {'label': 'Chasings Dark', 'value': 'chasings_dark'},
                        {'label': 'Chasings Light', 'value': 'chasings_light'},
                        {'label': 'In cohort sociability Dark', 'value': 'sociability_dark'},
                        {'label': 'In cohort sociability Light', 'value': 'sociability_light'},
                        {'label': 'Network Graph Dark', 'value': 'network_dark'},
                        {'label': 'Network Graph Light', 'value': 'network_light'}
                    ],
                    value='position_dark'
                ),
                dcc.Graph(id='comparison-plot-left'),
                html.Label('Phase', style={'margin-top': '20px'}),
                dcc.Slider(
                    id='slider-phase-left',
                    min=min(phases),
                    max=max(phases),
                    value=min(phases),
                    marks={str(phase): str(phase) for phase in phases},
                    step=None
                ),
            ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '0 10px'}),

            # Right panel
            html.Div([
                html.Label('Select Plot', style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='dropdown-plot-right',
                    options=[
                        {'label': 'Visits to compartments Dark', 'value': 'position_dark_visits'},
                        {'label': 'Visits to compartments Light', 'value': 'position_light_visits'},
                        {'label': 'Time spent in compartments Dark', 'value': 'position_dark_time'},
                        {'label': 'Time spent in compartments Light', 'value': 'position_light_time'},
                        {'label': 'Pairwise Encounters Dark', 'value': 'pairwise_encounters_dark'},
                        {'label': 'Pairwise Encounters Light', 'value': 'pairwise_encounters_light'},
                        {'label': 'Pairwise Time Dark', 'value': 'pairwise_time_dark'},
                        {'label': 'Pairwise Time Light', 'value': 'pairwise_time_light'},
                        {'label': 'Chasings Dark', 'value': 'chasings_dark'},
                        {'label': 'Chasings Light', 'value': 'chasings_light'},
                        {'label': 'In cohort sociability Dark', 'value': 'sociability_dark'},
                        {'label': 'In cohort sociability Light', 'value': 'sociability_light'},
                        {'label': 'Network Graph Dark', 'value': 'network_dark'},
                        {'label': 'Network Graph Light', 'value': 'network_light'}
                    ],
                    value='position_dark'
                ),
                dcc.Graph(id='comparison-plot-right'),
                html.Label('Phase', style={'margin-top': '20px'}),
                dcc.Slider(
                    id='slider-phase-right',
                    min=min(phases),
                    max=max(phases),
                    value=min(phases),
                    marks={str(phase): str(phase) for phase in phases},
                    step=None
                ),
            ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '0 10px'}),
        ])
    ])
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
            Output('pairwise-heatmap', 'figure'),
            Output('chasings-heatmap', 'figure'),
            Output('sociability-heatmap', 'figure'),
            Output('network-graph', 'figure'),
        ],
        [
            Input('phase-slider', 'value'),
            Input('mode-switch', 'value'),
            Input('aggregate-stats-switch', 'value'),
            Input('position-switch', 'value'),
            Input('pairwise-switch', 'value'),
        ]  
    )
    def update_plots(phase_range, mode, aggregate_stats_switch, position_switch,  pairwise_switch):
        
        position_fig = plot_position_fig(dash_data, mode,phase_range, position_switch, aggregate_stats_switch)
        pairwise_plot = plot_pairwise_plot(dash_data, mode, phase_range,  pairwise_switch, aggregate_stats_switch)
        chasings_plot = plot_chasings(dash_data, mode, phase_range, aggregate_stats_switch)
        incohort_soc_plot = plot_in_cohort_sociability(dash_data, mode,phase_range, aggregate_stats_switch)
        network_plot = plot_network_grah(dash_data, mode, phase_range)

        return [position_fig, pairwise_plot, chasings_plot, incohort_soc_plot, network_plot]

    @app.callback(
        [
            Output('comparison-plot-left', 'figure'),
            Output('comparison-plot-right', 'figure'),
        ],
        [
            Input('dropdown-plot-left', 'value'),
            Input('slider-phase-left', 'value'),
            Input('dropdown-plot-right', 'value'),
            Input('slider-phase-right', 'value'),
        ]
    )
    def update_independent_plots(plot_left, phase_left, plot_right, phase_right,):
        def get_plot(plot_type, phase):
            match plot_type:
                case 'position_dark_visits':
                    return plot_position_fig(dash_data, 'dark', phase, 'visits')
                case 'position_light_visits':
                    return plot_position_fig(dash_data, 'light', phase, 'visits')
                case 'position_dark_time':
                    return plot_position_fig(dash_data, 'dark', phase, 'time')
                case 'position_light_time':
                    return plot_position_fig(dash_data, 'light', phase, 'time')
                case 'pairwise_encounters_dark':
                    return plot_pairwise_plot(dash_data, 'dark', phase, 'visits')
                case 'pairwise_encounters_light':
                    return plot_pairwise_plot(dash_data, 'light', phase, 'visits')
                case 'pairwise_time_dark': 
                    return plot_pairwise_plot(dash_data, 'dark', phase, 'time')
                case 'pairwise_time_light':
                    return plot_pairwise_plot(dash_data, 'light', phase, 'time')
                case 'chasings_dark':
                    return plot_chasings(dash_data, 'dark', phase, 'phases')
                case 'chasings_light': 
                    return plot_chasings(dash_data, 'light', phase, 'phases')
                case 'sociability_dark':
                    return plot_in_cohort_sociability(dash_data, 'dark', phase, 'phases')
                case 'sociability_light':
                    return plot_in_cohort_sociability(dash_data, 'light', phase, 'phases')
                case 'network_dark':
                    return plot_network_grah(dash_data, 'dark', phase)
                case 'network_light':
                    return plot_network_grah(dash_data, 'light', phase)
                case _:
                    return {}

        fig_left = get_plot(plot_left, phase_left)
        fig_right = get_plot(plot_right, phase_right)

        return fig_left, fig_right

    # Run the app
    open_browser()
    app.run(debug=True, port=8050)
    