import dash_bootstrap_components as dbc
from dash import dcc, html

from deepecohab.utils import auxfun_dashboard


def generate_graphs_layout(days_range: list[int, int]) -> html.Div:
	"""Generates layout of the main dashboard tab"""
	return html.Div(
		[
			auxfun_dashboard.generate_settings_block(
				phase_type_id="phase_type",
				aggregate_stats_id="agg_switch",
				slider_id="days_range",
				position_switch_id="position_switch",
				pairwise_switch_id="pairwise_switch",
				sociability_switch_id="sociability_switch",
				days_range=days_range,
				include_download=True,
			),
			dbc.Container(
				[
					# Ranking, network graph, chasings
					dbc.Row([dbc.Col(html.H2("Social hierarchy"), className="text-left my-4")]),
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
										"network-dominance", css_class="plot-500"
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
								auxfun_dashboard.generate_standard_graph("chasings-heatmap"),
								width=6,
							),
							dbc.Col(
								auxfun_dashboard.generate_standard_graph("chasings-line"),
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
									id="position_switch",
									options=[
										{"label": "Visits", "value": "visits"},
										{"label": "Time", "value": "time"},
									],
									value="visits",
								),
								width=1,
							),
						]
					),
					dbc.Row(
						[
							dbc.Col(
								auxfun_dashboard.generate_standard_graph("activity-bar"),
								width=6,
							),
							dbc.Col(
								auxfun_dashboard.generate_standard_graph("activity-line"),
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
					dbc.Row([dbc.Col(html.H2("Sociability"), className="text-left my-4")]),
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
									"network-sociability", css_class="plot-600"
								),
								width=6,
							),
						],
						className="g-3",
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
								),
								width=2,
							),
						], className="mt-5"
					),
					dbc.Row(
						[
							dbc.Col(
								auxfun_dashboard.generate_standard_graph(
									"cohort-heatmap", css_class="plot-500"
								),
								width=6,
							),
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
			),
		]
	)


def generate_comparison_layout(phase_range: list[int, int]) -> html.Div:
	"""Generates layout for the comparisons tab"""
	return html.Div(
		[
			html.H2("Plot Comparison", className="text-center my-4"),
			dbc.Row(
				[
					dbc.Col(
						auxfun_dashboard.generate_comparison_block("left", phase_range),
						width=6,
					),
					dbc.Col(
						auxfun_dashboard.generate_comparison_block("right", phase_range),
						width=6,
					),
				],
				className="g-4",
			),
		]
	)
