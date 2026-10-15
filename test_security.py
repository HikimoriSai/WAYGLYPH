import base64
import copy
import io
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

from astar import a_star_search
from cipher import caesar_encrypt_letters, caesar_decrypt_letters, caesar_encrypt_message
from graph_store import parse_graph, save_graph_to_disk, load_graph_from_disk
from text_algorithms import huffman_compress, huffman_decompress, rle_compress, rle_decompress


class GraphAlgorithmTests(unittest.TestCase):
    def test_imported_weights_find_true_shortest_path(self):
        nodes = {'A': (0, 0), 'B': (1000, 0), 'C': (0, 1)}
        edges = {'A': [('C', 10), ('B', 1)], 'B': [('A', 1), ('C', 1)],
                 'C': [('A', 10), ('B', 1)]}
        result = a_star_search(nodes, edges, 'A', 'C')
        self.assertEqual(result['path'], ['A', 'B', 'C'])
        self.assertEqual(result['cost'], 2)

    def test_astar_matches_bellman_ford(self):
        rng = random.Random(83)
        for _ in range(40):
            nodes = {str(i): (rng.random() * 1000, rng.random() * 1000) for i in range(8)}
            edges = {node: [] for node in nodes}
            for a in range(8):
                for b in range(a + 1, 8):
                    if rng.random() < .4:
                        w = rng.randint(0, 50)
                        edges[str(a)].append((str(b), w))
                        edges[str(b)].append((str(a), w))
            distances = {n: math.inf for n in nodes}
            distances['0'] = 0
            for _ in range(7):
                for a, neighbors in edges.items():
                    for b, w in neighbors:
                        distances[b] = min(distances[b], distances[a] + w)
            result = a_star_search(nodes, edges, '0', '7')
            self.assertEqual(result['cost'], None if math.isinf(distances['7']) else distances['7'])

    def test_graph_parser_rejects_hostile_or_invalid_input(self):
        invalid = ['NODE,<img src=x onerror=alert(1)>,0,0', 'NODE,A,nan,0',
                   'NODE,A,inf,0', 'NODE,A,0,0\nNODE,A,1,1',
                   'NODE,A,0,0\nEDGE,A,B,1', 'bad line',
                   'NODE,A,0,0\nNODE,B,1,1\nEDGE,A,B,-1',
                   'NODE,A,0,0\nNODE,B,1,1\nEDGE,A,B,1\nEDGE,B,A,2']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_graph(text)

    def test_parser_accepts_edges_before_nodes(self):
        nodes, edges = parse_graph('EDGE,A,B,2\nNODE,A,0,0\nNODE,B,1,1')
        self.assertEqual(edges['A'], [('B', 2)])

    def test_atomic_graph_save_preserves_previous_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            file = str(Path(directory) / 'graph.txt')
            save_graph_to_disk({'A': (1, 2)}, {'A': []}, file)
            original = Path(file).read_bytes()
            with patch('graph_store.os.replace', side_effect=OSError('Simulated failure')):
                with self.assertRaises(OSError):
                    save_graph_to_disk({}, {}, file)
            self.assertEqual(Path(file).read_bytes(), original)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            self.assertIn('A', load_graph_from_disk(file)[0])

    def test_unicode_cipher_round_trip(self):
        text = 'Café 🌏 Ελληνικά 中文'
        self.assertEqual(caesar_decrypt_letters(caesar_encrypt_letters(text, 7), 7), text)
        self.assertEqual(caesar_encrypt_message('A1->AB9', 3), 'D4->DE2')


class CompressionSecurityTests(unittest.TestCase):
    def test_checksum_rejects_mutated_data(self):
        for compress, decompress in [(huffman_compress, huffman_decompress), (rle_compress, rle_decompress)]:
            data = bytearray(compress(b'banana' * 30))
            data[-5] ^= 1
            with self.assertRaises(ValueError):
                decompress(bytes(data))

    def test_legacy_files_still_restore(self):
        self.assertEqual(rle_decompress(b'WGR1\x03a'), b'aaa')
        self.assertEqual(huffman_decompress(b'WGH1\x00\x01' + struct.pack('>BQ', 97, 3) + b'\x00'), b'aaa')

    def test_decompression_bombs_rejected(self):
        with self.assertRaises(ValueError):
            huffman_decompress(b'WGH1\x00\x01' + struct.pack('>BQ', 97, 2_000_001))
        with self.assertRaises(ValueError):
            rle_decompress(b'WGR1' + b'\xffa' * 7844)


class ApiSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.module = app
        cls.client = app.app.test_client()

    def setUp(self):
        self.persist = patch.object(self.module, 'save_graph_to_disk')
        self.persist.start()
        self.original = self.module.GRAPH_STATE
        self.module.GRAPH_STATE = {'nodes': {'A': (0, 0), 'B': (1, 1)},
                                   'edges': {'A': [('B', 1.4)], 'B': [('A', 1.4)]}}

    def tearDown(self):
        self.module.GRAPH_STATE = self.original
        self.persist.stop()

    def test_bad_graph_requests_are_client_errors_without_mutation(self):
        original = copy.deepcopy(self.module.GRAPH_STATE)
        cases = [('/api/nodes', []), ('/api/nodes', {'x': 'bad', 'y': 1}),
                 ('/api/nodes', {'x': float('nan'), 'y': 1}),
                 ('/api/nodes', {'x': 1, 'y': 1, 'id': '<svg onload=alert(1)>'}),
                 ('/api/graph/reset', {'seed': 'false'}),
                 ('/api/edges', {'from': [], 'to': 'B'}),
                 ('/api/pathfind', {'start': 'A', 'goal': 'B', 'cipher_key': -1}),
                 ('/api/pathfind', {'start': 'A', 'goal': 'B', 'cipher_key': 1.2})]
        for path, body in cases:
            with self.subTest(path=path, body=body):
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.module.GRAPH_STATE, original)

    def test_cross_site_json_and_uploads_rejected(self):
        for path in ['/api/graph/load', '/api/graph/reset', '/api/text/compress']:
            response = self.client.post(path, json={}, headers={'Origin': 'https://attacker.example'})
            self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/graph/load', data={'file': (io.BytesIO(b'NODE,Z,1,1'), 'g.txt')},
                                    headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(response.status_code, 403)

    def test_host_guard_and_security_headers(self):
        self.assertEqual(self.client.get('/', headers={'Host': 'attacker.example'}).status_code, 403)
        response = self.client.get('/')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')

    def test_empty_map_persistence_and_valid_mutations(self):
        with patch.object(self.module, 'load_graph_from_disk', return_value=({}, {})):
            self.assertEqual(self.module._load_initial_state(), {'nodes': {}, 'edges': {}})
        self.assertEqual(self.client.post('/api/nodes', json={'id': 'C', 'x': 3, 'y': 4}).status_code, 200)
        self.assertEqual(self.client.post('/api/edges', json={'from': 'A', 'to': 'C'}).status_code, 200)
        self.assertEqual(self.client.delete('/api/nodes/C').status_code, 200)

    def test_single_node_path_and_export(self):
        self.module.GRAPH_STATE = {'nodes': {'A': (0, 0)}, 'edges': {'A': []}}
        with tempfile.TemporaryDirectory() as directory, patch.object(self.module, 'OUTPUT_DIR', directory):
            result = self.client.post('/api/pathfind', json={'start': 'A', 'goal': 'A', 'cipher_key': 3})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['path'], ['A'])
            self.assertEqual(result.json['cost'], 0)

    def test_invalid_upload_is_not_persisted(self):
        original = copy.deepcopy(self.module.GRAPH_STATE)
        response = self.client.post('/api/graph/load', data={'file': (io.BytesIO(b'NODE,A,nan,0'), 'g.txt')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.module.GRAPH_STATE, original)

    def test_persistence_failure_rolls_back_mutation(self):
        original = copy.deepcopy(self.module.GRAPH_STATE)
        with patch.object(self.module, 'save_graph_to_disk', side_effect=OSError('disk full')):
            with self.assertLogs(self.module.app.logger, level='ERROR'):
                response = self.client.post('/api/nodes', json={'id': 'C', 'x': 3, 'y': 4})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.module.GRAPH_STATE, original)

    def test_text_worker_capacity_and_limits(self):
        with patch.object(self.module.TEXT_SLOTS, 'acquire', return_value=False):
            self.assertEqual(self.client.post('/api/text/search', json={}).status_code, 429)
        docs = [{'name': 'a', 'text': 'abc'}]
        with patch.object(self.module, 'compress_text') as compress:
            response = self.client.post('/api/text/optimize', json={'documents': docs, 'capacity': -1})
            self.assertEqual(response.status_code, 400)
            compress.assert_not_called()
        self.assertEqual(self.client.post('/api/text/search', json={'documents': docs, 'pattern': 'x'*100001}).status_code, 400)
        with patch.dict(self.module.app.config, MAX_CONTENT_LENGTH=10):
            response = self.client.post('/api/nodes', json={'x': 1, 'y': 2})
            self.assertEqual(response.status_code, 413)
            self.assertIsNotNone(response.json['error'])


if __name__ == '__main__':
    unittest.main()
