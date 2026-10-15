import os
import tempfile
from validation import node_id as validate_node_id, coordinate, weight, MAX_NODES, MAX_EDGES

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
    pending_edges = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [p.strip() for p in line.split(",")]

        if parts[0] == "NODE" and len(parts) == 4:
            _, node_id, x, y = parts
            node_id = validate_node_id(node_id)
            if node_id in nodes or len(nodes) >= MAX_NODES:
                raise ValueError('Duplicate node ID or graph exceeds 1,000 nodes.')
            nodes[node_id] = (coordinate(float(x)), coordinate(float(y)))
            edges.setdefault(node_id, [])

        elif parts[0] == "EDGE" and len(parts) == 4:
            _, a, b, w = parts
            pending_edges.append((validate_node_id(a), validate_node_id(b), weight(float(w))))
            if len(pending_edges) > MAX_EDGES:
                raise ValueError('Graph exceeds 10,000 edges.')
        else:
            raise ValueError('Expected NODE,id,x,y or EDGE,from,to,weight.')

    seen = set()
    for a, b, w in pending_edges:
        if a not in nodes or b not in nodes or a == b:
            raise ValueError('Edges must connect two different existing nodes.')
        pair = tuple(sorted((a, b)))
        if pair in seen:
            raise ValueError('Duplicate edge.')
        seen.add(pair)
        edges[a].append((b, w))
        edges[b].append((a, w))

    return nodes, edges


def save_graph_to_disk(nodes, edges, path=GRAPH_FILE):
    # Replace only after a complete write, so interruptions cannot truncate the graph.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=os.path.dirname(path),
                                         delete=False) as f:
            temporary = f.name
            f.write(serialize_graph(nodes, edges))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_graph_from_disk(path=GRAPH_FILE):
    """Returns (nodes, edges) or (None, None) if the file doesn't exist yet."""
    if not os.path.exists(path):
        return None, None
    with open(path, "r", encoding="utf-8") as f:
        return parse_graph(f.read())
