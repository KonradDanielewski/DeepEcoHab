from typing import Literal, List

import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from plotly.subplots import make_subplots

from deepecohab.utils import auxfun_plots

def plot_ranking_in_time(dash_data:dict[pd.DataFrame]) -> go.Figure:
    """Auxfun to plot ranking through time
    """
    ranking_in_time = dash_data['ranking_in_time']
    main_df = dash_data['main_df']
    ranking = dash_data['ranking']

    animals = ranking_in_time.columns

    x = np.linspace(0, 1, len(animals))
    colors = px.colors.sample_colorscale('Phase', list(x))

    plot_df = auxfun_plots.prep_ranking_in_time_df(main_df, ranking_in_time, True)
    distribution_df = auxfun_plots.prep_ranking_distribution(ranking)

    max_range_y1 = distribution_df.max().max() + 0.02
    min_range_y2 = plot_df.min().min() - 5
    max_range_y2 = plot_df.max().max() + 5

    # Make fig
    fig = make_subplots(
        rows=2, 
        cols=1, 
        subplot_titles=['<b>Ranking probability distribution</b>', '<b>Social dominance ranking in time</b>'],
        vertical_spacing=0.12,
    )

    for i, animal in enumerate(animals):
        fig.add_trace(
            go.Scatter(
                x=distribution_df.index,
                y=distribution_df[animal], 
                mode='lines',
                fill='tozeroy',
                name=animal,
                marker=dict(color=colors[i]),
                showlegend=False,
                legendgroup=f'group{i}',
                ),
            row=1,
            col=1,
            )

    for i, animal in enumerate(animals):
        fig.add_trace(
            go.Scatter(
                x=plot_df.index, 
                y=plot_df[animal], 
                name=animal, 
                marker=dict(color=colors[i]),
                showlegend=True,
                legendgroup=f'group{i}',
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        xaxis=dict(
            title='Ranking',
        ),
        xaxis2=dict(
            rangeslider=dict(visible=True, thickness=0.05),
            title='Timeline'
        ),
        yaxis=dict(
            title='Probability density',
            range=[0, max_range_y1],
        ),
        yaxis2=dict(
            title='Ranking',
            range=[min_range_y2, max_range_y2],
        ),
        height=800,
        margin=dict(t=40, b=40, l=60, r=40),
    )
    
    return fig

def plot_position_fig(
    dash_data: dict[pd.DataFrame], 
    mode: str, 
    phase_range: List[int],
    position_switch: str, 
    aggregate_stats_switch: Literal['mean', 'sum'] | None = None,
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
    
    position_df = position_df[position_df['phase'] == phase]
    position_df = position_df[
        (position_df['phase_count'] >= phase_range[0]) &
        (position_df['phase_count'] <= phase_range[-1])]
    
    match aggregate_stats_switch:
        case 'sum':
            fig_data = position_df.groupby(['animal_id', 'phase', 'position'], observed=False).sum(min_count=1).reset_index()
            position_max_y = fig_data[position_y].max() + position_y_range_add
        case 'mean':
            fig_data = position_df.groupby(['animal_id', 'phase', 'position'], observed=False).mean().reset_index()
            position_max_y = fig_data[position_y].max() + position_y_range_add
        case _:
            fig_data  = position_df

    x = np.linspace(0, 1, len(position_y))
    colors = px.colors.sample_colorscale("Phase", x)
        
    position_fig = px.bar(
            fig_data,
            x='animal_id',
            y=position_y,
            color='position',
            color_discrete_sequence=colors,
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
    phase_range: List[int],
    pairwise_switch: str, 
    aggregate_stats_switch: Literal['mean', 'sum'] | None = None,
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
    pairwise_filtered = pairwise_filtered[
        (pairwise_filtered['phase_count'] >= phase_range[0]) &
        (pairwise_filtered['phase_count'] <= phase_range[-1])]
    
    pairwise_n_cages = len(pairwise_filtered['cages'].unique())
    pairwise_animal_ids = pairwise_filtered['animal_ids'].unique()
    pairwise_n_animals_ids = len(pairwise_animal_ids)
    
    
    match aggregate_stats_switch:
        case 'sum':
            fig_data = pairwise_filtered.groupby(['cages','animal_ids','phase'], observed=False).sum(min_count=1).reset_index().drop(columns=['phase_count'])
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
            fig_data  = pairwise_filtered
            fig_data = fig_data.drop(columns=['phase_count'])
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

    pairwise_plot = px.imshow(
        pairwise_heatmap_data,
        animation_frame=0,
        x=pairwise_animal_ids,
        y=pairwise_animal_ids,
        color_continuous_scale='Viridis',  
        text_auto=False,
        facet_col=1,
        facet_col_wrap=2,
        )
    
    pairwise_plot['layout'].pop('updatemenus')
    pairwise_plot = pairwise_plot.update_layout(
                        sliders=[{'currentvalue': {'prefix': 'Phase='}}],
                        plot_bgcolor='white',
                        title=dict(text=pairwise_title),
                        height=800,
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
    pairwise_plot.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    
    return pairwise_plot

def plot_chasings(dash_data: dict[pd.DataFrame], mode: str, phase_range: List[int], aggregate_stats_switch: str) -> go.Figure:
    """Auxfun to plot pairwise data
    """ 
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
        
    chasings_filtered = dash_data['chasings_df'].reset_index()
    chasings_filtered = chasings_filtered[chasings_filtered['phase'] == phase]
    chasings_filtered = chasings_filtered[
        (chasings_filtered['phase_count'] >= phase_range[0]) &
        (chasings_filtered['phase_count'] <= phase_range[-1])]
    
    chasings_title = f'<b>Number of chasings: <u>{mode} phase</u></b>'
    chasings_min_range = int(dash_data['chasings_df'].min().min())
    chasings_max_range = int(dash_data['chasings_df'].max().max())
    chasings_z_label = 'Number: %{z}'
    chasings_animal_ids = chasings_filtered['animal_ids'].unique()
    chasings_n_animal_ids = len(chasings_animal_ids)
    
    match aggregate_stats_switch:    
        case 'sum':
            fig_data = chasings_filtered.groupby(['animal_ids',  'phase'], observed=False).sum(min_count=1).reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
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
        color_continuous_scale='Viridis',  
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
    chasings_plot.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

    return chasings_plot

def plot_in_cohort_sociability(dash_data: dict[pd.DataFrame], mode: str, phase_range: List[int], sociability_summary_switch:str) -> go.Figure:
    """Auxfun to plot in cohort sociability data
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
        
    incohort_soc_filtered = dash_data['incohort_sociability_df'].reset_index()
    incohort_soc_filtered = incohort_soc_filtered[incohort_soc_filtered['phase'] == phase]
    incohort_soc_filtered = incohort_soc_filtered[
        (incohort_soc_filtered['phase_count'] >= phase_range[0]) &
        (incohort_soc_filtered['phase_count'] <= phase_range[-1])]

    incohort_soc_title = f'<b>Incohort sociability: <u>{mode} phase</u></b>'
    incohort_soc_min_range = int(dash_data['incohort_sociability_df'].min().min())
    incohort_soc_max_range = int(dash_data['incohort_sociability_df'].max().max())
    incohort_soc_z_label = 'Sociability: %{z}'
    incohort_soc_animal_ids = incohort_soc_filtered['animal_ids'].unique()
    incohort_soc_n_animal_ids = len(incohort_soc_animal_ids)
    
    match sociability_summary_switch:
        case 'sum': 
            fig_data = incohort_soc_filtered.groupby(['animal_ids',  'phase'], observed=False).sum(min_count=1).reset_index().drop(columns=['phase_count','phase', 'animal_ids'])
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
        color_continuous_scale='Viridis',  
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
    incohort_soc_plot.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

    return incohort_soc_plot

def plot_network_grah(dash_data: dict[pd.DataFrame], mode:str, phase_range: List[int]) -> go.Figure:
    """Auxfun to plot network graph
    """
    match mode: 
        case 'dark':
            phase = 'dark_phase'
        case 'light':
            phase = 'light_phase'
    
    plot_chasing_data_filtered = dash_data['plot_chasing_data'][dash_data['plot_chasing_data']['phase'] == phase]  
    plot_chasing_data_filtered = plot_chasing_data_filtered[
        # This is a special case, the structure is affected by the whole recording always
        # it can't start counting from a specific point.
        (plot_chasing_data_filtered['phase_count'] >= 0) & 
        (plot_chasing_data_filtered['phase_count'] <= phase_range[-1])
    ]
    
    plot_chasing_data_filtered = plot_chasing_data_filtered.drop(columns=['phase', 'phase_count'])
    plot_chasing_data_filtered = (
        plot_chasing_data_filtered
        .groupby(['target', 'source'])
        .sum()
        .reset_index()
    )
    
    plot_ranking_data_filtered = dash_data['plot_ranking_data'][dash_data['plot_ranking_data']['phase'] == phase]   
    plot_ranking_data_filtered = plot_ranking_data_filtered[plot_ranking_data_filtered.phase_count==phase_range[-1]]
    
    plot_ranking_data_filtered = plot_ranking_data_filtered.drop(columns=['phase', 'phase_count']).set_index('mouse_id')['ranking']

    animals = plot_ranking_data_filtered.index # TODO: Move this creation of colorscale out, should return the x and colors
    x = np.linspace(0, 1, len(animals))
    colors = px.colors.sample_colorscale('Phase', list(x))
    
    G = nx.from_pandas_edgelist(plot_chasing_data_filtered, create_using=nx.DiGraph, edge_attr='chasings')
    pos = nx.spring_layout(G, k=None, iterations=300, seed=42, weight='chasings', method='energy')
    node_trace = auxfun_plots.create_node_trace(G, pos, plot_ranking_data_filtered, 1, colors, x)
    edge_trace = auxfun_plots.create_edges_trace(G, pos, 0.2, 'Viridis')
    
    fig = go.Figure(
            data=edge_trace + [node_trace],
            layout=go.Layout(
                showlegend=False,
                hovermode='closest',
                margin=dict(b=0, l=0, r=0, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                title=dict(text=f'<b>Social structure network graph: <u>{mode} phase</u></b>', x=0.01, y=0.95),
                height=800,
            )
        )

    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)
    
    return fig

def plot_activity(
        dash_data: dict[pd.DataFrame],
        phase_range: List[int], 
        summary_switch: Literal['sum', 'mean']
    ) -> go.Figure:
    
    df = dash_data['padded_df']
    df = df[
        (df['phase_count'] >= phase_range[0]) & 
        (df['phase_count'] <= phase_range[-1])
    ]
    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    match summary_switch:
        case 'sum':
            return auxfun_plots.plot_sum_activity_per_hour(df, colors)
        case 'mean':
            return auxfun_plots.plot_mean_activity_per_hour(df, animals, colors)
        
def plot_chasing(
        dash_data: dict[pd.DataFrame],
        phase_range: List[int], 
        summary_switch: Literal['sum', 'mean']
    ) -> go.Figure:
    
    df = dash_data['main_df']
    match_df = dash_data['match_df']

    match_df = auxfun_plots.prep_match_df_line(df, match_df)

    match_df = match_df[
        (match_df['phase_count'] >= phase_range[0]) & 
        (match_df['phase_count'] <= phase_range[-1])
    ]

    animals = df.animal_id.cat.categories
    colors = auxfun_plots.color_sampling(animals)

    match summary_switch:
        case 'sum':
            return auxfun_plots.plot_sum_chasings_per_hour(match_df, colors)
        case 'mean':
            return auxfun_plots.plot_mean_chasings_per_hour(match_df, animals, colors)
    
def get_single_plot(dash_data, plot_type, phase_type, aggregate_stats_switch, phase_range):
    match plot_type:
        case 'position_visits':
            return plot_position_fig(dash_data, phase_type, phase_range, 'visits', aggregate_stats_switch)
        case 'position_time':
            return plot_position_fig(dash_data, phase_type, phase_range, 'time', aggregate_stats_switch)
        case 'pairwise_encounters':
            return plot_pairwise_plot(dash_data, phase_type, phase_range, 'visits', aggregate_stats_switch)
        case 'pairwise_time': 
            return plot_pairwise_plot(dash_data, phase_type, phase_range, 'time', aggregate_stats_switch)
        case 'chasings':
            return plot_chasings(dash_data, phase_type, phase_range, aggregate_stats_switch)
        case 'sociability':
            return plot_in_cohort_sociability(dash_data, phase_type,phase_range, sociability_summary_switch="mean")
        case 'network':
            return plot_network_grah(dash_data, phase_type, phase_range)
        case _:
            return {}

