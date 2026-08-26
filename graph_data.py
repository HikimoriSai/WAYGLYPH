from geometry import distance_between_nodes

NODES = {
    "A": (250, 30),
    "B": (35, 110),
    "C": (300, 200),
    "D": (445, 155),
    "E": (720, 80),
    "F": (860, 200),
    "G": (640, 220),
    "H": (300, 320),
    "I": (50, 220),
    "J": (95, 400),
    "K": (175, 385),
    "L": (155, 450),
    "M": (475, 445),
    "N": (615, 465),
    "O": (735, 395),
    "P": (845, 465),
    "Q": (885, 540),
    "R": (515, 520),
    "S": (335, 530),
    "T": (25, 540),
}

_CONNECTIONS = [
    ("A", "B"),
    ("A", "C"),
    ("B", "I"),
    ("I", "C"),
    ("I", "K"),
    ("C", "D"),
    ("C", "H"),
    ("D", "N"),
    ("H", "M"),
    ("H", "S"),
    ("K", "J"),
    ("K", "L"),
    ("L", "T"),
    ("T", "S"),
    ("S", "M"),
    ("M", "N"),
    ("N", "R"),
    ("N", "O"),
    ("O", "F"),
    ("O", "P"),
    ("P", "Q"),
    ("E", "F"),
    ("E", "G"),
]


def build_edges():
    edges = {node: [] for node in NODES}

    for a, b in _CONNECTIONS:
        weight = round(distance_between_nodes(NODES, a, b), 1)
        edges[a].append((b, weight))
        edges[b].append((a, weight))

    return edges


EDGES = build_edges()