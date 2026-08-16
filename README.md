# GraphCrypt — A* + Caesar Cipher

Python (Flask) backend + HTML/JS frontend that:
1. Runs A* on a weighted graph to find the shortest path (start -> goal).
2. Encrypts the edge weights along that path using a Caesar cipher.
3. Exports the encrypted weights + path to `outputs/encrypted_path.txt`.

## Project structure
```
graphcrypt/
├── app.py            # Flask server + API routes
├── astar.py          # A* pathfinding algorithm
├── cipher.py         # Caesar cipher (letters + numeric weights)
├── geometry.py       # Shared Euclidean-distance formula (edge weights + heuristic)
├── graph_data.py      # Sample graph (nodes A-F; weights auto-computed from coordinates)
├── graph_store.py     # Save/load the graph as a .txt file
├── requirements.txt
├── templates/
│   └── index.html    # Frontend UI (connects to the Flask API)
├── data/
│   └── graph.txt      # Auto-saved graph (created after first run)
└── outputs/
    └── encrypted_path.txt   # generated after you run a search
```

## How to run (VS Code)
1. Copy this whole `graphcrypt/` folder into VS Code.
2. Open a terminal in VS Code (``Ctrl+` ``) and create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # macOS/Linux
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   python app.py
   ```
5. Open your browser at **http://127.0.0.1:5000**

## How it works

### Building the graph (click-to-build)
The map is fully editable from the browser — nothing is hardcoded once the app
is running. Use the **Map Mode** buttons above the map:
- **Add Node** — click any empty spot on the map to drop a node there
  (auto-labeled A, B, C...).
- **Connect Nodes** — click one node, then a second node. The edge weight is
  **auto-computed** from the Euclidean (straight-line) distance between the
  two nodes' coordinates — you never type a weight by hand.
- **Delete Node** — click a node to remove it (its edges go with it).
- **Clear Map** — wipes everything so you start from a blank canvas.
- **Load Sample Graph** — reloads the built-in A–F demo graph — its weights
  are also computed from node coordinates (see `graph_data.py`), not typed
  in by hand.

### Why edge weights are auto-computed, not manual
This is what keeps A* correct. A* uses `f(n) = g(n) + h(n)`, where `h(n)` is
a straight-line-distance *estimate* of the remaining cost to the goal. For
A* to guarantee it finds the true shortest path, `h(n)` must never
*overestimate* the real remaining cost (called an **admissible** heuristic).
If edge weights were arbitrary numbers unrelated to on-screen distance, a
"shortcut" edge with an artificially low weight between two far-apart nodes
could break that guarantee — A* could actually skip over the real shortest
path. By making every edge weight *equal to* the straight-line distance
between its two endpoints, this can never happen: a straight line is never
longer than any path between two points (triangle inequality), so `h(n)` is
always admissible, for any graph you build. Both `astar.py`'s heuristic and
`app.py`'s edge-weight calculation call the same `geometry.py` function, so
they can never drift out of sync.

### Saving / loading the graph as .txt
The graph auto-saves to **`data/graph.txt`** every time you add/delete a node
or edge — so it survives restarting `python app.py` (it reloads from that
file on startup instead of resetting to the sample graph).

You also get manual controls in the Map Mode bar:
- **Save Graph (.txt)** — downloads the current graph as a plain text file
  (`graphcrypt_graph.txt`) you can keep as backup or submit with your project.
- **Load Graph (.txt)** — upload a previously saved graph file to replace
  the current map (e.g. to restore an old version, or share a graph with a
  groupmate).

The file format is simple and human-readable:
```
# GraphCrypt Graph File
NODE,A,200.0,150.0
NODE,B,450.0,300.0
EDGE,A,B,4.2
```
This is a **separate file** from `outputs/encrypted_path.txt` — that one is
the Caesar-cipher-encrypted result of a specific A* run (path + weights),
while `data/graph.txt` / the downloaded save file is the graph itself
(unencrypted, so it can be reloaded and re-run).

### Running A* + Caesar cipher
Pick a **Start Node** and **Goal Node**, set the **Cipher Key** (0-25), then click
**Find Path**. The backend:
1. Runs A* on the *plaintext* weights (encryption never touches the actual math —
   that would break the shortest-path computation).
2. Encrypts each weight along the winning path with the Caesar cipher, using the
   key you chose.
3. Writes `outputs/encrypted_path.txt` and returns the results to the page.

Click **Encrypt & Export .txt** to download that file.

## Extending this
- **Persist the graph** across restarts: save `GRAPH_STATE` to a JSON file
  (or SQLite) on every change instead of keeping it only in memory.
- **Different cipher**: only `cipher.py` needs to change (Vigenère, XOR, etc.) —
  `app.py` and `astar.py` stay the same.
- **Drag-to-move nodes**, multiple saved maps, or user accounts are all natural
  next steps if your panel asks for more polish.
