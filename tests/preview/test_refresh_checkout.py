"""Mock-only checkout refresh guard tests; execute on the designated Omen host."""
import importlib.util
import json
import hashlib
from types import SimpleNamespace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview_refresh', ROOT / 'scripts/refresh_preview_checkout.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


class RefreshGuards(unittest.TestCase):
    def fixture(self, root):
        (root / 'preview').mkdir()
        (root / 'input.txt').write_text('content\n', encoding='utf-8')
        (root / 'preview/manifest.json').write_text(json.dumps({
            'source_files': {'input.txt': hashlib.sha256(b'content\n').hexdigest()}, 'output_files': {}, 'runtime_assets': {}
        }), encoding='utf-8')

    def test_verifies_indexed_bytes_after_all_read_only_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with patch.object(refresh, 'ROOT', root), patch.object(refresh.subprocess, 'run', return_value=SimpleNamespace(stdout=b'content\n')) as run:
                refresh.refresh()
            self.assertEqual([call.args[0][1] for call in run.call_args_list],
                             ['ls-files', 'diff', 'diff', 'show', 'diff', 'diff'])
            self.assertEqual(run.call_args_list[3].args[0], ['git', 'show', ':input.txt'])
            self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))

    def test_either_content_diff_aborts_before_checkout(self):
        for failure_index in (1, 2):
            with self.subTest(failure_index=failure_index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                calls = []
                def fake_run(command, **kwargs):
                    calls.append(command)
                    if len(calls) - 1 == failure_index:
                        raise subprocess.CalledProcessError(1, command)
                with patch.object(refresh, 'ROOT', root), patch.object(refresh.subprocess, 'run', side_effect=fake_run):
                    with self.assertRaises(subprocess.CalledProcessError):
                        refresh.refresh()
                self.assertFalse(any('checkout-index' in command for command in calls))
                self.assertEqual((root / 'input.txt').read_text(), 'content\n')

    def test_missing_file_aborts_before_any_git_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'input.txt').unlink()
            with patch.object(refresh, 'ROOT', root), patch.object(refresh.subprocess, 'run', return_value=SimpleNamespace(stdout=b'content\n')) as run:
                with self.assertRaises(ValueError):
                    refresh.refresh()
                run.assert_not_called()

    def test_crlf_is_replaced_with_exact_verified_index_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'input.txt').write_bytes(b'content\r\n')
            with patch.object(refresh, 'ROOT', root), patch.object(refresh.subprocess, 'run', return_value=SimpleNamespace(stdout=b'content\n')):
                refresh.refresh()
            self.assertEqual((root / 'input.txt').read_bytes(), b'content\n')
            self.assertEqual(list(root.glob('.afterlight-lf-*')), [])

    def test_wrong_index_bytes_abort_before_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'input.txt').write_bytes(b'content\r\n')
            with patch.object(refresh, 'ROOT', root), patch.object(refresh.subprocess, 'run', return_value=SimpleNamespace(stdout=b'changed\n')):
                with self.assertRaisesRegex(ValueError, 'Indexed source'):
                    refresh.refresh()
            self.assertEqual((root / 'input.txt').read_bytes(), b'content\r\n')
