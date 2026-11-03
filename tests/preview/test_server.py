"""Preview server path contract. Execute on Omen, not in cloud development."""
from contextlib import ExitStack
import importlib.util
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

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

    def test_current_city_fallback(self):
        self.assertEqual(server.resolve_request('/assets/previews/city_expanded.png'), ROOT / 'assets/previews/city_expanded.png')

    def test_current_model_thumbnails(self):
        for name in ('ambulance_model.png', 'ghost_model.png'):
            self.assertEqual(server.resolve_request('/assets/previews/' + name), ROOT / 'assets/previews' / name)

    def test_full_retained_notices_are_present_under_their_locked_package_headings(self):
        container = (ROOT / 'web/public/THIRD_PARTY_NOTICES.txt').read_bytes()
        # A signature keeps the plain-text download readable on servers that
        # omit a charset; each original license body below remains untouched.
        self.assertTrue(container.startswith(b'\xef\xbb\xbf'))
        locked = json.loads((ROOT / 'web/package-lock.json').read_bytes())['packages']
        self.assertNotIn(b'\r', container)
        self.assertEqual(container.count(b'Permission is hereby granted'), 5)
        self.assertIn(b'does not specify a license for AFTERLIGHT source code or original assets', container)
        for notice, package in (('react', 'react'), ('react-dom', 'react-dom'),
                                ('scheduler', 'scheduler'), ('three', 'three'), ('vite-runtime', 'vite')):
            with self.subTest(package=package):
                original = (ROOT / f'preview/licenses/{notice}-LICENSE.txt').read_bytes()
                version = locked[f'node_modules/{package}']['version']
                heading = f'===== {notice} ({version}) =====\n\n'.encode()
                self.assertEqual(container.count(heading), 1)
                self.assertIn(heading + original, container, 'The entire retained notice must remain verbatim under its own heading')
                self.assertIn(b'Permission is hereby granted', original)
                self.assertIn(b'THE SOFTWARE IS PROVIDED', original)

    def test_manifest(self):
        declared = json.loads((ROOT / 'preview/manifest.json').read_text(encoding='utf-8'))
        # The compiled source may differ from HEAD after backend-only commits.
        # The server must still verify every declared input's exact raw bytes.
        verified = server.verify()
        self.assertEqual(verified, declared)
        self.assertRegex(verified['source_commit'], r'^[0-9a-f]{40}$')
        for section in ('source_files', 'output_files', 'runtime_assets'):
            self.assertTrue(verified[section], f'Missing {section}')


