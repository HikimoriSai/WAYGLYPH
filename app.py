import os
import copy
import string
import base64
import binascii
from threading import RLock, BoundedSemaphore
from urllib.parse import urlsplit
from flask import Flask, jsonify, request, render_template, send_from_directory, g
from werkzeug.exceptions import HTTPException, ServiceUnavailable
from validation import node_id as validate_node_id, coordinate, cipher_key as validate_key, MAX_NODES, MAX_EDGES

from astar import a_star_search
from cipher import caesar_encrypt_number, caesar_encrypt_message
from geometry import distance_between_nodes
from text_algorithms import (compress_text, huffman_decompress, rle_decompress,
                             parallel_search, optimize_storage, search_document)
from graph_data import NODES as SAMPLE_NODES, EDGES as SAMPLE_EDGES
from graph_store import (
    save_graph_to_disk, load_graph_from_disk, serialize_graph, parse_graph, GRAPH_FILE
)

app = Flask(__name__)
# 2 MB of text can expand to 12 MB under JSON escaping or 5.34 MB as base64 RLE.
app.config['MAX_CONTENT_LENGTH'] = 16_000_000
app.config['MAX_FORM_MEMORY_SIZE'] = 100_000
app.config['MAX_FORM_PARTS'] = 10
GRAPH_LOCK = RLock()
TEXT_SLOTS = BoundedSemaphore(2)


@app.before_request
def guard_requests():
    # This project is a local single-user lab. Reject DNS rebinding and browser
    # requests from other origins, including cross-site multipart form uploads.
    if urlsplit(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        return jsonify(error='This application accepts localhost requests only.'), 403
    if request.path.startswith('/api/'):
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and origin != request.host_url.rstrip('/')):
            return jsonify(error='Cross-origin API requests are not allowed.'), 403
    if request.path.startswith('/api/text/'):
        if not TEXT_SLOTS.acquire(blocking=False):
            return jsonify(error='Text workers are busy. Try again shortly.'), 429
        g.text_slot = True
    elif request.path.startswith('/api/'):
        GRAPH_LOCK.acquire()
        g.graph_lock = True
        if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
            g.graph_snapshot = copy.deepcopy(GRAPH_STATE)


@app.teardown_request
def release_locks(error):
    if g.pop('text_slot', False):
        TEXT_SLOTS.release()
    if g.pop('graph_lock', False):
        GRAPH_LOCK.release()


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
@app.errorhandler(OverflowError)
def invalid_input(error):
    return jsonify(error=str(error)), 400


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    return response


def _json():
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError('Send a JSON object.')
    return data

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
    global GRAPH_STATE
    try:
        save_graph_to_disk(GRAPH_STATE["nodes"], GRAPH_STATE["edges"])
    except OSError:
        if g.get('graph_snapshot') is not None:
            GRAPH_STATE = g.graph_snapshot
        app.logger.exception('Graph save failed')
        raise ServiceUnavailable('Could not save the graph. Changes were not applied.')


def _load_initial_state():
    """On startup: use the saved graph.txt if it exists, else seed the sample graph."""
    nodes, edges = load_graph_from_disk()
    if nodes is not None:
        return {"nodes": nodes, "edges": edges}
    state = _fresh_state(seed=True)
    return state


# In-memory graph state, restored from data/graph.txt if it exists
GRAPH_STATE = _load_initial_state()
# Do not write on import: parallel workers may import this module too.


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


@app.route('/pathfinder')
def pathfinder_page():
    return render_template('index.html')


def _documents(data):
    documents = data.get('documents')
    if not isinstance(documents, list) or not 1 <= len(documents) <= 30:
        raise ValueError('Provide 1 to 30 documents.')
    for doc in documents:
        if not isinstance(doc, dict) or not isinstance(doc.get('text'), str) or not isinstance(doc.get('name'), str):
            raise ValueError('Each document needs a name and text.')
        if not 1 <= len(doc['name']) <= 255:
            raise ValueError('Document names must contain 1 to 255 characters.')
    if sum(len(doc['text'].encode('utf-8')) for doc in documents) > 2_000_000:
        raise ValueError('Combined text must not exceed 2 MB.')
    return documents


