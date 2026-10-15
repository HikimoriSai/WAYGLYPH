# Wayglyph text workspace

## Run and demonstrate

Use the prepared project environment: run `.\.venv\Scripts\python.exe app.py`
and open http://127.0.0.1:5000. On a fresh checkout, create an environment with
`py -m venv .venv` and install dependencies with
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` first.
The original map and cipher interface is the home page. Open **Text Lab** from
the header or **Search & Compression** from the Build Menu to reveal the text
tools inline, styled to match the original interface. Close Text Lab to return
to the map layout. `/pathfinder` remains an alias for the same integrated page.

1. Open **Text Lab**, then load the sample dataset, type text and add it, or upload UTF-8 `.txt` files.
2. Search for `text` with KMP. Results include overlapping matches, zero-based
   Unicode code-point positions, highlighting, and elapsed time.
3. Run parallel file search. Up to four worker processes independently search
   the documents; results retain input order. Worker startup is included in wall time.
4. Compare Huffman and RLE compression. Download binary `.wgc` files and restore
   them using the restore file input. New downloads include a CRC32 checksum to
   detect accidental corruption; original v1 downloads remain readable.
   Original bytes, compressed bytes, ratio,
   savings, and compression time are shown. Header bytes count toward file size.
5. Set priorities and a storage budget. Exact 0/1 knapsack chooses a subset with
   maximum total priority. Each file uses the smaller of Huffman and RLE; the
   selected files can be downloaded. A file may grow under both methods.

Dataset state lives in the browser's memory and resets on reload. Downloads
preserve compressed files. Limits: 30 files, 2 MB combined UTF-8 text,
100,000-byte optimization capacity, integer priorities from 1 to 1000.
The UI limits previews and displayed positions; matching still processes all text.

## Requirement mapping

| Requirement | Implementation |
| --- | --- |
| Text input / dataset | Typed text, UTF-8 uploads, built-in samples |
| Pattern matching | Explicit KMP prefix table and search implementation |
| Compression | Huffman coding and byte-oriented RLE, with decompression and metrics |
| Optimization | Exact dynamic-programming 0/1 storage knapsack |
| Parallel / randomized | ProcessPoolExecutor runs KMP across separate worker processes |
| Performance analysis | Complexity table in UI and below, measured computation times |

## Time and space analysis

Let n be text length (characters for KMP, bytes for compression), m pattern
length, z returned matches, k distinct bytes (at most 256), L maximum Huffman
code length, B encoded bits, c compressed bytes, F files, C byte budget,
N combined text characters, Z combined matches, and p worker processes.

| Algorithm | Time | Auxiliary space, including output |
| --- | --- | --- |
| KMP | O(n + m) | O(m + z) |
| Huffman compression | O(n + k log k + B) | O(kL + B) |
| Huffman decompression | O(k log k + B + n) | O(k + n) |
| RLE compression | O(n) | O(c) |
| RLE decompression | O(c + n) | O(n) |
| Knapsack selection | O(F C) | O(F C) |
| Parallel KMP | Ideal balanced compute O((N + Fm)/p), plus startup and transfer | O(N + pm + Z), plus process overhead |

KMP preprocesses the pattern once per document, then never moves its text cursor
backward. Huffman counts bytes, builds a frequency heap/tree, and packs codes
into bits. Its binary header stores frequencies so decoding rebuilds the tree;
tiny or diverse files can grow due to that header. RLE writes one count byte and
one value byte per run, splitting runs longer than 255. It benefits repeated bytes
and may nearly double non-repeating data. Ratio is compressed/original size;
savings is 100 × (1 − ratio). Empty input has no defined ratio.

Knapsack uses a descending capacity loop to prevent selecting the same file
twice, with one decision array per file for reconstruction. It is
pseudo-polynomial in C; file and capacity limits bound computation and memory.
Compression preparation adds the cost of running both compressors per file;
the reported knapsack time excludes preparation. Parallel search is useful for
larger independent inputs; process startup/serialization can outweigh any
benefit for small inputs. No speedup guarantee is claimed.

The retained A* lab uses heap-based graph search. It scales its Euclidean
heuristic to remain consistent with rounded and imported nonnegative weights.
Its traversal is O((V+E) log(V+E)), with O(V+E) storage including duplicate heap
entries and trace rows. Path reconstruction additionally scans adjacency lists
for path edges. Caesar encryption scans the text in O(n) time with O(n)
output space. These extras do not substitute for the text requirements above.

## Verification

Run `.\.venv\Scripts\python.exe -m unittest -v test_text_algorithms` for overlapping/Unicode searches,
binary compression round trips, malformed files, exact knapsack comparisons
against exhaustive subsets, real parallel search, and Flask route checks.
For the security and frontend checks, install `requirements-dev.txt` and run
`.\.venv\Scripts\python.exe -m unittest -v test_text_algorithms test_security test_frontend`.
