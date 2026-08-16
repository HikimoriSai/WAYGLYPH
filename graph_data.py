from geometry import distance_between_nodes

NODES = {
    "A": (200, 150),
    "B": (450, 300),
    "C": (700, 200),
    "D": (300, 400),
    "E": (550, 500),
    "F": (850, 450),
}

# Which node pairs are connected (undirected). Weights are computed below.
_CONNECTIONS = [
    ("A", "B"),
    ("B", "C"),
    ("A", "D"),
    ("D", "E"),
    ("B", "E"),
    ("C", "F"),
    ("E", "F"),
]


def build_edges():
    edges = {node: [] for node in NODES}
    for a, b in _CONNECTIONS:
        weight = round(distance_between_nodes(NODES, a, b), 1)
        edges[a].append((b, weight))
        edges[b].append((a, weight))
    return edges


EDGES = build_edges()
