"""Tiny committed-tree fixtures and mocked npm only; no actual product build."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('afterlight_freezer_under_test', PROJECT / 'scripts/freeze_production.py')
freezer = module_from_spec(spec); spec.loader.exec_module(freezer)
COMMIT = 'a' * 40


class ProductionFreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='afterlight-freezer-fixture-')
        self.root = Path(self.temp.name).resolve()
        content = {'scripts/build_preview.py': (PROJECT / 'scripts/build_preview.py').read_bytes(),
                   'scripts/freeze_production.py': (PROJECT / 'scripts/freeze_production.py').read_bytes(),
                   'scripts/serve_preview.py': b'# synthetic server\n', '.gitignore': b'local-runtime/\n',
                   '.gitattributes': b'*.bin -text\n', 'vercel.json': b'{"outputDirectory":"web/dist"}',
                   'web/package.json': b'{"synthetic":true}', 'web/package-lock.json': b'{"synthetic":true}',
                   'web/index.html': b'<html>SYNTHETIC BUILD INPUT</html>', 'web/tsconfig.json': b'{"synthetic":true}',
                   'web/vite.config.ts': b'// synthetic configuration\n', 'web/src/App.tsx': b'// synthetic component\n',
                   'web/scripts/prepare-assets.mjs': b'// mocked; never executed\n',
                   'web/public/favicon.svg': b'<svg/>', 'web/public/THIRD_PARTY_NOTICES.txt': b'SYNTHETIC notices\n',
                   'web/public/replays/catalog.json': b'{"synthetic":true}', 'web/public/replays/synthetic.json.gz': b'SYNTHETIC COMPRESSED BYTES',
                   'web/public/study/synthetic-proof.bin': b'SYNTHETIC PUBLIC INPUT; NO OUTCOMES',
                   'web/public/brand/synthetic.svg': b'<svg>SYNTHETIC BRAND</svg>',
                   'web/public/media/synthetic.bin': b'SYNTHETIC MEDIA',
                   'preview/licenses/synthetic-LICENSE.txt': b'SYNTHETIC LICENSE\n',
                   'assets/map/city_manifest.json': b'{"synthetic":true}'}
        content.update({f'assets/exports/synthetic-{i:02d}.glb': b'SYNTHETIC ASSET ' + str(i).encode() for i in range(13)})
        content.update({'assets/previews/' + name: b'SYNTHETIC PREVIEW' for name in
                        ('city_overview.png', 'city_expanded.png', 'ambulance_model.png', 'ghost_model.png')})
        for name, data in content.items():
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.committed = content
        self.oids = {name: hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() for name, data in content.items()}
        self.index = dict(self.oids)
        self.fake_git_patch = patch.object(freezer, 'git', side_effect=self.git)
        self.fake_git_patch.start()
        self.guards = freezer.load_guards(self.root, COMMIT)
        self.guards.git = self.git
        self.guards.environment = lambda root: ({'node': 'synthetic', 'npm': 'synthetic', 'node_executable': 'LOCAL-ONLY-SYNTHETIC-TOOL'},
                                                {'preview/licenses/synthetic-LICENSE.txt': b'SYNTHETIC LICENSE\n'})
        self.guards.tool_commands = lambda: {'npm': ['synthetic-node', 'synthetic-npm-cli.js']}
        self.load_patch = patch.object(freezer, 'load_guards', return_value=self.guards); self.load_patch.start()
        self.run_calls = []; self.hook = None
        self.run_patch = patch.object(freezer.subprocess, 'run', side_effect=self.run_command); self.run_patch.start()

    def tearDown(self):
        self.run_patch.stop(); self.load_patch.stop(); self.fake_git_patch.stop(); self.temp.cleanup()

    def git(self, root, *args):
        if args == ('rev-parse', 'HEAD'): return (COMMIT + '\n').encode()
        if args[0] == 'show': return self.committed[args[1].split(':', 1)[1]]
        if args[0] == 'cat-file':
            return next(self.committed[name] for name, oid in self.oids.items() if oid == args[2])
        if args[0] == 'ls-tree':
            return b''.join(f'100644 blob {oid}\t{name}\0'.encode() for name, oid in sorted(self.oids.items()))
        if args[0] == 'ls-files':
            return b''.join(f'100644 {oid} 0\t{name}\0'.encode() for name, oid in sorted(self.index.items()))
        if args[0] == 'check-ignore':
            if b'local-runtime/' not in self.committed['.gitignore']: raise subprocess.CalledProcessError(1, ['synthetic-git'])
            return b''
        raise AssertionError(('Unexpected Git command', args))

    def run_command(self, argv, **kwargs):
        self.run_calls.append((list(argv), dict(kwargs['env'])))
        if 'prepare:assets' in argv:
            assets = self.guards.snapshot(self.root, COMMIT)['runtime_assets']
            for name in assets:
                target = self.root / ('web/public/' + name); target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((self.root / name).read_bytes())
            phase = 'prepare'
        elif 'build' in argv:
            site = Path(argv[argv.index('--outDir') + 1])
            for source in (self.root / 'web/public').rglob('*'):
                if source.is_file():
                    target = site / source.relative_to(self.root / 'web/public'); target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            (site / 'index.html').write_bytes(b'<html>SYNTHETIC BUILD OUTPUT</html>')
            phase = 'build'
        else: raise AssertionError(('No real command allowed', argv))
        if self.hook: self.hook(phase)
        return subprocess.CompletedProcess(argv, 0)

    def freeze(self, execute=True): return freezer.freeze(self.root, COMMIT, Path('local-runtime/candidate'), execute=execute)

    def test_default_plan_writes_nothing_and_runs_no_npm(self):
        result = self.freeze(execute=False)
        self.assertEqual(result['status'], 'plan_only_no_writes_or_build')
        self.assertEqual(self.run_calls, [])
        self.assertFalse((self.root / 'local-runtime').exists())
        self.assertFalse((self.root / 'web/public/assets').exists())

    def test_mock_build_binds_complete_inputs_and_served_output_without_exposing_toolpaths(self):
        result = self.freeze()
        manifest_path = self.root / 'local-runtime/candidate/manifest.json'; manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(result['status'], 'frozen')
        self.assertEqual(len(manifest['strict_inputs']['prepared_public_assets']), 18)
        for name in ('web/tsconfig.json', 'web/vite.config.ts', 'web/public/replays/synthetic.json.gz',
                     'web/public/study/synthetic-proof.bin', 'web/public/THIRD_PARTY_NOTICES.txt',
                     'web/public/brand/synthetic.svg', 'web/public/media/synthetic.bin', 'vercel.json', freezer.SELF):
            self.assertIn(name, manifest['source']['files'])
        self.assertIsNone(manifest['compiled_env']['VITE_API_BASE'])
        self.assertFalse(manifest['build_env_policy']['VITE_API_BASE_present'])
        self.assertNotIn('manifest.json', manifest['files'])
        site = manifest_path.parent / 'site'
        self.assertFalse(any(b'LOCAL-ONLY-SYNTHETIC-TOOL' in p.read_bytes() for p in site.rglob('*') if p.is_file()))
        self.assertEqual(freezer.verify_frozen(self.root, manifest_path)['files'], len(manifest['files']))

    def test_existing_or_outside_output_is_rejected_before_any_mutating_command(self):
        existing = self.root / 'local-runtime/existing'; existing.mkdir(parents=True); (existing / 'keep').write_bytes(b'KEEP')
        for output in (existing, self.root / 'elsewhere', Path('../escape'), self.root / 'local-runtime/nested/child'):
            with self.subTest(output=output), self.assertRaises((ValueError, FileExistsError)):
                freezer.freeze(self.root, COMMIT, output, execute=True)
        self.assertEqual((existing / 'keep').read_bytes(), b'KEEP'); self.assertEqual(self.run_calls, [])

    def test_redirected_runtime_is_rejected_before_any_mutating_command(self):
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', autospec=True, side_effect=lambda path: path == self.root / 'local-runtime' or original(path)):
            with self.assertRaisesRegex(ValueError, 'Redirected'): self.freeze()
        self.assertEqual(self.run_calls, [])

    def test_vite_and_node_environment_removed_for_tools_then_restored(self):
        original_environment = self.guards.environment
        def checked_environment(root):
            self.assertFalse(any(key.upper().startswith('VITE_') or key.upper() in ('NODE_OPTIONS', 'NODE_ENV') for key in os.environ))
            npm_keys = {key.upper() for key in os.environ if key.upper().startswith('NPM_CONFIG_')}
            self.assertEqual(npm_keys, {'NPM_CONFIG_USERCONFIG', 'NPM_CONFIG_GLOBALCONFIG'})
            self.assertNotEqual(os.environ['NPM_CONFIG_USERCONFIG'], os.environ['NPM_CONFIG_GLOBALCONFIG'])
            self.assertFalse(Path(os.environ['NPM_CONFIG_USERCONFIG']).exists())
            self.assertFalse(Path(os.environ['NPM_CONFIG_GLOBALCONFIG']).exists())
            return original_environment(root)
        self.guards.environment = checked_environment
        with patch.dict(os.environ, {'VITE_API_BASE': 'DO-NOT-RECORD-THIS', 'VITE_SECRET_TEST': 'DO-NOT-RECORD-THIS',
                                    'NODE_OPTIONS': 'synthetic', 'NODE_ENV': 'synthetic',
                                    'npm_config_node_options': 'DO-NOT-RECORD-THIS', 'NPM_CONFIG_SCRIPT_SHELL': 'DO-NOT-RECORD-THIS',
                                    'NPM_CONFIG_USERCONFIG': 'DO-NOT-RECORD-THIS', 'npm_config_globalconfig': 'DO-NOT-RECORD-THIS'}):
            self.freeze()
            self.assertEqual(os.environ['VITE_API_BASE'], 'DO-NOT-RECORD-THIS')
            self.assertEqual(os.environ['npm_config_node_options'], 'DO-NOT-RECORD-THIS')
        self.assertTrue(all(not any(key.upper().startswith('VITE_') or key.upper() in ('NODE_OPTIONS', 'NODE_ENV') for key in env) for _, env in self.run_calls))
        manifest = (self.root / 'local-runtime/candidate/manifest.json').read_bytes()
        self.assertNotIn(b'DO-NOT-RECORD-THIS', manifest)

    def test_public_byte_changes_or_untracked_additions_fail_before_prepare(self):
        for name in ('web/public/replays/synthetic.json.gz', 'web/public/study/synthetic-proof.bin', 'web/tsconfig.json', 'vercel.json'):
            path = self.root / name; original = path.read_bytes(); path.write_bytes(original + b'CHANGED')
            with self.subTest(name=name), self.assertRaises(ValueError): self.freeze()
            path.write_bytes(original)
        extra = self.root / 'web/public/replays/untracked.bin'; extra.write_bytes(b'EXTRA')
        with self.assertRaises(ValueError): self.freeze()
        self.assertEqual(self.run_calls, [])

    def test_public_staged_identity_cannot_differ_from_HEAD(self):
        self.index['web/public/replays/synthetic.json.gz'] = 'f' * 40
        with self.assertRaises(ValueError): self.freeze()
        self.assertEqual(self.run_calls, [])

    def test_hidden_config_case_aliases_are_rejected_before_any_tool_calls(self):
        environment = self.guards.environment
        self.guards.environment = unittest.mock.Mock(side_effect=environment)
        for directory in (self.root, self.root / 'web'):
            for filename in ('.ENV', '.Env.production', '.NPMRC', '.nPmRc', '.env.example'):
                path = directory / filename; path.write_bytes(b'SYNTHETIC CONFIG; CONTENTS MUST NOT BE READ')
                try:
                    with self.subTest(directory=directory.name, filename=filename), self.assertRaisesRegex(ValueError, 'case-insensitive'):
                        self.freeze()
                finally: path.unlink()
        self.guards.environment.assert_not_called()
        self.assertEqual(self.run_calls, [])
        self.assertFalse((self.root / 'local-runtime').exists())

    def test_generated_asset_extras_are_rejected_before_copy_or_build(self):
        extra = self.root / 'web/public/assets/obsolete.glb'; extra.parent.mkdir(parents=True); extra.write_bytes(b'STALE')
        with self.assertRaisesRegex(ValueError, 'Unexpected generated'): self.freeze()
        self.assertEqual(self.run_calls, [])

    def test_generated_mirror_mismatch_after_prepare_prevents_output_creation(self):
        def change(phase):
            if phase == 'prepare': (self.root / 'web/public/assets/exports/synthetic-00.glb').write_bytes(b'WRONG')
        self.hook = change
        with self.assertRaisesRegex(ValueError, 'authoritative source'): self.freeze()
        self.assertFalse((self.root / 'local-runtime/candidate').exists())

    def test_authoritative_input_change_during_prepare_is_not_normalized_away(self):
        def change(phase):
            if phase == 'prepare': (self.root / 'assets/exports/synthetic-00.glb').write_bytes(b'CHANGED SOURCE')
        self.hook = change
        with self.assertRaises(ValueError): self.freeze()
        self.assertFalse((self.root / 'local-runtime/candidate').exists())

    def test_public_input_changed_during_build_retains_failed_site_without_success_manifest(self):
        def change(phase):
            if phase == 'build': (self.root / 'web/public/replays/synthetic.json.gz').write_bytes(b'CHANGED')
        self.hook = change
        with self.assertRaises(ValueError): self.freeze()
        candidate = self.root / 'local-runtime/candidate'
        self.assertTrue((candidate / 'site').is_dir()); self.assertFalse((candidate / 'manifest.json').exists())

    def test_tool_or_license_drift_is_rejected_before_output_is_reserved(self):
        original = self.guards.environment(self.root)
        self.guards.environment = unittest.mock.Mock(side_effect=[original, ({'node': 'CHANGED'}, original[1])])
        with self.assertRaisesRegex(ValueError, 'Tool environment changed'): self.freeze()
        self.assertFalse((self.root / 'local-runtime/candidate').exists())

    def test_frozen_file_set_additions_and_byte_changes_are_detected(self):
        self.freeze(); path = self.root / 'local-runtime/candidate/manifest.json'; site = path.parent / 'site'
        extra = site / 'unexpected.bin'; extra.write_bytes(b'EXTRA')
        with self.assertRaisesRegex(ValueError, 'file set or bytes'): freezer.verify_frozen(self.root, path)
        extra.unlink(); (site / 'index.html').write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'file set or bytes'): freezer.verify_frozen(self.root, path)

    def test_externally_pinned_manifest_rejects_coherent_output_and_manifest_rewrites(self):
        result = self.freeze(); path = self.root / 'local-runtime/candidate/manifest.json'
        manifest = json.loads(path.read_bytes()); data = b'REWRITTEN'
        (path.parent / 'site/index.html').write_bytes(data)
        manifest['files']['index.html'] = {'bytes': len(data), 'sha256': freezer.sha(data)}
        manifest['total_bytes'] = sum(row['bytes'] for row in manifest['files'].values())
        path.write_bytes(json.dumps(manifest).encode())
        with self.assertRaisesRegex(ValueError, 'externally recorded'):
            freezer.verify_frozen(self.root, path, expected_manifest_sha256=result['manifest_sha256'])

    def test_environment_is_restored_after_a_mocked_preparation_failure(self):
        self.hook = lambda phase: (_ for _ in ()).throw(RuntimeError('synthetic preparation failure'))
        with patch.dict(os.environ, {'NODE_ENV': 'ORIGINAL', 'VITE_API_BASE': 'SYNTHETIC'}):
            with self.assertRaisesRegex(RuntimeError, 'synthetic preparation'): self.freeze()
            self.assertEqual(os.environ['NODE_ENV'], 'ORIGINAL')
            self.assertEqual(os.environ['VITE_API_BASE'], 'SYNTHETIC')

    def test_configuration_injected_during_prepare_cannot_reach_build(self):
        def change(phase):
            if phase == 'prepare':
                path = self.root / 'local-runtime/candidate/.disabled-user.npmrc'
                path.parent.mkdir(parents=True); path.write_bytes(b'node-options=UNBOUND\n')
        self.hook = change
        with self.assertRaisesRegex(ValueError, 'configuration must remain absent'): self.freeze()
        self.assertEqual(len(self.run_calls), 1)
        self.assertFalse((self.root / 'local-runtime/candidate/manifest.json').exists())

    def test_failed_terminal_postcheck_keeps_only_pending_metadata(self):
        with patch.object(freezer, '_verify_manifest', side_effect=ValueError('synthetic terminal rejection')):
            with self.assertRaisesRegex(ValueError, 'terminal rejection'): self.freeze()
        candidate = self.root / 'local-runtime/candidate'
        self.assertFalse((candidate / 'manifest.json').exists())
        self.assertTrue((candidate / 'manifest.pending.json').is_file())
        self.assertTrue((candidate / 'site/index.html').is_file())
        with self.assertRaises(ValueError): freezer.verify_frozen(self.root, candidate / 'manifest.pending.json')

    def test_atomic_publication_does_not_replace_a_concurrent_manifest(self):
        original_link = os.link
        def publish(source, destination):
            Path(destination).write_bytes(b'CONCURRENT FILE MUST BE PRESERVED')
            return original_link(source, destination)
        with patch.object(freezer.os, 'link', side_effect=publish):
            with self.assertRaises(FileExistsError): self.freeze()
        self.assertEqual((self.root / 'local-runtime/candidate/manifest.json').read_bytes(), b'CONCURRENT FILE MUST BE PRESERVED')

    def test_oversize_build_is_retained_without_a_success_manifest(self):
        with patch.object(freezer, 'MAX_PRODUCTION_BYTES', 1), self.assertRaisesRegex(ValueError, 'below 50 MB'): self.freeze()
        self.assertFalse((self.root / 'local-runtime/candidate/manifest.json').exists())

    def test_raw_guard_loader_rejects_uncommitted_helper_before_execution(self):
        (self.root / freezer.HELPER).write_bytes(b'raise RuntimeError("UNVERIFIED CODE EXECUTED")\n')
        self.load_patch.stop()
        try:
            with self.assertRaisesRegex(ValueError, 'guard bytes differ'): freezer.load_guards(self.root, COMMIT)
        finally: self.load_patch.start()

    def test_raw_guard_loader_also_requires_committed_freezer_tool(self):
        (self.root / freezer.SELF).write_bytes(b'# modified freezer source\n')
        self.load_patch.stop()
        try:
            with self.assertRaisesRegex(ValueError, 'freezer bytes differ'): freezer.load_guards(self.root, COMMIT)
        finally: self.load_patch.start()


if __name__ == '__main__': unittest.main(verbosity=2)
