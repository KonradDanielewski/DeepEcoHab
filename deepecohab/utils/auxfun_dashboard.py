import argparse
import io
import json
import zipfile

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import polars as pl
from dash import dcc, exceptions, html

COMMON_CFG = {"displayModeBar": False}


def generate_settings_block(
    phase_type_id, aggregate_stats_id, slider_id, slider_range, include_download=False
):
    block = html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            dcc.RadioItems(
                                id=phase_type_id,
                                options=[
                                    {"label": "Dark", "value": "dark_phase"},
                                    {"label": "Light", "value": "light_phase"},
                                    {"label": "All", "value": 'all'},
                                ],
                                value="dark_phase",
                                labelStyle={"display": "block", "marginBottom": "5px"},
                                inputStyle={"marginRight": "6px"},
                            )
                        ],
                        className="control-radio-btns",
                    ),
                    html.Div(className="divider"),
                    html.Div(
                        [
                            dcc.RadioItems(
                                id=aggregate_stats_id,
                                options=[
                                    {"label": "Sum", "value": "sum"},
                                    {"label": "Mean", "value": "mean"},
                                ],
                                value="sum",
                                labelStyle={"display": "block", "marginBottom": "5px"},
                                inputStyle={"marginRight": "6px"},
                            )
                        ],
                        className="control-radio-btns",
                    ),
                    html.Div(className="divider"),
                    html.Div(
                        [
                            html.Label("Days of experiment", className="slider-label"),
                            dcc.RangeSlider(
                                id=slider_id,
                                min=slider_range[0],
                                max=slider_range[1],
                                value=[1, 1],
                                count=1,
                                tooltip={"placement": "bottom", "always_visible": True},
                                updatemode="mouseup",
                                included=True,
                                vertical=False,
                                persistence=True,
                                persistence_type='session',
                                className="slider",
                            ),
                        ],
                        className="flex-container",
                    ),
                    # Conditional block
                    *(
                        [
                            html.Div(className="divider"),
                            html.Div(
                                [
                                    dbc.Container(
                                        [
                                            html.Button(
                                                "Downloads",
                                                id="open-modal",
                                                n_clicks=0,
                                                className="DownloadButton",
                                            ),
                                            generate_download_block(),
                                        ]
                                    ),
                                ],
                                className="download-row",
                            ),
                        ]
                        if include_download
                        else []
                    ),
                ],
                className="centered-container",
            ),
        ],
        className="header-bar",
    )

    return block


def generate_comparison_block(side: str, slider_range: list[int]):
    return html.Div(
        [
            html.Label("Select Plot", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id={"type": "plot-dropdown", "side": side},
                options=[
                    {"label": "Visits to compartments", "value": "position_visits"},
                    {"label": "Time spent in compartments", "value": "position_time"},
                    {"label": "Pairwise encounters", "value": "pairwise_encounters"},
                    {"label": "Pairwise time", "value": "pairwise_time"},
                    {"label": "Chasings", "value": "chasings"},
                    {"label": "In cohort sociability", "value": "sociability"},
                    {"label": "Network graph", "value": "network"},
                ],
                value="position_visits",
            ),
            html.Div(
                [
                    dcc.Graph(id={"type": "comparison-plot", "side": side}),
                    dcc.Store(id={"store": "comparison-plot", "side": side}),
                ]
            ),
            generate_settings_block(
                {"type": "mode-switch", "side": side},
                {"type": "aggregate-switch", "side": side},
                {"type": "phase-slider", "side": side},
                slider_range,
            ),
            get_fmt_download_buttons(
                "download-btn-comparison",
                ["svg", "png", "json", "csv"],
                side,
                is_vertical=False,
            ),
            dcc.Download(id={"type": "download-component-comparison", "side": side}),
        ],
        className="h-100 p-2",
    )


def generate_plot_download_tab():
    return dcc.Tab(
        label="Plots",
        value="tab-plots",
        className="dash-tab",
        selected_className="dash-tab--selected",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Checklist(
                            id="plot-checklist",
                            options=[],
                            value=[],
                            inline=False,
                            className="download-dropdown",
                        ),
                        width=8,
                    ),
                    dbc.Col(
                        get_fmt_download_buttons(
                            "download-btn", ["svg", "png", "json", "csv"], "plots"
                        ),
                        width=4,
                        className="d-flex flex-column align-items-start",
                    ),
                ]
            )
        ],
    )


def generate_csv_download_tab():
    options = [
        {"label": "Main DF", "value": "main_df"},
        {"label": "Chasing", "value": "chasings_df"},
        {"label": "Activity", "value": "activity_df"},
        {"label": "Pairwise meetings", "value": "pairwise_meetings"},
        {"label": "Incohort sociability", "value": "incohort_sociability"},
        {"label": "Time alone", "value": "time_alone"},
        {"label": "Ranking", "value": "ranking"},
    ]

    return dcc.Tab(
        label="DataFrames",
        value="tab-dataframes",
        className="dash-tab",
        selected_className="dash-tab--selected",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Checklist(
                            id="data-keys-checklist",
                            options=options,
                            value=[],
                            inline=False,
                            className="download-dropdown",
                        ),
                        align="center",
                        width=8,
                    ),
                    dbc.Col(
                        [
                            dbc.Button(
                                "Download DataFrame/s",
                                id={
                                    "type": "download-btn",
                                    "fmt": "csv",
                                    "side": "dfs",
                                },
                                n_clicks=0,
                                color="primary",
                                className="ModalButton",
                            )
                        ],
                        width=4,
                        align="center",
                        className="d-flex flex-column align-items-start",
                    ),
                ]
            )
        ],
    )


