import math


def euclidean_distance(x1, y1, x2, y2):
    return math.hypot(x1 - x2, y1 - y2)


def distance_between_nodes(nodes, a, b):
    """nodes: {id: (x, y)}"""
    ax, ay = nodes[a]
    bx, by = nodes[b]
    return euclidean_distance(ax, ay, bx, by)
