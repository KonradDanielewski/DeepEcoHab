import base64
import datetime as dt
from pathlib import Path
from typing import Any

import dash
import dash_bootstrap_components as dbc
import toml
from dash import (
	ALL,
	Input,
	Output,
	State,
	callback,
	ctx,
	no_update,
	clientside_callback,
)

from deepecohab.app.page_layouts import home_layout
from deepecohab.core import create_data_structure, create_project
from deepecohab.utils.cache_config import launch_cache
from deepecohab.utils import auxfun_dashboard


dash.register_page(__name__, path="/", name="Home")

layout = home_layout.generate_layout()


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
def validate_and_highlight(
	inputs: list[str], current_valid: list[bool], current_invalid: list[bool]
):
	"""Helper callback to highlight if an input is correct or no."""
	if not ctx.triggered_id:
		return no_update

	inputs_meta = ctx.inputs_list[0]

	technical_validity = [
		auxfun_dashboard._get_status(meta["id"]["index"], val)
		for meta, val in zip(inputs_meta, inputs)
	]

	new_valid_ui = []
	new_invalid_ui = []

	for meta, is_valid, old_v, old_inv in zip(
		inputs_meta, technical_validity, current_valid, current_invalid
	):
		if meta["id"] == ctx.triggered_id:
			new_valid_ui.append(is_valid)
			new_invalid_ui.append(not is_valid)
		else:
			new_valid_ui.append(old_v)
			new_invalid_ui.append(old_inv)

	button_disabled = not all(technical_validity)

	return button_disabled, new_valid_ui, new_invalid_ui


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
		Output("btn-text", "children"),
		Output("create-project-btn", "color"),
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
		State("interpolate-check", "value"),
		State("sanitize-check", "value"),
		State("min-cross", "value"),
	],
	prevent_initial_call=True,
)
def _create_project(
	n_clicks: int,
	name: str,
	project_location: str,
	data_path: str,
	light_start: str,
	dark_start: str,
	ext: str,  # placeholder for now
	prefix: str,
	timezone: str,
	animals: str,
	layouts: list[bool],
	exp_start: str,
	exp_end: str,
	interpolate: bool,
	sanitize: bool,
	min_cross: int,
) -> tuple[dict[str, Any], dbc.Toast, str, str]:
	"""Project creation callback.

	Args:
		n_clicks: _description_
		name: project name.
		project_location: location where project will be created.
		data_path: path to raw data from the acquisition software.
		light_start: hour and minute of light phase start.
		dark_start: hour and minute of dark phase start.
		ext: extension of the file containing raw data.
		timezone: IANA format timezone.
		animals: comma separated string of animal names.
		layouts: type of layout.
		exp_start: datetime of experiment start.
		exp_end: datetime of experiment end.
		interpolate: toogle whether to use interpolated antenna combinations or no (handles position estimation if only one antenna missing).
		sanitize: toggle whether to sanitize animal ids.
		min_cross: minimum number of antenna crossings used within the sanitation.

	Returns:
		dict of the project config, toast with info, type of info.
	"""    
	if n_clicks == 0:
		return no_update, no_update, "Create Project", "primary"

	animal_ids = [i.strip() for i in animals.split(",")] if animals else None
	is_field = "field" in layouts
	if "field" in layouts:
		is_custom = True
	else:
		is_custom = "custom" in layouts

	project_location = Path(project_location)
	if not project_location.is_dir():
		project_location.mkdir(parents=True, exist_ok=True)

	try:
		config_path, _ = create_project.create_ecohab_project(
			project_location=project_location,
			data_path=data_path,
			experiment_name=name,
			light_phase_start=light_start,
			dark_phase_start=dark_start,
			animal_ids=animal_ids,
			custom_layout=is_custom,
			field_ecohab=is_field,
			start_datetime=exp_start,
			finish_datetime=exp_end,
			interpolate_positions=interpolate,
		)

		create_data_structure.get_ecohab_data_structure(
			config_path,
			sanitize_animal_ids=sanitize,
			min_antenna_crossings=int(min_cross),
			fname_prefix=prefix,
			custom_layout=is_custom,
			timezone=timezone,
		)
		config_dict = toml.load(config_path)

		match _:
			case "exists":
				return (
					config_dict,
					dbc.Toast(
						f"Project already exists at {config_path}! Loaded existing.",
						id="project-success-toast",
						header="Warning",
						is_open=True,
						dismissable=True,
						icon="warning",
						duration=10000,
						class_name="custom-toast toast-warning",
					),
					"Warning!",
					"warning",
				)
			case "created":
				return (
					config_dict,
					dbc.Toast(
						f"Project created at: {config_path}",
						id="project-success-toast",
						header="Success",
						is_open=True,
						dismissable=True,
						icon="success",
						duration=10000,
						class_name="custom-toast toast-success",
					),
					"Success!",
					"success",
				)

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
				class_name="custom-toast toast-danger",
			),
			"Try Again",
			"danger",
		]


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("load-project-modal", "is_open", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
	],
	Input("upload-config", "contents"),
	State("upload-config", "filename"),
	prevent_initial_call=True,
)
def load_config_to_store(
	contents: dict[str, Any], filename: str
) -> tuple[dict[str, Any], bool, dbc.Toast]:
	"""Helper to load the config into cache for the period of the session."""
	if not contents:
		return [no_update] * 3

	try:
		content_string = contents.split(",")[-1]
		decoded = base64.b64decode(content_string).decode("utf-8")
		config_dict = toml.loads(decoded)

		return (
			config_dict,
			False,
			dbc.Toast(
				f"Loaded {filename} into session",
				header="Success",
				icon="success",
				duration=10000,
				className="custom-toast toast-success",
			),
		)

	except Exception as e:
		error_toast = dbc.Toast(
			f"Failed to load {filename}: {str(e)}",
			header="Load Error",
			icon="danger",
			className="custom-toast toast-danger",
		)
		return no_update, True, error_toast


@callback(
	[
		Output("project-config-store", "data", allow_duplicate=True),
		Output("toast-container", "children", allow_duplicate=True),
	],
	Input("clear-session-btn", "n_clicks"),
	prevent_initial_call=True,
)
def clear_app_cache(n_clicks: int) -> tuple[None, dbc.Toast]:
	"""Helper to clear the cache for clean load of another project."""
	if not n_clicks:
		return no_update, no_update

	launch_cache.clear()

	return (
		None,
		dbc.Toast(
			"Session and cache cleared. You can now load a new project.",
			header="System Reset",
			icon="info",
			duration=10000,
			className="custom-toast toast-info",
		),
	)


clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="is_disabled"),
	Output("clear-session-btn", "disabled"),
	Input("project-config-store", "data"),
)


clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="toggle_bool"),
	Output("load-project-modal", "is_open"),
	Input("load-project", "n_clicks"),
	State("load-project-modal", "is_open"),
	prevent_initial_call=True,
)

clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="toggle_bool"),
	Output("opt-collapse", "is_open"),
	Input("opt-btn", "n_clicks"),
	State("opt-collapse", "is_open"),
	prevent_initial_call=True,
)

clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="is_checked"),
	Output("min-cross", "disabled"),
	Input("sanitize-check", "value"),
)
