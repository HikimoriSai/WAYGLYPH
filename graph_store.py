import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
GRAPH_FILE = os.path.join(DATA_DIR, "graph.txt")


def serialize_graph(nodes, edges):
    """nodes: {id: (x, y)}  edges: {id: [(neighbor, weight), ...]}  -> txt string"""
    lines = ["# GraphCrypt Graph File", "# Format: NODE,id,x,y  /  EDGE,from,to,weight"]

    for node_id, (x, y) in nodes.items():
        lines.append(f"NODE,{node_id},{x},{y}")

    seen = set()
    for node_id, neighbors in edges.items():
        for neighbor, weight in neighbors:
            key = tuple(sorted((node_id, neighbor)))
            if key not in seen:
                seen.add(key)
                lines.append(f"EDGE,{node_id},{neighbor},{weight}")

    return "\n".join(lines) + "\n"


def parse_graph(text):
    """txt string -> (nodes, edges) in the same shape used by GRAPH_STATE"""
    nodes = {}
    edges = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(",")]

        if parts[0] == "NODE" and len(parts) == 4:
            _, node_id, x, y = parts
            node_id = node_id.upper()
            nodes[node_id] = (float(x), float(y))
            edges.setdefault(node_id, [])

        elif parts[0] == "EDGE" and len(parts) == 4:
            _, a, b, w = parts
            a, b, w = a.upper(), b.upper(), float(w)
            if a not in nodes or b not in nodes:
                continue  # skip edges referencing unknown nodes
            edges.setdefault(a, []).append((b, w))
            edges.setdefault(b, []).append((a, w))

    return nodes, edges


def save_graph_to_disk(nodes, edges, path=GRAPH_FILE):
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialize_graph(nodes, edges))


def load_graph_from_disk(path=GRAPH_FILE):
    """Returns (nodes, edges) or (None, None) if the file doesn't exist yet."""
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return parse_graph(f.read())
