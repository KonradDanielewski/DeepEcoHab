import time

import dash
import dash_bootstrap_components as dbc
from dash import dcc
from dash import html, Input, Output, State, callback, no_update

from deepecohab.antenna_analysis import (
	calculate_incohort_sociability,
	calculate_pairwise_meetings,
	calculate_activity,
	calculate_cage_occupancy,
	calculate_chasings,
	calculate_ranking,
	calculate_time_alone,
)
from deepecohab.utils.cache_config import launch_cache

ANALYSIS_STEPS = [ # TODO: It should be taken from registry with delisting of some dataframes (the ones made at start of the project)
	(calculate_incohort_sociability, "Sociability"),
	(calculate_pairwise_meetings, "Pairwise Meetings"),
	(calculate_activity, "Activity"),
	(calculate_cage_occupancy, "Occupancy"),
	(calculate_chasings, "Chasings"),
	(calculate_ranking, "Ranking"),
	(calculate_time_alone, "Time Alone"),
]

dash.register_page(__name__, path="/analysis", name="Analysis")

layout = [
	dbc.Row(
		[
			dbc.Col(
				[
					html.H2("Experiment analysis", className="h2 text-center"),
				]
			),
		]
	),
	dbc.Row(
		[
			dbc.Col(
				[
					dbc.Card(
						[
							dbc.CardBody(
								[
									html.H3("Antenna analysis", className="h3"),
									dbc.Row(
										[
											dbc.Col(
												[
													dbc.Label(
														"Minimum time together", class_name="mb-3"
													),
													dbc.Input(
														id="styled-numeric-input",
														type="number",
														min=2,
														placeholder="2",
														class_name="filled-input",
													),
												],
												width=6,
											),
										],
										class_name="mb-4",
									),
									dbc.Row(
										[
											dbc.Col(
												[
													dbc.Label(
														"Chasing time window", class_name="mb-3"
													),
													dcc.RangeSlider(
														id="chasing_window",
														min=0,
														max=5,
														step=0.1,
														count=1,
														value=[0.1, 1.2],
														marks={i: str(i) for i in [0, 5]},
														tooltip={
															"placement": "bottom",
															"always_visible": False,
															"style": {
																"color": "LightSteelBlue",
																"fontSize": "12px",
															},
														},
														className="dash-slider",
													),
												],
												width=6,
											),
										],
										class_name="mb-4",
									),
									dbc.Row(
										[
											dbc.Col(
												[
													dbc.Button(
														"Analyze",
														id="antenna-button",
														color="primary",
														n_clicks=0,
														size="md",
														disabled=True,
														class_name="w-100",
													),
													html.Div(
														[
															dbc.Progress(
																id="analysis-progress",
																value=0,
																striped=True,
																animated=True,
																className="mb-3",
																style={"height": "30px"},
															),
															html.P(
																id="progress-text",
																className="progress-print",
															),
															dcc.Interval(
																id="progress-interval",
																interval=200,
																n_intervals=0,
																disabled=True,
															),
														],
														className="mt-3",
													),
												],
												width=12,
											),
										]
									),
								]
							),
						]
					),
					dbc.Card(
						[
							dbc.CardBody(
								[
									html.H3("Group analysis", className="h3"),
									dbc.Row(
										[html.H4("PLACEHOLDER", className="h4")], class_name="mb-4"
									),
									dbc.Row(
										[html.H4("PLACEHOLDER", className="h4")], class_name="mb-4"
									),
									dbc.Row(
										[
											dbc.Col(
												[
													dbc.Button(
														"PLACEHOLDER",
														id="placeholder-button",
														color="primary",
														n_clicks=0,
														size="md",
														class_name="w-100",
													),
												],
												width=12,
											),
										]
									),
								]
							),
						]
					),
				],
				width=6,
			),
			dbc.Col(
				[
					dbc.Card(
						[
							dbc.CardBody(
								[
									html.H3("Pose analysis", className="h3"),
									dbc.Row(
										[html.H4("PLACEHOLDER", className="h4")], class_name="mb-4"
									),
									dbc.Row(
										[html.H4("PLACEHOLDER", className="h4")], class_name="mb-4"
									),
									dbc.Row(
										[
											dbc.Col(
												[
													dbc.Button(
														"PLACEHOLDER",
														id="placeholder-button2",
														color="primary",
														n_clicks=0,
														size="mg",
														class_name="w-100",
													),
												],
												width=12,
											),
										]
									),
								]
							),
						]
					),
				],
				width=6,
			),
		]
	),
]


@callback(
	Output("antenna-button", "disabled", allow_duplicate=True),
	Input("project-config-store", "data"),
	prevent_initial_call="initial_duplicate",
)
def update_analysis_page(config):
	if not config:
		return "No project loaded.", True

	return False


@callback(
	[
		Output("progress-interval", "disabled"),
		Output("antenna-button", "disabled", allow_duplicate=True),
	],
	Input("antenna-button", "n_clicks"),
	State("project-config-store", "data"),
	State("styled-numeric-input", "value"),
	State("chasing_window", "value"),
	prevent_initial_call=True,
)
def start_analysis(n_clicks, config, min_time, chasing_window):
	if not n_clicks or not config:
		return no_update, no_update

	launch_cache.set("analysis_status", {"percent": 0, "msg": "Starting..."})
	total_steps = len(ANALYSIS_STEPS)

	for i, (func, name) in enumerate(ANALYSIS_STEPS):
		launch_cache.set(
			"analysis_status",
			{"percent": int((i / total_steps) * 100), "msg": f"Running {name}..."},
		)

		if func == calculate_pairwise_meetings:
			func(config, minimum_time=min_time if min_time else 2)
		elif func == calculate_chasings:
			func(config, chasing_time_window=chasing_window)
		else:
			func(config)

		new_percent = int(((i + 1) / total_steps) * 100)
		launch_cache.set("analysis_status", {"percent": new_percent, "msg": f"Finished {name}"})

	time.sleep(0.5)
	return True, True


@callback(
	[
		Output("analysis-progress", "value"),
		Output("analysis-progress", "label"),
		Output("analysis-progress", "color"),
		Output("progress-text", "children"),
	],
	Input("progress-interval", "n_intervals"),
)
def update_progress_bar(n):
	status = launch_cache.get("analysis_status")
	if not status:
		return 0, "", "primary", ""

	percent = status.get("percent", 0)
	msg = status.get("msg", "")
	color = "success" if percent == 100 else "primary"

	return percent, f"{percent}%" if percent > 5 else "", color, msg


@callback(
	Output("progress-interval", "disabled", allow_duplicate=True),
	Input("antenna-button", "n_clicks"),
	prevent_initial_call=True,
)
def enable_interval(n):
	if n:
		return False
	return no_update
