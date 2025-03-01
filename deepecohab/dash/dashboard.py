import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.io as pio
import os
import json

def create_plot_label(plot_json):
    return plot_json.replace('.json', '').replace('_', ' ').title()

# Initialize the Dash app
app = dash.Dash(__name__)

# Path to the directory containing your .json plot files
plot_dir = r"/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-25/plots/fig_source" # Replace with your directory path

# List all .json files in the directory
plot_files = [f for f in os.listdir(plot_dir) if f.endswith('.json')]

# Load plots from .json files
plots = {}
for filename in plot_files:
    with open(os.path.join(plot_dir, filename), 'r') as file:
        plots[filename] = json.load(file)

# Define the layout of the app
app.layout = html.Div(
    style={'backgroundColor': '#1a1a1a', 'color': 'lightgray', 'font-family': 'Arial', 'height': '100vh'},
    children=[
        html.H1('EcoHab Results', style={'textAlign': 'center'}),
        html.Div(
            style={'display': 'flex', 'justifyContent': 'space-around', 'height': '90%'},
            children=[
                html.Div(
                    children=[
                        dcc.Dropdown(
                            id='left-plot-dropdown',
                            options=sorted([{'label': create_plot_label(f), 'value': f} for f in plot_files], key=lambda x: x['label']),
                            placeholder='Select a plot for the left side',
                            style={'backgroundColor': '#333', 'color': 'black'}
                        ),
                        dcc.Graph(id='left-plot', style={'height': '100%', 'width': '100%'}, config={'responsive': True}),
                    ],
                    style={'width': '45%', 'height': '100%'}
                ),
                html.Div(
                    children=[
                        dcc.Dropdown(
                            id='right-plot-dropdown',
                            options=sorted([{'label': create_plot_label(f), 'value': f} for f in plot_files], key=lambda x: x['label']),
                            placeholder='Select a plot for the right side',
                            style={'backgroundColor': '#333', 'color': 'black'}
                        ),
                        dcc.Graph(id='right-plot', style={'height': '100%', 'width': '100%'}, config={'responsive': True}),
                    ],
                    style={'width': '45%', 'height': '100%'}
                ),
            ]
        )
    ]
)

# Callback to update the left plot based on dropdown selection
@app.callback(
    Output('left-plot', 'figure'),
    Input('left-plot-dropdown', 'value')
)
def update_left_plot(selected_plot):
    if selected_plot:
        plot = plots[selected_plot]
        # Update layout for responsiveness
        plot['layout']['autosize'] = True
        plot['layout']['width'] = None
        plot['layout']['height'] = None
        return plot
    return {}

# Callback to update the right plot based on dropdown selection
@app.callback(
    Output('right-plot', 'figure'),
    Input('right-plot-dropdown', 'value')
)
def update_right_plot(selected_plot):
    if selected_plot:
        plot = plots[selected_plot]
        # Update layout for responsiveness
        plot['layout']['autosize'] = True
        plot['layout']['width'] = None
        plot['layout']['height'] = None
        return plot
    return {}

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
