import time
from typing import Any

import dash
from dash import (
	Input,
	Output,
	State,
	callback,
	clientside_callback,
	no_update,
)

from deepecohab.app.page_layouts import analysis_layout
from deepecohab.core.registries import df_registry
from deepecohab.utils import cache_config

dash.register_page(__name__, path="/analysis", name="Analysis")

layout = analysis_layout.generate_layout()


@callback(
	[
		Output("progress-interval", "disabled"),
		Output("antenna-button", "disabled", allow_duplicate=True),
	],
	Input("antenna-button", "n_clicks"),
	[
		State("project-config-store", "data"),
		State("numeric-input", "value"),
		State("chasing_window", "value"),
		State("tube-dwell-input", "value"),
		State("overwrite-check", "value"),
	],
	prevent_initial_call=True,
)
def start_analysis(
	n_clicks: int,
	config: dict[str, Any],
	min_time: float,
	chasing_window: list[float],
	max_dwell: float,
	overwrite: bool,
) -> tuple[bool, bool]:
	"""Run analysis for antenna data."""
	if not n_clicks or not config:
		# Dash no_update sentinels leave both outputs untouched until analysis is triggered.
		return no_update, no_update  # ty: ignore[invalid-return-type]

	pipeline_generator = df_registry.run_pipeline(
		config,
		minimum_time=min_time,
		chasing_time_window=chasing_window,
		max_dwell=max_dwell,
		overwrite=overwrite,
	)

	for step_name, current, total in pipeline_generator:
		percent = int((current / total) * 100)

		cache_config.launch_cache.set(
			"analysis_status", {"percent": percent, "msg": f"Running {step_name}..."}
		)

	cache_config.launch_cache.set("analysis_status", {"percent": 100, "msg": "Analysis Complete"})
	time.sleep(0.5)
	cache_config.get_project_data(config)

	return True, True


@callback(
	[
		Output("analysis-progress", "value"),
		Output("analysis-progress", "label"),
		Output("analysis-progress", "color"),
		Output("progress-text", "children"),
		Output("progress-interval", "disabled", allow_duplicate=True),
	],
	Input("progress-interval", "n_intervals"),
	prevent_initial_call=True,
)
def update_progress_bar(n_clicks: int) -> tuple[float, str, str, str, bool]:
	"""Progress bar update logic based on number of steps."""
	status = cache_config.launch_cache.get("analysis_status")

	if not status:
		# Dash no_update keeps the interval enabled while waiting for analysis to start.
		return 0, "", "primary", "Waiting for analysis to start...", no_update  # ty: ignore[invalid-return-type]

	percent = status.get("percent", 0)
	msg = status.get("msg", "")

	is_finished = percent >= 100
	color = "success" if is_finished else "primary"
	label = f"{percent}%" if percent > 5 else ""

	return percent, label, color, msg, is_finished


clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="enable_on_click"),
	Output("progress-interval", "disabled", allow_duplicate=True),
	Input("antenna-button", "n_clicks"),
	prevent_initial_call=True,
)


clientside_callback(
	dash.ClientsideFunction(namespace="clientside", function_name="check_config_exists"),
	Output("antenna-button", "disabled", allow_duplicate=True),
	Input("project-config-store", "data"),
	prevent_initial_call="initial_duplicate",
)
