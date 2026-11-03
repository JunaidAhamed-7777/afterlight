"""Small bounded-reader fixtures; no real replay/SUMO or performance tests."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from api.artifacts import ArtifactError, read_bytes, read_json, parse_json_object, MAX_JSON_DEPTH


class BoundedArtifactTests(unittest.TestCase):
    def test_read_cap_applies_to_actual_read_even_if_stat_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'grown.json';path.write_bytes(b'x'*33)
            with patch('api.artifacts.os.fstat',return_value=SimpleNamespace(st_mode=0o100644,st_size=1)):
                with self.assertRaisesRegex(ArtifactError,'size limit'):read_bytes(path,limit=32)

    def test_stat_rejects_oversize_before_payload_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'large.json';path.write_bytes(b'x'*33)
            with self.assertRaisesRegex(ArtifactError,'size limit'):read_bytes(path,limit=32)

    def test_exact_cap_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'exact.json';path.write_bytes(b'x'*32)
            self.assertEqual(read_bytes(path,limit=32),b'x'*32)

    def test_json_rejects_nonfinite_nonobject_and_invalid_utf8(self):
        for payload in (b'{"x":NaN}',b'{"x":Infinity}',b'{"nested":{"x":1e309}}',b'{"nested":[-1e309]}',b'[]',b'null',b'\xff'):
            with self.subTest(payload=payload),self.assertRaises(ArtifactError):parse_json_object(payload)

    def test_excessive_json_depth_is_an_artifact_error(self):
        payload=b'{"deep":'+b'['*2000+b'0'+b']'*2000+b'}'
        with self.assertRaises(ArtifactError):parse_json_object(payload)

    def test_exact_depth_boundary_and_overflow_precedes_structure_decode(self):
        at_limit=b'{"x":'+b'['*(MAX_JSON_DEPTH-1)+b'0'+b']'*(MAX_JSON_DEPTH-1)+b'}'
        self.assertIn('x',parse_json_object(at_limit))
        over=b'{"x":'+b'['*MAX_JSON_DEPTH+b'0'+b']'*MAX_JSON_DEPTH+b'}'
        with patch('api.artifacts.json.loads') as loads:
            with self.assertRaisesRegex(ArtifactError,'depth'):parse_json_object(over)
            loads.assert_not_called()

    def test_brackets_escaped_quotes_and_backslash_runs_inside_strings_are_data(self):
        strings=['['*1000+'}'*1000, 'quote: " [ ]', 'backslash: \\', '\\"[', '\\\\"{', 'unicode: \u2603']
        value={'strings':strings,'nested':{'okay':True}}
        self.assertEqual(parse_json_object(json.dumps(value).encode()),value)
        # Escaped Unicode quote/bracket spellings do not delimit scanner strings.
        self.assertEqual(parse_json_object(b'{"x":"\\u0022\\u005b"}'),{'x':'"['})

    def test_utf8_bom_allowed_but_utf16_and_utf32_rejected(self):
        self.assertEqual(parse_json_object(b'\xef\xbb\xbf{"x":1}'),{'x':1})
        for encoding in ('utf-16','utf-32'):
            with self.subTest(encoding=encoding),self.assertRaises(ArtifactError):
                parse_json_object('{"x":1}'.encode(encoding))

    def test_deep_wrong_root_type_still_hits_depth_guard_before_decode(self):
        payload=b'['*(MAX_JSON_DEPTH+1)+b'0'+b']'*(MAX_JSON_DEPTH+1)
        with patch('api.artifacts.json.loads') as loads:
            with self.assertRaisesRegex(ArtifactError,'depth'):parse_json_object(payload)
            loads.assert_not_called()

    def test_shared_read_json_uses_canonical_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'object.json';path.write_text(json.dumps({'payload':'long enough'}))
            with patch('api.artifacts.MAX_REPLAY_BYTES',8):
                with self.assertRaisesRegex(ArtifactError,'size limit'):read_json(path)

    def test_missing_and_directory_paths_are_artifact_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in (Path(directory),Path(directory)/'missing'):
                with self.assertRaises(ArtifactError):read_bytes(path)


if __name__=='__main__':unittest.main()
