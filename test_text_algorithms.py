import base64
import itertools
import random
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from text_algorithms import (kmp_search, huffman_compress, huffman_decompress,
                             rle_compress, rle_decompress, optimize_storage,
                             parallel_search)


class AlgorithmTests(unittest.TestCase):
    def test_kmp_overlaps_unicode_and_absent(self):
        self.assertEqual(kmp_search('aaaa', 'aa'), [0, 1, 2])
        self.assertEqual(kmp_search('🌏a🌏a', '🌏a'), [0, 2])
        self.assertEqual(kmp_search('abc', 'xyz'), [])
        with self.assertRaises(ValueError):
            kmp_search('abc', '')

    def test_compression_round_trips(self):
        rng = random.Random(42)
        samples = [b'', b'a', b'a' * 1000, bytes(range(256)),
                   'Hello 🌏 café\n'.encode() * 100,
                   bytes(rng.randrange(256) for _ in range(5000))]
        for data in samples:
            for compress, decompress in [(huffman_compress, huffman_decompress),
                                          (rle_compress, rle_decompress)]:
                self.assertEqual(decompress(compress(data)), data)

    def test_corrupt_files(self):
        for unpack in [huffman_decompress, rle_decompress]:
            with self.assertRaises(ValueError):
                unpack(b'bad')
        with self.assertRaises(ValueError):
            huffman_decompress(huffman_compress(b'abcd' * 100)[:-1])

    def test_knapsack_matches_exhaustive_subsets(self):
        rng = random.Random(7)
        for _ in range(30):
            items = [{'compressed_bytes': rng.randint(4, 25),
                      'priority': rng.randint(1, 10)} for _ in range(7)]
            capacity = rng.randint(0, 80)
            result = optimize_storage(items, capacity)
            best = max(sum(items[i]['priority'] for i in range(7) if mask[i])
                       for mask in itertools.product([0, 1], repeat=7)
                       if sum(items[i]['compressed_bytes'] for i in range(7) if mask[i]) <= capacity)
            self.assertEqual(result['total_priority'], best)
            selected = result['selected_indices']
            self.assertEqual(len(selected), len(set(selected)))
            self.assertEqual(sum(items[i]['priority'] for i in selected), best)
            self.assertLessEqual(result['used_bytes'], capacity)

    def test_parallel_search(self):
        docs = [{'name': 'one', 'text': 'banana'}, {'name': 'two', 'text': 'ana'}]
        result = parallel_search(docs, 'ana')
        self.assertEqual(result['workers'], 2)
        self.assertEqual([r['positions'] for r in result['results']], [[1, 3], [0]])


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Importing the original app persists its graph. Suppress that write in tests.
        with patch('graph_store.save_graph_to_disk'):
            from app import app
        cls.client = app.test_client()

    def test_pages_and_text_workflow(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('id="graphSvg"', html)
        self.assertIn('id="cipherLab"', html)
        self.assertIn('id="textLab" hidden', html)
        self.assertIn('data-text-lab-toggle', html)
        self.assertIn('id="compressionResults"', html)
        self.assertIn('id="optimizationResults"', html)
        class IdCollector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
            def handle_starttag(self, tag, attrs):
                self.ids.extend(value for key, value in attrs if key == 'id')
        parser = IdCollector()
        parser.feed(html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)), 'Integrated controls must have unique IDs')
        self.assertEqual(self.client.get('/pathfinder').status_code, 200)
        docs = [{'name': 'demo', 'text': 'banana 🌏' * 50, 'priority': 3}]
        result = self.client.post('/api/text/search', json={'documents': docs, 'pattern': 'ana'})
        self.assertEqual(result.json['results'][0]['count'], 100)
        for method in ['huffman', 'rle']:
            response = self.client.post('/api/text/compress', json={'documents': docs, 'method': method})
            stats = response.json['results'][0]
            self.assertEqual(stats['compressed_bytes'], len(base64.b64decode(stats['payload'])))
            restored = self.client.post('/api/text/decompress', json={'payload': stats['payload']})
            self.assertEqual(restored.json['text'], docs[0]['text'])
        result = self.client.post('/api/text/optimize', json={'documents': docs, 'capacity': 1000})
        self.assertEqual(result.json['selected_indices'], [0])

    def test_bad_requests(self):
        for action, body in [('search', {}), ('compress', {'documents': []}),
                             ('decompress', {'payload': '!'}),
                             ('optimize', {'documents': [{'name': 'x', 'text': 'a', 'priority': -1}], 'capacity': 10})]:
            self.assertEqual(self.client.post('/api/text/' + action, json=body).status_code, 400)


if __name__ == '__main__':
    unittest.main()
