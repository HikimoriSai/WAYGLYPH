from geometry import distance_between_nodes

NODES = {
    "A": (180, 120),
    "B": (600, 120),
    "C": (600, 400),
    "D": (180, 400),
    "E": (320, 220),
    "F": (740, 220),
    "G": (740, 500),
    "H": (320, 500),
}

_CONNECTIONS = [
    ("A", "B"),
    ("B", "C"),
    ("C", "D"),
    ("D", "A"),
    ("E", "F"),
    ("F", "G"),
    ("G", "H"),
    ("H", "E"),
    ("A", "E"),
    ("B", "F"),
    ("C", "G"),
    ("D", "H"),
]


def build_edges():
    edges = {node: [] for node in NODES}

    for a, b in _CONNECTIONS:
        weight = round(distance_between_nodes(NODES, a, b), 1)
        edges[a].append((b, weight))
        edges[b].append((a, weight))

    return edges


EDGES = build_edges()