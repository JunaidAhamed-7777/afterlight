"""Preview server path contract. Execute on Omen, not in cloud development."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview_server', ROOT / 'scripts/serve_preview.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class PreviewPaths(unittest.TestCase):
    def test_static_entries(self):
        self.assertEqual(server.resolve_request('/'), ROOT / 'preview/site/index.html')
        self.assertEqual(server.resolve_request('/local.html'), ROOT / 'preview/site/local.html')

    def test_private_and_traversal_paths(self):
        for path in ('/../README.md', '/%2e%2e/README.md', '/.git/config', '/assets/exports/../../README.md', '/C:%5cprivate', '/%00'):
            with self.subTest(path=path):
                self.assertIsNone(server.resolve_request(path))

    def test_original_map(self):
        self.assertEqual(server.resolve_request('/assets/map/city_manifest.json?v=1'), ROOT / 'assets/map/city_manifest.json')

    def test_manifest(self):
        declared = json.loads((ROOT / 'preview/manifest.json').read_text(encoding='utf-8'))
        # The compiled source may differ from HEAD after backend-only commits.
        # The server must still verify every declared input's exact raw bytes.
        verified = server.verify()
        self.assertEqual(verified, declared)
        self.assertRegex(verified['source_commit'], r'^[0-9a-f]{40}$')
        for section in ('source_files', 'output_files', 'runtime_assets'):
            self.assertTrue(verified[section], f'Missing {section}')
