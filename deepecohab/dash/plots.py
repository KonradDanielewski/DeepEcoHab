from typing import Literal

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from deepecohab.utils import auxfun_plots

def plot_ranking_in_time(dash_data:dict[pd.DataFrame]) -> go.Figure:
    """Auxfun to plot ranking through time
    """
    colors = px.colors.qualitative.__dict__['Set3']
    ranking_in_time = dash_data['ranking_in_time']
    main_df = dash_data['main_df']

    plot_df = auxfun_plots.prep_ranking_in_time_df(main_df, ranking_in_time, per_hour=False)

    # Make fig
    fig = go.Figure()

    for i, animal in enumerate(ranking_in_time.columns):
        fig.add_trace(
            go.Scatter(x=plot_df.index, y=plot_df[animal], name=animal, marker=dict(color=colors[i]))
        )

    fig.update_layout(
        title='<b>Social dominance ranking in time</b>',
        xaxis=dict(
            rangeslider=dict(visible=True),
            type='date',
            title='<b>Time</b>'
        ),
        yaxis=dict(title='<b>Ranking</b>'),
        legend=dict(title='<b>Animal IDs</b>'),
        height=600,
    )
    
    return fig

def plot_position_fig(
    dash_data: dict[pd.DataFrame], 
    mode: str, selected_phase: int, 
    position_switch: str, 
    summary_postion_switch: Literal['mean', 'sum'] | None = None,
    ) -> go.Figure:
    """Auxfun to plot position data
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
    match position_switch:
        case 'visits':
            position_df = dash_data['visits_per_position_df']
            position_title = f'<b>Visits to each position: <u>{mode} phase</u></b>'
            position_y_title = '<b>Number of visits</b>'
            position_y = 'Visits[#]'
            position_y_range_add = 50
            
        case 'time':
            position_df = dash_data['time_per_position_df']
            position_title = f'<b>Time spent in each position: <u>{mode} phase</u></b>'
            position_y_title = '<b>Time spent [s]</b>'
            position_y = 'Time[s]'
            position_y_range_add = 1000
        
    position_max_y = position_df[position_y].max() + position_y_range_add
    
    position_filtered = position_df[position_df['phase'] == phase]
    position_filtered = position_filtered[position_filtered['phase_count'] == selected_phase]
    
    match summary_postion_switch:
        case 'sum':
            fig_data = position_df[position_df['phase'] == phase].groupby(['animal_id', 'phase', 'position'], observed=False).sum().reset_index()
            position_max_y = fig_data[position_y].max() + position_y_range_add
        case 'mean':
            fig_data = position_df[position_df['phase'] == phase].groupby(['animal_id', 'phase', 'position'], observed=False).mean().reset_index()
            position_max_y = fig_data[position_y].max() + position_y_range_add
        case _:
            fig_data  = position_filtered
        
    position_fig = px.bar(
            fig_data,
            x='animal_id',
            y=position_y,
            color='position',
            color_discrete_sequence=px.colors.qualitative.__dict__['Set3'],
            barmode='group',
            title=position_title,
            range_y=[0, position_max_y],
        )
    
    position_fig.update_xaxes(title_text='<b>Animal ID</b>')
    position_fig.update_yaxes(title_text=position_y_title)
    
    return position_fig

def plot_pairwise_plot(
    dash_data: dict[pd.DataFrame], 
    mode: str, 
    selected_phase: int, 
    pairwise_switch: str, 
    summary_pairwise_switch: Literal['mean', 'sum'] | None = None,
    ) -> go.Figure:
    """Auxfun to plot pairwise data
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
    
    match pairwise_switch:
        case 'visits':
            pairwise_df = dash_data['pairwise_encounters']
            pairwise_title = f'<b>Number of pairwise encounters: <u>{mode} phase</u></b>'
            pairwise_z_label = 'Number: %{z}'   
        case 'time':
            pairwise_df = dash_data['time_together']
            pairwise_title = f'<b>Time spent together: <u>{mode} phase</u></b>'
            pairwise_z_label = 'Time [s]: %{z}'
    
    pairwise_filtered = pairwise_df[pairwise_df['phase'] == phase]
    pairwise_n_cages = len(pairwise_filtered['cages'].unique())
    pairwise_animal_ids = pairwise_filtered['animal_ids'].unique()
    pairwise_n_animals_ids = len(pairwise_animal_ids)
    
    match summary_pairwise_switch:
        case 'sum':
            fig_data = pairwise_filtered.groupby(['cages','animal_ids','phase'], observed=False).sum().reset_index().drop(columns=['phase_count'])
            pairwise_heatmap_data = (
            fig_data
            .drop(columns=['phase', 'animal_ids', 'cages'])
            .values
            .reshape(
                1,
                pairwise_n_cages,
                pairwise_n_animals_ids, 
                pairwise_n_animals_ids
            )
        )
        case 'mean':
            fig_data = pairwise_filtered.groupby(['cages','animal_ids','phase'], observed=False).mean().reset_index().drop(columns=['phase_count'])
            pairwise_heatmap_data = (
            fig_data
            .drop(columns=['phase','animal_ids','cages'])
            .values
            .reshape(
                1,
                pairwise_n_cages,
                pairwise_n_animals_ids, 
                pairwise_n_animals_ids
            )
        )
        case _:
            fig_data  = pairwise_filtered[pairwise_filtered['phase_count'] == selected_phase]
            pairwise_n_phases = len(fig_data['phase_count'].unique())
            fig_data = fig_data.drop(columns=['phase_count'])
            pairwise_heatmap_data = (
            fig_data
            .drop(columns=['phase','animal_ids','cages'])
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
        color_continuous_scale='OrRd',  
        text_auto=False,
        facet_col=1,
        facet_col_wrap=2,
        )
    
    pairwise_plot['layout'].pop('updatemenus')
    pairwise_plot = pairwise_plot.update_layout(
                        sliders=[{'currentvalue': {'prefix': 'Phase='}}],
                        plot_bgcolor='white',
                        title=dict(text=pairwise_title),
                        height=600,
                    )
    for i in range(pairwise_n_cages):
        facet_col_n = int(pairwise_plot.layout.annotations[i]['text'][-1])
        pairwise_plot.layout.annotations[i]['text'] = f'<u><b>Cage {facet_col_n+1}</u></b>'
        
    pairwise_plot.update_xaxes(showspikes=True, spikemode='across')
    pairwise_plot.update_yaxes(showspikes=True, spikemode='across')
    pairwise_plot.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            pairwise_z_label,
        ])
    )
    
    return pairwise_plot

