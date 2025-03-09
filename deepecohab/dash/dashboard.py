import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import pandas as pd
import networkx as nx
import plotly.express as px
from deepecohab.utils import auxfun_plots

store = pd.HDFStore('examples/test_name2_2025-02-25/results/test_name2_data.h5')

# Initialize the Dash app
app = dash.Dash(__name__)

# Load data from hdf
ranking_in_time = pd.read_hdf(store, key='ranking_in_time').reset_index().melt(id_vars='datetime', var_name='mouse_id', value_name='ranking')
time_per_position_df = pd.read_hdf(store, key="time_per_position")
time_per_position_df = time_per_position_df.melt(ignore_index=False, value_name="Time[s]", var_name="animal_id").reset_index()
visits_per_position_df = pd.read_hdf(store, key="visits_per_position")
visits_per_position_df = visits_per_position_df.melt(ignore_index=False, value_name="Visits[#]", var_name="animal_id").reset_index()
time_together = pd.read_hdf(store, key='time_together').reset_index()
pairwise_encounters = pd.read_hdf(store, key='pairwise_encounters').reset_index()
chasings_df = pd.read_hdf(store, key='chasings')
incohort_sociability_df = pd.read_hdf(store, key='incohort_sociability')
ranking_ordinal_df = pd.read_hdf(store, key='ranking_ordinal')
plot_chasing_data = auxfun_plots.prep_network_df(chasings_df)
plot_ranking_data = auxfun_plots.prep_ranking(ranking_ordinal_df)


# Mockup data for demonstration purposes
# Replace these with actual data processing
phases = list(range(1, 11))  # Example phases

# Define the app layout
app.layout = html.Div([
    # Fixed Header Container
    html.Div([
        html.H1('EcoHAB Results', style={'textAlign': 'center', 'margin-bottom': '10px'}),
        html.Div([
            html.Label('Phases', style={'margin-right': '10px'}),
            dcc.Slider(
                id='phase-slider',
                min=min(phases),
                max=max(phases),
                value=min(phases),
                marks={str(phase): str(phase) for phase in phases},
                step=None,
                tooltip={"placement": "bottom", "always_visible": True},
                updatemode='drag',
                included=True,
                vertical=False,
                className='slider'
            ),
            dcc.RadioItems(
                id='mode-switch',
                options=[{'label': 'Dark', 'value': 'dark'}, {'label': 'Light', 'value': 'light'}],
                value='dark',
                labelStyle={'display': 'inline-block', 'margin-left': '10px'}
            )
        ], style={'width': '100%', 'textAlign': 'center'})
    ], style={
        'position': 'fixed', 'top': '0', 'left': '0', 'right': '0', 'background-color': '#FFFFFF',
        'z-index': '1000', 'padding': '10px', 'display': 'flex', 'flexDirection': 'column',
        'alignItems': 'center', 'justifyContent': 'center', 'width': '100%', 'height': '120px'
    }),

    # Scrollable content area
    html.Div([
        dcc.Graph(id='ranking-time-plot'),
        dcc.Graph(id='position-plot'),
        dcc.RadioItems(
            id='position-switch',
            options=[{'label': 'Visits', 'value': 'visits'}, {'label': 'Time', 'value': 'time'}],
            value='visits',
            labelStyle={'display': 'inline-block', 'color': 'lightgrey'}
        ),
        dcc.Graph(id='pairwise-heatmap'),
        dcc.RadioItems(
            id='pairwise-switch',
            options=[{'label': 'Time', 'value': 'time'}, {'label': 'Visits', 'value': 'visits'}],
            value='time',
            labelStyle={'display': 'inline-block', 'color': 'lightgrey'}
        ),
        html.Div([
            dcc.Graph(id='chasings-heatmap', style={'display': 'inline-block', 'width': '49%'}),
            dcc.Graph(id='sociability-heatmap', style={'display': 'inline-block', 'width': '49%'})
        ], style={'width': '80%', 'margin': 'auto'}),
        dcc.Graph(id='network-graph')
    ], style={
        'margin-top': '130px', 'overflow-y': 'auto', 'height': 'calc(100vh - 130px)', 'padding': '20px'
    })
])