class PreviewStudyRoutes(unittest.TestCase):
    """Synthetic transport files only; never public scientific evidence."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root_patch = patch.object(server, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.payload = b'{"scope":"synthetic preview route unit test only"}\n'
        self.manifest = self.put('web/public/study/manifest.json', self.payload)
        self.report = self.put('web/public/study/proof/report.json', self.payload)
        self.put('preview/site/index.html', b'Unit HTML must not replace missing study evidence')
        self.put('private.json', b'Private file must never be served')

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_public_manifest_and_nested_proof_resolve_without_copying_them(self):
        self.assertEqual(server.resolve_request('/study/manifest.json'), self.manifest)
        self.assertEqual(server.resolve_request('/study/manifest.json?version=1'), self.manifest)
        self.assertEqual(server.resolve_request('/study/proof/report.json'), self.report)

    def test_missing_study_is_a_404_candidate_not_spa_html(self):
        for path in ('/study/missing.json', '/study/', '/study', '/studyish/manifest.json'):
            with self.subTest(path=path):
                self.assertIsNone(server.resolve_request(path))

    def test_study_prefix_cannot_escape_into_private_or_other_public_files(self):
        for path in ('/study/../../private.json', '/study/%2e%2e/private.json',
                     '/study/proof/%2e%2e/%2e%2e/private.json', '/study/%2f..%2fprivate.json',
                     '/study//private.json', '/study/C:%5cprivate.json',
                     '/study/proof%5c..%5cprivate.json', '/study/%00report.json'):
            with self.subTest(path=path):
                self.assertIsNone(server.resolve_request(path))

    def test_study_symlink_aliases_are_refused_even_inside_the_public_tree(self):
        alias = self.root / 'web/public/study/alias.json'
        try:
            alias.symlink_to(self.manifest)
        except OSError:
            self.skipTest('This Windows account cannot create symlinks')
        self.assertIsNone(server.resolve_request('/study/alias.json'))

    def test_study_windows_junctions_are_refused_before_resolving_a_file(self):
        junction = self.root / 'web/public/study/proof'
        with patch.object(Path, 'is_junction', lambda path: path == junction, create=True):
            self.assertIsNone(server.resolve_request('/study/proof/report.json'))

    def test_http_serves_exact_json_and_head_without_fallback_or_host_escape(self):
        class QuietHandler(server.Handler):
            def log_message(self, *args):
                pass

        with server.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler) as httpd, ExitStack() as cleanup:
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            cleanup.callback(worker.join, 2)
            cleanup.callback(httpd.shutdown)
            connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
            cleanup.callback(connection.close)
            connection.request('GET', '/study/manifest.json', headers={'Accept': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'application/json')
            self.assertEqual(response.getheader('Content-Length'), str(len(self.payload)))
            self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
            self.assertEqual(response.read(), self.payload)
            connection.request('HEAD', '/study/proof/report.json')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Length'), str(len(self.payload)))
            self.assertEqual(response.read(), b'')
            connection.request('GET', '/study/absent.json')
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            self.assertNotIn(b'Unit HTML', response.read())
            connection.request('GET', '/study/manifest.json', headers={'Host': 'untrusted.invalid'})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()


class PreviewNoticeRoute(unittest.TestCase):
    def setUp(self):
        self.notice = (ROOT / 'web/public/THIRD_PARTY_NOTICES.txt').read_bytes()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.public = self.root / 'web/public'
        self.public.mkdir(parents=True)
        self.path = self.public / 'THIRD_PARTY_NOTICES.txt'
        self.path.write_bytes(self.notice)
        (self.public / 'unrelated.txt').write_bytes(b'Must not be exposed by the notice route')
        root_patch = patch.object(server, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def test_only_the_explicit_notice_path_exposes_the_canonical_public_file(self):
        self.assertEqual(server.resolve_request('/THIRD_PARTY_NOTICES.txt'), self.path)
        self.assertEqual(server.resolve_request('/THIRD_PARTY_NOTICES.txt?download=1'), self.path)
        for path in ('/unrelated.txt', '/public/unrelated.txt', '/web/public/unrelated.txt',
                     '/THIRD_PARTY_NOTICES.txt/../unrelated.txt', '/THIRD_PARTY_NOTICES.txt/unrelated.txt',
                     '/third_party_notices.txt', '/preview/licenses/react-LICENSE.txt'):
            with self.subTest(path=path):
                self.assertIsNone(server.resolve_request(path))

    def test_redirected_notice_or_public_folder_is_refused(self):
        for target in (self.root / 'web', self.public, self.path):
            with self.subTest(target=target), patch.object(Path, 'is_symlink', lambda path: path == target):
                self.assertIsNone(server.resolve_request('/THIRD_PARTY_NOTICES.txt'))

    def test_http_notice_response_preserves_every_byte_and_plain_text_mime(self):
        class QuietHandler(server.Handler):
            def log_message(self, *args):
                pass

        with server.ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler) as httpd, ExitStack() as cleanup:
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            cleanup.callback(worker.join, 2)
            cleanup.callback(httpd.shutdown)
            connection = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
            cleanup.callback(connection.close)
            connection.request('GET', '/THIRD_PARTY_NOTICES.txt')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Content-Type'), 'text/plain; charset=utf-8')
            self.assertEqual(response.getheader('Content-Length'), str(len(self.notice)))
            self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
            self.assertEqual(response.read(), self.notice)
            connection.request('GET', '/unrelated.txt')
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
