import dash
from dash import dcc, html, Input, Output, State
import os
import dash_daq as daq

# temporary hardcoded path to the folder with plots
folder_path = "/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-25/plots"  # Zmienna do zastąpienia argumentem skryptu

plot_files = [f for f in os.listdir(folder_path) if f.endswith(".html")]

app = dash.Dash(__name__)
app.title = "Plots Dashboard"

# Layout
app.layout = html.Div([
    html.Div([
        html.H2("Choose plot:", style={'color': 'white'}),
        dcc.Dropdown(
            id='plot-dropdown',
            options=[{'label': f, 'value': f} for f in plot_files],
            placeholder="Choose plot:",
            style={'width': '90%', 'backgroundColor': '#333', 'color': 'white'}
        ),
        html.Br(),
        html.H3("Notes:", style={'color': 'white'}),
        dcc.Textarea(
            id='notes-area',
            style={'width': '90%', 'height': '200px', 'backgroundColor': '#222', 'color': 'white'}
        ),
        html.Button("Save notes", id='save-button', n_clicks=0, style={'marginTop': '10px'}),
        html.Div(id='save-status', style={'marginTop': '10px', 'fontSize': '14px', 'color': 'green'})
    ], style={'width': '30%', 'float': 'left', 'padding': '20px', 'backgroundColor': '#111', 'height': '100vh'}),

    html.Div([
        html.Iframe(
            id='plot-frame',
            style={'width': '100%', 'height': '100vh', 'border': 'none'}
        )
    ], style={'width': '65%', 'float': 'right', 'padding': '20px', 'backgroundColor': '#222'})
], style={'display': 'flex', 'flexDirection': 'row', 'backgroundColor': '#000', 'height': '100vh'})

@app.callback(
    [Output('plot-frame', 'srcDoc'), Output('notes-area', 'value')],
    Input('plot-dropdown', 'value')
)
def update_plot(selected_file):
    if selected_file:
        with open(os.path.join(folder_path, selected_file), "r", encoding="utf-8") as f:
            plot_content = f.read()
        
        notes_path = os.path.join(folder_path, f"{selected_file}.txt")
        if os.path.exists(notes_path):
            with open(notes_path, "r", encoding="utf-8") as f:
                notes_content = f.read()
        else:
            notes_content = ""
        
        return plot_content, notes_content
    return "", ""

@app.callback(
    Output('save-status', 'children'),
    Input('save-button', 'n_clicks'),
    State('notes-area', 'value'),
    State('plot-dropdown', 'value')
)
def save_notes(n_clicks, notes, selected_file):
    if n_clicks > 0 and selected_file and notes:
        notes_path = os.path.join(folder_path, f"{selected_file}.txt")
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write(notes)
        return "Notes saved"
    return ""

if __name__ == '__main__':
    app.run_server(debug=True)
