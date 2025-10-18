import dash_bootstrap_components as dbc
from dash import dcc, html

from deepecohab.utils import auxfun_dashboard


def generate_graphs_layout(phase_range):
    return html.Div([
        auxfun_dashboard.generate_settings_block('mode-switch', 
                                                 'aggregate-stats-switch', 
                                                 'phase-slider', 
                                                 phase_range,
                                                 include_download=True),    
        
        dbc.Container([
            # Ranking, network graph, chasings
            dbc.Row([
                dbc.Col(html.H2('Social hierarchy'), className="text-left my-4")
            ]),
            dbc.Row([
                
                
            ]),
            dbc.Row([
                dbc.Col([
                    auxfun_dashboard.generate_standard_graph('ranking-time-plot'),
                    auxfun_dashboard.generate_standard_graph('ranking-distribution', css_class='plot-450'),
                ], width=5),
                dbc.Col([
                    html.Div([
                        auxfun_dashboard.generate_standard_graph('network', css_class='fullsize'),
                    ], style={'display': 'flex', 'height': '100%'}),
                ], width=7),
            ], className="g-3"),
            
            dbc.Row([
                dbc.Col(auxfun_dashboard.generate_standard_graph('chasings-heatmap'), width=6),
                dbc.Col(auxfun_dashboard.generate_standard_graph('chasings-plot'), width=6),
            ], className="g-3"),
            # Activity per hour line and per position bar
            dbc.Row([
                dbc.Col(html.H2('Activity'), className="text-left my-4")
            ]),
            
            dbc.Row([
                dbc.Col(dcc.RadioItems(
                    id='position-switch',
                    options=[
                        {'label': 'Visits', 'value': 'visits'},
                        {'label': 'Time', 'value': 'time'}
                    ],
                    value='visits',
                    labelStyle={'display': 'inline-block'}
                ), width=1),
            ]),
            
            dbc.Row([
                dbc.Col(auxfun_dashboard.generate_standard_graph('position-plot'), width=6),
                dbc.Col(auxfun_dashboard.generate_standard_graph('activity-plot'), width=6),
            ], className="g-3"),

            dbc.Row([
                dbc.Col(auxfun_dashboard.generate_standard_graph('time-per-cage', css_class='plot-800'), width=12),
            ], className="g-3"),
            # Pairwise and incohort heatmaps
            dbc.Row([
                dbc.Col(html.H2('Sociability'), className="text-left my-4")
            ]), 
            
            dbc.Row([
                dbc.Col(dcc.RadioItems(
                    id='pairwise-switch',
                    options=[
                        {'label': 'Visits', 'value': 'visits'},
                        {'label': 'Time', 'value': 'time'}
                    ],
                    value='visits',
                    labelStyle={'display': 'inline-block'}
                ), width=1),
            ]),
            
            dbc.Row([                
                dbc.Col(auxfun_dashboard.generate_standard_graph('pairwise-heatmap'), width=6),
                dbc.Col(auxfun_dashboard.generate_standard_graph('sociability-heatmap'), width=6),
            ], className="g-3"),
            ], fluid=True, style={'padding': '20px'})
    ])

def generate_comparison_layout(phase_range):
    return html.Div([
        html.H2('Plot Comparison', className="text-center my-4"),

        dbc.Row([
        dbc.Col(auxfun_dashboard.generate_comparison_block('left', phase_range), width=6),
        dbc.Col(auxfun_dashboard.generate_comparison_block('right', phase_range), width=6),
    ], className="g-4")
    ])


