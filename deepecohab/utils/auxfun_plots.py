import pandas as pd
import networkx as nx
import numpy as np
import plotly.graph_objects as go

from typing import Literal
import plotly.express as px
from scipy.stats import norm


def create_edges_trace(G: nx.Graph, pos: dict, width_multiplier: float | int, cmap: str = 'bluered') -> list:
    """Auxfun to create edges trace with color mapping based on edge width."""
    edge_trace = []
    
    # Get all edge widths to create a color scale
    edge_widths = [G.edges[edge]['chasings'] * width_multiplier for edge in G.edges()]
    
    # Normalize edge widths to the range [0, 1] for color mapping
    max_width = max(edge_widths)
    min_width = min(edge_widths)
    if max_width == 0 and min_width == 0:
        normalized_widths = [0 for _ in edge_widths]
    else:
        normalized_widths = [(width - min_width) / (max_width - min_width) for width in edge_widths]
    
    colorscale = px.colors.sample_colorscale(cmap, normalized_widths)
    
    for i, edge in enumerate(G.edges()):
        source_x, source_y = pos[edge[0]]  # Start point (source node)
        target_x, target_y = pos[edge[1]]  # End point (target node)
        edge_width = edge_widths[i]
        
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
                marker=dict(size=edge_width * 4, symbol='arrow', angleref='previous'),
                opacity=0.5,
                showlegend=False,
            )
        )
    
    return edge_trace

def create_node_trace(G: nx.DiGraph, pos: dict, ranking_ordinal: pd.Series, node_size_multiplier: float | int, colors: list, animals: list) -> go.Scatter:
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
    
    # Add positions and text to node_trace
    ranking_score_list = []
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += (x,)
        node_trace['y'] += (y,)
        node_trace['text'] += ('<b>' + node + '</b>',)
        ranking_score = round(ranking_ordinal[node], 3) if ranking_ordinal[node] > 0 else 0.1
        ranking_score_list.append(ranking_score)
        node_trace['hovertext'] += (
            f'Mouse ID: {node}<br>Ranking: {ranking_score}',
            )
        
    # Scale node size and color
    node_trace['marker']['color'] = animals
    node_trace['marker']['size'] = [rank * node_size_multiplier for rank in ranking_score_list]
    return node_trace

