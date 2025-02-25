import dash
import dash_bootstrap_components as dbc
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.io as pio
import pandas as pd

# Inicjalizacja aplikacji Dash z ciemnym motywem
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

# Funkcja do wczytywania wykresu z pliku HTML
def load_html_plot(file_path):
    with open(file_path, 'r') as file:
        return file.read()

plot_paths = {
    'Wykres 1': '/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-24/plots/visits_per_position_light.html',
    'Wykres 2': '/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-24/plots/time_per_position_dark.html',
    'Wykres 3': '/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-24/plots/time_together_dark.html'
}

path = r"/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-24/results/test_name2_data.h5"
df = pd.read_hdf(path,key="chasings")

# Layout aplikapip install dash dash-bootstrap-componentscji
app.layout = html.Div([
    dbc.Row([
        dbc.Col([
            html.H3("Wybierz wykres:"),
            dcc.Dropdown(
                id='plot-dropdown',
                options=[{'label': plot, 'value': plot} for plot in plot_paths],
                value='Wykres 1',
                style={'backgroundColor': '#2c2c2c', 'color': 'white'}
            ),
            html.Hr(),
            html.H3("Tabela z danymi:"),
            html.Div(id='data-table'),
        ], width=4),
        dbc.Col([
            html.H3("Wykres:"),
            html.Div(id='plot-container'),
            html.Hr(),
            html.H3("Notatki:"),
            dcc.Textarea(
                id='notes',
                value='',
                style={'width': '100%', 'height': 100, 'backgroundColor': '#2c2c2c', 'color': 'white'}
            ),
            html.Button('Zapisz notatki', id='save-notes', n_clicks=0, style={'marginTop': '10px'}),
        ], width=8)
    ])
])

# Callback do aktualizacji tabeli z danymi
@app.callback(
    Output('data-table', 'children'),
    [Input('plot-dropdown', 'value')]
)
def update_table(selected_plot):
    # Wyświetlenie tabeli z danymi
    return html.Div([
        html.Table([
            html.Thead(
                html.Tr([html.Th(col) for col in df.columns])
            ),
            html.Tbody([
                html.Tr([html.Td(df.iloc[i][col]) for col in df.columns]) for i in range(len(df))
            ])
        ])
    ])

# Callback do aktualizacji wykresu
@app.callback(
    Output('plot-container', 'children'),
    [Input('plot-dropdown', 'value')]
)
def update_plot(selected_plot):
    # Wczytanie i wyświetlenie wykresu
    plot_html = load_html_plot(plot_paths[selected_plot])
    return html.Iframe(srcDoc=plot_html, width='100%', height='600px')

if __name__ == '__main__':
    app.run_server(debug=True)
