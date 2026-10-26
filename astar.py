import heapq
import math
from geometry import distance_between_nodes


def heuristic(nodes, a, b):
    """Return node distance for the scaled A* cost estimate."""
    return distance_between_nodes(nodes, a, b)


def a_star_search(nodes, edges, start, goal):
    """Return the shortest path, cost, edge weights, and trace to app.pathfind."""
    if start not in nodes or goal not in nodes:
        raise ValueError("Start or goal node does not exist in the graph.")

    # Imported weights and rounded map distances can be below Euclidean distance.
    # Scale the heuristic by the smallest edge/distance ratio to keep it consistent.
    scale = 1.0
    for a, neighbors in edges.items():
        if a not in nodes:
            raise ValueError('Edge references an unknown node.')
        for b, weight in neighbors:
            if b not in nodes or not math.isfinite(weight) or weight < 0:
                raise ValueError('Edges require known nodes and finite nonnegative weights.')
            distance = heuristic(nodes, a, b)
            if distance:
                scale = min(scale, weight / distance)

    def estimate(a):
        """Return a scaled remaining-cost estimate for the A* priority queue."""
        return scale * heuristic(nodes, a, goal)

    open_set = []
    heapq.heappush(open_set, (estimate(start), start))

    came_from = {}
    g_score = {n: math.inf for n in nodes}
    g_score[start] = 0

    f_score = {n: math.inf for n in nodes}
    f_score[start] = estimate(start)

    visited = set()
    log = []
    step = 1

    def add_row(edge, weight, g, h, f, status):
        """Append one search step to the log returned for the browser trace table."""
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

        h_current = estimate(current)
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
                h_neighbor = estimate(neighbor)
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
