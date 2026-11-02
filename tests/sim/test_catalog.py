"""File-publication primitives only; synthetic bytes are never a replay."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from export.catalog import _install_bytes_exclusive


class AtomicRecordingCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.target=Path(self.temp.name)/'recording.json'
        self.payload=b'synthetic file-copy contract; not traffic evidence'
        self.digest=hashlib.sha256(self.payload).hexdigest()

    def test_success_is_exact_and_repeat_is_idempotent(self):
        _install_bytes_exclusive(self.target,self.payload,self.digest)
        _install_bytes_exclusive(self.target,self.payload,self.digest)
        self.assertEqual(self.target.read_bytes(),self.payload)
        self.assertEqual(list(self.target.parent.iterdir()),[self.target])

    def test_different_existing_recording_is_never_overwritten(self):
        self.target.write_bytes(b'prior evidence')
        with self.assertRaises(ValueError):
            _install_bytes_exclusive(self.target,self.payload,self.digest)
        self.assertEqual(self.target.read_bytes(),b'prior evidence')

    def test_failed_atomic_install_leaves_no_partial_final_name(self):
        with patch('export.catalog.os.link',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                _install_bytes_exclusive(self.target,self.payload,self.digest)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()),[])

    def test_wrong_digest_refuses_publication(self):
        with self.assertRaises(ValueError):
            _install_bytes_exclusive(self.target,self.payload,'0'*64)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()),[])


if __name__=='__main__': unittest.main()