# Callback to update all plots based on slider and radio buttons
@app.callback(
    [Output('ranking-time-plot', 'figure'),
     Output('position-plot', 'figure'),
     Output('pairwise-heatmap', 'figure'),
     Output('chasings-heatmap', 'figure'),
     Output('sociability-heatmap', 'figure'),
     Output('network-graph', 'figure')
     ],
    [Input('phase-slider', 'value'),
     Input('mode-switch', 'value'),
     Input('position-switch', 'value'),
     Input('pairwise-switch', 'value')]
)
def update_plots(selected_phase, mode, position_switch, pairwise_switch):
    # Define color schemes for dark and light modes
    if mode == 'dark':
        phase = "dark_phase"
    else:
        phase = "light_phase"

    if position_switch == 'visits':
        position_df = visits_per_position_df
        position_title = f"<b>Visits to each position: <u>{mode} phase</u></b>"
        position_y_title = "<b>Number of visits</b>"
        position_y = "Visits[#]"
        position_y_range_add = 50
        
    else:
        position_df = time_per_position_df
        position_title = f"<b>Time spent in each position: <u>{mode} phase</u></b>"
        position_y_title = "<b>Time spent [s]</b>"
        position_y = "Time[s]"
        position_y_range_add = 1000
        
    position_max_y = position_df[position_y].max() + position_y_range_add
    
    if pairwise_switch == 'visits':
        pairwise_df = pairwise_encounters
        pairwise_title = f"<b>Number of pairwise encounters: <u>{mode} phase</u></b>"
        pairwise_z_label = "Number: %{z}"   
    else:
        pairwise_df = time_together
        pairwise_title = f"<b>Time spent in each position: <u>{mode} phase</u></b>"
        pairwise_z_label = "Time [s]: %{z}"
        

    # Filter data based on selected phase

    position_filtered = position_df[position_df['phase'] == phase]
    position_filtered = position_filtered[position_filtered['phase_count'] == selected_phase]
    
    pairwise_filtered = pairwise_df[pairwise_df['phase'] == phase]
    pairwise_filtered = pairwise_filtered[pairwise_filtered['phase_count'] == selected_phase]
    
    chasings_filtered = chasings_df.reset_index()
    chasings_filtered = chasings_filtered[chasings_filtered['phase'] == phase]
    chasings_filtered = chasings_filtered[chasings_filtered['phase_count'] == selected_phase]
    
    incohort_soc_filtered = incohort_sociability_df.reset_index()
    incohort_soc_filtered = incohort_soc_filtered[incohort_soc_filtered['phase'] == phase]
    incohort_soc_filtered = incohort_soc_filtered[incohort_soc_filtered['phase_count'] == selected_phase]
    
    plot_chasing_data_filtered = plot_chasing_data[plot_chasing_data['phase'] == phase]
    plot_chasing_data_filtered = plot_chasing_data_filtered[plot_chasing_data_filtered['phase_count'] == selected_phase]
    plot_chasing_data_filtered = plot_chasing_data_filtered.drop(columns=['phase', 'phase_count'])
    
    plot_ranking_data_filtered = plot_ranking_data[plot_ranking_data['phase'] == phase]
    plot_ranking_data_filtered = plot_ranking_data_filtered[plot_ranking_data_filtered['phase_count'] == selected_phase]
    plot_ranking_data_filtered = plot_ranking_data_filtered.drop(columns=['phase', 'phase_count']).set_index('mouse_id')['ranking']

    # Ranking in time bar plot
    ranking_fig = px.line(ranking_in_time, x='datetime', y='ranking', color='mouse_id')
    ranking_fig.update_layout(
        title='Ranking in Time'
    )
    
    position_fig = px.bar(
            position_filtered,
            x="animal_id",
            y=position_y,
            color="position",
            color_discrete_sequence=px.colors.qualitative.__dict__["Pastel"],
            barmode='group',
            title=position_title,
            range_y=[0, position_max_y],
        )
    
    position_fig.update_xaxes(title_text="<b>Animal ID</b>")
    position_fig.update_yaxes(title_text=position_y_title)
    
    pairwise_n_phases = len(pairwise_filtered['phase_count'].unique())
    pairwise_n_cages = len(pairwise_filtered['cages'].unique())
    pairwise_animal_ids = pairwise_filtered['animal_ids'].unique()
    pairwise_n_animals_ids = len(pairwise_animal_ids)
    
    pairwise_heatmap_data = (
        pairwise_filtered
        .drop(columns=["phase", "phase_count", "animal_ids", "cages"])
        .values
        .reshape(
            pairwise_n_phases,
            pairwise_n_cages,
            pairwise_n_animals_ids, 
            pairwise_n_animals_ids
        )
    )

    pairwise_plot = px.imshow(
        pairwise_heatmap_data,
        animation_frame=0,
        x=pairwise_animal_ids,
        y=pairwise_animal_ids,
        color_continuous_scale="OrRd",  
        text_auto=False,
        facet_col=1,
        facet_col_wrap=2,
        )
    
    pairwise_plot["layout"].pop("updatemenus")
    pairwise_plot = pairwise_plot.update_layout(
                        sliders=[{"currentvalue": {"prefix": "Phase="}}],
                        plot_bgcolor='white',
                        title=dict(text=pairwise_title),
                    )
    for i in range(pairwise_n_cages):
        facet_col_n = int(pairwise_plot.layout.annotations[i]['text'][-1])
        pairwise_plot.layout.annotations[i]['text'] = f"<u><b>Cage {facet_col_n+1}</u></b>"
        
    pairwise_plot.update_xaxes(showspikes=True, spikemode="across")
    pairwise_plot.update_yaxes(showspikes=True, spikemode="across")
    pairwise_plot.update_traces(
        hovertemplate="<br>".join([
            "X: %{x}",
            "Y: %{y}",
            pairwise_z_label,
        ])
    )
    
    
    chasings_title = f"<b>Number of chasings: <u>{mode} phase</u></b>"
    chasings_min_range = int(chasings_df.min().min())
    chasings_max_range = int(chasings_df.max().max())
    chasings_z_label = "Number: %{z}"
    chasings_animal_ids = chasings_filtered['animal_ids'].unique()
    chasings_n_animal_ids = len(chasings_animal_ids)
    
    chasings_heatmap_data = (
        chasings_filtered
        .drop(columns=["phase", "phase_count", "animal_ids"])
        .values
        .reshape(chasings_n_animal_ids, chasings_n_animal_ids)
        .round(3)
    )

    chasings_plot = px.imshow(
        chasings_heatmap_data,
        x=chasings_animal_ids,
        y=chasings_animal_ids,
        color_continuous_scale="OrRd",  
        text_auto=False,
        range_color=[chasings_min_range, chasings_max_range]
    )
    
    chasings_plot = chasings_plot.update_layout(
                        title=dict(text=chasings_title),
                        plot_bgcolor='white',
                    )
        
    chasings_plot.update_xaxes(showspikes=True, spikemode="across")
    chasings_plot.update_yaxes(showspikes=True, spikemode="across")
    chasings_plot.update_traces(
        hovertemplate="<br>".join([
            "X: %{x}",
            "Y: %{y}",
            chasings_z_label,
        ])
    )
    
    incohort_soc_title = f"<b>Incohort sociability: <u>{mode} phase</u></b>"
    incohort_soc_min_range = int(incohort_sociability_df.min().min())
    incohort_soc_max_range = int(incohort_sociability_df.max().max())
    incohort_soc_z_label = "{z}"
    incohort_soc_animal_ids = incohort_soc_filtered['animal_ids'].unique()
    incohort_soc_n_animal_ids = len(incohort_soc_animal_ids)
    
    incohort_soc_heatmap_data = (
        incohort_soc_filtered
        .drop(columns=["phase", "phase_count", "animal_ids"])
        .values
        .reshape(incohort_soc_n_animal_ids, incohort_soc_n_animal_ids)
        .round(3)
    )

    incohort_soc_plot = px.imshow(
        incohort_soc_heatmap_data,
        x=incohort_soc_animal_ids,
        y=incohort_soc_animal_ids,
        color_continuous_scale="OrRd",  
        text_auto=False,
        range_color=[incohort_soc_min_range, incohort_soc_max_range]
    )
    
    incohort_soc_plot = incohort_soc_plot.update_layout(
                        title=dict(text=incohort_soc_title),
                        plot_bgcolor='white',
                    )
        
    incohort_soc_plot.update_xaxes(showspikes=True, spikemode="across")
    incohort_soc_plot.update_yaxes(showspikes=True, spikemode="across")
    incohort_soc_plot.update_traces(
        hovertemplate="<br>".join([
            "X: %{x}",
            "Y: %{y}",
            incohort_soc_z_label,
        ])
    )
    
    G = nx.from_pandas_edgelist(plot_chasing_data_filtered, create_using=nx.DiGraph, edge_attr="chasings")
    pos = nx.spring_layout(G, k=None, iterations=500, seed=42, weight="chasings")
    node_trace = auxfun_plots.create_node_trace(G, pos, plot_ranking_data_filtered, 2, "bluered")
    edge_trace = auxfun_plots.create_edges_trace(G, pos, 0.4, 2, "bluered")
    
    net_plot = go.Figure(
            data=edge_trace + [node_trace],
            layout=go.Layout(
                showlegend=False,
                hovermode='closest',
                margin=dict(b=0, l=0, r=0, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            )
        )
    
    net_plot = net_plot.update_layout(
                plot_bgcolor='white',
                title=dict(text=f"<b>Social structure network graph: <u>{mode} phase</u></b>", x=0.01, y=0.95),
            )
    net_plot.update_xaxes(showticklabels=False)
    net_plot.update_yaxes(showticklabels=False)
    
    return [ranking_fig, position_fig, pairwise_plot, chasings_plot, incohort_soc_plot, net_plot]

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