@app.route('/api/text/<action>', methods=['POST'])
def text_action(action):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Send a JSON object.'), 400
    try:
        if action == 'decompress':
            encoded = data.get('payload')
            if not isinstance(encoded, str):
                raise ValueError('Provide a base64 payload.')
            packed = base64.b64decode(encoded, validate=True)
            if packed[:4] in (b'WGH1', b'WGH2'):
                unpacked = huffman_decompress(packed)
            elif packed[:4] in (b'WGR1', b'WGR2'):
                unpacked = rle_decompress(packed)
            else:
                raise ValueError('Unknown compression format.')
            return jsonify(text=unpacked.decode('utf-8'), original_bytes=len(unpacked))
        docs = _documents(data)
        if action in ('search', 'parallel-search'):
            pattern = data.get('pattern')
            if not isinstance(pattern, str) or not pattern:
                raise ValueError('Enter a non-empty pattern.')
            if len(pattern) > 100_000:
                raise ValueError('Pattern must not exceed 100,000 characters.')
            if action == 'parallel-search':
                return jsonify(parallel_search(docs, pattern))
            return jsonify(results=[search_document((d['name'], d['text'], pattern)) for d in docs])
        if action == 'compress':
            results = []
            for doc in docs:
                packed, stats = compress_text(doc['text'], data.get('method', 'huffman'))
                results.append(dict(stats, name=doc['name'], payload=base64.b64encode(packed).decode('ascii')))
            return jsonify(results=results)
        if action == 'optimize':
            # Reject invalid budgets and priorities before compression work.
            optimize_storage([{'compressed_bytes': 1, 'priority': d.get('priority', 1)} for d in docs], 0)
            optimize_storage([], data.get('capacity'))
            items = []
            for doc in docs:
                choices = [compress_text(doc['text'], method) for method in ('huffman', 'rle')]
                packed, stats = min(choices, key=lambda choice: len(choice[0]))
                items.append(dict(stats, name=doc['name'], priority=doc.get('priority', 1),
                                  payload=base64.b64encode(packed).decode('ascii')))
            result = optimize_storage(items, data.get('capacity'))
            return jsonify(dict(result, items=items))
        return jsonify(error='Unknown text operation.'), 404
    except (ValueError, TypeError, KeyError, binascii.Error) as error:
        return jsonify(error=str(error)), 400


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
    data = _json()
    seed = data.get("seed", False)
    if not isinstance(seed, bool):
        raise ValueError('seed must be true or false.')
    global GRAPH_STATE
    GRAPH_STATE = _fresh_state(seed=seed)
    _persist()
    return get_graph()


@app.route("/api/nodes", methods=["POST"])
def add_node():
    """Body: {"x": float, "y": float, "id": optional str}"""
    data = _json()
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify({"error": "x and y are required"}), 400

    x, y = coordinate(x), coordinate(y)
    node_id = validate_node_id(data['id']) if 'id' in data else _next_node_id()
    if len(GRAPH_STATE['nodes']) >= MAX_NODES:
        raise ValueError('Graph limit: 1,000 nodes.')
    if node_id in GRAPH_STATE["nodes"]:
        return jsonify({"error": f"Node '{node_id}' already exists"}), 400

    GRAPH_STATE["nodes"][node_id] = (float(x), float(y))
    GRAPH_STATE["edges"].setdefault(node_id, [])
    _persist()
    return jsonify({"id": node_id, "x": x, "y": y})


@app.route("/api/nodes/<node_id>", methods=["DELETE"])
def delete_node(node_id):
    node_id = validate_node_id(node_id)
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
    (x, y) map coordinates. A* scales its Euclidean heuristic to remain
    consistent with these rounded distances and with imported weights.
    """
    data = _json()
    a = validate_node_id(data.get('from'))
    b = validate_node_id(data.get('to'))

    if a not in GRAPH_STATE["nodes"] or b not in GRAPH_STATE["nodes"]:
        return jsonify({"error": "Both nodes must exist before connecting them"}), 400
    if a == b:
        return jsonify({"error": "Cannot connect a node to itself"}), 400
    if not any(n == b for n, _ in GRAPH_STATE['edges'].get(a, [])) and sum(map(len, GRAPH_STATE['edges'].values())) // 2 >= MAX_EDGES:
        raise ValueError('Graph limit: 10,000 edges.')

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
    data = _json()
    a = validate_node_id(data.get('from'))
    b = validate_node_id(data.get('to'))

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
    except (ValueError, UnicodeError) as e:
        return jsonify({"error": f"Could not parse graph file: {e}"}), 400

    if not nodes:
        return jsonify({"error": "The uploaded file has no valid NODE lines."}), 400

    global GRAPH_STATE
    GRAPH_STATE = {"nodes": nodes, "edges": edges}
    _persist()
    return get_graph()


@app.route("/api/pathfind", methods=["POST"])
def pathfind():
    data = _json()
    start = validate_node_id(data.get('start'))
    goal = validate_node_id(data.get('goal'))
    cipher_key = validate_key(data.get('cipher_key', 3))

    if not start or not goal:
        return jsonify({"error": "start and goal are required"}), 400

    nodes = GRAPH_STATE["nodes"]
    edges = GRAPH_STATE["edges"]

    if not nodes:
        return jsonify({"error": "Add a node to the map first."}), 400

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

    encrypted_path_str = caesar_encrypt_message("->".join(result["path"]), cipher_key)

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
    app.run(host='127.0.0.1', debug=False)
