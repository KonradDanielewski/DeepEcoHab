import dash
import dash_bootstrap_components as dbc

from dash import html, dcc

from deepecohab.utils.cache_config import background_manager


app = dash.Dash(
	__name__,
	use_pages=True,
	suppress_callback_exceptions=True,
	background_callback_manager=background_manager,
	external_stylesheets=[
		"/assets/styles.css",
		dbc.icons.FONT_AWESOME,
		dbc.themes.BOOTSTRAP,
	],
)

server = app.server

icon_map = {
	"/": "fas fa-house",
	"/analysis": "fas fa-magnifying-glass-chart",
	"/cohort_dashboard": "fas fa-chart-diagram",
	"/group_dashboard": "fas fa-chart-column",
}


def sidebar_layout():
	return html.Div(
		[
			html.Div("MENU", className="sidebar-label"),
			html.Div(
				[
					dcc.Link(
						html.Button(
							html.I(className=icon_map.get(page["relative_path"], "fas fa-file")),
							title="",
							className="icon-btn",
						),
						href=page["relative_path"],
						className="nav-link-wrapper",
					)
					for page in dash.page_registry.values()
				],
				className="tab-buttons",
			),
		],
		id="sidebar",
	)


app.layout = html.Div(
	[
		dcc.Location(id="url", refresh=False),
		sidebar_layout(),
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
			style={"padding": "40px"},
		),
	]
)

if __name__ == "__main__":
	app.run(debug=True, port=8050)
