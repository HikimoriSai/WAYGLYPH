from pathlib import Path
import re
import unittest

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:
    Parser = None


class FrontendTests(unittest.TestCase):
    @unittest.skipIf(Parser is None, 'Install requirements-dev.txt for JavaScript syntax checks')
    def test_javascript_syntax(self):
        parser = Parser(Language(tree_sitter_javascript.language()))
        for path in Path('templates').glob('*.html'):
            source = path.read_text(encoding='utf-8')
            for i, script in enumerate(re.findall(r'<script[^>]*>(.*?)</script>', source, re.S)):
                with self.subTest(file=str(path), script=i):
                    tree = parser.parse(script.encode('utf-8'))
                    self.assertFalse(tree.root_node.has_error, str(tree.root_node))

    def test_literal_control_references_exist(self):
        import app
        html = app.app.test_client().get('/').get_data(as_text=True)
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        references = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", html))
        self.assertFalse(references - ids, references - ids)


if __name__ == '__main__':
    unittest.main()
