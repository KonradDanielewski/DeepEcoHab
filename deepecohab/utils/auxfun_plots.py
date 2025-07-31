import pandas as pd
import networkx as nx
import numpy as np
import plotly.graph_objects as go

from typing import Literal
import plotly.express as px
from scipy.stats import norm


def create_edges_trace(
    G: nx.Graph, 
    pos: dict, 
    cmap: str = 'Viridis'
) -> list:
    """Auxfun to create edges trace with color mapping based on edge width
    """
    edge_trace = []
    
    edge_widths = [G.edges[edge]['chasings'] for edge in G.edges()]
    
    # Normalize edge widths to the range [0, 1] for color mapping
    max_width = max(edge_widths)
    min_width = min(edge_widths)
    if max_width == 0 and min_width == 0:
        normalized_widths = [0 for _ in edge_widths]
    else:
        normalized_widths = [(width - min_width) / (max_width - min_width) for width in edge_widths]
    
    colorscale = px.colors.sample_colorscale(cmap, normalized_widths)
    
    for i, edge in enumerate(G.edges()):
        source_x, source_y = pos[edge[0]]
        target_x, target_y = pos[edge[1]]
        edge_width = normalized_widths[i] * 10 # Scale width of edges to be nicely visible
        
        edge_trace.append(
            go.Scatter(
                x=[source_x, target_x, None],  
                y=[source_y, target_y, None],
                line=dict(
                    width=edge_width,
                    color=colorscale[i],
                ),
                hoverinfo='none',
                mode='lines+markers',
                marker=dict(size=edge_width, symbol='arrow', angleref='previous'),
                opacity=0.5,
                showlegend=False,
            )
        )
    
    return edge_trace

def create_node_trace(
    G: nx.DiGraph, 
    pos: dict, 
    ranking_ordinal: pd.Series, 
    colors: list,
) -> go.Scatter:
    """Auxfun to create node trace
    """
    node_trace = go.Scatter(
        x=[],
        y=[],
        text=[],
        hovertext=[],
        hoverinfo='text',
        mode='markers+text',
        textposition='top center',
        showlegend=False,
        marker=dict(
            showscale=False,
            colorscale=colors,
            size=[], color=[],
        )
    )
    
    ranking_score_list = []
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['text'] += ('<b>' + node + '</b>',)
        ranking_score = round(ranking_ordinal.loc[node], 3) if ranking_ordinal.loc[node] > 0 else 0.1
        ranking_score_list.append(ranking_score)
        node_trace['hovertext'] += (
            f'Mouse ID: {node}<br>Ranking: {ranking_score}',
            )
        
    node_trace['marker']['color'] = colors
    node_trace['marker']['size'] = [rank for rank in ranking_score_list]
    return node_trace

