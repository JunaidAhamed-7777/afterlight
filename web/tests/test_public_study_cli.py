"""Negative CLI/import probes only: every child blocks DNS and socket access.

No positive publication fixture, scientific outcome, fit, simulator or browser.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'scripts/verify_public_study.py'
HELPER = ROOT / 'web/tests/released_study_pack.py'
VALID_ARGS = ['--base-url', 'https://never-contact.invalid/', '--released-manifest-sha256', 'a' * 64]
BOOTSTRAP = '''
import runpy,socket,sys
def blocked(*args,**kwargs):
    raise RuntimeError('TEST_BLOCKED_NETWORK_BEFORE_ANY_HTTP')
socket.create_connection=blocked
socket.getaddrinfo=blocked
socket.socket.connect=blocked
target=sys.argv[1];sys.argv=[target,*sys.argv[2:]]
try:
    runpy.run_path(target,run_name='__main__')
finally:
    prohibited=[name for name in sys.modules if name in {'sim','evaluation','models','playwright'} or name.startswith(('sim.','evaluation.','models.','playwright.'))]
    if prohibited: raise RuntimeError('UNEXPECTED_NON_STDLIB_OR_SCIENTIFIC_IMPORT:'+repr(prohibited))
'''


class PublicStudyCLIGuards(unittest.TestCase):
    def run_child(self, target=CLI, args=(), flags=(), optimize_env=None):
        env = os.environ.copy(); env.pop('PYTHONOPTIMIZE', None)
        if optimize_env is not None: env['PYTHONOPTIMIZE'] = optimize_env
        return subprocess.run([sys.executable, *flags, '-c', BOOTSTRAP, str(target), *args],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)

    def assert_no_network(self, completed):
        self.assertNotIn('TEST_BLOCKED_NETWORK', completed.stderr)
        self.assertNotIn('UNEXPECTED_NON_STDLIB_OR_SCIENTIFIC_IMPORT', completed.stderr)

    def test_help_is_stdlib_only_and_does_not_open_publication(self):
        completed = self.run_child(args=['--help'])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('--released-manifest-sha256', completed.stdout)
        self.assert_no_network(completed)

    def test_both_release_arguments_are_required_before_network(self):
        for args in ([], ['--base-url', 'https://never-contact.invalid/'], ['--released-manifest-sha256', 'a' * 64]):
            with self.subTest(args=args):
                completed = self.run_child(args=args)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertEqual(completed.stdout, '')
                self.assert_no_network(completed)

    def test_private_input_and_fitting_switches_are_not_supported(self):
        for flag in ('--study', '--train', '--validation', '--fit-model', '--collection'):
            with self.subTest(flag=flag):
                completed = self.run_child(args=[*VALID_ARGS, flag, 'synthetic-unused-path'])
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assert_no_network(completed)

    def test_invalid_manifest_and_unsafe_base_urls_fail_before_network(self):
        invalid = [VALID_ARGS[:2] + ['--released-manifest-sha256', 'not-a-sha'],
                   ['--base-url', 'file:///synthetic-not-read', *VALID_ARGS[2:]],
                   ['--base-url', 'http://never-contact.invalid/', *VALID_ARGS[2:]],
                   ['--base-url', 'https://user:password@never-contact.invalid/', *VALID_ARGS[2:]],
                   ['--base-url', 'https://never-contact.invalid:bad/', *VALID_ARGS[2:]],
                   ['--base-url', 'https://never-contact.invalid/?private=unused', *VALID_ARGS[2:]]]
        for args in invalid:
            with self.subTest(args=args):
                completed = self.run_child(args=args)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assert_no_network(completed)

    def test_existing_output_is_preserved_before_any_network(self):
        with TemporaryDirectory(prefix='afterlight-cli-negative-') as directory:
            path = Path(directory) / 'existing.json'; original = b'original byte-exact contents\r\n'; path.write_bytes(original)
            completed = self.run_child(args=[*VALID_ARGS, '--output', str(path)])
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertEqual(path.read_bytes(), original)
            self.assert_no_network(completed)

    def test_missing_output_parent_is_not_created_or_contacted(self):
        with TemporaryDirectory(prefix='afterlight-cli-negative-') as directory:
            path = Path(directory) / 'missing/report.json'
            completed = self.run_child(args=[*VALID_ARGS, '--output', str(path)])
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertFalse(path.parent.exists())
            self.assert_no_network(completed)

    def test_unavailable_publication_does_not_create_report_or_print_success(self):
        with TemporaryDirectory(prefix='afterlight-cli-negative-') as directory:
            path = Path(directory) / 'report.json'
            completed = self.run_child(args=[*VALID_ARGS, '--output', str(path)])
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertIn('Verification failed:', completed.stderr)
            self.assertIn('TEST_BLOCKED_NETWORK_BEFORE_ANY_HTTP', completed.stderr)
            self.assertEqual(completed.stdout, '')
            self.assertFalse(path.exists())

    def test_optimized_cli_refuses_before_even_parsing_or_network(self):
        for flags, optimize_env in ((['-O'], None), (['-OO'], None), ([], '1')):
            with self.subTest(flags=flags, optimize_env=optimize_env):
                completed = self.run_child(flags=flags, optimize_env=optimize_env)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn('refuses optimized Python', completed.stderr)
                self.assertEqual(completed.stdout, '')
                self.assert_no_network(completed)

    def test_optimized_helper_import_refuses_without_any_verification_call(self):
        for flags, optimize_env in ((['-O'], None), (['-OO'], None), ([], '1')):
            with self.subTest(flags=flags, optimize_env=optimize_env):
                completed = self.run_child(target=HELPER, flags=flags, optimize_env=optimize_env)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn('refuses optimized Python', completed.stderr)
                self.assert_no_network(completed)

    def test_normal_helper_import_runs_no_network_or_scientific_helpers(self):
        completed = self.run_child(target=HELPER)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, '')
        self.assert_no_network(completed)


if __name__ == '__main__': unittest.main(verbosity=2)
