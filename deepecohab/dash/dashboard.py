import argparse
import sys
import io
import zipfile
from pathlib import Path
import json

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, ctx
from dash.dependencies import Input, Output, State, MATCH, ALL

from deepecohab.dash import dash_plotting
from deepecohab.dash import dash_layouts

import dash_bootstrap_components as dbc

from deepecohab.utils import (
    auxfun_plots,
    auxfun_dashboard,
)
    
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
                                                                                   dbc.themes.BOOTSTRAP,
                                                                                   "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",])

app.title = 'EcoHAB Dashboard'
if __name__ == '__main__':
    args = parse_arguments()
    results_path = args.results_path

    if not Path(results_path).is_file():
        FileNotFoundError(f'{results_path} not found.')
        sys.exit(1)
    
    store = pd.HDFStore(results_path, mode='r')
    store = {key.replace('/', ''): store[key] for key in store.keys() if 'meta' not in key and 'binary' not in key} # Avoid reading binary as not used
    
    _data = store['chasings']
    n_phases = _data.index.get_level_values(1).max()
    phase_range = [1, n_phases]

    # Dashboard layout
    dashboard_layout = dash_layouts.generate_graphs_layout(phase_range)
    comparison_tab = dash_layouts.generate_comparison_layout(phase_range)
    
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
            Output({'graph':'position-plot'}, 'figure'),
            Output({'graph':'activity-plot'}, 'figure'),
            Output({'graph':'pairwise-heatmap'}, 'figure'),
            Output({'graph':'chasings-heatmap'}, 'figure'),
            Output({'graph':'sociability-heatmap'}, 'figure'),
            Output({'graph':'network'}, 'figure'),
            Output({'graph':'chasings-plot'}, 'figure'),
            Output({'graph':'ranking-time-plot'}, 'figure'),
            Output({'graph':'ranking-distribution'}, 'figure'),
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
        data_slice = auxfun_dashboard.get_data_slice(mode, phase_range)
            
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
        data_slice = auxfun_dashboard.get_data_slice(mode, phase_range)
            
        animals = store['main_df'].animal_id.cat.categories
        colors = auxfun_plots.color_sampling(animals)
        return dash_plotting.get_single_plot(store, mode, plot_type, data_slice, phase_range, aggregate_stats_switch, animals, colors)
    
    # @app.callback(
    #     Output({'type': 'dropdown-visible', 'graph':MATCH}, "data"),
    #     [
    #         Input({'type': 'download-icon-button', 'graph': MATCH}, "n_clicks"),
    #         Input({'type': 'download-option', 'format': ALL, 'graph': MATCH}, 'n_clicks'),
    #     ],
    #     State({'type': 'dropdown-visible', 'graph':MATCH}, "data"),
    #     prevent_initial_call=True
    # )
    # def toggle_dropdown(icon_clicks, download_clicks, visible):
            
    #     triggered_id = ctx.triggered_id

    #     if triggered_id['type'] == 'download-icon-button' and icon_clicks is not None:
    #         return not visible
    #     elif isinstance(triggered_id, dict) and triggered_id['type'] == 'download-option':
    #         return False
    #     raise dash.exceptions.PreventUpdate
    
    # @app.callback(
    #     Output({'type': 'dropdown-container', 'graph': MATCH}, "children"),
    #     Input({'type': 'dropdown-visible', 'graph': MATCH}, "data"),
    # )
    # def render_dropdown(visible):
    #     if visible:
    #         triggered_id = ctx.triggered_id
    #         graph_id = triggered_id['graph']
            
    #         dropdown_items = [
    #             html.Div("Download SVG", id={'type': 'download-option', 'format': 'svg', 'graph': graph_id},
    #                      n_clicks=0, className="dropdown-item", style={"cursor": "pointer"}),
    #             html.Div("Download JSON", id={'type': 'download-option', 'format': 'json', 'graph': graph_id},
    #                      n_clicks=0, className="dropdown-item", style={"cursor": "pointer"}),
    #         ]
            
    #         if not graph_id == 'network':
    #             dropdown_items.append(html.Div("Download CSV", id={'type': 'download-option', 'format': 'csv', 'graph': graph_id},
    #                      n_clicks=0, className="dropdown-item", style={"cursor": "pointer"}),)
            
            
    #         return html.Div([
    #             html.Div(dropdown_items, className="dropdown-menu show", style={"position": "absolute", "zIndex": 1000}),
    #         ])
    #     return None
            
    # @app.callback(
    #     Output({'type': 'download-component', 'graph': MATCH}, 'data'),
    #     Input({'type': 'download-option', 'format': ALL, 'graph': MATCH}, 'n_clicks'),
    #     State({'graph': MATCH}, 'figure'),
    #     prevent_initial_call=True,
    # )
    # def download_figure(n_clicks, figure):
    #     triggered_id = ctx.triggered_id

    #     if not isinstance(triggered_id, dict) or not any(n_clicks):
    #         raise dash.exceptions.PreventUpdate

    #     plot_type = triggered_id['graph']
    #     fmt = triggered_id['format']

    #     figure = go.Figure(figure)

    #     if fmt == 'svg':
    #         svg_bytes = figure.to_image(format='svg')
    #         return dcc.send_bytes(svg_bytes, filename=f"{plot_type}.svg")
    #     elif fmt == 'json':
    #         return dcc.send_string(json.dumps(figure.to_plotly_json()), filename=f"{plot_type}.json")
    #     elif fmt == 'csv':
    #         pass # TODO: implement logic that run data transformation and outputs the df used for the plot creation
    #     else:
    #         raise dash.exceptions.PreventUpdate

