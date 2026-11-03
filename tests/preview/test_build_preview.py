"""Pure/mocked preview assembly regressions. Execute on Omen only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('build_preview', ROOT / 'scripts/build_preview.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PreviewAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.put('preview/manifest.json', b'{"output_files": {}}')

    def put(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_source_discovery_includes_new_files_and_configs(self):
        for name in ('web/src/new/Scene.tsx', 'web/src/new.wgsl', 'web/scripts/new.mjs',
                     'web/vite.config.ts', 'web/.env.local', 'web/public/favicon.svg'):
            self.assertTrue(builder.is_source(name), name)
        for name in ('web/node_modules/x.js', 'web/dist/index.html', 'web/tests/a.ts',
                     'web/public/assets/exports/city.glb', 'web/public/replays/catalog.json'):
            self.assertFalse(builder.is_source(name), name)

    def test_paths_refuse_traversal_and_redirect(self):
        for name in ('../secret', '/tmp/secret', 'web/../secret', 'C:/secret', 'web\\x'):
            with self.assertRaises(ValueError):
                builder.safe(self.root, name)
        link = self.root / 'link'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            return  # Windows without symlink privilege: other guards still exercised.
        with self.assertRaises(ValueError):
            builder.safe(self.root, 'link/preview/manifest.json')

    def test_plan_never_builds_or_publishes(self):
        with patch.object(builder, 'snapshot', return_value={'source_files': {}, 'runtime_assets': {}}), \
             patch.object(builder, 'environment', return_value=({'node': '24'}, {})), \
             patch.object(builder.subprocess, 'run') as run, patch.object(builder, 'publish') as publish:
            result = builder.build(self.root, 'a' * 40)
        self.assertEqual(result['action'], 'plan')
        run.assert_not_called()
        publish.assert_not_called()

    def test_build_failure_preserves_existing_preview(self):
        before = (self.root / 'preview/manifest.json').read_bytes()
        with patch.object(builder, 'snapshot', return_value={}), \
             patch.object(builder, 'environment', return_value=({}, {})), \
             patch.object(builder.shutil, 'which', return_value='npm'), \
             patch.object(builder.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'npm')), \
             patch.object(builder, 'publish') as publish:
            with self.assertRaises(subprocess.CalledProcessError):
                builder.build(self.root, 'a' * 40, execute=True)
        publish.assert_not_called()
        self.assertEqual((self.root / 'preview/manifest.json').read_bytes(), before)

    def test_source_drift_after_build_refuses_publication(self):
        with patch.object(builder, 'snapshot', side_effect=[{'source_files': {}}, {'source_files': {'new': 'hash'}}]), \
             patch.object(builder, 'environment', return_value=({}, {})), \
             patch.object(builder.shutil, 'which', return_value='npm'), \
             patch.object(builder.subprocess, 'run'), patch.object(builder, 'publish') as publish:
            with self.assertRaisesRegex(ValueError, 'changed during'):
                builder.build(self.root, 'a' * 40, execute=True)
        publish.assert_not_called()

    def test_collect_only_direct_chunks_and_two_entries(self):
        for folder in ('static', 'local'):
            self.put(f'{folder}/index.html', folder.encode())
            self.put(f'{folder}/assets/shared.js', b'shared')
            self.put(f'{folder}/assets/style.css', b'css')
            self.put(f'{folder}/assets/exports/huge.glb', b'not copied')
        out = builder.collect_outputs(self.root / 'static', self.root / 'local', b'icon')
        self.assertEqual(out['preview/site/local.html'], b'local')
        self.assertEqual(len(out), 5)
        self.put('local/assets/shared.js', b'different')
        with self.assertRaisesRegex(ValueError, 'collision'):
            builder.collect_outputs(self.root / 'static', self.root / 'local', b'icon')

    def test_missing_javascript_refused(self):
        self.put('static/index.html', b'x')
        self.put('static/assets/style.css', b'x')
        with self.assertRaisesRegex(ValueError, 'no JavaScript'):
            builder.collect_outputs(self.root / 'static', self.root / 'local', b'icon')

    def test_publish_preserves_unrelated_and_obsolete_files(self):
        self.put('preview/site/notes.txt', b'user note')
        self.put('preview/site/assets/old.js', b'old')
        old = (self.root / 'preview/manifest.json').read_bytes()
        builder.publish(self.root, {'preview/site/index.html': b'new'}, {'output_files': {}}, old)
        self.assertEqual((self.root / 'preview/site/notes.txt').read_bytes(), b'user note')
        self.assertEqual((self.root / 'preview/site/assets/old.js').read_bytes(), b'old')

    def test_unowned_or_edited_existing_output_refused(self):
        self.put('preview/site/index.html', b'user edit')
        old = (self.root / 'preview/manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unowned or edited'):
            builder.publish(self.root, {'preview/site/index.html': b'new'}, {}, old)
        self.assertEqual((self.root / 'preview/site/index.html').read_bytes(), b'user edit')

    def test_manifest_drift_refused(self):
        old = (self.root / 'preview/manifest.json').read_bytes()
        self.put('preview/manifest.json', b'{"new": true}')
        with self.assertRaisesRegex(ValueError, 'manifest changed'):
            builder.publish(self.root, {'preview/site/index.html': b'new'}, {}, old)
        self.assertFalse((self.root / 'preview/site/index.html').exists())

    def test_publish_failure_rolls_back_only_owned_writes(self):
        old = (self.root / 'preview/manifest.json').read_bytes()
        real_write = builder.atomic_write
        def fail_manifest(path, payload):
            if path.name == 'manifest.json':
                raise OSError('disk full')
            return real_write(path, payload)
        with patch.object(builder, 'atomic_write', side_effect=fail_manifest):
            with self.assertRaises(OSError):
                builder.publish(self.root, {'preview/site/index.html': b'new'}, {}, old)
        self.assertFalse((self.root / 'preview/site/index.html').exists())
        self.assertEqual((self.root / 'preview/manifest.json').read_bytes(), old)

    def test_arbitrary_output_rejected(self):
        old = (self.root / 'preview/manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Not a preview output'):
            builder.publish(self.root, {'README.md': b'bad'}, {}, old)

    def test_missing_license_fails_before_build(self):
        for name in builder.PACKAGES:
            self.put(f'web/node_modules/{name}/package.json', b'{"version":"1"}')
        self.put('web/package-lock.json', json.dumps({'packages': {
            f'node_modules/{n}': {'version': '1'} for n in builder.PACKAGES}}).encode())
        with patch.object(builder.shutil, 'which', return_value='tool'), \
             patch.object(builder.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '1\n', '')):
            with self.assertRaises(FileNotFoundError):
                builder.environment(self.root)

    def test_both_builds_have_explicit_isolated_environment(self):
        self.put('web/public/favicon.svg', b'icon')
        self.put('scripts/serve_preview.py', b'server')
        inputs = {'source_files': {}, 'runtime_assets': {}}
        with patch.object(builder, 'snapshot', return_value=inputs), \
             patch.object(builder, 'environment', return_value=({}, {})), \
             patch.object(builder.shutil, 'which', return_value='npm'), \
             patch.object(builder.subprocess, 'run') as run, \
             patch.object(builder, 'collect_outputs', return_value={}), \
             patch.object(builder, 'publish'), \
             patch.dict(builder.os.environ, {'VITE_API_BASE': 'https://wrong', 'VITE_SECRET': 'hidden', 'NODE_OPTIONS': 'bad'}):
            builder.build(self.root, 'a' * 40, execute=True)
        self.assertEqual(run.call_count, 2)
        first, second = run.call_args_list
        self.assertNotIn('VITE_API_BASE', first.kwargs['env'])
        self.assertNotIn('VITE_SECRET', first.kwargs['env'])
        self.assertNotIn('NODE_OPTIONS', first.kwargs['env'])
        self.assertEqual(second.kwargs['env']['VITE_API_BASE'], 'http://127.0.0.1:8765')
        self.assertEqual(first.args[0][1:6], ['run', 'build', '--prefix', 'web', '--'])

    def source_fixture(self):
        commit = 'a' * 40
        names = ['web/package.json', 'web/package-lock.json', 'web/index.html', 'web/tsconfig.json',
                 'web/public/favicon.svg', 'scripts/serve_preview.py', 'scripts/build_preview.py',
                 'web/src/new.ts']
        entries = {}
        for i, name in enumerate(names):
            payload = name.encode()
            self.put(name, payload)
            entries[name] = (f'{i:040x}', payload)
        tree = b''.join(f'100644 blob {oid}\t{name}\0'.encode() for name, (oid, _) in entries.items())
        index = b''.join(f'100644 {oid} 0\t{name}\0'.encode() for name, (oid, _) in entries.items())
        blobs = {oid: data for oid, data in entries.values()}
        def git(_root, *args):
            if args == ('rev-parse', 'HEAD'):
                return commit.encode()
            if args[:1] == ('ls-tree',):
                return tree
            if args[:1] == ('ls-files',):
                return index
            if args[:2] == ('cat-file', 'blob'):
                return blobs[args[2]]
            raise AssertionError(args)
        return commit, git

    def test_snapshot_includes_new_source_and_rejects_modified_bytes(self):
        commit, git = self.source_fixture()
        with patch.object(builder, 'git', side_effect=git):
            snapshot = builder.snapshot(self.root, commit)
            self.assertIn('web/src/new.ts', snapshot['source_files'])
            self.put('web/src/new.ts', b'edited')
            with self.assertRaisesRegex(ValueError, 'Actual source bytes'):
                builder.snapshot(self.root, commit)

    def test_ignored_source_and_env_rejected_without_reading_contents(self):
        commit, git = self.source_fixture()
        with patch.object(builder, 'git', side_effect=git):
            self.put('web/.env.local', b'secret value')
            with self.assertRaisesRegex(ValueError, 'Untracked/missing'):
                builder.snapshot(self.root, commit)
            (self.root / 'web/.env.local').unlink()
            self.put('web/src/ignored.ts', b'new ignored source')
            with self.assertRaisesRegex(ValueError, 'Untracked/missing'):
                builder.snapshot(self.root, commit)

    def test_locked_version_mismatch_rejected(self):
        self.put('web/node_modules/vite/package.json', b'{"version":"2"}')
        self.put('web/package-lock.json', b'{"packages":{"node_modules/vite":{"version":"1"}}}')
        with self.assertRaisesRegex(ValueError, 'differs from lockfile'):
            builder.environment(self.root)


if __name__ == '__main__':
    unittest.main()
