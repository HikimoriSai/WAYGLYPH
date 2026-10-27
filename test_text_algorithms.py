import base64
import itertools
import random
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

from text_algorithms import (kmp_search, huffman_compress, huffman_decompress,
                             rle_compress, rle_decompress, optimize_storage,
                             parallel_search, compress_text, quick_sort_documents)


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

    def test_compact_headers_and_rle_literal_blocks(self):
        text = b'This ordinary text contains distinct letters and spaces. ' * 8
        self.assertLess(len(huffman_compress(text)), len(text))
        varied = bytes(range(256)) * 3
        self.assertLessEqual(len(rle_compress(varied)), len(varied) + 14)
        for length in [1, 2, 3, 127, 128, 129, 130, 131, 255, 256]:
            for sample in [b'a' * length, bytes(range(128)) + b'b' * length + bytes(range(128))]:
                self.assertEqual(rle_decompress(rle_compress(sample)), sample)

    def test_auto_never_enlarges_and_preserves_original_bytes(self):
        for text in ['', 'a', 'abc', 'A' * 1000, 'Ordinary text with spaces. ' * 30, '🌏 café']:
            packed, stats = compress_text(text, 'auto')
            original = text.encode('utf-8')
            self.assertLessEqual(len(packed), len(original))
            unpack = {'original': lambda value: value, 'huffman': huffman_decompress, 'rle': rle_decompress}[stats['method']]
            self.assertEqual(unpack(packed), original)
            self.assertEqual(stats['compressed_bytes'], len(packed))
        self.assertEqual(compress_text('abc', 'auto')[1]['method'], 'original')

    def test_quick_sort_matches_size_order_and_keeps_ties(self):
        rng = random.Random(42)
        for _ in range(30):
            docs = [{'name': str(i), 'text': '🌏' * rng.randrange(20)} for i in range(30)]
            result = quick_sort_documents(docs)
            self.assertEqual([r['index'] for r in result['results']],
                             sorted(range(len(docs)), key=lambda i: len(docs[i]['text'].encode('utf-8'))))
        self.assertEqual(quick_sort_documents([])['results'], [])

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

    def test_concurrent_algorithms_downloads_sort_and_knapsack(self):
        docs = [{'name': 'tiny.txt', 'text': 'abc', 'priority': 10},
                {'name': 'runs.txt', 'text': 'a' * 1000, 'priority': 3},
                {'name': 'text.txt', 'text': 'Ordinary text with spaces. ' * 30, 'priority': 2}]
        response = self.client.post('/api/text/run-all', json={'documents': docs, 'capacity': 3})
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json
        self.assertEqual(result['workers'], 4)
        self.assertEqual(result['optimization']['selected_indices'], [0])
        self.assertEqual(result['optimization']['used_bytes'], 3)
        self.assertEqual(result['optimization']['items'][0]['method'], 'original')
        self.assertEqual(base64.b64decode(result['optimization']['items'][0]['payload']), b'abc')
        self.assertEqual([row['index'] for row in result['quicksort']['results']], [0, 2, 1])
        for method in ['huffman', 'rle']:
            for doc, item in zip(docs, result[method]['results']):
                self.assertEqual(len(base64.b64decode(item['payload'])), item['compressed_bytes'])
                restored = self.client.post('/api/text/decompress', json={'payload': item['payload']})
                self.assertEqual(restored.json['text'], doc['text'])
        sorted_response = self.client.post('/api/text/sort', json={'documents': docs})
        self.assertEqual([row['index'] for row in sorted_response.json['results']], [0, 2, 1])
        smallest = self.client.post('/api/text/compress', json={'documents': docs})
        self.assertEqual(smallest.json['results'][0]['method'], 'original')
        for body in [{'documents': docs, 'capacity': -1}, {'documents': docs, 'capacity': True},
                     {'documents': [dict(docs[0], priority=-1)], 'capacity': 3}]:
            with patch('app.run_algorithms') as run_all:
                self.assertEqual(self.client.post('/api/text/run-all', json=body).status_code, 400)
                run_all.assert_not_called()


if __name__ == '__main__':
    unittest.main()