# import dash_bootstrap_components as dbc
# from dash import html, dcc, Input, Output, State, ctx

    @app.callback(
        Output({'type': 'modal-container', 'graph': MATCH}, "children"),
        Input({'type': 'download-icon-button', 'graph': MATCH}, "n_clicks"),
        State({'type': 'modal-container', 'graph': MATCH}, "children"),
        prevent_initial_call=True,
    )
    def toggle_modal(n_clicks, current_children):
        triggered_id = ctx.triggered_id
        graph_id = triggered_id["graph"]

        if n_clicks is None:
            raise dash.exceptions.PreventUpdate

        buttons = [
            dbc.Button(
                "Download SVG",
                id={'type': 'download-option', 'format': 'svg', 'graph': graph_id},
                color="primary", className="me-2"
            ),
            dbc.Button(
                "Download JSON",
                id={'type': 'download-option', 'format': 'json', 'graph': graph_id},
                color="secondary", className="me-2"
            ),
        ]

        if "network" not in str(graph_id).lower():
            buttons.append(
                dbc.Button(
                    "Download CSV",
                    id={'type': 'download-option', 'format': 'csv', 'graph': graph_id},
                    color="success"
                )
            )

        modal = dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Download Options")),
                dbc.ModalBody([
                    dbc.Input(
                        id={'type': 'yaxis-input', 'graph': graph_id},
                        placeholder="Y-axis"
                    ),
                    html.Br(),
                    *buttons,
                ]),
                dbc.ModalFooter(
                    dbc.Button(
                        "Close",
                        id={'type': 'close-modal', 'graph': graph_id},
                        className="ms-auto"
                    )
                ),
            ],
            id={'type': 'download-modal', 'graph': graph_id},
            is_open=True,
            backdrop=True,
            centered=True,
        )

        return modal
        
    @app.callback(
        Output({'type': 'download-modal', 'graph': MATCH}, "is_open"),
        Input({'type': 'close-modal', 'graph': MATCH}, "n_clicks"),
        State({'type': 'download-modal', 'graph': MATCH}, "is_open"),
        prevent_initial_call=True,
    )
    def close_modal(close_click, is_open):
        if close_click:
            return False
        raise dash.exceptions.PreventUpdate
    
    @app.callback(
        Output({'type': 'download-component', 'graph': MATCH}, 'data'),
        Input({'type': 'download-option', 'format': ALL, 'graph': MATCH}, 'n_clicks'),
        State({'graph': MATCH}, 'figure'),
        State({'type': 'yaxis-input', 'graph': MATCH}, 'value'),
        prevent_initial_call=True,
    )
    def download_figure(n_clicks, figure, yaxis_value):
        triggered_id = ctx.triggered_id

        if not isinstance(triggered_id, dict) or not any(n_clicks):
            raise dash.exceptions.PreventUpdate

        plot_type = triggered_id['graph']
        fmt = triggered_id['format']

        figure = go.Figure(figure)

        if fmt == 'svg':
            svg_bytes = figure.to_image(format='svg')
            return dcc.send_bytes(lambda b: b.write(svg_bytes), filename=f"{plot_type}.svg")

        elif fmt == 'json':
            return dcc.send_string(json.dumps(figure.to_plotly_json()), filename=f"{plot_type}.json")

        elif fmt == 'csv':
            # Example: export data from figure
            df = pd.DataFrame(figure.data[0])  # adapt for your figure structure
            if yaxis_value:
                df = df[[yaxis_value]] if yaxis_value in df.columns else df
            return dcc.send_data_frame(df.to_csv, f"{plot_type}.csv", index=False)

        else:
            raise dash.exceptions.PreventUpdate
        
    @app.callback(
        Output("download-dataframe", "data"),
        Input("download-data", "n_clicks"),
        State("data-keys-dropdown", "value"),
        State('mode-switch', "value"),
        State('phase-slider', "value"),
        prevent_initial_call=True,
    )
    def download_selected_data(n_clicks, selected_names, mode, phase_range,):
        if not selected_names:
            return None
        
        if len(selected_names) == 1:
            name = selected_names[0]
            data_slice = auxfun_dashboard.check_if_slice_applicable(name, mode, phase_range)
            if name in store:
                df = store[name].loc[data_slice]
                return dcc.send_data_frame(df.to_csv, f"{name}.csv")
            return None

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for name in selected_names:
                if name in store:
                    data_slice = auxfun_dashboard.check_if_slice_applicable(name, mode, phase_range)
                    df = store[name].loc[data_slice]
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    zf.writestr(f"{name}.csv", csv_bytes)

        zip_buffer.seek(0)
        
        return dcc.send_bytes(
            lambda b: b.write(zip_buffer.getvalue()),
            filename="selected_dataframes.zip"
        )
    
    # Run the app
    auxfun_plots.open_browser()
    app.run(debug=True, port=8050)
    