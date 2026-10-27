"""Text algorithms with portable binary compression formats (including headers)."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import base64
import heapq
import random
import struct
import time
import zlib


def _seal(data, version=b'2'):
    """Add a version tag and CRC32 checksum to compressed bytes returned for download."""
    versioned = data[:3] + version + data[4:]
    return versioned + struct.pack('>I', zlib.crc32(versioned))


def _unseal(data, magic):
    """Check compressed bytes and return the payload format expected by the decoders."""
    if data[:4] == magic[:3] + b'2':
        if len(data) < 8 or zlib.crc32(data[:-4]) != struct.unpack('>I', data[-4:])[0]:
            raise ValueError('Compressed file checksum failed. The file is damaged.')
        return magic + data[4:-4]
    return data  # Backward compatibility with original v1 downloads.


def _open_v3(data):
    if len(data) < 8 or zlib.crc32(data[:-4]) != struct.unpack('>I', data[-4:])[0]:
        raise ValueError('Compressed file checksum failed. The file is damaged.')
    return data[:-4]


def _varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _read_varint(data, offset):
    value = 0
    for shift in range(0, 21, 7):
        if offset >= len(data):
            break
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('Invalid Huffman frequency.')


def kmp_search(text, pattern):
    """Return all matching character positions for document search results."""
    if not pattern:
        raise ValueError("Enter a non-empty search pattern.")
    lps = [0] * len(pattern)
    j = 0
    for i in range(1, len(pattern)):
        while j and pattern[i] != pattern[j]:
            j = lps[j - 1]
        if pattern[i] == pattern[j]:
            j += 1
        lps[i] = j
    matches, j = [], 0
    for i, char in enumerate(text):
        while j and char != pattern[j]:
            j = lps[j - 1]
        if char == pattern[j]:
            j += 1
        if j == len(pattern):
            matches.append(i - len(pattern) + 1)
            j = lps[j - 1]
    return matches


def _tree(frequencies):
    """Build a byte-frequency tree used by Huffman encoding and decoding."""
    heap = [(count, symbol, symbol) for symbol, count in frequencies.items()]
    heapq.heapify(heap)
    serial = 256
    while len(heap) > 1:
        count_a, _, a = heapq.heappop(heap)
        count_b, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (count_a + count_b, serial, (a, b)))
        serial += 1
    return heap[0][2] if heap else None


def huffman_compress(data):
    """Encode input bytes as a Huffman file with a header and checksum."""
    frequencies = Counter(data)
    root = _tree(frequencies)
    codes = {}

    def visit(node, prefix):
        """Fill the Huffman code table by walking the tree with binary prefixes."""
        if isinstance(node, int):
            codes[node] = prefix or '0'
        elif node is not None:
            visit(node[0], prefix + '0')
            visit(node[1], prefix + '1')

    visit(root, '')
    header = b'WGH1' + struct.pack('>H', len(frequencies))
    header += b''.join(bytes([symbol]) + _varint(count)
                       for symbol, count in sorted(frequencies.items()))
    payload = bytearray()
    accumulator = bits = 0
    for symbol in data:
        for bit in codes[symbol]:
            accumulator = (accumulator << 1) | int(bit)
            bits += 1
            if bits == 8:
                payload.append(accumulator)
                accumulator = bits = 0
    if bits:
        payload.append(accumulator << (8 - bits))
    return _seal(header + payload, b'3')


def huffman_decompress(data):
    """Validate a Huffman file and return its original bytes for the text API."""
    if data[:4] == b'WGH3':
        data = _open_v3(data)
        if len(data) < 6:
            raise ValueError('Invalid Huffman header.')
        size = struct.unpack('>H', data[4:6])[0]
        if size > 256:
            raise ValueError('Invalid Huffman header.')
        offset, entries = 6, bytearray()
        for _ in range(size):
            if offset >= len(data):
                raise ValueError('Truncated Huffman header.')
            symbol = data[offset]
            count, offset = _read_varint(data, offset + 1)
            entries.extend(struct.pack('>BQ', symbol, count))
        data = b'WGH1' + data[4:6] + entries + data[offset:]
    data = _unseal(data, b'WGH1')
    if len(data) < 6 or data[:4] != b'WGH1':
        raise ValueError('Invalid Huffman file.')
    size = struct.unpack('>H', data[4:6])[0]
    if size > 256 or len(data) < 6 + size * 9:
        raise ValueError('Invalid Huffman header.')
    frequencies = {}
    for offset in range(6, 6 + size * 9, 9):
        symbol, count = struct.unpack('>BQ', data[offset:offset + 9])
        if not count or symbol in frequencies:
            raise ValueError('Invalid Huffman frequencies.')
        frequencies[symbol] = count
    total = sum(frequencies.values())
    if total > 2_000_000:
        raise ValueError('Decompressed text exceeds 2 MB.')
    root = _tree(frequencies)
    if root is None:
        if len(data) != 6:
            raise ValueError('Unexpected Huffman payload.')
        return b''
    if isinstance(root, int):
        if len(data) - (6 + size * 9) != (total + 7) // 8 or any(data[6 + size * 9:]):
            raise ValueError('Truncated Huffman data.')
        return bytes([root]) * total
    result, node = bytearray(), root
    payload = data[6 + size * 9:]
    for byte_index, byte in enumerate(payload):
        for shift in range(7, -1, -1):
            node = node[(byte >> shift) & 1]
            if isinstance(node, int):
                result.append(node)
                node = root
                if len(result) == total:
                    if byte_index != len(payload) - 1 or byte & ((1 << shift) - 1) or Counter(result) != frequencies:
                        raise ValueError('Invalid Huffman payload or padding.')
                    return bytes(result)
    raise ValueError('Truncated Huffman data.')


def rle_compress(data):
    """Pack repeated runs and literal blocks so ordinary text is not doubled."""
    result = bytearray(b'WGR1')
    i = 0
    literals = bytearray()

    def flush():
        if literals:
            result.append(len(literals) - 1)
            result.extend(literals)
            literals.clear()

    while i < len(data):
        count = 1
        while i + count < len(data) and data[i + count] == data[i] and count < 130:
            count += 1
        if count >= 3:
            flush()
            result.extend((128 + count - 3, data[i]))
        else:
            for byte in data[i:i + count]:
                literals.append(byte)
                if len(literals) == 128:
                    flush()
        i += count
    flush()
    return _seal(bytes(result), b'3')


def rle_decompress(data):
    """Validate an RLE file and return its original bytes for the text API."""
    if data[:4] == b'WGR3':
        data = _open_v3(data)
        result, offset = bytearray(), 4
        while offset < len(data):
            control = data[offset]
            offset += 1
            count = control + 1 if control < 128 else control - 128 + 3
            width = count if control < 128 else 1
            if offset + width > len(data) or len(result) + count > 2_000_000:
                raise ValueError('Invalid or oversized RLE data.')
            result.extend(data[offset:offset + width] if control < 128 else data[offset:offset + 1] * count)
            offset += width
        return bytes(result)
    data = _unseal(data, b'WGR1')
    if data[:4] != b'WGR1' or (len(data) - 4) % 2:
        raise ValueError('Invalid RLE file.')
    result = bytearray()
    for i in range(4, len(data), 2):
        if data[i] == 0 or len(result) + data[i] > 2_000_000:
            raise ValueError('Invalid or oversized RLE data.')
        result.extend(bytes([data[i + 1]]) * data[i])
    return bytes(result)


def compress_text(text, method):
    """Encode UTF-8 text and return compressed bytes plus statistics to the text API."""
    data = text.encode('utf-8')
    if method not in ('huffman', 'rle', 'auto'):
        raise ValueError('Choose auto, huffman or rle.')
    start = time.perf_counter()
    if method == 'auto':
        # Raw text wins ties: never enlarge a download just to wrap it in a format.
        method, packed = min([('original', data), ('huffman', huffman_compress(data)),
                              ('rle', rle_compress(data))], key=lambda choice: len(choice[1]))
    else:
        packed = huffman_compress(data) if method == 'huffman' else rle_compress(data)
    return packed, {
        'method': method, 'original_bytes': len(data), 'compressed_bytes': len(packed),
        'ratio': round(len(packed) / len(data), 4) if data else None,
        'savings_percent': round(100 * (1 - len(packed) / len(data)), 2) if data else None,
        'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
    }


def compression_batch(documents, method):
    results = []
    for doc in documents:
        packed, stats = compress_text(doc['text'], method)
        results.append(dict(stats, name=doc['name'], payload=base64.b64encode(packed).decode('ascii')))
    return {'results': results}


def optimize_documents(documents, capacity):
    items = [dict(item, priority=doc.get('priority', 1)) for item, doc in
             zip(compression_batch(documents, 'auto')['results'], documents)]
    return dict(optimize_storage(items, capacity), items=items)


def quick_sort_documents(documents):
    """Randomized three-way Quick Sort by UTF-8 size, preserving input order on ties."""
    start = time.perf_counter()
    items = [{'name': doc['name'], 'original_bytes': len(doc['text'].encode('utf-8')),
              'index': i} for i, doc in enumerate(documents)]
    rng = random.Random()

    def sort(rows):
        if len(rows) < 2:
            return rows
        pivot = rng.choice(rows)['original_bytes']
        smaller, equal, larger = [], [], []
        for row in rows:
            (smaller if row['original_bytes'] < pivot else larger if row['original_bytes'] > pivot else equal).append(row)
        return sort(smaller) + equal + sort(larger)

    results = sort(items)
    return {'results': results, 'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)}


def run_algorithms(documents, capacity):
    """Run the four independent analysis jobs in separate Python processes."""
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as executor:
        jobs = {
            'huffman': executor.submit(compression_batch, documents, 'huffman'),
            'rle': executor.submit(compression_batch, documents, 'rle'),
            'quicksort': executor.submit(quick_sort_documents, documents),
            # Knapsack prepares its own best-size candidates, so it can run independently.
            'optimization': executor.submit(optimize_documents, documents, capacity),
        }
        results = {name: job.result() for name, job in jobs.items()}
    return dict(results, workers=4, elapsed_ms=round((time.perf_counter() - start) * 1000, 3))


def search_document(job):
    """Search one (name, text, pattern) job and return positions, count, and timing."""
    name, text, pattern = job
    start = time.perf_counter()
    positions = kmp_search(text, pattern)
    return {'name': name, 'positions': positions, 'count': len(positions),
            'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)}


def parallel_search(documents, pattern):
    """Send document jobs to up to four processes and return combined search results."""
    if not pattern:
        raise ValueError('Enter a non-empty search pattern.')
    start = time.perf_counter()
    jobs = [(doc['name'], doc['text'], pattern) for doc in documents]
    workers = min(4, len(jobs))
    if not jobs:
        raise ValueError('Provide at least one document.')
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(search_document, jobs))
    return {'results': results, 'workers': workers,
            'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)}


def optimize_storage(items, capacity):
    """Use 0/1 knapsack to return file indices with maximum priority within a byte budget."""
    if not isinstance(capacity, int) or isinstance(capacity, bool) or not 0 <= capacity <= 100_000:
        raise ValueError('Storage budget must be an integer from 0 to 100,000 bytes.')
    if len(items) > 30:
        raise ValueError('Use at most 30 files.')
    for item in items:
        if not isinstance(item['priority'], int) or isinstance(item['priority'], bool) or not 1 <= item['priority'] <= 1000:
            raise ValueError('Each priority must be an integer from 1 to 1000.')
    start = time.perf_counter()
    dp = [0] * (capacity + 1)
    decisions = []
    for item in items:
        take = bytearray(capacity + 1)
        cost, value = item['compressed_bytes'], item['priority']
        for budget in range(capacity, cost - 1, -1):
            candidate = dp[budget - cost] + value
            if candidate > dp[budget]:
                dp[budget] = candidate
                take[budget] = 1
        decisions.append(take)
    selected, budget = [], capacity
    for i in range(len(items) - 1, -1, -1):
        if decisions[i][budget]:
            selected.append(i)
            budget -= items[i]['compressed_bytes']
    return {'selected_indices': sorted(selected), 'total_priority': dp[capacity],
            'used_bytes': capacity - budget, 'capacity_bytes': capacity,
            'elapsed_ms': round((time.perf_counter() - start) * 1000, 3)}
