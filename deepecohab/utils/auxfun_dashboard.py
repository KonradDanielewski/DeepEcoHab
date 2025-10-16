from typing import Literal

from dash import dcc, html
import dash_bootstrap_components as dbc
import pandas as pd


def generate_settings_block(phase_type_id, aggregate_stats_id, slider_id, slider_range, include_download=False):
    block = html.Div([
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
                    value=[1, 1],
                    count=1,
                    step=1,
                    tooltip={'placement': 'bottom', 'always_visible': True},
                    updatemode='drag',
                    included=True,
                    vertical=False,
                    persistence=True,
                    className='slider',
                )
            ], className="flex-container"),
        ], className="centered-container"),
    ], className="header-bar")

    if include_download:
        block.children.append(
            html.Div([
                html.Div([
                    dbc.DropdownMenu(
                        label='Choose DataFrame/s:',
                        children=[
                            dbc.Checklist(
                                options=[
                                    {'label': 'Main DF' ,'value': 'main_df'},
                                    {'label': 'Chasing' ,'value': 'chasings'},
                                    {'label': 'Time per position' ,'value': 'time_per_position'},
                                    {'label': 'Visits per position' ,'value': 'visits_per_position'},
                                    {'label': 'Time together' ,'value': 'time_together'},
                                    {'label': 'Pairwise encounters' ,'value': 'pairwise_encounters'},
                                    {'label': 'Incohort sociability' ,'value': 'incohort_sociability'},
                                    {'label': 'Ranking in time' ,'value': 'ranking_in_time'},
                                    {'label': 'Ranking' ,'value': 'ranking'},
                                    {'label': 'Ranking ordinal' ,'value': 'ranking_ordinal'},
                                    {'label': 'Match DF' ,'value': 'match_df'},
                                ],
                                value=[],
                                id='data-keys-dropdown',
                                inline=False,
                                className='download-dropdown',
                            ),]
                    ),
                    html.Button('Download', id='download-data', n_clicks=0),
                    dcc.Download(id="download-dataframe"),
                    dbc.Container([
                        html.Button('Plot downloads...', id='open-modal', n_clicks=0),
                        generate_download_block(),
                    ]),
                ], className='download-row'),
            ], className='download-container')
        )

    return block       
            
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
            slider_range,
        )
    ], className="h-100 p-2")

def generate_download_block():
    plot_options = [
        {'label': 'Position Plot', 'value': {'graph': 'position-plot'}},
        {'label': 'Activity Plot', 'value': {'graph': 'activity-plot'}},
        {'label': 'Pairwise Heatmap', 'value': {'graph': 'pairwise-heatmap'}},
        {'label': 'Chasings Heatmap', 'value': {'graph': 'chasings-heatmap'}},
        {'label': 'Sociability Heatmap', 'value': {'graph': 'sociability-heatmap'}},
        {'label': 'Network', 'value': {'graph': 'network'}},
        {'label': 'Chasings Plot', 'value': {'graph': 'chasings-plot'}},
        {'label': 'Ranking Time Plot', 'value': {'graph': 'ranking-time-plot'}},
        {'label': 'Ranking Distribution', 'value': {'graph': 'ranking-distribution'}},
        {'label': 'Time per Cage', 'value': {'graph': 'time-per-cage'}},
    ]
    modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Select Plots to Download")),
        dbc.ModalBody(
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Checklist(
                            id="plot-checklist",
                            options=plot_options,
                            value=[],
                            inline=False,
                        ),
                        width=8
                    ),
                    dbc.Col(
                        [
                            dbc.Button("Download SVG", id="download-svg", n_clicks=0, color="primary", className="mb-2 w-100"),
                            dbc.Button("Download JSON", id="download-json", n_clicks=0, color="secondary", className="mb-2 w-100"),
                            dbc.Button("Download CSV", id="download-csv", n_clicks=0, color="success", className="w-100"),
                        ],
                        width=4,
                        className="d-flex flex-column align-items-start"
                    )
                ]
            )
        ),
        dbc.ModalFooter([
            dbc.Button("Close", id="close-modal", className="ms-auto", n_clicks=0),
            dcc.Download(id="download-component"),
        ]),
    ],
    id="modal",
    is_open=False,
)

    return modal


    # return html.Div([
    #     dbc.Button(
    #         id={'type': 'download-icon-button', 'graph': graph_id},
    #         className="fa-solid fa-file-export icon-button-dark",
    #         style={"fontSize": "30px", "marginRight": "10px"}
    #     ),

    #     dbc.Popover(
    #         [
    #             dbc.PopoverHeader("Download Options"),
    #             dbc.PopoverBody([
    #                 dbc.Input(
    #                     id={'type': 'yaxis-input', 'graph': graph_id},
    #                     placeholder="Y-axis"
    #                 ),
    #                 html.Br(),
    #                 dbc.Button(
    #                     "Download SVG",
    #                     id={'type': 'download-option', 'format': 'svg', 'graph': graph_id},
    #                     color="primary", className="me-2"
    #                 ),
    #                 dbc.Button(
    #                     "Download JSON",
    #                     id={'type': 'download-option', 'format': 'json', 'graph': graph_id},
    #                     color="secondary", className="me-2"
    #                 ),
    #                 *( [] if "network" in str(graph_id).lower() else [
    #                     dbc.Button(
    #                         "Download CSV",
    #                         id={'type': 'download-option', 'format': 'csv', 'graph': graph_id},
    #                         color="success"
    #                     )
    #                 ])
    #             ])
    #         ],
    #         id={'type': 'download-popover', 'graph': graph_id},
    #         target={'type': 'download-icon-button', 'graph': graph_id},  # anchor to the button
    #         is_open=False,
    #         placement="bottom",
    #     ),

    #     dcc.Download(id={'type': 'download-component', 'graph': graph_id}),
    # ])
    
def get_data_slice(mode: str, phase_range: list):
    """Sets data slice to be taken from data used for dashboard."""        
    idx = pd.IndexSlice
    if mode == 'all':
        return idx[(slice(None), slice(phase_range[0], phase_range[-1])), :]
    else:
        return idx[(mode, slice(phase_range[0], phase_range[-1])), :]
    
def check_if_slice_applicable(name: str, mode: str, phase_range: list):
    if name not in ['main_df', 'ranking', 'match_df', 'ranking_in_time']:
        return get_data_slice(mode, phase_range)
    else:
        return slice(None)