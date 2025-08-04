from dash import dcc, html
import dash_bootstrap_components as dbc

def generate_settings_block(phase_type_id, aggregate_stats_id, slider_id, slider_range):
    return html.Div([
            html.Div([
                html.Div([
                    dcc.RadioItems(
                        id=phase_type_id,
                        options=[
                            {'label': 'Dark', 'value': 'dark_phase'},
                            {'label': 'Light', 'value': 'light_phase'},
                            {'label': 'All', 'value': 'all'},
                        ],
                        value='dark_phase',
                        labelStyle={'display': 'block', 'marginBottom': '5px'},
                        inputStyle={'marginRight': '6px'},
                    )
                ], className="control-radio-btns"),
                html.Div(className="divider"),
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
                ], className="control-radio-btns"),
                html.Div(className="divider"),
                html.Div([
                    html.Label('Phases', className="slider-label"),
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
                ], className ="flex-container")
            ], className="centered-container")
        ], className="header-bar")
            
            
            
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
    ], className="h-100 p-2")

#TODO replacement with modal
def generate_download_block(graph_id):
    
    return html.Div([
        dcc.Store(id={'type': 'dropdown-visible', 'graph': graph_id}, data=False),
        dbc.Button(id={'type': 'download-icon-button', 'graph': graph_id}, className="fa-solid fa-file-export icon-button-dark", 
                   style={"fontSize": "30px", "marginRight": "10px"}),
        html.Div(id={'type': 'dropdown-container', 'graph': graph_id}, style={"position": "relative"}),
        dcc.Download(id={'type': 'download-component', 'graph': graph_id})
    ])