def prep_network_df(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare network data for plotting
    """
    graph_data = (
        df
        .groupby(level='animal_ids')
        .sum(min_count=1)
        .melt(ignore_index=False, value_name='chasings', var_name='source')
        .dropna()
        .reset_index(level=['animal_ids'])
        .rename(columns={'animal_ids': 'target'})
        .groupby(['target', 'source'])
        .sum()
        .reset_index()
    )
    return graph_data

def prep_sum_per_position_df(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare visits_per_position data for plotting
    """
    plot_df = (
        df
        .melt(ignore_index=False, var_name='animal_id', value_name='y_val')
        .reset_index(level='position')
        .groupby(by=['animal_id', 'position'], observed=False)
        .sum(min_count=1)
        .reset_index()
    )
    return plot_df

def prep_mean_per_position_df(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare visits_per_position data for plotting
    """        
    plot_df = (
        df
        .melt(ignore_index=False, var_name='animal_id', value_name='y_val')
        .reset_index(level=['position', 'phase_count'])
    )
    return plot_df

def prep_ranking(ranking_df: pd.DataFrame, phase_range: list[int, int]) -> pd.Series:
    """Auxfun to prepare ranking data for plotting.
    """
    ranking = (
        ranking_df
        .loc[('dark_phase', phase_range[-1]), :] # TODO: think of a good way to handle it. Pass mode? check which phase was last if all chosen?
        )
    return ranking

def prep_ranking_distribution(ranking_df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare df for ranking distribution plotting.
    """
    df = pd.DataFrame()
    df.index = np.arange(-25, 75, 0.1) # Index that should handle most possible rankings
    for ind, row in ranking_df.iterrows():
        df[row.animal_id] = norm.pdf(df.index, row.mu, row.sigma)
    
    return df

def prep_ranking_in_time_df(main_df: pd.DataFrame, ranking_in_time: pd.DataFrame, per_hour: bool) -> pd.DataFrame:
    """Auxfun to prep the axes and data for ranking through time plot.
    """    
    # Create sampling every 5 minutes (makes plotting prettier and reduces memory footprint)
    if per_hour:
        multiplier = 0.0002778
    else:
        multiplier = 0.00333
    index_len = np.ceil((main_df.datetime.iloc[-1] - main_df.datetime.iloc[0]).total_seconds()*multiplier).astype(int)
    idx = pd.date_range(main_df.datetime.iloc[0], main_df.datetime.iloc[-1], index_len)
    idx = idx[idx <= ranking_in_time.index[-1]]

    plot_indices = np.searchsorted(np.array(ranking_in_time.index), np.array(idx), side='left')

    plot_df = ranking_in_time.iloc[plot_indices]
    
    return plot_df

def prep_pairwise_arr(df: pd.DataFrame, agg_switch: Literal['sum', 'mean']) -> tuple[np.ndarray, pd.Index]:
    """Prepares a pairwise array from DataFrame based on aggregation type."""
    cages = df.index.get_level_values('cages').unique()
    animals = df.index.get_level_values('animal_ids').unique()
    match agg_switch:
        case 'sum':
            plot_df = df.groupby(level=['cages', 'animal_ids']).sum(min_count=1)
        case 'mean':
            plot_df = df.groupby(level=['cages', 'animal_ids']).mean()
    
    plot_arr = plot_df.values.reshape(len(cages), len(animals), len(animals))

    return plot_arr, animals

def prep_chasings_plot_df(df: pd.DataFrame, agg_switch: Literal['sum', 'mean']) -> pd.DataFrame:
    """Prepares chasings plot DataFrame based on aggregation type."""
    match agg_switch:
        case 'sum':
            return df.groupby(level='animal_ids').sum(min_count=1)
        case 'mean':
            return df.groupby(level='animal_ids').mean()
        
def prep_within_cohort_plot_df(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares within-cohort plot DataFrame using mean aggregation."""
    return df.groupby(level='animal_ids').mean()

def prep_activity_overtime_sum(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of activity over hours
    """    
    plot_df = (
        df
        .loc[:, ['animal_id', 'hour']]
        .groupby('hour', observed=True)
        .value_counts()
        .reset_index()
    )

    plot_df = plot_df.groupby(['animal_id', 'hour'], observed=False).sum().reset_index()

    return plot_df

def prep_activity_overtime_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of activity over hours
    """   
    plot_df = (
        df
        .loc[:, ['animal_id', 'phase_count', 'hour']]
        .groupby(['phase_count', 'hour'], observed=True)
        .value_counts()
        .reset_index()
    )

    mean_df = plot_df.groupby(['animal_id', 'hour'], observed=False).mean().reset_index()
    sem_df = plot_df.groupby(['animal_id', 'hour'], observed=False).sem().reset_index()
    mean_df['lower'] = mean_df['count'].values - sem_df['count'].values
    mean_df['higher'] = mean_df['count'].values + sem_df['count'].values

    return mean_df

def color_sampling(values: list[str], cmap: str = 'Phase') -> list[str]:
    """Samples colors from a colormap for given values."""
    x = np.linspace(0, 1, len(values))
    colors = px.colors.sample_colorscale(cmap, x)

    return colors

def prep_match_df_line(df: pd.DataFrame, match_df: pd.DataFrame) -> pd.DataFrame:
    """Prepares match DataFrame for line plotting by concatenating and updating indices."""
    temp_df = df.loc[:, ['animal_id', 'datetime']].copy()
    match_df_temp = match_df.loc[:, ['winner', 'datetime']].copy()
    match_df_temp.columns = ['animal_id', 'datetime']

    temp_df = pd.concat([temp_df, match_df_temp])
    indices = temp_df[temp_df.duplicated(keep='last')].sort_index().index

    match_df.loc[:, ['phase_count', 'hour']] = df.loc[indices, ['phase_count', 'hour']].values

    match_df = match_df.astype({
        'phase_count': int,
        'hour': int,
    })

    return match_df

def prep_chasing_overtime_mean(match_df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of chasing over hours - mean
    """   
    plot_df = (
        match_df
        .loc[:, ['winner', 'phase_count', 'hour']]
        .groupby(['phase_count', 'hour'], observed=True)
        .value_counts()
        .reset_index()
        .rename({'winner': 'animal_id'}, axis=1)
    )   

    mean_df = plot_df.groupby(['animal_id', 'hour'], observed=False)['count'].mean().reset_index()
    sem_df = plot_df.groupby(['animal_id', 'hour'], observed=False)['count'].sem().reset_index()
    mean_df['lower'] = mean_df['count'].values - sem_df['count'].values
    mean_df['higher'] = mean_df['count'].values + sem_df['count'].values

    return mean_df

def prep_chasing_overtime_sum(match_df) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of chasing over hours - sum
    """       
    plot_df = (
        match_df
        .loc[:, ['winner', 'hour']]
        .groupby('hour', observed=True)
        .value_counts()
        .reset_index()
        .rename({'winner': 'animal_id'}, axis=1)
    )

    return plot_df