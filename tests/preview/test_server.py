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
        inter_heading = b'===== Inter variable font (OFL-1.1) =====\n\n'
        self.assertEqual(container.count(inter_heading), 1)
        mit_notices, inter_notice = container.split(inter_heading)
        self.assertEqual(mit_notices.count(b'Permission is hereby granted'), 5)
        inter_license = (ROOT / 'web/public/fonts/Inter-LICENSE.txt').read_bytes()
        self.assertEqual(container.count(inter_license), 1)
        self.assertTrue(inter_notice.startswith(inter_license), 'The full original Inter OFL must remain verbatim under its heading')
        self.assertIn(b'does not specify a license for AFTERLIGHT source code or original assets', container)
        for notice, package in (('react', 'react'), ('react-dom', 'react-dom'),
                                ('scheduler', 'scheduler'), ('three', 'three'), ('vite-runtime', 'vite')):
            with self.subTest(package=package):
                original = (ROOT / f'preview/licenses/{notice}-LICENSE.txt').read_bytes()
                version = locked[f'node_modules/{package}']['version']
                heading = f'===== {notice} ({version}) =====\n\n'.encode()
                self.assertEqual(mit_notices.count(heading), 1)
                self.assertIn(heading + original, mit_notices, 'The entire retained MIT notice must remain verbatim before the Inter heading')
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


class PreviewPublicAssets(unittest.TestCase):
    """Synthetic byte transport, including blocked compiled-output aliases."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        root_patch = patch.object(server, 'ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.assets = {
            '/brand/mark.svg': (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml'),
            '/brand/social-preview.jpg': (b'\xff\xd8\xffSynthetic JPEG transport bytes', 'image/jpeg'),
            '/fonts/InterVariable.woff2': (b'wOF2Synthetic font transport bytes', 'font/woff2'),
            '/fonts/Inter-LICENSE.txt': (b'Synthetic font-license transport bytes\n', 'text/plain; charset=utf-8'),
            '/media/afterlight-desktop-demo.mp4': (b'Synthetic MP4 transport bytes', 'video/mp4'),
        }
        for route, (payload, _) in self.assets.items():
            self.put('web/public' + route, payload)
            self.put('preview/site' + route, b'Compiled alias must not replace the canonical public file')
        for route in ('/brand/private.svg', '/fonts/private.txt', '/media/private.mp4'):
            self.put('web/public' + route, b'Unlisted public file')
            self.put('preview/site' + route, b'Compiled alias must not bypass the allowlist')
        self.put('web/public/private.txt', b'Unrelated public file')
        self.put('private.txt', b'Private repository file')

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_exact_public_files_and_query_parameters_resolve_to_canonical_bytes(self):
        self.assertEqual(set(server.PUBLIC_ASSET_ROUTES), set(self.assets))
        for route in self.assets:
            with self.subTest(route=route):
                expected = self.root / ('web/public' + route)
                self.assertEqual(server.resolve_request(route), expected)
                self.assertEqual(server.resolve_request(route + '?download=1'), expected)

    def test_unlisted_files_directories_and_case_aliases_cannot_use_compiled_fallback(self):
        for route in ('/brand/private.svg', '/fonts/private.txt', '/media/private.mp4',
                      '/brand', '/brand/', '/fonts', '/fonts/', '/media', '/media/',
                      '/BRAND/mark.svg', '/Fonts/InterVariable.woff2', '/media/AFTERLIGHT-desktop-demo.mp4',
                      '/brand/mark.svg/', '/fonts/InterVariable.woff2.backup',
                      '/private.txt', '/web/public/brand/mark.svg'):
            with self.subTest(route=route):
                self.assertIsNone(server.resolve_request(route))

    def test_traversal_backslashes_and_nul_are_refused(self):
        for route in ('/brand/../fonts/InterVariable.woff2', '/brand/%2e%2e/private.txt',
                      '/fonts/%2e%2e/%2e%2e/private.txt', '/media/%2f..%2fprivate.txt',
                      '/brand/..%5cprivate.txt', '/fonts/C:%5cprivate.txt',
                      '/brand/%00mark.svg', '/brand/%252e%252e/private.txt'):
            with self.subTest(route=route):
                self.assertIsNone(server.resolve_request(route))

    def test_every_path_component_refuses_symlinks_and_windows_junctions(self):
        for route in self.assets:
            parts = ('web', 'public', *route.lstrip('/').split('/'))
            for length in range(1, len(parts) + 1):
                blocked = self.root.joinpath(*parts[:length])
                for check in ('is_symlink', 'is_junction'):
                    with self.subTest(route=route, component=length, check=check), patch.object(
                            Path, check, lambda path, target=blocked: path == target, create=True):
                        self.assertIsNone(server.resolve_request(route))

    def test_missing_allowed_file_does_not_use_a_compiled_alias(self):
        for route in self.assets:
            with self.subTest(route=route):
                (self.root / ('web/public' + route)).unlink()
                self.assertIsNone(server.resolve_request(route))

    def test_http_get_and_head_preserve_all_five_payloads_and_explicit_mime_types(self):
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
            for route, (payload, mime) in self.assets.items():
                for method in ('GET', 'HEAD'):
                    with self.subTest(route=route, method=method):
                        connection.request(method, route)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.getheader('Content-Type'), mime)
                        self.assertEqual(response.getheader('Content-Length'), str(len(payload)))
                        self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
                        self.assertEqual(response.read(), payload if method == 'GET' else b'')
            for route in ('/brand/private.svg', '/fonts/private.txt', '/media/private.mp4'):
                connection.request('GET', route)
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                self.assertNotIn(b'Compiled alias', response.read())
            connection.request('GET', '/brand/mark.svg', headers={'Host': 'untrusted.invalid'})
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
