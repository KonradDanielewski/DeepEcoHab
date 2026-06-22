import dash_bootstrap_components as dbc
from dash import dcc, html


def _field(label, control, help_text):
	"""One label/control/helper-text group with consistent spacing."""
	return html.Div(
		[
			dbc.Label(label, class_name="input-label"),
			control,
			dbc.FormText(help_text, class_name="form-help"),
		],
		className="form-field",
	)


def generate_cohort_card():
	"""Build the antenna-analysis card for the analysis page."""
	return dbc.Card(
		[
			dbc.CardBody(
				[
					html.H3("Antenna analysis", className="h3"),
					html.P(
						"Detect pairwise meetings, tube-test wins and chasings "
						"from antenna recordings. Tune the parameters below, then "
						"run the analysis.",
						className="card-intro",
					),
					_field(
						"Minimum time together [s]",
						dbc.Input(
							id="numeric-input",
							type="number",
							min=0,
							value=2,
							placeholder="2",
							class_name="filled-input",
						),
						"Shortest continuous co-presence counted as a pairwise "
						"meeting; also drives in-cohort sociability.",
					),
					_field(
						"Maximum tunnel dwell time [s]",
						dbc.Input(
							id="tube-dwell-input",
							type="number",
							min=0,
							value=10,
							placeholder="10",
							class_name="filled-input",
						),
						"Caps tunnel dwell time when detecting tube test wins.",
					),
					_field(
						"Chasing time window [s]",
						dcc.RangeSlider(
							id="chasing_window",
							min=0,
							max=5,
							step=0.1,
							count=1,
							value=[0.1, 1.2],
							marks={i: str(i) for i in [0, 5]},
							allow_direct_input=False,
							tooltip={
								"placement": "bottom",
								"always_visible": True,
							},
							className="rc-slider",
						),
						"Min-max duration of a tunnel-following event counted as a chasing.",
					),
					html.Hr(className="card-divider"),
					dbc.Switch(
						id="overwrite-check",
						label="Overwrite existing results",
						value=False,
						class_name="overwrite-switch",
					),
					dbc.Button(
						"Analyze",
						id="antenna-button",
						color="primary",
						n_clicks=0,
						size="md",
						disabled=True,
						class_name="w-100 mt-2",
					),
					html.Div(
						[
							dbc.Progress(
								id="analysis-progress",
								value=0,
								striped=True,
								animated=True,
								className="progress-bar",
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
				]
			),
		],
		className="analysis-form-card",
	)


def generate_layout():
	"""Build the full layout for the experiment analysis page."""
	return [
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
						generate_cohort_card(),
					],
					width="auto",
				),
			],
			justify="center",
		),
	]