def plot_chasings(dash_data: dict[pd.DataFrame], mode:str, selected_phase:int, chasings_summary_switch:str) -> go.Figure:
    """Auxfun to plot pairwise data
    """ 
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
        
    chasings_filtered = dash_data['chasings_df'].reset_index()
    chasings_filtered = chasings_filtered[chasings_filtered['phase'] == phase]
    
    
    chasings_title = f'<b>Number of chasings: <u>{mode} phase</u></b>'
    chasings_min_range = int(dash_data['chasings_df'].min().min())
    chasings_max_range = int(dash_data['chasings_df'].max().max())
    chasings_z_label = 'Number: %{z}'
    chasings_animal_ids = chasings_filtered['animal_ids'].unique()
    chasings_n_animal_ids = len(chasings_animal_ids)
    
    match chasings_summary_switch:    
        case 'sum':
            fig_data = chasings_filtered.groupby(['animal_ids',  'phase'], observed=False).sum().reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
            chasings_min_range = fig_data.min().min()
            chasings_max_range = fig_data.max().max()
            chasings_heatmap_data = (
            fig_data
            .values
            .reshape(
                chasings_n_animal_ids, 
                chasings_n_animal_ids
            ).round(3)
            )
            
        case 'mean':
            fig_data = chasings_filtered.groupby(['animal_ids',  'phase'], observed=False).mean().reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
            chasings_min_range = fig_data.min().min()
            chasings_max_range = fig_data.max().max()
            chasings_heatmap_data = (
            fig_data
            .values
            .reshape(
                chasings_n_animal_ids, 
                chasings_n_animal_ids
            ).round(3)
            )
        case _:
            chasings_filtered = chasings_filtered[chasings_filtered['phase_count'] == selected_phase]
            chasings_heatmap_data = (
            chasings_filtered
            .drop(columns=['phase', 'phase_count', 'animal_ids'])
            .values
            .reshape(chasings_n_animal_ids, chasings_n_animal_ids)
            .round(3)
        )
 
    chasings_plot = px.imshow(
        chasings_heatmap_data,
        x=chasings_animal_ids,
        y=chasings_animal_ids,
        color_continuous_scale='OrRd',  
        text_auto=False,
        range_color=[chasings_min_range, chasings_max_range]
    )
    
    chasings_plot = chasings_plot.update_layout(
                        title=dict(text=chasings_title),
                        plot_bgcolor='white',
                    )
        
    chasings_plot.update_xaxes(showspikes=True, spikemode='across')
    chasings_plot.update_yaxes(showspikes=True, spikemode='across')
    chasings_plot.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            chasings_z_label,
        ])
    )
    
    return chasings_plot

