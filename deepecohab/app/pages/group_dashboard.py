import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.express as px
import polars as pl
import numpy as np

dash.register_page(__name__, path="/group_dashboard", name="Group Dashboard")


# --- Generate Fake Data ---
def generate_fake_data():
	groups = ["Control", "Treatment A", "Treatment B", "Treatment C"]
	data = []
	for group in groups:
		# Create 50 random data points per group with different means
		mu = np.random.randint(40, 80)
		values = np.random.normal(mu, 10, 50)
		for val in values:
			data.append({"Group": group, "Score": val, "Metric": "Performance"})
	return pl.DataFrame(data)


df = generate_fake_data()

# Create the Box Plot
fig = px.box(
	df,
	x="Group",
	y="Score",
	color="Group",
	points="all",  # Show individual data points
	template="simple_white",
	title="Inter-Group Distribution Analysis",
)
fig.update_layout(showlegend=False)

# --- Page Layout ---
layout = html.Div(
	[
		dbc.Row(
			[
				# Side Column for Analysis Filters
				dbc.Col(
					[
						html.H4("Analysis Filters"),
						html.Hr(),
						dbc.Label("Select Metric:"),
						dcc.Dropdown(
							options=["Performance", "Latency", "Accuracy"],
							value="Performance",
							className="mb-3",
						),
						dbc.Label("Grouping Variable:"),
						dbc.RadioItems(
							options=[
								{"label": "Treatment", "value": 1},
								{"label": "Genotype", "value": 2},
								{"label": "Age", "value": 3},
							],
							value=1,
							id="grouping-input",
							className="mb-3",
						),
						dbc.Button(
							"Download Report", color="secondary", size="sm", className="w-100"
						),
					],
					width=3,
					style={"borderRadius": "10px", "minHeight": "70vh"},
				),
				# Main Column for Charts
				dbc.Col(
					[
						dbc.Card(
							[
								dbc.CardHeader(html.H5("Group Comparisons", className="mb-0")),
								dbc.CardBody([dcc.Graph(figure=fig, id="box-plot-main")]),
							]
						),
						dbc.Row(
							[
								dbc.Col(
									dbc.Card(
										dbc.CardBody(
											[
												html.H6("Mean Delta", className="text-muted"),
												html.H3("+12.4%"),
											]
										)
									),
									width=6,
								),
								dbc.Col(
									dbc.Card(
										dbc.CardBody(
											[
												html.H6("P-Value", className="text-muted"),
												html.H3("0.0042"),
											]
										)
									),
									width=6,
								),
							]
						),
					],
					width=9,
				),
			]
		)
	]
)
