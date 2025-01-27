from dash import Dash, html, dcc, Input, Output
import pandas as pd
import networkx as nx
import plotly.graph_objects as go

# Przykładowe dane
data = pd.DataFrame({
    'A': [0, 1, 0.5],
    'B': [1, 0, 0.2],
    'C': [0.5, 0.2, 0]
}, index=['A', 'B', 'C'])

ranking_ordinal = pd.Series({'A': 1, 'B': 2, 'C': 3})

# Tworzenie grafu
G = nx.DiGraph()
for mouse_1, row in data.iterrows():
    for mouse_2, weight in row.items():
        if pd.notna(weight):
            G.add_edge(mouse_2, mouse_1, weight=weight)

# Layout
pos = nx.spring_layout(G, seed=42)

# Funkcja do tworzenia edge traces na podstawie progu
def create_edge_trace(graph, pos, threshold=0):
    edge_trace = []
    for edge in graph.edges():
        weight = graph.edges[edge].get('weight', 0)
        if weight >= threshold:
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_trace.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                line=dict(width=2 * weight, color='#888'),  # Szerokość krawędzi zależna od wagi
                hoverinfo='none',
                mode='lines'
            ))
    return edge_trace

# Tworzenie node trace
node_trace = go.Scatter(
    x=[], y=[], text=[], hovertext=[],
    mode='markers',
    hoverinfo='text',
    marker=dict(
        showscale=True,
        colorscale='Viridis',
        size=20,
        color=[],
        colorbar=dict(thickness=15, title='Ranking')
    ),
    customdata=list(G.nodes())
)

# Dodawanie pozycji i tekstu do node_trace
for node in G.nodes():
    x, y = pos[node]
    node_trace['x'] += (x,)
    node_trace['y'] += (y,)
    node_trace['hovertext'] += (f"Mouse ID: {node}<br>Ranking: {ranking_ordinal[node]}",)
    node_trace['marker']['color'] += (ranking_ordinal[node],)

# Aplikacja Dash
app = Dash(__name__)
app.layout = html.Div([
    dcc.Graph(id='network-graph'),
    html.Div(id='click-output'),
    html.Div([
        html.Label("Próg wagi krawędzi:"),
        dcc.Slider(
            id='weight-threshold-slider',
            min=0,
            max=1,
            step=0.1,
            value=0,  # Domyślny próg
            marks={i: str(i) for i in [0, 0.2, 0.4, 0.6, 0.8, 1]},
        )
    ]),
    html.Div(id='network-stats')
])

# Callback do aktualizacji grafu i statystyk
@app.callback(
    [Output('network-graph', 'figure'),
     Output('network-stats', 'children')],
    [Input('weight-threshold-slider', 'value')]
)
def update_graph(threshold):
    # Filtruj krawędzie na podstawie progu
    filtered_edges = [(u, v) for u, v, w in G.edges(data='weight') if w >= threshold]
    filtered_graph = G.edge_subgraph(filtered_edges)

    # Tworzenie edge traces dla przefiltrowanego grafu
    edge_trace = create_edge_trace(filtered_graph, pos, threshold)

    # Tworzenie figury
    fig = go.Figure(
        data=edge_trace + [node_trace],
        layout=go.Layout(
            title='Network Graph',
            showlegend=False,
            hovermode='closest',
            margin=dict(b=0, l=0, r=0, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            width=800,
            height=600
        )
    )

    # Obliczanie statystyk dla przefiltrowanego grafu
    stats = {
        "Liczba węzłów": filtered_graph.number_of_nodes(),
        "Liczba krawędzi": filtered_graph.number_of_edges(),
        "Średni stopień węzła": round(sum(dict(filtered_graph.degree()).values()) / filtered_graph.number_of_nodes(), 2),
        "Gęstość sieci": round(nx.density(filtered_graph), 4),
    }
    if nx.is_connected(filtered_graph.to_undirected()):
        stats["Średnica sieci"] = nx.diameter(filtered_graph.to_undirected())
    else:
        stats["Średnica sieci"] = "Graf nie jest spójny"

    # Formatowanie statystyk
    stats_html = html.Ul([html.Li(f"{key}: {value}") for key, value in stats.items()])

    return fig, stats_html

# Callback do podświetlania sąsiadów
@app.callback(
    Output('click-output', 'children'),
    Input('network-graph', 'clickData')
)
def highlight_edges(clickData):
    if clickData:
        selected_node = clickData['points'][0]['customdata']
        neighbors = list(G.neighbors(selected_node))
        return f"Wybrano węzeł: {selected_node}. Sąsiedzi: {', '.join(neighbors)}"
    return "Kliknij węzeł, aby zobaczyć sąsiadów."

# Uruchomienie aplikacji
if __name__ == '__main__':
    app.run_server(debug=True)