import io
import zipfile
import json

from dash import dcc, html, exceptions
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

import pandas as pd


COMMON_CFG = {"displayModeBar": False}

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
                html.Label('Days of experiment', className="slider-label"),
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
            dcc.Store(id={'store': 'comparison-plot', 'side': side})
            ]),
        generate_settings_block(
            {'type': 'mode-switch', 'side': side},
            {'type': 'aggregate-switch', 'side': side},
            {'type': 'phase-slider', 'side': side},
            slider_range,
        ),
        get_fmt_download_buttons("download-btn-comparison", ["svg", "json", "csv"], side, 20),
        dcc.Download(id={"type": "download-component-comparison", "side": side}),

    ], className="h-100 p-2")

def generate_plot_download_tab():
    return dcc.Tab(
        label='Plots',
        value='tab-plots',
        className='dash-tab',
        selected_className='dash-tab--selected',
        children = [dbc.Row(
            [
                dbc.Col(
                    dbc.Checklist(
                        id="plot-checklist",
                        options=[],
                        value=[],
                        inline=False,
                    ),
                    width=8
                ),
                dbc.Col(
                    get_fmt_download_buttons("download-btn", ["svg", "json", "csv"], "plots"),
                    width=4,
                    className="d-flex flex-column align-items-start"
                )
            ]
        )],
    )
    

def generate_csv_download_tab():
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
        {'label': 'Binary DF' ,'value': 'binary_df'},
    ]

    return dcc.Tab(
        label='DataFrames',
        value='tab-dataframes',
        className='dash-tab',
        selected_className='dash-tab--selected',
        children = [dbc.Row(
            [
                dbc.Col(
                    dbc.Checklist(
                        id='data-keys-checklist',
                        options=options,
                        value=[],
                        inline=False,
                        className='download-dropdown',
                    ),
                    width=8
                ),
                dbc.Col(
                    [
                        dbc.Button("Download", id={"type":"download-btn", "fmt":"csv", "side": "dfs"}, n_clicks=0, color="primary", className="mb-2 w-100")
                    ],
                    width=4,
                    className="d-flex flex-column align-items-start"
                )
            ]
        )],
    )

def generate_download_block():
    modal = dbc.Modal(
    [
        dbc.ModalHeader(),#dbc.ModalTitle("Select Plots to Download")),
        dbc.ModalBody(
            dcc.Tabs(
                id='download-tabs',
                value='tab-plots',
                children=[
                    generate_plot_download_tab(),
                    generate_csv_download_tab()
                ],
                style={
                    'backgroundColor': '#1f2c44',
                }
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
    
def generate_standard_graph(graph_id: str, css_class: str = "plot-450"):
    return html.Div([dcc.Graph(id={'graph': graph_id}, className=css_class, config=COMMON_CFG), 
            dcc.Store(id={'store': graph_id})])

def get_options_from_ids(obj_ids: list):
    return [{"label": get_display_name(obj_id), "value": obj_id} for obj_id in obj_ids]

def get_display_name(name: str, sep: str = "-"):
    return " ".join(word.capitalize() for word in name.split(sep))

def get_fmt_download_buttons(type: str, fmts: list, side: str, width: int = 100):
    buttons = []
    for fmt in fmts:
        btn = dbc.Button(f"Download {fmt.upper()}", 
                   id={"type":type, "fmt":fmt, "side": side}, 
                   n_clicks=0, 
                   color="primary", 
                   className=f"mb-2 w-{width}")
        buttons.append(btn)
    return html.Div(buttons)

def get_plot_file(df_data: pd.DataFrame, figure: go.Figure, fmt: str, plot_name: str):
    if fmt == "svg":
        content = figure.to_image(format="svg")
        return (f"{plot_name}.svg", content)
    elif fmt == "json":
        content = json.dumps(figure.to_plotly_json()).encode("utf-8")
        return (f"{plot_name}.json", content)
    elif fmt == "csv":
        df = pd.read_json(df_data, orient="split")
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        return (f"{plot_name}.csv", csv_bytes)
    else:
        raise exceptions.PreventUpdate

def download_plots(selected_plots: list, 
                   fmt: str, 
                   all_figures: list, 
                   all_ids: list, 
                   all_stores: list, 
                   store_ids: list):

    if not selected_plots or not fmt:
            raise exceptions.PreventUpdate
    
    fig_dict = {id_dict["graph"]: fig for id_dict, fig in zip(all_ids, all_figures)}
    state_dict = {id_dict["store"]: data for id_dict, data in zip(store_ids, all_stores)}

    files = []
    for plot_id in selected_plots:
        plot_name = f'plot_{plot_id}'
        figure = go.Figure(fig_dict[plot_id])
        if figure is None:
            continue

        df_data = state_dict[plot_id]
        if df_data is None:
            continue
        
        plt_file = get_plot_file(df_data, figure, fmt, plot_name)
        files.append(plt_file)

    if len(files) == 1:
        fname, content = files[0]
        return dcc.send_bytes(lambda b: b.write(content), filename=fname)

    elif len(files) > 1:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for fname, content in files:
                zf.writestr(fname, content)
        zip_buffer.seek(0)
        return dcc.send_bytes(lambda b: b.write(zip_buffer.read()), filename=f"plots_{fmt}.zip")

    else:
        raise exceptions.PreventUpdate
    
def download_dataframes(selected_dfs: list,
                        mode: str, 
                        phase_range: list,
                        store: pd.HDFStore):
    
    if not selected_dfs:
        raise exceptions.PreventUpdate
    
    if len(selected_dfs) == 1:
        name = selected_dfs[0]
        data_slice = check_if_slice_applicable(name, mode, phase_range)
        if name in store:
            df = store[name].loc[data_slice]
            return dcc.send_data_frame(df.to_csv, f"{name}.csv")
        return None

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for name in selected_dfs:
            if name in store:
                data_slice = check_if_slice_applicable(name, mode, phase_range)
                df = store[name].loc[data_slice]
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                zf.writestr(f"{name}.csv", csv_bytes)

    zip_buffer.seek(0)
    
    return dcc.send_bytes(
        lambda b: b.write(zip_buffer.getvalue()),
        filename="selected_dataframes.zip"
    )

    