def prep_network_df(chasing_data: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare network data for plotting
    """
    graph_data = (
        chasing_data
        .melt(ignore_index=False, value_name='chasings', var_name='source')
        .dropna()
        .reset_index()
        .rename(columns={'animal_ids': 'target'})
    )
    return graph_data

def prep_per_position_df(visits_per_position: pd.DataFrame, plot_type: Literal['visits', 'time']) -> pd.DataFrame:
    """Auxfun to prepare visits_per_position data for plotting
    """
    match plot_type:
        case 'visits':
            val_name = 'Visits[#]'
        case 'time':
            val_name = 'Time[s]'
        case _:
            raise ValueError('Invalid type. Choose between "visits" and "time".')
        
    visits_per_position_df = visits_per_position.melt(ignore_index=False, value_name=val_name, var_name='animal_id').reset_index()
    return visits_per_position_df

def prep_ranking(ranking_df: pd.DataFrame) -> pd.Series:
    """Auxfun to prepare ranking data for plotting.
    """
    ranking = (
        ranking_df
        .melt(ignore_index=False, var_name='mouse_id', value_name='ranking')
        .reset_index()
        )
    return ranking

def prep_ranking_distribution(ranking_df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prepare df for ranking distribution plotting.
    """
    df = pd.DataFrame()
    df.index = np.arange(-25, 75, 0.1)
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

def prep_activity_overtime_sum(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of activity over hours
    """    
    plot_df = (
        df
        .loc[:, ["animal_id", 'phase_count', "hour"]]
        .groupby(["phase_count", "hour"], observed=True)
        .value_counts()
        .reset_index()
    )

    plot_df = plot_df.iloc[:, 1:].groupby(["animal_id", "hour"], observed=False).sum().reset_index()

    return plot_df

def prep_activity_overtime_mean(df: pd.DataFrame) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of activity over hours
    """   
    plot_df = (
        df
        .loc[:, ["animal_id", 'phase_count', "hour"]]
        .groupby(["phase_count", "hour"], observed=True)
        .value_counts()
        .reset_index()
    )

    mean_df = plot_df.iloc[:, 1:].groupby(["animal_id", "hour"], observed=False).mean().reset_index()
    sem_df = plot_df.iloc[:, 1:].groupby(["animal_id", "hour"], observed=False).sem().reset_index()
    mean_df["lower"] = mean_df['count'].values - sem_df['count'].values
    mean_df["higher"] = mean_df['count'].values + sem_df['count'].values

    return mean_df

def color_sampling(values: list[str], cmap: str = "Phase") -> list[str]:
    x = np.linspace(0, 1, len(values))
    colors = px.colors.sample_colorscale(cmap, x)

    return colors

def plot_mean_activity_per_hour(df: pd.DataFrame, animals: list[str], colors: list[str]) -> go.Figure:
    """Create a line plot showing per hour activity grouped by phase_count - mean per phase_count. 
    Activity is defined as every antenna detection.

    Args:
        df: main_df of the dataset
        animals: animal_ids
        colors: list of colors to be used for animals

    Returns:
        Line plot of mean N detections in phase_counts with shaded region for SEM
    """

    plot_df = prep_activity_overtime_mean(df)

    fig = go.Figure()

    x = list(range(24))
    x_rev = x[::-1]

    for animal, color in zip(animals, colors):
        animal_df = plot_df.query("animal_id == @animal")
        
        y = list(animal_df["count"].values)
        y_upper = list(animal_df["higher"].values) 
        y_lower = list(animal_df["lower"].values)[::-1]

        shade_color = color.replace('rgb', 'rgba').replace(')', ', 0.2)') # shaded region is SEM
 
        fig.add_trace(go.Scatter(
            x=x+x_rev,
            y=y_upper+y_lower,
            fill='toself',
            fillcolor=shade_color,
            line_color='rgba(255,255,255,0)',
            showlegend=False,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

        fig.add_trace(go.Scatter(
            x=x, y=y,
            line_color=color,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

    fig.update_layout(title="<b>Activity over time</b>")
    fig.update_yaxes(title="<b>Antenna detections</b>")
    fig.update_xaxes(title="<b>Hours</b>")
    
    return fig

def plot_sum_activity_per_hour(df: pd.DataFrame, colors: list[str]) -> go.Figure:
    """Create a line plot showing per hour activity grouped by phase_count - sum of phase_counts. 
    Activity is defined as every antenna detection.

    Args:
        df: main_df of the dataset
        colors: list of colors to be used for animals

    Returns:
        Line plot of sum of all antenna detections across selected phases
    """
    plot_df = prep_activity_overtime_sum(df)

    fig = px.line(
        plot_df, 
        x="hour", 
        y="count", 
        color="animal_id", 
        color_discrete_sequence=colors, 
        line_shape='spline', 
        title="<b>Activity over time</b>", 
    )
    fig.update_yaxes(title="Antenna detections")
    fig.update_xaxes(title="<b>Hours</b>")
    
    return fig

def prep_match_df_line(df, match_df):
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

def prep_chasing_overtime_mean(match_df):
    """Auxfun to prep data for a line plot of chasing over hours - mean
    """   
    plot_df = (
        match_df
        .loc[:, ['winner', 'phase_count', 'hour']]
        .groupby(['phase_count', 'hour'], observed=True)
        .value_counts()
        .reset_index()
    )

    mean_df = plot_df.iloc[:, 1:].groupby(["winner", "hour"], observed=False).mean().reset_index()
    sem_df = plot_df.iloc[:, 1:].groupby(["winner", "hour"], observed=False).sem().reset_index()
    mean_df["lower"] = mean_df['count'].values - sem_df['count'].values
    mean_df["higher"] = mean_df['count'].values + sem_df['count'].values

    return mean_df

def prep_chasing_overtime_sum(match_df) -> pd.DataFrame:
    """Auxfun to prep data for a line plot of chasing over hours - sum
    """       
    plot_df = (
        match_df
        .loc[:, ['winner', 'phase_count', 'hour']]
        .groupby(['phase_count', 'hour'], observed=True)
        .value_counts()
        .reset_index()
    )

    plot_df = plot_df.iloc[:, 1:].groupby(["winner", "hour"], observed=False).sum().reset_index()

    return plot_df


def plot_mean_chasings_per_hour(
        match_df: pd.DataFrame, 
        animals: list[str], 
        colors: list[str]
    ) -> go.Figure:
    """Create a line plot showing per hour activity grouped by phase_count - mean per phase_count. 
    Activity is defined as every antenna detection.

    Args:
        df: mean_df of antenna detections per hour
        animals: animal_ids
        colors: list of colors to be used for animals

    Returns:
        Line plot of mean N detections in phase_counts with shaded region for SEM
    """

    plot_df = prep_chasing_overtime_mean(match_df)

    fig = go.Figure()

    x = list(range(24))
    x_rev = x[::-1]

    for animal, color in zip(animals, colors):
        animal_df = plot_df.query("winner == @animal")
        
        y = list(animal_df["count"].values)
        y_upper = list(animal_df["higher"].values) 
        y_lower = list(animal_df["lower"].values)[::-1]

        shade_color = color.replace('rgb', 'rgba').replace(')', ', 0.2)') # shaded region is SEM
 
        fig.add_trace(go.Scatter(
            x=x+x_rev,
            y=y_upper+y_lower,
            fill='toself',
            fillcolor=shade_color,
            line_color='rgba(255,255,255,0)',
            showlegend=False,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

        fig.add_trace(go.Scatter(
            x=x, y=y,
            line_color=color,
            name=animal,
            legendgroup=animal,
            line=dict(
                shape='spline'
            )
        ))

    fig.update_layout(title="<b>Chasing over time</b>")
    fig.update_yaxes(title="<b># of chasing events</b>")
    fig.update_xaxes(title="<b>Hours</b>")
    
    return fig

def plot_sum_chasings_per_hour(match_df: pd.DataFrame, colors: list[str]) -> go.Figure:
    """Create a line plot showing per hour chasing grouped by phase_count - sum of phase_counts. 

    Args:
        df: mean_df of antenna detections per hour
        colors: list of colors to be used for animals

    Returns:
        Line plot of sum of all antenna detections across selected phases
    """
    plot_df = prep_chasing_overtime_sum(match_df)

    fig = px.line(
        plot_df, 
        x="hour", 
        y="count", 
        color="winner", 
        color_discrete_sequence=colors, 
        line_shape='spline', 
        title="<b>Chasing over time</b>", 
    )
    fig.update_yaxes(title="# of chasing events")
    fig.update_xaxes(title="<b>Hours</b>")
    
    return fig

def load_dashboard_data(store: pd.HDFStore) -> dict[pd.DataFrame | pd.Series]:
    """Auxfun to load data from HDF5 store
    """
    main_df = pd.read_hdf(store, key='main_df')
    padded_df = pd.read_hdf(store, key='padded_df')
    ranking_in_time = pd.read_hdf(store, key='ranking_in_time')
    time_per_position_df = pd.read_hdf(store, key='time_per_position')
    time_per_position_df = time_per_position_df.melt(ignore_index=False, value_name='Time[s]', var_name='animal_id').reset_index()
    visits_per_position_df = pd.read_hdf(store, key='visits_per_position')
    visits_per_position_df = visits_per_position_df.melt(ignore_index=False, value_name='Visits[#]', var_name='animal_id').reset_index()
    time_together = pd.read_hdf(store, key='time_together').reset_index()
    pairwise_encounters = pd.read_hdf(store, key='pairwise_encounters').reset_index()
    chasings_df = pd.read_hdf(store, key='chasings')
    incohort_sociability_df = pd.read_hdf(store, key='incohort_sociability')
    ranking_ordinal_df = pd.read_hdf(store, key='ranking_ordinal')
    ranking = pd.read_hdf(store, key='ranking')
    plot_chasing_data = prep_network_df(chasings_df)
    plot_ranking_data = prep_ranking(ranking_ordinal_df)
    match_df = pd.read_hdf(store, key='match_df')
    
    return {
        'main_df': main_df,
        'padded_df': padded_df,
        'ranking_in_time': ranking_in_time,
        'time_per_position_df': time_per_position_df,
        'visits_per_position_df': visits_per_position_df,
        'time_together': time_together,
        'pairwise_encounters': pairwise_encounters,
        'chasings_df': chasings_df,
        'incohort_sociability_df': incohort_sociability_df,
        'ranking_ordinal_df': ranking_ordinal_df,
        'plot_chasing_data': plot_chasing_data,
        'plot_ranking_data': plot_ranking_data,
        'ranking': ranking,
        'match_df': match_df,
    }    