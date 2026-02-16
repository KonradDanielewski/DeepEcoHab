import dash_bootstrap_components as dbc
from dash import dcc, html


def generate_input_block(
	label_name: str,
	id: str | dict[str, str],
	placeholder: str,
	required: bool,
	value: str | None = None,
	type: str | None = None,
) -> list[dbc.Label, dbc.Input]:

	return [
		dbc.Label(label_name, className="home-label"),
		dbc.Input(
			id=id,
			placeholder=placeholder,
			required=required,
			value=value,
			type=type,
			className="filled-input",
			debounce=True,
		),
	]


modal = dbc.Modal(
	[
		dbc.ModalHeader([dbc.ModalTitle("Upload config")]),
		dbc.ModalBody(
			[
				dcc.Upload(
					id="upload-config",
					children=html.Div(["Drag and Drop or ", html.A("Select config.toml")]),
					className="upload_config",
				),
				html.Div(id="output-config-upload"),
			]
		),
	],
	id="load-project-modal",
	is_open=False,
)


def generate_layout():
	return dbc.Row(
		[
			dbc.Col(
				[
					html.H2("Project Configuration", className="h2"),
					dbc.Card(
						[
							dbc.CardBody(
								[
									*generate_input_block(
										label_name="Project Name:",
										id={"type": "required-input", "index": "proj-name"},
										placeholder="test_project",
										required=True,
									),
									*generate_input_block(
										label_name="Project Location:",
										id={"type": "required-input", "index": "proj-loc"},
										placeholder="/etc/home/Documents/projects",
										required=True,
									),
									*generate_input_block(
										label_name="Location of Raw Data:",
										id={"type": "required-input", "index": "data-loc"},
										placeholder="/etc/home/Documents/data",
										required=True,
									),
									dbc.Row(
										[
											dbc.Col(
												generate_input_block(
													label_name="Start Light Phase:",
													id={
														"type": "required-input",
														"index": "light-start",
													},
													placeholder="00:00",
													required=True,
													type="time",
												),
												width=6,
											),
											dbc.Col(
												generate_input_block(
													label_name="Start Dark Phase:",
													id={
														"type": "required-input",
														"index": "dark-start",
													},
													placeholder="12:00",
													required=True,
													type="time",
												),
												width=6,
											),
										],
										className="mb-3",
									),
									dbc.Button(
										"Optional Settings",
										id="opt-btn",
										color="link",
										size="sm",
										className="p-0 mb-2",
									),
									dbc.Collapse(
										html.Div(
											[
												dbc.Row(
													[
														dbc.Col(
															generate_input_block(
																label_name="Start datetime:",
																id="experiment-start",
																placeholder="2024-11-05 00:00:00",
																required=False,
															),
															width=6,
														),
														dbc.Col(
															generate_input_block(
																label_name="End datetime:",
																id="experiment-end",
																placeholder="2024-11-29 12:00:00",
																required=False,
															),
															width=6,
														),
													],
													className="mb-3",
												),
												dbc.Row(
													[
														dbc.Col(
															generate_input_block(
																label_name="Data extension",
																id="file_ext",
																placeholder="txt",
																required=False,
																value="txt",
															),
														),
														dbc.Col(
															generate_input_block(
																label_name="Data prefix",
																id="file_prefix",
																placeholder="COM",
																required=False,
																value="COM",
															),
														),
														dbc.Col(
															generate_input_block(
																label_name="Timezone",
																id="timezone",
																placeholder="Europe/Warsaw",
																required=False,
																value="Europe/Warsaw",
															),
														),
													]
												),
												dbc.Row(
													[
														dbc.Col(
															generate_input_block(
																label_name="Animal IDs:",
																id="animal-ids",
																placeholder="ID_01, ID_02, etc.",
																required=False,
															),
															align="center",
															width=7,
														),
														dbc.Col(
															[
																dbc.Row(
																	[
																		dbc.Col(
																			dbc.Label(
																				"Sanitize IDs:",
																				className="home-label",
																			)
																		),
																		dbc.Col(
																			dbc.Checkbox(
																				id="sanitize-check",
																				value=True,
																				className="checkbox",
																			),
																			align="center",
																		),
																	],
																	className="mb-0",
																),
																dbc.Row(
																	[
																		dbc.Col(
																			dbc.Label(
																				"Min antenna crossings:",
																				className="home-label",
																			)
																		),
																		dbc.Col(
																			dbc.Input(
																				id="min-cross",
																				placeholder=100,
																				value=100,
																				type="number",
																				step=1,
																				className="filled-input",
																			)
																		),
																	],
																	className="mb-0",
																),
															],
															align="center",
														),
													],
													align="end",
												),
												dbc.Row(
													[
														dbc.Col(
															[
																dbc.Label(
																	"Layout settings:",
																	className="home-label",
																),
																dbc.Checklist(
																	options=[
																		{
																			"label": " Field layout",
																			"value": "field",
																		},
																	],
																	value=[],
																	id="layout-checks",
																	inline=True,
																	className="mb-3",
																),
															]
														),
													]
												),
											]
										),
										id="opt-collapse",
										is_open=False,
									),
									dbc.Row(
										[
											dbc.Col(
												dbc.Button(
													children=[dbc.Spinner(
														html.Span("Create Project", id="btn-text"),
														size="sm",
														spinner_class_name="me-2",
													)],
													id="create-project-btn",
													color="primary",
													disabled=True,
													className="w-100 mt-3",
													n_clicks=0,
												),
												width=4,
											),
											dbc.Col(
												dbc.Container(
													[
														dbc.Button(
															"Load project",
															id="load-project",
															color="primary",
															className="w-100 mt-3",
															n_clicks=0,
														),
														modal,
													]
												),
												width=4,
											),
											dbc.Col(
												dbc.Button(
													"Clear Session",
													id="clear-session-btn",
													disabled=True,
													className="w-100 mt-3",
													n_clicks=0,
												)
											),
										]
									),
								]
							)
						],
						className="shadow",
					),
					html.Div(
						id="toast-container",
						className="toast-container",
					),
				],
				xs=12,
				sm=12,
				md=8,
				lg=6,
			),
			dbc.Col(
				html.Img(src="assets/logo_test.png", width=500, height=500),
				className="fullscreen_centered",
			),
		],
		justify="left",
		align="center",
	)
