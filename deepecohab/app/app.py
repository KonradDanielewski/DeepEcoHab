import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from deepecohab.utils import (
	auxfun_dashboard,
	cache_config,
)

app = dash.Dash(
	__name__,
	use_pages=True,
	suppress_callback_exceptions=True,
	background_callback_manager=cache_config.background_manager,
	external_stylesheets=[
		"/assets/styles.css",
		dbc.icons.FONT_AWESOME,
		dbc.themes.BOOTSTRAP,
	],
)

icon_map = {
	"/": "fas fa-house",
	"/analysis": "fas fa-magnifying-glass-chart",
	"/cohort_dashboard": "fas fa-chart-diagram",
	"/group_dashboard": "fas fa-chart-column",
}

tooltips = ["Home", "Analysis", "Cohort Dashboard", "Group Dashboard"]

app.layout = html.Div(
	[
		dcc.Location(id="url", refresh=False),
		auxfun_dashboard.generate_sidebar(icon_map, dash.page_registry, tooltips),
		html.Div(
			[
				dbc.Container(
					[
						dbc.Row(
							dbc.Col(
								dash.page_container,
								width=12,
							)
						),
						dcc.Store(id="project-config-store", storage_type="session"),
					],
					fluid=True,
				)
			],
			id="main-content",
		),
	]
)
