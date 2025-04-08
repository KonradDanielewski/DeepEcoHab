import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
from deepecohab.utils import auxfun_plots
from plots import (
    plot_ranking_in_time,
    plot_position_fig,
    plot_pairwise_plot,
    plot_chasings,
    plot_in_cohort_sociability,
    plot_network_grah
)

# Initialize the Dash app
app = dash.Dash(__name__)

# Load data from hdf
store = pd.HDFStore('examples/test_name2_2025-02-25/results/test_name2_data.h5')
dash_data = auxfun_plots.load_dashboard_data(store)
n_phases = dash_data["time_per_position_df"]["phase_count"].max()

phases = list(range(1, n_phases+1))  # Example phases

# Define the app layout
app.layout = html.Div([
    # Fixed Header Container
    html.Div([
        html.H1('EcoHAB Results', style={'textAlign': 'center', 'margin-bottom': '10px'}),
        html.Div([
            html.Label('Phases', style={'margin-right': '10px'}),
            dcc.Slider(
                id='phase-slider',
                min=min(phases),
                max=max(phases),
                value=min(phases),
                marks={str(phase): str(phase) for phase in phases},
                step=None,
                tooltip={"placement": "bottom", "always_visible": True},
                updatemode='drag',
                included=True,
                vertical=False,
                className='slider'
            ),
            dcc.RadioItems(
                id='mode-switch',
                options=[{'label': 'Dark', 'value': 'dark'}, {'label': 'Light', 'value': 'light'}],
                value='dark',
                labelStyle={'display': 'inline-block', 'margin-left': '10px'}
            )
        ], style={'width': '100%', 'textAlign': 'center'})
    ], style={
        'position': 'fixed', 'top': '0', 'left': '0', 'right': '0', 'background-color': '#FFFFFF',
        'z-index': '1000', 'padding': '10px', 'display': 'flex', 'flexDirection': 'column',
        'alignItems': 'center', 'justifyContent': 'center', 'width': '100%', 'height': '120px'
    }),

    # Scrollable content area
    html.Div([
        dcc.Graph(id='ranking-time-plot', figure=plot_ranking_in_time(dash_data)),
        dcc.Graph(id='position-plot'),
        dcc.RadioItems(
            id='position-switch',
            options=[{'label': 'Visits', 'value': 'visits'}, {'label': 'Time', 'value': 'time'}],
            value='visits',
            labelStyle={'display': 'inline-block'}
        ),
        dcc.Graph(id='pairwise-heatmap'),
        dcc.RadioItems(
            id='pairwise-switch',
            options=[{'label': 'Visits', 'value': 'visits'}, {'label': 'Time', 'value': 'time'}],
            value='visits',
            labelStyle={'display': 'inline-block'}
        ),
        html.Div([
            dcc.Graph(id='chasings-heatmap', style={'display': 'inline-block', 'width': '49%'}),
            dcc.Graph(id='sociability-heatmap', style={'display': 'inline-block', 'width': '49%'})
        ], style={'width': '80%', 'margin': 'auto'}),
        dcc.Graph(id='network-graph')
    ], style={
        'margin-top': '130px', 'overflow-y': 'auto', 'height': 'calc(100vh - 130px)', 'padding': '20px'
    })
])

# Callback to update all plots based on slider and radio buttons
@app.callback(
    [Output('position-plot', 'figure'),
     Output('pairwise-heatmap', 'figure'),
     Output('chasings-heatmap', 'figure'),
     Output('sociability-heatmap', 'figure'),
     Output('network-graph', 'figure')
     ],
    [Input('phase-slider', 'value'),
     Input('mode-switch', 'value'),
     Input('position-switch', 'value'),
     Input('pairwise-switch', 'value')]
)
def update_plots(selected_phase, mode, position_switch, pairwise_switch):
    position_fig = plot_position_fig(dash_data, mode, selected_phase, position_switch)
    pairwise_plot = plot_pairwise_plot(dash_data, mode, selected_phase, pairwise_switch)
    chasings_plot = plot_chasings(dash_data, mode, selected_phase)
    incohort_soc_plot = plot_in_cohort_sociability(dash_data, mode, selected_phase)
    network_plot = plot_network_grah(dash_data, mode, selected_phase)
    
    return [position_fig, pairwise_plot, chasings_plot, incohort_soc_plot, network_plot]

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
