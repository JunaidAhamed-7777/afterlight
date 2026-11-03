"""Pure Git-record/byte fixtures; no real Git, SUMO or cloud test execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sim.source_identity import MAP, blob_id, parse_index, parse_tree, source_snapshot


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.contents={'sim/worker.py':b'value = 1\n',MAP:b'{"unit_fixture":true}\n','sim/README.md':b'unit fixture\n'}
        for name,data in self.contents.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            path.chmod(0o644)
        self.algorithm='sha1';self.commit='a'*40
        self.tree_modes={name:'100644' for name in self.contents}
        self.index_modes=dict(self.tree_modes)
        self.index_contents=dict(self.contents)
        self.index_stages={}
        self.untracked=b''
        self.calls=[]

    def tree(self):
        return b''.join(f'{self.tree_modes[name]} blob {blob_id(data,self.algorithm)}\t{name}\0'.encode() for name,data in sorted(self.contents.items()))

    def index(self):
        return b''.join(f'{self.index_modes[name]} {blob_id(data,self.algorithm)} {self.index_stages.get(name,0)}\t{name}\0'.encode() for name,data in sorted(self.index_contents.items()))

    def git(self,root,*args):
        self.assertEqual(root,self.root)
        self.calls.append(args)
        if args==('rev-parse','--verify','HEAD'):return self.commit.encode()+b'\n'
        if args==('rev-parse','--show-object-format'):return self.algorithm.encode()+b'\n'
        if args[0]=='ls-tree':return self.tree()
        if args[:2]==('ls-files','--stage'):return self.index()
        if args[:2]==('ls-files','--others'):return self.untracked
        raise AssertionError(f'Unexpected Git/cache operation: {args}')

    def snapshot(self):
        with patch('sim.source_identity._git',side_effect=self.git):return source_snapshot(self.root)

    def test_identical_bytes_index_head_clean_without_status_or_refresh(self):
        result=self.snapshot()
        self.assertFalse(result['source_dirty'])
        expected={name:hashlib.sha256(self.contents[name]).hexdigest() for name in ('sim/worker.py',MAP)}
        self.assertEqual(result['source_files'],expected)
        canonical=json.dumps(expected,sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(result['source_code_sha256'],hashlib.sha256(canonical).hexdigest())
        self.assertEqual(set(result),{'source_commit','source_dirty','source_files','source_code_sha256'})
        self.assertTrue(all(args[0] not in {'status','update-index','diff'} for args in self.calls))

    def test_actual_source_edit_dirty_even_if_index_unchanged(self):
        (self.root/'sim/worker.py').write_bytes(b'value = 2\n')
        result=self.snapshot()
        self.assertTrue(result['source_dirty'])
        self.assertEqual(result['source_files']['sim/worker.py'],hashlib.sha256(b'value = 2\n').hexdigest())

    def test_staged_edit_dirty_even_when_worktree_matches_head(self):
        self.index_contents['sim/worker.py']=b'staged edit\n'
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_staged_addition_and_deletion_are_dirty(self):
        self.index_contents['sim/new.py']=b'new\n';self.index_modes['sim/new.py']='100644'
        self.assertTrue(self.snapshot()['source_dirty'])
        del self.index_contents['sim/new.py'];del self.index_contents['sim/worker.py']
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_deleted_worktree_file_is_dirty(self):
        (self.root/'sim/worker.py').unlink()
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_untracked_scoped_nonpython_file_is_dirty(self):
        self.untracked=b'sim/new-notes.txt\0'
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_ignored_python_addition_is_dirty_without_git_untracked_entry(self):
        (self.root/'sim/ignored.py').write_text('ignored but executable source\n')
        result=self.snapshot()
        self.assertTrue(result['source_dirty'])
        self.assertIn('sim/ignored.py',result['source_files'])

    def test_ignored_uppercase_python_suffix_is_not_hidden_on_windows(self):
        (self.root/'sim/ignored.PY').write_text('ignored Windows importable source\n')
        result=self.snapshot()
        self.assertTrue(result['source_dirty'])
        self.assertIn('sim/ignored.PY',result['source_files'])

    def test_tracked_nonpython_raw_edit_is_dirty(self):
        (self.root/'sim/README.md').write_bytes(b'changed\n')
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_crlf_raw_bytes_are_not_silently_normalized(self):
        (self.root/'sim/worker.py').write_bytes(b'value = 1\r\n')
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_unmerged_index_stage_fails_closed(self):
        self.index_stages['sim/worker.py']=2
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_staged_mode_change_is_dirty(self):
        self.index_modes['sim/worker.py']='100755'
        self.assertTrue(self.snapshot()['source_dirty'])

    @unittest.skipIf(os.name=='nt','Windows does not represent Git executable mode')
    def test_posix_worktree_mode_change_is_dirty(self):
        (self.root/'sim/worker.py').chmod(0o755)
        self.assertTrue(self.snapshot()['source_dirty'])

    def test_source_redirect_is_not_read_or_hashed(self):
        target=self.root/'sim/worker.py'
        original=Path.is_symlink
        def redirected(path):return path==target or original(path)
        original_read=Path.read_bytes
        def guarded_read(path):
            if path==target:raise AssertionError('Redirected target was read')
            return original_read(path)
        with patch.object(Path,'is_symlink',redirected),patch.object(Path,'read_bytes',guarded_read):
            result=self.snapshot()
        self.assertTrue(result['source_dirty'])
        self.assertNotIn('sim/worker.py',result['source_files'])

    def test_git_error_is_unavailable_not_clean(self):
        with patch('sim.source_identity._git',side_effect=subprocess.CalledProcessError(1,['git'])):
            result=source_snapshot(self.root)
        self.assertIsNone(result['source_dirty'])
        self.assertEqual(result['source_commit'],'unavailable')

    def test_sha256_git_repository_supported(self):
        self.algorithm='sha256';self.commit='a'*64
        self.assertFalse(self.snapshot()['source_dirty'])

    def test_concurrent_index_change_fails_closed(self):
        seen=0
        def changing(root,*args):
            nonlocal seen
            if args[:2]==('ls-files','--stage'):
                seen+=1
                if seen==2:self.index_contents['sim/worker.py']=b'changed index\n'
            return self.git(root,*args)
        with patch('sim.source_identity._git',side_effect=changing):result=source_snapshot(self.root)
        self.assertTrue(result['source_dirty'])

    def test_late_worktree_mutation_cannot_return_clean_cached_bytes(self):
        head_reads=0
        original=self.contents['sim/worker.py']
        def changing(root,*args):
            nonlocal head_reads
            if args==('rev-parse','--verify','HEAD'):
                head_reads+=1
                if head_reads==2:(self.root/'sim/worker.py').write_bytes(b'changed during snapshot\n')
            return self.git(root,*args)
        with patch('sim.source_identity._git',side_effect=changing):result=source_snapshot(self.root)
        self.assertTrue(result['source_dirty'])
        self.assertEqual(result['source_files']['sim/worker.py'],hashlib.sha256(original).hexdigest())

    @unittest.skipIf(os.name=='nt','Windows does not represent Git executable mode')
    def test_late_executable_mode_mutation_cannot_return_clean(self):
        head_reads=0
        def changing(root,*args):
            nonlocal head_reads
            if args==('rev-parse','--verify','HEAD'):
                head_reads+=1
                if head_reads==2:(self.root/'sim/worker.py').chmod(0o755)
            return self.git(root,*args)
        with patch('sim.source_identity._git',side_effect=changing):result=source_snapshot(self.root)
        self.assertTrue(result['source_dirty'])

    def test_parser_rejects_symlink_mode_and_path_escape(self):
        with self.assertRaises(ValueError):parse_tree(b'120000 blob '+b'a'*40+b'\tsim/link.py\0')
        with self.assertRaises(ValueError):parse_index(b'100644 '+b'a'*40+b' 0\t../escape.py\0')

    def test_git_blob_header_uses_raw_byte_count(self):
        data='é\n'.encode()
        self.assertEqual(blob_id(data,'sha1'),hashlib.sha1(b'blob 3\0'+data).hexdigest())


if __name__=='__main__':unittest.main()
