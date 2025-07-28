import argparse
import sys
import webbrowser
from pathlib import Path
import io
import json

import dash
import pandas as pd
from dash import dcc, html, ctx
from dash.dependencies import Input, Output, State, MATCH, ALL
import dash_bootstrap_components as dbc


from deepecohab.utils import auxfun_plots
from deepecohab.dash.plots import ( # TODO: change import style
    plot_ranking_in_time,
    plot_activity,
    plot_position_fig,
    plot_pairwise_plot,
    plot_chasings,
    plot_in_cohort_sociability,
    plot_network_grah,
    get_single_plot,
    plot_chasing,
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
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=["/assets/styles.css",dbc.icons.FONT_AWESOME])

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


def generate_settings_block(phase_type_id, aggregate_stats_id, slider_id, slider_range):
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    dcc.RadioItems(
                        id=phase_type_id,
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
                        id=aggregate_stats_id,
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
                html.Div([
                    html.Label('Phases', style={
                        'fontWeight': 'bold',
                        'textAlign': 'left',
                        'marginRight': '10px',
                        'whiteSpace': 'nowrap'
                    }),
                    dcc.RangeSlider(
                        id=slider_id,
                        min=slider_range[0],
                        max=slider_range[1],
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
                ], style={'flex': '1'})
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
    })
            
def generate_comparison_block(side: str, slider_range: list[int]):
    return html.Div([
        html.Label('Select Plot', style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id={'type': 'plot-dropdown', 'side': side},
            options=[
                {'label': 'Visits to compartments', 'value': 'position_visits'},
                {'label': 'Time spent in compartments', 'value': 'position_time'},
                {'label': 'Pairwise encounters', 'value': 'pairwise_encounters'},
                {'label': 'Pairwise time', 'value': 'pairwise_time'},
                {'label': 'Chasings', 'value': 'chasings'},
                {'label': 'In cohort sociability', 'value': 'sociability'},
                {'label': 'Network graph', 'value': 'network'},
            ],
            value='position_visits',
        ),
        html.Div([
            dcc.Graph(id={'type': 'comparison-plot', 'side': side}),
            ]),
        generate_settings_block(
            {'type': 'mode-switch', 'side': side},
            {'type': 'aggregate-switch', 'side': side},
            {'type': 'phase-slider', 'side': side},
            slider_range
        )
    ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '0 10px'})

def generate_download_block(graph_id):
    
    return html.Div([
        dcc.Store(id={'type': 'dropdown-visible', 'graph': graph_id}, data=False),
        dbc.Button(id={'type': 'download-icon-button', 'graph': graph_id}, className="fa-solid fa-file-export icon-button-dark", 
                   style={"fontSize": "30px", "marginRight": "10px"}),
        html.Div(id={'type': 'dropdown-container', 'graph': graph_id}, style={"position": "relative"}),
        dcc.Download(id={'type': 'download-component', 'graph': graph_id})
    ])
    


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
        generate_settings_block('mode-switch', 'aggregate-stats-switch', 'phase-slider', [min(phases), max(phases)]),    
            
        html.Div([
            # Ranking, network graph, chasings
            html.H2('Social hierarchy', style={'textAlign': 'left', 'margin-bottom': '40px'}),
            html.Div([
                html.Div([
                    dcc.Graph(id='ranking-time-plot', figure=plot_ranking_in_time(dash_data)),
                    html.Div([
                        html.Button("Download SVG", id="btn-ranking-time-plot-svg"),
                        dcc.Download(id="download-ranking-time-plot-svg")
                        ]),
                ], style={'width': '59%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                html.Div([
                    dcc.Graph(id={'graph':'network'}),
                    generate_download_block('network'),
                ], style={'width': '39%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            ]),
            html.Div([
                html.Div([
                    dcc.Graph(id='chasings-heatmap')
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                html.Div([
                    dcc.Graph(id='chasings-plot')
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            ]),
            # Activity per hour line and per position bar
            html.H2('Activity', style={'textAlign': 'left', 'margin-bottom': '40px'}),
            html.Div([
                dcc.RadioItems(
                    id='position-switch',
                    options=[
                        {'label': 'Visits', 'value': 'visits'},
                        {'label': 'Time', 'value': 'time'}
                        ],
                    value='visits',
                    labelStyle={'display': 'inline-block'},
                    ),
                html.Div([
                    dcc.Graph(id='position-plot', style={'height': '500px'}),
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'bot'}),
                html.Div([
                    dcc.Graph(id='activity-plot', style={'height': '500px'})
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'bot'}),
            ]),
            # Pairwise and incohort heatmaps
            html.H2('Sociability', style={'textAlign': 'left', 'margin-bottom': '40px'}),
            html.Div([
                dcc.RadioItems(
                id='pairwise-switch',
                options=[{'label': 'Visits', 'value': 'visits'}, {'label': 'Time', 'value': 'time'}],
                value='visits',
                labelStyle={'display': 'inline-block'}
                ),
                html.Div([
                    dcc.Graph(id='pairwise-heatmap')
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                html.Div([
                    dcc.Graph(id='sociability-heatmap')
                ], style={'width': '49%', 'display': 'inline-block', 'verticalAlign': 'top'}),
                    ], style={'width': '90%', 'margin': 'auto'}),
            ], style={'padding': '20px'})
    ])

    comparison_tab = html.Div([
        html.H2('Plots Comparison', style={'textAlign': 'center', 'margin-bottom': '40px'}),

        html.Div([
            # Left panel
            generate_comparison_block('left', [min(phases), max(phases)]),

            # Right panel  
            generate_comparison_block('right', [min(phases), max(phases)]),
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
            Output('activity-plot', 'figure'),
            Output('pairwise-heatmap', 'figure'),
            Output('chasings-heatmap', 'figure'),
            Output('sociability-heatmap', 'figure'),
            Output({'graph':'network'}, 'figure'),
            Output('chasings-plot', 'figure'),
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
        
        position_fig = plot_position_fig(dash_data, mode,phase_range, position_switch, aggregate_stats_switch)
        activity_fig = plot_activity(dash_data, phase_range, aggregate_stats_switch)
        pairwise_plot = plot_pairwise_plot(dash_data, mode, phase_range,  pairwise_switch, aggregate_stats_switch)
        chasings_plot = plot_chasings(dash_data, mode, phase_range, aggregate_stats_switch)
        incohort_soc_plot = plot_in_cohort_sociability(dash_data, mode,phase_range, sociability_summary_switch="mean") # it's never a sum, probably just discard the parameter
        network_plot = plot_network_grah(dash_data, mode, phase_range)
        chasing_line_plot = plot_chasing(dash_data, phase_range, aggregate_stats_switch)

        return [position_fig, activity_fig, pairwise_plot, chasings_plot, incohort_soc_plot, network_plot, chasing_line_plot]


    @app.callback(
        Output({'type': 'comparison-plot', 'side': MATCH}, 'figure'),
        [
            Input({'type': 'plot-dropdown', 'side': MATCH}, 'value'),
            Input({'type': 'mode-switch', 'side': MATCH}, 'value'),
            Input({'type': 'aggregate-switch', 'side': MATCH}, 'value'),
            Input({'type': 'phase-slider', 'side': MATCH}, 'value'),
        ]
    )
    def update_comparison_plot(plot_type, phase_type, aggregate_stats_switch, phase_range):
        return get_single_plot(dash_data, plot_type, phase_type, aggregate_stats_switch, phase_range)
    
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
    