import heapq
import math
from geometry import distance_between_nodes


def heuristic(nodes, a, b):
    """Straight-line (Euclidean) distance heuristic between two nodes.
    Uses the exact same formula as the auto-computed edge weights, which is
    what keeps this heuristic admissible by construction (see module docstring)."""
    return distance_between_nodes(nodes, a, b)


def a_star_search(nodes, edges, start, goal):
    """
    Runs A* search.

    Returns a dict with:
        path        -> list of node ids from start to goal (or None if no path)
        cost        -> total path cost (sum of edge weights)
        edge_weights-> list of (from_node, to_node, weight) for each edge used in the path
        log         -> list of human-readable strings describing each expansion step
    """
    if start not in nodes or goal not in nodes:
        raise ValueError("Start or goal node does not exist in the graph.")

    open_set = []
    heapq.heappush(open_set, (0, start))

    came_from = {}
    g_score = {n: math.inf for n in nodes}
    g_score[start] = 0

    f_score = {n: math.inf for n in nodes}
    f_score[start] = heuristic(nodes, start, goal)

    visited = set()
    log = []
    step = 1

    while open_set:
        current_f, current = heapq.heappop(open_set)

        if current in visited:
            continue
        visited.add(current)

        log.append(f"[{step:03d}] Expanding node {current}, f(n)={current_f:.2f}")
        step += 1

        if current == goal:
            # Reconstruct path
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()

            edge_weights = []
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                w = next(weight for (nb, weight) in edges[a] if nb == b)
                edge_weights.append((a, b, w))

            log.append(f"[{step:03d}] Goal reached! Total cost: {g_score[goal]:.2f}")

            return {
                "path": path,
                "cost": g_score[goal],
                "edge_weights": edge_weights,
                "log": log,
            }

        neighbors = edges.get(current, [])
        neighbor_names = ", ".join(n for n, _ in neighbors) if neighbors else "none"
        log.append(f"[{step:03d}] Found neighbors: {neighbor_names}")
        step += 1

        for neighbor, weight in neighbors:
            tentative_g = g_score[current] + weight
            if tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(nodes, neighbor, goal)
                heapq.heappush(open_set, (f_score[neighbor], neighbor))

    # No path found
    log.append("No path could be found between start and goal.")
    return {"path": None, "cost": None, "edge_weights": [], "log": log}
