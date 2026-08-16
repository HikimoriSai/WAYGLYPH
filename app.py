import os
import copy
import string
from flask import Flask, jsonify, request, render_template, send_from_directory

from astar import a_star_search
from cipher import caesar_encrypt_number, caesar_encrypt_letters
from geometry import distance_between_nodes
from graph_data import NODES as SAMPLE_NODES, EDGES as SAMPLE_EDGES
from graph_store import (
    save_graph_to_disk, load_graph_from_disk, serialize_graph, parse_graph, GRAPH_FILE
)

app = Flask(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
EXPORT_FILENAME = "encrypted_path.txt"


def _fresh_state(seed=True):
    """Build a fresh in-memory graph state. seed=True loads the sample graph;
    seed=False starts from a totally empty canvas."""
    if seed:
        return {
            "nodes": copy.deepcopy(SAMPLE_NODES),   # {id: (x, y)}
            "edges": copy.deepcopy(SAMPLE_EDGES),   # {id: [(neighbor, weight), ...]}
        }
    return {"nodes": {}, "edges": {}}


def _persist():
    """Auto-save the current in-memory graph to data/graph.txt."""
    save_graph_to_disk(GRAPH_STATE["nodes"], GRAPH_STATE["edges"])


def _load_initial_state():
    """On startup: use the saved graph.txt if it exists, else seed the sample graph."""
    nodes, edges = load_graph_from_disk()
    if nodes is not None and nodes:
        return {"nodes": nodes, "edges": edges}
    state = _fresh_state(seed=True)
    return state


# In-memory graph state, restored from data/graph.txt if it exists
GRAPH_STATE = _load_initial_state()
_persist()  # make sure graph.txt exists on first run


def _next_node_id():
    """Auto-generate the next free node id: A, B, C, ... Z, A1, B1, ..."""
    used = set(GRAPH_STATE["nodes"].keys())
    for letter in string.ascii_uppercase:
        if letter not in used:
            return letter
    suffix = 1
    while True:
        for letter in string.ascii_uppercase:
            candidate = f"{letter}{suffix}"
            if candidate not in used:
                return candidate
        suffix += 1


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/graph", methods=["GET"])
def get_graph():
    """Returns the current plaintext graph so the frontend can draw it."""
    edge_list = []
    seen = set()
    for node, neighbors in GRAPH_STATE["edges"].items():
        for neighbor, weight in neighbors:
            key = tuple(sorted((node, neighbor)))
            if key not in seen:
                seen.add(key)
                edge_list.append({"from": node, "to": neighbor, "weight": weight})

    node_list = [{"id": n, "x": x, "y": y} for n, (x, y) in GRAPH_STATE["nodes"].items()]
    return jsonify({"nodes": node_list, "edges": edge_list})


@app.route("/api/graph/reset", methods=["POST"])
def reset_graph():
    """Body: {"seed": true|false} -> true loads the sample A-F graph, false clears it."""
    data = request.get_json(force=True, silent=True) or {}
    seed = bool(data.get("seed", False))
    global GRAPH_STATE
    GRAPH_STATE = _fresh_state(seed=seed)
    _persist()
    return get_graph()


@app.route("/api/nodes", methods=["POST"])
def add_node():
    """Body: {"x": float, "y": float, "id": optional str}"""
    data = request.get_json(force=True)
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify({"error": "x and y are required"}), 400

    node_id = (data.get("id") or "").strip().upper() or _next_node_id()
    if node_id in GRAPH_STATE["nodes"]:
        return jsonify({"error": f"Node '{node_id}' already exists"}), 400

    GRAPH_STATE["nodes"][node_id] = (float(x), float(y))
    GRAPH_STATE["edges"].setdefault(node_id, [])
    _persist()
    return jsonify({"id": node_id, "x": x, "y": y})


@app.route("/api/nodes/<node_id>", methods=["DELETE"])
def delete_node(node_id):
    node_id = node_id.upper()
    if node_id not in GRAPH_STATE["nodes"]:
        return jsonify({"error": f"Node '{node_id}' not found"}), 404

    del GRAPH_STATE["nodes"][node_id]
    GRAPH_STATE["edges"].pop(node_id, None)
    for neighbors in GRAPH_STATE["edges"].values():
        neighbors[:] = [(n, w) for (n, w) in neighbors if n != node_id]
    _persist()
    return jsonify({"deleted": node_id})


@app.route("/api/edges", methods=["POST"])
def add_edge():
    """
    Body: {"from": "A", "to": "B"}

    The edge weight is NOT provided manually. It is computed automatically
    from the Euclidean (straight-line) distance between the two nodes'
    (x, y) map coordinates -- the exact same formula used by A*'s heuristic
    in astar.py (both call geometry.distance_between_nodes). Using the same
    formula in both places is what guarantees the heuristic never
    overestimates the true remaining cost, which is required for A* to
    guarantee it finds the true shortest path.
    """
    data = request.get_json(force=True)
    a = (data.get("from") or "").strip().upper()
    b = (data.get("to") or "").strip().upper()

    if a not in GRAPH_STATE["nodes"] or b not in GRAPH_STATE["nodes"]:
        return jsonify({"error": "Both nodes must exist before connecting them"}), 400
    if a == b:
        return jsonify({"error": "Cannot connect a node to itself"}), 400

    weight = round(distance_between_nodes(GRAPH_STATE["nodes"], a, b), 1)
    if weight <= 0:
        weight = 0.1  # guard against two nodes placed on the exact same spot

    GRAPH_STATE["edges"].setdefault(a, [])
    GRAPH_STATE["edges"].setdefault(b, [])

    # Replace existing edge between a-b if present, else add new
    GRAPH_STATE["edges"][a] = [(n, w) for (n, w) in GRAPH_STATE["edges"][a] if n != b]
    GRAPH_STATE["edges"][b] = [(n, w) for (n, w) in GRAPH_STATE["edges"][b] if n != a]
    GRAPH_STATE["edges"][a].append((b, weight))
    GRAPH_STATE["edges"][b].append((a, weight))
    _persist()

    return jsonify({"from": a, "to": b, "weight": weight})


@app.route("/api/edges", methods=["DELETE"])
def delete_edge():
    """Body: {"from": "A", "to": "B"}"""
    data = request.get_json(force=True)
    a = (data.get("from") or "").strip().upper()
    b = (data.get("to") or "").strip().upper()

    if a in GRAPH_STATE["edges"]:
        GRAPH_STATE["edges"][a] = [(n, w) for (n, w) in GRAPH_STATE["edges"][a] if n != b]
    if b in GRAPH_STATE["edges"]:
        GRAPH_STATE["edges"][b] = [(n, w) for (n, w) in GRAPH_STATE["edges"][b] if n != a]
    _persist()

    return jsonify({"deleted_edge": [a, b]})


@app.route("/api/graph/save", methods=["GET"])
def save_graph_file():
    """Downloads the current graph as a plain .txt file (nodes + edges),
    so it can be reloaded later or shared/submitted alongside the export."""
    _persist()  # make sure the file on disk matches the current in-memory state
    directory, filename = os.path.split(GRAPH_FILE)
    return send_from_directory(directory, filename, as_attachment=True,
                                download_name="graphcrypt_graph.txt")


@app.route("/api/graph/load", methods=["POST"])
def load_graph_file():
    """Body: multipart/form-data with a 'file' field containing a graph .txt
    (same format produced by /api/graph/save). Replaces the current graph."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded = request.files["file"]
    try:
        text = uploaded.read().decode("utf-8")
        nodes, edges = parse_graph(text)
    except Exception as e:
        return jsonify({"error": f"Could not parse graph file: {e}"}), 400

    if not nodes:
        return jsonify({"error": "The uploaded file has no valid NODE lines."}), 400

    global GRAPH_STATE
    GRAPH_STATE = {"nodes": nodes, "edges": edges}
    _persist()
    return get_graph()


@app.route("/api/pathfind", methods=["POST"])
def pathfind():
    data = request.get_json(force=True)
    start = (data.get("start") or "").strip().upper()
    goal = (data.get("goal") or "").strip().upper()
    cipher_key = int(data.get("cipher_key", 3))

    if not start or not goal:
        return jsonify({"error": "start and goal are required"}), 400

    nodes = GRAPH_STATE["nodes"]
    edges = GRAPH_STATE["edges"]

    if len(nodes) < 2:
        return jsonify({"error": "Add at least two nodes to the map first."}), 400

    try:
        result = a_star_search(nodes, edges, start, goal)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if result["path"] is None:
        return jsonify({"error": "No path found between the selected nodes.",
                         "log": result["log"]}), 200

    # Encrypt each edge weight along the discovered path
    encrypted_edges = []
    for (a, b, w) in result["edge_weights"]:
        encrypted_edges.append({
            "from": a,
            "to": b,
            "plain_weight": w,
            "encrypted_weight": caesar_encrypt_number(w, cipher_key),
        })

    encrypted_path_str = caesar_encrypt_letters("->".join(result["path"]), cipher_key)

    # Write the .txt export
    export_path = os.path.join(OUTPUT_DIR, EXPORT_FILENAME)
    with open(export_path, "w", encoding="utf-8") as f:
        f.write("GraphCrypt Encrypted Export\n")
        f.write("============================\n")
        f.write(f"Cipher Key: {cipher_key}\n")
        f.write(f"Origin Path (plaintext): {' -> '.join(result['path'])}\n")
        f.write(f"Origin Path (encrypted): {encrypted_path_str}\n")
        f.write(f"Total Cost (plaintext): {result['cost']:.2f}\n\n")
        f.write("Encrypted Edge Weights (basis for shortest-path cost):\n")
        for e in encrypted_edges:
            f.write(f"  {e['from']} -> {e['to']} : {e['encrypted_weight']}"
                     f"  (plain: {e['plain_weight']})\n")

    return jsonify({
        "path": result["path"],
        "encrypted_path": encrypted_path_str,
        "cost": round(result["cost"], 2),
        "log": result["log"],
        "encrypted_edges": encrypted_edges,
        "cipher_key": cipher_key,
        "export_ready": True,
    })


@app.route("/api/download", methods=["GET"])
def download():
    return send_from_directory(OUTPUT_DIR, EXPORT_FILENAME, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
