import datetime as dt
from pathlib import Path
import dash
import dash_bootstrap_components as dbc
import base64
import toml
from dash import dcc, html, Input, Output, State, callback, no_update, ALL, ctx

import polars as pl

from deepecohab.core import create_project
from deepecohab.core import create_data_structure
from deepecohab.utils.cache_config import get_project_data, launch_cache


def is_valid_time(time_str):
	try:
		dt.time.strptime(str(time_str), "%H:%M:%S")
		return True
	except (ValueError, TypeError):
		return False


dash.register_page(__name__, path="/", name="Home")

modal = dbc.Modal(
	[
		dbc.ModalHeader([dbc.ModalTitle("Downloads")]),
		dbc.ModalBody(
			[
				dcc.Upload(
					id="upload-data",
					children=html.Div(["Drag and Drop or ", html.A("Select Files")]),
					style={
						"width": "100%",
						"height": "60px",
						"lineHeight": "60px",
						"borderWidth": "1px",
						"borderStyle": "dashed",
						"borderRadius": "5px",
						"textAlign": "center",
						"margin": "10px",
					},
				),
				html.Div(id="output-data-upload"),
			]
		),
	],
	id="load-project-modal",
	is_open=False,
)

layout = dbc.Row(
	[
		dbc.Col(
			[
				html.H2("Project Configuration", className="h2"),
				dbc.Card(
					[
						dbc.CardBody(
							[
								dbc.Label("Project Name:", className="home-label"),
								dbc.Input(
									id={"type": "required-input", "index": "proj-name"},
									placeholder="test_project",
									required=True,
									className="filled-input",
								),
								dbc.Label("Project Location:", className="home-label"),
								dbc.Input(
									id={"type": "required-input", "index": "proj-loc"},
									placeholder="/etc/home/Documents/projects",
									required=True,
									className="filled-input",
								),
								dbc.Label("Location of Raw Data:", className="home-label"),
								dbc.Input(
									id={"type": "required-input", "index": "data-loc"},
									placeholder="/etc/home/Documents/data",
									required=True,
									className="filled-input",
								),
								dbc.Row(
									[
										dbc.Col(
											[
												dbc.Label(
													"Start Light Phase:", className="home-label"
												),
												dbc.Input(
													id={
														"type": "required-input",
														"index": "light-start",
													},
													placeholder="00:00:00",
													required=True,
													className="filled-input",
												),
											],
											width=6,
										),
										dbc.Col(
											[
												dbc.Label(
													"Start Dark Phase:", className="home-label"
												),
												dbc.Input(
													id={
														"type": "required-input",
														"index": "dark-start",
													},
													placeholder="12:00:00",
													required=True,
													className="filled-input",
												),
											],
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
														[
															dbc.Label(
																"Start datetime:",
																className="home-label",
															),
															dbc.Input(
																id="experiment-start",
																placeholder="2024-11-05 00:00:00",
																value=None,
																className="filled-input",
															),
														],
														width=6,
													),
													dbc.Col(
														[
															dbc.Label(
																"End datetime:",
																className="home-label",
															),
															dbc.Input(
																id="experiment-end",
																placeholder="2024-11-29 12:00:00",
																value=None,
																className="filled-input",
															),
														],
														width=6,
													),
												],
												className="mb-3",
											),
											dbc.Row(
												[
													dbc.Col(
														[
															dbc.Label(
																"Data extension",
																class_name="home-label",
															),
															dbc.Input(
																id="file_ext",
																placeholder="txt",
																value="txt",
																className="filled-input",
															),
														]
													),
													dbc.Col(
														[
															dbc.Label(
																"Data prefix",
																class_name="home-label",
															),
															dbc.Input(
																id="file_prefix",
																placeholder="COM",
																value="COM",
																className="filled-input",
															),
														]
													),
													dbc.Col(
														[
															dbc.Label(
																"Timezone", class_name="home-label"
															),
															dbc.Input(
																id="timezone",
																placeholder="Europe/Warsaw",
																value="Europe/Warsaw",
																className="filled-input",
															),
														]
													),
												]
											),
											dbc.Row(
												[
													dbc.Col(
														[
															dbc.Label(
																"Animal IDs:",
																class_name="home-label",
															),
															dbc.Input(
																id="animal-ids",
																placeholder="ID_01, ID_02, etc.",
																value=None,
																className="filled-input",
															),
														],
														width=7,
													),
													dbc.Col(
														[
															dbc.Label(
																"Sanitize IDs:",
																class_name="home-label",
															),
															dbc.Label(
																"Min antenna crossings:",
																class_name="home-label",
															),
														]
													),
													dbc.Col(
														[
															dbc.Checkbox(
																id="sanitize-check",
																value=True,
																class_name="checkbox",
															),
															dbc.Input(
																id="min-cross",
																placeholder=100,
																value=100,
																type="number",
																step=1,
																class_name="filled-input mb-0",
															),
														]
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
																		"label": " Custom layout",
																		"value": "custom",
																	},
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
												"Create Project",
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
					className="position-fixed top-0 end-0 p-3 txt",
					style={"zIndex": 1050},
				),
			],
			xs=12,
			sm=12,
			md=8,
			lg=6,
		),
		dbc.Col(
			html.Img(src="assets/logo_test.png", width=500, height=500),
			className="d-flex justify-content-center align-items-center",
			style={"height": "100vh"},
		),
	],
	justify="left",
	align="center",
)


@callback(
	Output("load-project-modal", "is_open"),
	Input("load-project", "n_clicks"),
	State("load-project-modal", "is_open"),
	prevent_initial_call=True,
)
def toggle_modal(n_clicks, is_open):
	"""Opens and closes Downloads modal component"""
	if n_clicks:
		return not is_open
	return is_open


@callback(
	Output("opt-collapse", "is_open"),
	Input("opt-btn", "n_clicks"),
	State("opt-collapse", "is_open"),
	prevent_initial_call=True,
)
def toggle_opt(n, is_open):
	return not is_open


@callback(
	Output("layout-checks", "value"), Input("layout-checks", "value"), prevent_initial_call=True
)
def sync_checks(selected):
	if not selected:
		return no_update

	if "field" in selected and "custom" not in selected:
		return selected + ["custom"]

	return no_update


@callback(
	[
		Output("create-project-btn", "disabled"),
		Output({"type": "required-input", "index": ALL}, "valid"),
		Output({"type": "required-input", "index": ALL}, "invalid"),
	],
	Input({"type": "required-input", "index": ALL}, "value"),
	State({"type": "required-input", "index": ALL}, "valid"),
	State({"type": "required-input", "index": ALL}, "invalid"),
	prevent_initial_call=True,
)
def validate_and_highlight(values, current_valid_states, current_invalid_states):
	triggered_id = ctx.triggered_id
	if not triggered_id:
		return no_update

	inputs_info = ctx.inputs_list[0]

	new_valid_states = []
	new_invalid_states = []

	all_technically_valid = []

	for i, item in enumerate(inputs_info):
		idx = item["id"]["index"]
		val = values[i]

		is_empty = not (val and str(val).strip())

		if is_empty:
			is_valid = False
		elif idx in ["proj-loc", "data-loc"]:
			is_valid = Path(str(val)).is_dir()
		elif idx in ["light-start", "dark-start"]:
			is_valid = is_valid_time(val)
		else:
			is_valid = True

		all_technically_valid.append(is_valid)

		if item["id"] == triggered_id:
			new_valid_states.append(is_valid)
			new_invalid_states.append(not is_valid)
		else:
			new_valid_states.append(current_valid_states[i])
			new_invalid_states.append(current_invalid_states[i])

	button_disabled = not all(all_technically_valid)

	return button_disabled, new_valid_states, new_invalid_states


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
	],
	Input("create-project-btn", "n_clicks"),
	[
		State({"type": "required-input", "index": "proj-name"}, "value"),
		State({"type": "required-input", "index": "proj-loc"}, "value"),
		State({"type": "required-input", "index": "data-loc"}, "value"),
		State({"type": "required-input", "index": "light-start"}, "value"),
		State({"type": "required-input", "index": "dark-start"}, "value"),
		State("file_ext", "value"),
		State("file_prefix", "value"),
		State("timezone", "value"),
		State("animal-ids", "value"),
		State("layout-checks", "value"),
		State("experiment-start", "value"),
		State("experiment-end", "value"),
		State("sanitize-check", "value"),
		State("min-cross", "value"),
	],
	prevent_initial_call=True,
)
def _create_project(
	n_clicks,
	name,
	loc,
	data,
	light,
	dark,
	ext,
	prefix,
	tz,
	animals,
	layouts,
	exp_start,
	exp_end,
	sanitize,
	min_cross,
):
	if n_clicks == 0:
		return no_update

	id_list = [i.strip() for i in animals.split(",")] if animals else None
	is_custom = "custom" in layouts
	is_field = "field" in layouts

	try:
		config_path = create_project.create_ecohab_project(
			project_location=loc,
			data_path=data,
			experiment_name=name,
			light_phase_start=light,
			dark_phase_start=dark,
			animal_ids=id_list,
			custom_layout=is_custom,
			field_ecohab=is_field,
			start_datetime=exp_start,
			finish_datetime=exp_end,
		)

		create_data_structure.get_ecohab_data_structure(
			config_path,
			sanitize_animal_ids=sanitize,
			min_antenna_crossings=int(min_cross),
			fname_prefix=prefix,
			custom_layout=is_custom,
			timezone=tz,
		)
		config_dict = toml.load(config_path)

		if isinstance(config_dict, dict):
			return (
				config_dict,
				dbc.Toast(
					f"Project created at: {config_path}",
					id="project-success-toast",
					header="Success",
					is_open=True,
					dismissable=True,
					icon="success",
					duration=5000,
					class_name="custom-toast",
					style={"width": 350},
				),
			)
		else:
			raise Exception("Couldn't create the EcoHab data structure!")

	except Exception as e:
		return [
			"",
			dbc.Toast(
				f"Error: {str(e)}",
				id="project-error-toast",
				header="Project Creation Failed",
				is_open=True,
				dismissable=True,
				icon="danger",
				style={"width": 350},
				class_name="custom-toast",
			),
		]


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("load-project-modal", "is_open", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
	],
	Input("upload-data", "contents"),
	State("upload-data", "filename"),
	prevent_initial_call=True,
)
def load_config_to_store(contents, filename):
	if not contents:
		return [no_update] * 3

	try:
		content_type, content_string = contents.split(",")
		decoded = base64.b64decode(content_string).decode("utf-8")
		config_dict = toml.loads(decoded)
		get_project_data(config_dict)

		return [
			config_dict,
			False,
			dbc.Toast(
				f"Loaded {filename} into session",
				header="Success",
				icon="success",
				duration=3000,
				className="custom-toast",
			),
		]

	except Exception as e:
		error_toast = dbc.Toast(
			f"Error: {str(e)}", header="Load Error", icon="danger", className="custom-toast"
		)
		return [no_update, no_update, no_update, no_update, no_update, no_update, True, error_toast]


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
	],
	Input("clear-session-btn", "n_clicks"),
	prevent_initial_call=True,
)
def clear_app_cache(n_clicks):
	if not n_clicks:
		return no_update, no_update

	launch_cache.clear()
	launch_cache.cull()

	return (
		None,
		dbc.Toast(
			"Session and cache cleared. You can now load a new project.",
			header="System Reset",
			icon="info",
			duration=4000,
			className="custom-toast",
		),
	)


@callback(
	Output("clear-session-btn", "disabled"),
	Input("project-config-store", "data"),
)
def toggle_clear_button(config_data):
	return config_data is None or not config_data
