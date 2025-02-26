import os
from dash import Dash, dcc, html, Input, Output
from flask import send_from_directory

FOLDER_CHARTS = f"/home/winiar/Desktop/projects/ecohab/deepecohab/examples/test_name2_2025-02-25/plots"  # Change this to the path of your folder
html_files = [f for f in os.listdir(FOLDER_CHARTS) if f.endswith(".html")]

def format_plot_label(plot_name):
    return plot_name.replace(".html", "").replace("_", " ").title()

app = Dash(__name__)


@app.server.route('/charts/<path:filename>')
def serve_chart(filename):
    return send_from_directory(FOLDER_CHARTS, filename)

app.layout = html.Div([
    
    html.Div(
        html.H1("EcoHAB results", style={
            "color": "#D3D3D3",
            "textAlign": "center",
            "margin": "20px 0"
        })
    ),
    
    html.Div([
       
        html.Div([
            html.H2("Plots:", style={"color": "#FFFFFF"}),
            html.Div(
                dcc.Checklist(
                    id='file-checklist',
                    options=sorted([{'label': format_plot_label(f), 'value': f} for f in html_files], key=lambda x: x['label']),
                    value=[],  
                    labelStyle={'display': 'block', 'padding': '5px 0', 'color': '#FFFFFF'},
                ),
                style={
                    "border": "2px solid #444444",
                    "borderRadius": "5px",
                    "padding": "10px",
                    "backgroundColor": "#333333"
                }
            )
        ], style={
            "width": "20%",
            "padding": "20px",
            "boxSizing": "border-box"
        }),
       
        html.Div(id='plots-container', style={
            "width": "80%",
            "padding": "20px",
            "boxSizing": "border-box"
        })
    ], style={
        "display": "flex",
        "alignItems": "flex-start",
        "backgroundColor": "#2c2c2c",
        "minHeight": "80vh"
    })
], style={
    "backgroundColor": "#2c2c2c",
    "fontFamily": "Arial, sans-serif"
})

@app.callback(
    Output('plots-container', 'children'),
    Input('file-checklist', 'value')
)
def update_plots(selected_files):
    children = []
    for file in selected_files:
        src_url = f"/charts/{file}"
        children.append(
            html.Div([
                html.Iframe(src=src_url, style={
                    'width': '100%', 
                    'height': '800px', 
                    'border': 'none'
                })
            ], style={'marginBottom': '20px'})
        )
    return children

if __name__ == '__main__':
    app.run_server(debug=True)
