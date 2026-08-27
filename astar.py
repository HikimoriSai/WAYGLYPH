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
        log         -> list of structured trace rows, one per row of the
                        "A* Search Trace" table:
                          {
                            "step":   int,
                            "edge":   "A" (a node was popped/reached) or
                                      "A -> B" style label when an edge from A
                                      to B was relaxed,
                            "weight": edge weight, or None for a node-only row,
                            "g": g(n), "h": h(n), "f": f(n) = g(n) + h(n),
                            "status": human-readable evaluation status,
                          }
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

    def add_row(edge, weight, g, h, f, status):
        nonlocal step
        log.append({
            "step": step,
            "edge": edge,
            "weight": None if weight is None else round(weight, 1),
            "g": round(g, 1),
            "h": round(h, 1),
            "f": round(f, 1),
            "status": status,
        })
        step += 1

    while open_set:
        current_f, current = heapq.heappop(open_set)

        if current in visited:
            continue
        visited.add(current)

        h_current = heuristic(nodes, current, goal)
        add_row(current, None, g_score[current], h_current,
                g_score[current] + h_current, "Node selected from open set")

        if current == goal:
            # Reconstruct path
            path = [current]
            node = current
            while node in came_from:
                node = came_from[node]
                path.append(node)
            path.reverse()

            edge_weights = []
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                w = next(weight for (nb, weight) in edges[a] if nb == b)
                edge_weights.append((a, b, w))

            add_row(goal, None, g_score[goal], 0.0, g_score[goal], "Goal reached")

            return {
                "path": path,
                "cost": g_score[goal],
                "edge_weights": edge_weights,
                "log": log,
            }

        for neighbor, weight in edges.get(current, []):
            tentative_g = g_score[current] + weight
            if tentative_g < g_score[neighbor]:
                h_neighbor = heuristic(nodes, neighbor, goal)
                f_neighbor = tentative_g + h_neighbor
                edge_label = f"{current} \u2192 {neighbor}"

                # A route improvement is reported in two rows: the moment it's
                # found, then the moment it's committed to g/f-scores and the
                # open set -- mirroring the two-phase "relax, then push" step.
                add_row(edge_label, weight, tentative_g, h_neighbor, f_neighbor,
                        "Better route found")

                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = f_neighbor
                heapq.heappush(open_set, (f_neighbor, neighbor))

                add_row(edge_label, weight, tentative_g, h_neighbor, f_neighbor,
                        "Best route updated")

    # No path found (0s here are just placeholders -- inf isn't valid JSON)
    add_row(None, None, 0.0, 0.0, 0.0, "No path found")
    return {"path": None, "cost": None, "edge_weights": [], "log": log}