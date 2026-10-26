import math


def euclidean_distance(x1, y1, x2, y2):
    """Return straight-line distance for graph weights and A* estimates."""
    return math.hypot(x1 - x2, y1 - y2)


def distance_between_nodes(nodes, a, b):
    """Look up two node coordinates and return their straight-line distance."""
    ax, ay = nodes[a]
    bx, by = nodes[b]
    return euclidean_distance(ax, ay, bx, by)
