import dash_bootstrap_components as dbc
from dash import dcc, html

from deepecohab.utils import auxfun_dashboard


def generate_graphs_layout(phase_range: list[int, int]) -> html.Div:
    return html.Div(
        [
            auxfun_dashboard.generate_settings_block(
                "mode-switch",
                "aggregate-stats-switch",
                "phase-slider",
                phase_range,
                include_download=True,
            ),
            dbc.Container(
                [
                    # Ranking, network graph, chasings
                    dbc.Row(
                        [
                            dbc.Col(
                                html.H2("Social hierarchy"), className="text-left my-4"
                            )
                        ]
                    ),
                    dbc.Row([]),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    auxfun_dashboard.generate_standard_graph(
                                        "ranking-line", css_class="plot-500"
                                    ),
                                    auxfun_dashboard.generate_standard_graph(
                                        "ranking-distribution-line"
                                    ),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    auxfun_dashboard.generate_standard_graph(
                                        "metrics-polar-line", css_class="plot-500"
                                    ),
                                    auxfun_dashboard.generate_standard_graph(
                                        "network-graph", css_class="plot-500"
                                    ),
                                ],
                                width=6,
                            ),
                        ],
                        className="g-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "chasings-heatmap"
                                ),
                                width=6,
                            ),
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "chasings-line"
                                ),
                                width=6,
                            ),
                        ],
                        className="g-3",
                    ),
                    # Activity per hour line and per position bar
                    dbc.Row([dbc.Col(html.H2("Activity"), className="text-left my-4")]),
                    dbc.Row(
                        [
                            dbc.Col(
                                dcc.RadioItems(
                                    id="position-switch",
                                    options=[
                                        {"label": "Visits", "value": "visits"},
                                        {"label": "Time", "value": "time"},
                                    ],
                                    value="visits",
                                    labelStyle={"display": "inline-block"},
                                ),
                                width=1,
                            ),
                        ]
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "activity-bar"
                                ),
                                width=6,
                            ),
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "activity-line"
                                ),
                                width=6,
                            ),
                        ],
                        className="g-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "time-per-cage-heatmap", css_class="plot-500"
                                ),
                                width=12,
                            ),
                        ],
                        className="g-3",
                    ),
                    # Pairwise and incohort heatmaps
                    dbc.Row(
                        [dbc.Col(html.H2("Sociability"), className="text-left my-4")]
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                dcc.RadioItems(
                                    id="pairwise-switch",
                                    options=[
                                        {"label": "Visits", "value": "pairwise_encounters"},
                                        {"label": "Time", "value": "time_together"},
                                    ],
                                    value="pairwise_encounters",
                                    labelStyle={"display": "inline-block"},
                                ),
                                width=1,
                            ),
                        ]
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                    "sociability-heatmap", css_class="plot-600"
                                ),
                                width=6,
                            ),
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                        "cohort-heatmap", css_class="plot-600"
                                    ),
                                width=6,
                                ),

                        ],
                        className="g-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                auxfun_dashboard.generate_standard_graph(
                                        "time-alone-bar", css_class="plot-500"
                                    ),
                                width=6,
                                ),
                        ],
                    ),
                ],
                fluid=True,
                style={"padding": "20px"},
            ),
        ]
    )


def generate_comparison_layout(phase_range: list[int, int]) -> html.Div:
    return html.Div(
        [
            html.H2("Plot Comparison", className="text-center my-4"),
            dbc.Row(
                [
                    dbc.Col(
                        auxfun_dashboard.generate_comparison_block(
                            "left", phase_range
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        auxfun_dashboard.generate_comparison_block(
                            "right", phase_range
                        ),
                        width=6,
                    ),
                ],
                className="g-4",
            ),
        ]
    )
