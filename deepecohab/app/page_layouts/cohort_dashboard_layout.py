import dash_bootstrap_components as dbc
from dash import dcc, html

from deepecohab.utils import auxfun_dashboard


def generate_graphs_layout(days_range: list[int]) -> html.Div:
	"""Generates layout of the main dashboard tab"""
	return html.Div(
		[
			html.Div(
				auxfun_dashboard.generate_settings_block(
					phase_type_id="phase_type",
					aggregate_stats_id="agg_switch",
					slider_id="days",
					slider_switch_id="slider_switch",
					position_switch_id="position_switch",
					pairwise_switch_id="pairwise_switch",
					ranking_switch_id="ranking_switch",
					sociability_switch_id="sociability_switch",
					days_range=days_range,
					include_download=True,
				),
				className="sticky-settings-block",
			),
			dbc.Container(
				[
					dbc.Row([dbc.Col(html.H2("Cohort overview"), className="text-left my-4")]),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"metrics-polar-line", css_class="plot-500"
									),
									color="primary",
								),
								width=6,
							),
						],
						class_name="row-size",
					),
					# Ranking, network graph, chasings
					dbc.Row([dbc.Col(html.H2("Social hierarchy"), className="text-left my-4")]),
					dbc.Row(
						[
							dbc.Col(
								dcc.RadioItems(
									id="ranking_switch",
									options=[
										{"label": "In time", "value": "intime"},
										{"label": "Day stability", "value": "stability"},
									],
									value="intime",
									className="dash-radio",
								),
								width=1,
							),
						],
						class_name="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								[
									dbc.Spinner(
										auxfun_dashboard.generate_standard_graph(
											"ranking-line", css_class="plot-350"
										),
										color="primary",
									),
									dbc.Spinner(
										auxfun_dashboard.generate_standard_graph(
											"ranking-distribution-line", css_class="plot-300"
										),
										color="primary",
									),
								],
								width=6,
							),
							dbc.Col(
								[
									dbc.Spinner(
										auxfun_dashboard.generate_standard_graph(
											"network-dominance",
											css_class="plot-650",
										),
										color="primary",
									),
								],
								width=6,
							),
						],
						class_name="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph("tube-test-heatmap"),
									color="primary",
								),
								width=3,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph("chasings-heatmap"),
									color="primary",
								),
								width=3,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph("chasings-line"),
									color="primary",
								),
								width=6,
							),
						],
						className="row-size",
					),
					# Activity per hour line and per position bar
					dbc.Row([dbc.Col(html.H2("Activity", className="text-left mb-2"))]),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"cage-preference-evolution", css_class="plot-400"
									),
									color="primary",
								),
								width=8,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"cage-preference", css_class="plot-400"
									),
									color="primary",
								),
								width=4,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dcc.RadioItems(
									id="position_switch",
									options=[
										{"label": "Visits", "value": "visits"},
										{"label": "Time", "value": "time"},
									],
									value="visits",
									className="dash-radio",
								),
								width=1,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph("activity-bar"),
									color="primary",
								),
								width=6,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph("activity-line"),
									color="primary",
								),
								width=6,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"time-per-cage-heatmap", css_class="plot-400"
									),
									color="primary",
								),
								width=12,
							),
						],
						className="gx-3 gy-0",
					),
					# Pairwise and incohort heatmaps
					dbc.Row(
						[
							dbc.Col(html.H2("Sociability"), className="text-left mb-2"),
						]
					),
					dbc.Row(
						[
							dbc.Col(
								dcc.RadioItems(
									id="pairwise_switch",
									options=[
										{"label": "Visits", "value": "pairwise_encounters"},
										{"label": "Time", "value": "time_together"},
									],
									value="pairwise_encounters",
									className="dash-radio",
								),
								width=1,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"sociability-heatmap", css_class="plot-600"
									),
									color="primary",
								),
								width=6,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"network-sociability",
										css_class="plot-600",
									),
									color="primary",
								),
								width=6,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dcc.RadioItems(
									id="sociability_switch",
									options=[
										{"label": "Time together", "value": "proportion_together"},
										{"label": "Incohort sociability", "value": "sociability"},
									],
									value="proportion_together",
									className="dash-radio",
								),
								width=2,
							),
						],
						className="row-size",
					),
					dbc.Row(
						[
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"cohort-heatmap", css_class="plot-500"
									),
									color="primary",
								),
								width=4,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"social-stability", css_class="plot-500"
									),
									color="primary",
								),
								width=4,
							),
							dbc.Col(
								dbc.Spinner(
									auxfun_dashboard.generate_standard_graph(
										"time-alone-bar", css_class="plot-500"
									),
									color="primary",
								),
								width=4,
							),
						],
						className="row-size",
					),
				],
				fluid=True,
			),
		],
	)


def generate_comparison_layout(phase_range: list[int, int]) -> html.Div:
	"""Generates layout for the comparisons tab"""
	return html.Div(
		[
			html.H2("Plot Comparison", className="text-center my-4"),
			dbc.Row(
				[
					dbc.Col(
						dbc.Spinner(
							auxfun_dashboard.generate_comparison_block("left", phase_range),
							color="primary",
						),
						width=6,
					),
					dbc.Col(
						dbc.Spinner(
							auxfun_dashboard.generate_comparison_block("right", phase_range),
							color="primary",
						),
						width=6,
					),
				],
				className="g-4",
			),
		]
	)