def plot_in_cohort_sociability(dash_data: dict[pd.DataFrame], mode:str, selected_phase:int, sociability_summary_switch:str) -> go.Figure:
    """Auxfun to plot in cohort sociability data
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
        
    incohort_soc_filtered = dash_data['incohort_sociability_df'].reset_index()
    incohort_soc_filtered = incohort_soc_filtered[incohort_soc_filtered['phase'] == phase]

    incohort_soc_title = f'<b>Incohort sociability: <u>{mode} phase</u></b>'
    incohort_soc_min_range = int(dash_data['incohort_sociability_df'].min().min())
    incohort_soc_max_range = int(dash_data['incohort_sociability_df'].max().max())
    incohort_soc_z_label = 'Sociability: %{z}'
    incohort_soc_animal_ids = incohort_soc_filtered['animal_ids'].unique()
    incohort_soc_n_animal_ids = len(incohort_soc_animal_ids)
    
    match sociability_summary_switch:
        case 'sum':
            fig_data = incohort_soc_filtered.groupby(['animal_ids',  'phase'], observed=False).sum().reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
            incohort_soc_min_range = fig_data.min().min()
            incohort_soc_max_range = fig_data.max().max()
            incohort_soc_heatmap_data = (
            fig_data
            .values
            .reshape(
                incohort_soc_n_animal_ids, 
                incohort_soc_n_animal_ids
            ).round(3)
            )
            
        case 'mean':
            fig_data = incohort_soc_filtered.groupby(['animal_ids',  'phase'], observed=False).mean().reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
            incohort_soc_min_range = fig_data.min().min()
            incohort_soc_max_range = fig_data.max().max()
            incohort_soc_heatmap_data = (
            fig_data
            .values
            .reshape(
                incohort_soc_n_animal_ids, 
                incohort_soc_n_animal_ids
            ).round(3)
            )
        case _:
            incohort_soc_filtered = incohort_soc_filtered[incohort_soc_filtered['phase_count'] == selected_phase]
            incohort_soc_heatmap_data = (
            incohort_soc_filtered
            .drop(columns=['phase', 'phase_count', 'animal_ids'])
            .values
            .reshape(incohort_soc_n_animal_ids, incohort_soc_n_animal_ids)
            .round(3)
        )
    incohort_soc_plot = px.imshow(
        incohort_soc_heatmap_data,
        x=incohort_soc_animal_ids,
        y=incohort_soc_animal_ids,
        color_continuous_scale='OrRd',  
        text_auto=False,
        range_color=[incohort_soc_min_range, incohort_soc_max_range]
    )
    
    incohort_soc_plot = incohort_soc_plot.update_layout(
                        title=dict(text=incohort_soc_title),
                        plot_bgcolor='white',
                    )
        
    incohort_soc_plot.update_xaxes(showspikes=True, spikemode='across')
    incohort_soc_plot.update_yaxes(showspikes=True, spikemode='across')
    incohort_soc_plot.update_traces(
        hovertemplate='<br>'.join([
            'X: %{x}',
            'Y: %{y}',
            incohort_soc_z_label,
        ])
    )
    
    return incohort_soc_plot

def plot_network_grah(dash_data: dict[pd.DataFrame], mode:str, selected_phase:int) -> go.Figure:
    """Auxfun to plot network graph
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
    
    plot_chasing_data_filtered = dash_data['plot_chasing_data'][dash_data['plot_chasing_data']['phase'] == phase]
    plot_chasing_data_filtered = plot_chasing_data_filtered[plot_chasing_data_filtered['phase_count'] == selected_phase]
    plot_chasing_data_filtered = plot_chasing_data_filtered.drop(columns=['phase', 'phase_count'])
    
    plot_ranking_data_filtered = dash_data['plot_ranking_data'][dash_data['plot_ranking_data']['phase'] == phase]
    plot_ranking_data_filtered = plot_ranking_data_filtered[plot_ranking_data_filtered['phase_count'] == selected_phase]
    plot_ranking_data_filtered = plot_ranking_data_filtered.drop(columns=['phase', 'phase_count']).set_index('mouse_id')['ranking']
    
    G = nx.from_pandas_edgelist(plot_chasing_data_filtered, create_using=nx.DiGraph, edge_attr='chasings')
    pos = nx.spring_layout(G, k=None, iterations=500, seed=42, weight='chasings')
    node_trace = auxfun_plots.create_node_trace(G, pos, plot_ranking_data_filtered, 2, 'bluered')
    edge_trace = auxfun_plots.create_edges_trace(G, pos, 0.4, 2, 'bluered')
    
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
                title=dict(text=f'<b>Social structure network graph: <u>{mode} phase</u></b>', x=0.01, y=0.95),
            )
    net_plot.update_xaxes(showticklabels=False)
    net_plot.update_yaxes(showticklabels=False)
    
    return net_plot
