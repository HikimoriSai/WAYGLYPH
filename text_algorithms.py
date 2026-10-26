"""Text algorithms with portable binary compression formats (including headers)."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import heapq
import struct
import time
import zlib


def _seal(data):
    """Add a version tag and CRC32 checksum to compressed bytes returned for download."""
    versioned = data[:3] + b'2' + data[4:]
    return versioned + struct.pack('>I', zlib.crc32(versioned))


def _unseal(data, magic):
    """Check compressed bytes and return the payload format expected by the decoders."""
    if data[:4] == magic[:3] + b'2':
        if len(data) < 8 or zlib.crc32(data[:-4]) != struct.unpack('>I', data[-4:])[0]:
            raise ValueError('Compressed file checksum failed. The file is damaged.')
        return magic + data[4:-4]
    return data  # Backward compatibility with original v1 downloads.


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
    header += b''.join(struct.pack('>BQ', symbol, count)
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
    return _seal(header + payload)


def huffman_decompress(data):
    """Validate a Huffman file and return its original bytes for the text API."""
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
    """Encode repeated bytes as count-value pairs with a header and checksum."""
    result = bytearray(b'WGR1')
    i = 0
    while i < len(data):
        count = 1
        while i + count < len(data) and data[i + count] == data[i] and count < 255:
            count += 1
        result.extend((count, data[i]))
        i += count
    return _seal(bytes(result))


def rle_decompress(data):
    """Validate an RLE file and return its original bytes for the text API."""
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
    if method not in ('huffman', 'rle'):
        raise ValueError('Choose huffman or rle.')
    start = time.perf_counter()
    packed = huffman_compress(data) if method == 'huffman' else rle_compress(data)
    return packed, {
        'method': method, 'original_bytes': len(data), 'compressed_bytes': len(packed),
        'ratio': round(len(packed) / len(data), 4) if data else None,
        'savings_percent': round(100 * (1 - len(packed) / len(data)), 2) if data else None,
        'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
    }


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
