# Wayglyph validation and security review

Reviewed and fixed on 15 October 2026. Scope: local Python/Flask application,
graph persistence, A* and Caesar algorithms, text algorithms, templates, API
validation, and declared Python dependencies. The original UI and existing
saved graph were preserved. This is a source review with automated tests,
not a guarantee that no vulnerabilities remain.

## Findings and fixes

| Finding | Impact | Fix |
| --- | --- | --- |
| Unvalidated node IDs interpolated into HTML/SVG | High: a hostile uploaded graph could inject markup or script | Strict node ID validation on uploads and API calls; escape IDs in SVG, options and result tables |
| Cross-site graph upload/reset requests and unrestricted Host header | High for a local app: another website could attempt to modify graph state or use DNS rebinding | Require localhost Host values; reject cross-origin API requests using Origin and Fetch Metadata; require JSON on JSON routes |
| Debugger enabled in `python app.py` | High if accidentally exposed beyond the local machine | Bind to 127.0.0.1 and disable debug by default |
| Flask 3.0.3 advisory CVE-2026-27205 / GHSA-68rp-wp8r-4726 | Conditional session-cache disclosure; this app does not use sessions, so the advisory's exploit conditions were not present | Upgrade to Flask 3.1.3; mark responses no-store |
| Malformed API bodies, non-finite coordinates, negative weights, unknown or duplicate graph records | Errors, invalid graph state, and incorrect algorithm behavior | Validate object types, numeric ranges, IDs, cipher keys, and complete graph uploads before mutation; return JSON client errors |
| Rounded/imported edge weights exceed the raw heuristic's assumptions | Wrong shortest path | Scale the Euclidean heuristic by the minimum edge-weight/distance ratio; compare results with independent Bellman–Ford reference cases |
| Empty persisted graph treated as absent | Cleared map becomes sample graph after restart | Distinguish an empty graph from a missing file |
| Graph writes could truncate data; concurrent handlers mutate shared state | Data loss or inconsistent state | Atomic file replacement, request-level graph lock, and in-memory rollback if persistence fails; no import-time persistence writes |
| Repeated concurrent text operations could spawn unlimited workers | CPU/process exhaustion | At most two simultaneous text requests, at most four workers each, and explicit dataset, pattern, graph, upload and optimization limits |
| Compression accepts undetected file corruption | Incorrect restored text | CRC32-protected v2 downloads, with bounded decompression and checks for malformed Huffman payloads; retain legacy v1 support |
| RLE output or JSON escaping can exceed the original request limit | Valid files fail restoration/upload | Size request envelope for allowed JSON expansion; avoid sending the dataset during decompression; account for compression headers and checksum |
| Non-ASCII letters damaged by Python cipher | Text corruption | Shift ASCII letters only; preserve other characters |
| Numeric node IDs incompatible with browser decryption | Wrong decrypted path after 26 nodes | Shift digits in path messages as the browser does; extend export parser to valid node names |
| Downloads could use another tab's most recent server export; old path results survive edits | Wrong or stale exported result | Download the browser's displayed result snapshot; invalidate results on graph reload and ignore obsolete search responses |
| Message export metadata decrypted as message content | Incorrect restored message | Parse the known export wrapper and decrypt only the payload; validate embedded keys |

Security headers include nosniff, frame blocking, no-referrer, no-store, and
CSP restrictions on framing, base URLs and embedded objects. These controls
follow [Flask's security guidance](https://flask.palletsprojects.com/en/stable/web-security/).
Debug mode is disabled following [Flask's debugger guidance](https://flask.palletsprojects.com/en/stable/debugging/).

## Verification

Install runtime and optional verification dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest -v test_text_algorithms test_security test_frontend
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

All 26 tests passed. The suite covers Unicode/overlapping search, binary round trips, malformed
and corrupted compressed files, decompression bounds, exact knapsack against
exhaustive subsets, real multiprocessing, graph correctness against Bellman–Ford,
hostile uploads, API validation, cross-site/Host guards, persistence failure,
empty maps, integrated routes, unique controls, and JavaScript syntax.

Dependency audit JSON files are in `outputs/dependency-audit-before.json` and
`outputs/dependency-audit-after.json`. The initial audit returned two entries
for the same Flask advisory. After the upgrade it reported no known
vulnerabilities in the eight resolved application packages. This is a
point-in-time advisory check, not a proof of safety. `pip check` found no broken
requirements. Browser interaction/visual checks were unavailable because no
browser was connected; frontend checks use JavaScript parsing and rendered HTML.
The restarted server returned HTTP 200 for the home page and successfully ran
parallel search through the live HTTP endpoint. The saved graph's SHA-256 hash
was unchanged across restart and the live checks.

## Remaining limits

- This is a local single-user demonstration with shared graph state and no
  authentication. It is intentionally restricted to localhost. Internet or
  multi-user hosting requires authentication, per-user storage, production
  serving, and appropriate deployment limits. In-process locks and limits are
  designed for one server process, not multiple WSGI processes.
- Caesar cipher is not secure encryption. Path exports deliberately include
  the key and plaintext. The legacy `/api/download` endpoint still serves the
  latest local server export; browser downloads now use their own result.
- The existing UI loads Tailwind, Anime.js and fonts from third-party CDNs.
  The Python dependency audit does not assess these assets; offline operation
  and stronger supply-chain protection require vendored or integrity-pinned assets.
- CRC32 detects accidental corruption; it is not cryptographic authentication.
  Legacy v1 compressed files have no checksum.
- The text dataset remains in browser memory and resets on refresh. Saving a
  compressed download preserves a document, not the whole workspace.