def generate_download_block():
    modal = dbc.Modal(
        [
            dbc.ModalHeader([dbc.ModalTitle("Downloads")]),
            dbc.ModalBody(
                dcc.Tabs(
                    id="download-tabs",
                    value="tab-plots",
                    children=[
                        generate_plot_download_tab(),
                        generate_csv_download_tab(),
                    ],
                    style={
                        "backgroundColor": "#1f2c44",
                    },
                )
            ),
            dcc.Download(id="download-component"),
        ],
        id="modal",
        is_open=False,
    )

    return modal


def generate_standard_graph(graph_id: str, css_class: str = "plot-450"):
    return html.Div(
        [
            dcc.Graph(id={"graph": graph_id}, className=css_class, config=COMMON_CFG),
            dcc.Store(id={"store": graph_id}),
        ]
    )


def get_options_from_ids(obj_ids: list):
    return [{"label": get_display_name(obj_id), "value": obj_id} for obj_id in obj_ids]


def get_display_name(name: str, sep: str = "-"):
    return " ".join(word.capitalize() for word in name.split(sep))


def get_fmt_download_buttons(type: str, fmts: list, side: str, is_vertical=True):
    buttons = []
    width_col = 12
    if not is_vertical:
        width_col = 12 // len(fmts)
    for fmt in fmts:
        btn = dbc.Button(
            f"Download {fmt.upper()}",
            id={"type": type, "fmt": fmt, "side": side},
            n_clicks=0,
            color="primary",
            className="ModalButton",
        )
        buttons.append(dbc.Col(btn, width=width_col))
    return dbc.Row(buttons)


def get_plot_file(df_data: pl.DataFrame, figure: go.Figure, fmt: str, plot_name: str):
    if fmt == "svg":
        content = figure.to_image(format="svg")
        return (f"{plot_name}.svg", content)
    elif fmt == "png":
        content = figure.to_image(format="png")
        return (f"{plot_name}.png", content)
    elif fmt == "json":
        content = json.dumps(figure.to_plotly_json()).encode("utf-8")
        return (f"{plot_name}.json", content)
    elif fmt == "csv":
        df = pl.read_json(io.StringIO(df_data)).explode(pl.all())
        csv_bytes = df.write_csv().encode("utf-8")
        return (f"{plot_name}.csv", csv_bytes)
    else:
        raise exceptions.PreventUpdate


def download_plots(
    selected_plots: list,
    fmt: str,
    all_figures: list,
    all_ids: list,
    all_stores: list,
    store_ids: list,
):
    if not selected_plots or not fmt:
        raise exceptions.PreventUpdate

    fig_dict = {id_dict["graph"]: fig for id_dict, fig in zip(all_ids, all_figures)}
    state_dict = {
        id_dict["store"]: data for id_dict, data in zip(store_ids, all_stores)
    }

    files = []
    for plot_id in selected_plots:
        plot_name = f"plot_{plot_id}"
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
        return dcc.send_bytes(
            lambda b: b.write(zip_buffer.read()), filename=f"plots_{fmt}.zip"
        )

    else:
        raise exceptions.PreventUpdate


def download_dataframes(
    selected_dfs: list, phase_type: list[str], days_range: list, store: dict
):
    if not selected_dfs:
        raise exceptions.PreventUpdate

    phase_type = ([phase_type] if not phase_type == 'all' else ['dark_phase', 'light_phase'])

    if len(selected_dfs) == 1:
        name = selected_dfs[0]
        if name in store:
            df = store[name].filter(
                pl.col('day').is_between(days_range[0], days_range[-1]),
                pl.col('phase').is_in(phase_type),
            )
            return dcc.send_string(df.write_csv, f"{name}.csv")
        return None

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for name in selected_dfs:
            if name in store:
                df = store[name].filter(
                    pl.col('day').is_between(days_range[0], days_range[-1]),
                    pl.col('phase').is_in(phase_type),
                )
                csv_bytes = df.write_csv().encode("utf-8")
                zf.writestr(f"{name}.csv", csv_bytes)

    zip_buffer.seek(0)

    return dcc.send_bytes(
        lambda b: b.write(zip_buffer.getvalue()), filename="selected_dataframes.zip"
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description="Run DeepEcoHab Dashboard")
    parser.add_argument(
        "--results-path",
        type=str,
        required=True,
        help="h5 file path extracted from the config (examples/test_name2_2025-04-18/results/test_name2_data.h5)",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        required=True,
        help="path to the config file of the project",
    )
    return parser.parse_args()