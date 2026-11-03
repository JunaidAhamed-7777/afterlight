"""Isolated byte/module guards; no Study pack, HTTP, outcomes or simulation.

The only project-shaped modules executed here are synthetic temporary files.
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import os
import py_compile
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from released_study_pack import ANALYSIS_ARTIFACTS, PURE_HELPER_FILES, bound_scientific_modules, canonical_sha, sha, strict_json, verify_analysis_amendment


def scientific(name):
    return name in ('evaluation', 'models') or name.startswith(('evaluation.', 'models.'))


class StrictJSONTests(unittest.TestCase):
    def test_finite_extremes_and_nested_values_remain_usable(self):
        value = strict_json(b'{"finite":[1.7976931348623157e308,-1.2e-300,0,1.5],"empty":null}')
        self.assertEqual(value['finite'][0], sys.float_info.max)
        self.assertEqual(value['finite'][1:], [-1.2e-300, 0, 1.5])
        self.assertIsNone(value['empty'])

    def test_positive_negative_and_nested_exponent_overflow_are_rejected(self):
        for raw in (b'1e400', b'-1e400', b'{"values":[1,{"overflow":1e99999}]}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'Nonfinite published JSON'):
                strict_json(raw)

    def test_nonstandard_nonfinite_tokens_are_still_rejected(self):
        for raw in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'Nonfinite published JSON'):
                strict_json(raw)

    def test_duplicate_nested_keys_are_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate published JSON key'):
            strict_json(b'{"object":{"key":1,"key":2}}')


class AnalysisAmendmentGuards(unittest.TestCase):
    """Synthetic metadata/bytes only; no positive Study summary or outcomes."""
    def setUp(self):
        original = {'source_commit': 'a' * 40, 'source_code_sha256': 'b' * 64, 'source_dirty': False,
                    'source_files': {'evaluation/study_reporting.py': 'c' * 64, 'evaluation/study_manifest.py': 'd' * 64}}
        estimator = {'version': 'synthetic-estimator', 'config': {'civilian_weight': 1.0}}
        study = {'source': original}; protocol = {'analytical_estimator': estimator}
        self.documents = {'study': {'sha256': canonical_sha(study), 'study': study},
                          'protocol': {'sha256': canonical_sha(protocol), 'protocol': protocol},
                          'selection': {'selection': {'created_utc': '2026-01-01T00:01:00+00:00'}},
                          'report': {'report': {'created_utc': '2026-01-01T00:03:00+00:00'}},
                          'release': {'release': {'created_utc': '2026-01-01T00:02:00+00:00'}}}
        self.raw = {kind: b'raise RuntimeError("DOWNLOADED SOURCE MUST NEVER EXECUTE")\n' for kind in
                    ('analysis_verifier_source', 'analysis_binding_source', 'analysis_entrypoint_source')}
        self.raw.update(analysis_diff=b'SYNTHETIC reviewed diff\n', analysis_failure_log=b'SYNTHETIC pre-fit verifier failure\n',
                        analysis_failure_journal=json.dumps({'schema': 'afterlight.selection-dependency-watcher.v1',
                            'state': 'watcher_stopped_no_test_release', 'return_code': 1, 'automatic_retries': 0,
                            'created_utc': '2025-12-31T23:59:57+00:00', 'invoked_utc': '2025-12-31T23:59:58+00:00',
                            'stopped_utc': '2025-12-31T23:59:59+00:00'}).encode())
        def item(kind): return {'filename': ANALYSIS_ARTIFACTS[kind], 'sha256': sha(self.raw[kind])}
        files = {'verifier': {**item('analysis_verifier_source'), 'original_path': 'evaluation/study_reporting.py', 'original_sha256': 'c' * 64},
                 'binding_helper': {**item('analysis_binding_source'), 'original_path': 'evaluation/study_manifest.py', 'original_sha256': 'd' * 64},
                 'entrypoint': item('analysis_entrypoint_source'), 'diff': item('analysis_diff')}
        self.amendment = {'schema': 'afterlight.analysis-amendment.v1', 'id': 'frozen-estimator-config-v1',
                          'created_utc': '2026-01-01T00:00:00+00:00', 'original_study_sha256': self.documents['study']['sha256'],
                          'original_protocol_sha256': self.documents['protocol']['sha256'], 'original_source': original,
                          'frozen_analytical_estimator': json.loads(json.dumps(estimator)), 'frozen_analytical_estimator_sha256': canonical_sha(estimator),
                          'correction': 'Synthetic exact-config verifier correction; no estimator or outcome change.',
                          'unchanged_design': ['Synthetic original simulation and estimator remain frozen.'],
                          'failed_attempt': {'state': 'verification_failed_before_model_fit', 'model_fit_reached': False,
                                             'journal': item('analysis_failure_journal'), 'log': item('analysis_failure_log')},
                          'analysis_files': files}
        self.artifacts = {}; self.seal()

    def seal(self):
        descriptor = {'sha256': canonical_sha(self.amendment), 'amendment': self.amendment}
        self.documents['analysis_amendment'] = descriptor
        self.raw['analysis_amendment'] = json.dumps(descriptor, indent=2, allow_nan=False).encode()
        files = self.amendment['analysis_files']
        binding = {'schema': 'afterlight.analysis-amendment-binding.v1', 'id': self.amendment['id'], 'sha256': descriptor['sha256'],
                   'file_sha256': sha(self.raw['analysis_amendment']), 'implementation_sha256': files['verifier']['sha256'],
                   'binding_helper_sha256': files['binding_helper']['sha256'], 'entrypoint_sha256': files['entrypoint']['sha256']}
        for key in ('selection', 'report'):
            self.documents[key][key]['analysis_amendment'] = dict(binding)
            self.documents[key]['sha256'] = canonical_sha(self.documents[key][key])
        self.raw['selection'] = json.dumps(self.documents['selection'], indent=2).encode()
        self.documents['release']['release'].update(selection_sha256=self.documents['selection']['sha256'], selection_file_sha256=sha(self.raw['selection']))
        for kind, filename in ANALYSIS_ARTIFACTS.items():
            self.artifacts[kind] = {'kind': kind, 'url': filename, 'sha256': sha(self.raw[kind]), 'bytes': len(self.raw[kind])}

    def verify(self): return verify_analysis_amendment(self.documents, self.raw, self.artifacts)

    def test_exact_metadata_and_source_companions_bind_without_executing_any_code(self):
        with patch('builtins.exec', side_effect=AssertionError('Analysis source execution forbidden')), \
             patch('released_study_pack.bound_scientific_modules', side_effect=AssertionError('Original helper imports not part of this metadata probe')):
            result = self.verify()
        self.assertTrue(result['present'])
        self.assertFalse(result['downloaded_analysis_code_executed'])
        self.assertEqual(result['all_analysis_companions_hash_verified'], sorted(ANALYSIS_ARTIFACTS))

    def test_original_frozen_estimator_int_float_identity_is_not_coerced(self):
        self.amendment['frozen_analytical_estimator']['config']['civilian_weight'] = 1
        self.seal()
        with self.assertRaisesRegex(AssertionError, 'representation'): self.verify()

    def test_foreign_original_source_is_rejected_even_after_resealing_descriptor(self):
        self.amendment['original_source'] = {**self.amendment['original_source'], 'source_commit': 'f' * 40}
        self.seal()
        with self.assertRaisesRegex(AssertionError, 'simulation provenance'): self.verify()

    def test_wrong_original_reporting_or_binding_source_hash_is_rejected(self):
        for key in ('verifier', 'binding_helper'):
            with self.subTest(key=key):
                original = self.amendment['analysis_files'][key]['original_sha256']
                self.amendment['analysis_files'][key]['original_sha256'] = 'e' * 64; self.seal()
                with self.assertRaisesRegex(AssertionError, 'original source mismatch'): self.verify()
                self.amendment['analysis_files'][key]['original_sha256'] = original; self.seal()

    def test_amended_report_cannot_drop_or_change_selection_binding(self):
        self.documents['report']['report']['analysis_amendment']['sha256'] = 'e' * 64
        with self.assertRaisesRegex(AssertionError, 'Report differs'): self.verify()

    def test_original_release_must_bind_selection_logical_and_original_byte_hash(self):
        for key in ('selection_sha256', 'selection_file_sha256'):
            with self.subTest(key=key):
                original = self.documents['release']['release'][key]
                self.documents['release']['release'][key] = 'e' * 64
                with self.assertRaisesRegex(AssertionError, 'Original release'): self.verify()
                self.documents['release']['release'][key] = original

    def test_missing_companion_and_wrong_public_alias_are_rejected(self):
        removed = self.artifacts.pop('analysis_diff')
        with self.assertRaisesRegex(AssertionError, 'every declared public proof'): self.verify()
        self.artifacts['analysis_diff'] = {**removed, 'url': 'different.patch'}
        with self.assertRaisesRegex(AssertionError, 'companion URL'): self.verify()

    def test_descriptor_failure_filenames_must_match_explicit_public_aliases(self):
        self.amendment['failed_attempt']['journal']['filename'] = 'original-client-journal.json'
        self.amendment['failed_attempt']['log']['filename'] = 'original-selection-error.txt'
        self.seal()
        with self.assertRaisesRegex(AssertionError, 'filename differs'): self.verify()

    def test_failure_journal_cannot_claim_success_fit_completion_or_a_retry(self):
        original = self.raw['analysis_failure_journal']
        for change in ({'state': 'completed'}, {'return_code': 0}, {'automatic_retries': 1}, {'model_fit_reached': True}, {'fit_completed': True}):
            with self.subTest(change=change):
                journal = json.loads(original); journal.update(change)
                self.raw['analysis_failure_journal'] = json.dumps(journal).encode()
                self.amendment['failed_attempt']['journal']['sha256'] = sha(self.raw['analysis_failure_journal']); self.seal()
                with self.assertRaisesRegex(AssertionError, 'journal'): self.verify()

    def test_original_journal_without_fit_marker_is_reported_as_a_metadata_limit(self):
        result = self.verify()
        self.assertFalse(result['failure_journal']['fit_stage_marker_present'])
        self.assertFalse(result['failure_journal']['independently_proves_no_fit'])

    def test_companion_transfer_hash_cannot_replace_descriptor_source_identity(self):
        self.raw['analysis_verifier_source'] += b'# substituted source\n'; self.seal()
        with self.assertRaisesRegex(AssertionError, 'Descriptor companion binding'): self.verify()

    def test_failed_attempt_must_explicitly_precede_any_model_fit(self):
        self.amendment['failed_attempt']['model_fit_reached'] = True; self.seal()
        with self.assertRaises(AssertionError): self.verify()

    def test_descriptor_created_after_selection_is_rejected(self):
        self.amendment['created_utc'] = '2026-01-01T00:01:01+00:00'; self.seal()
        with self.assertRaisesRegex(AssertionError, 'before selection'): self.verify()

    def test_unamended_metadata_cannot_smuggle_an_orphan_descriptor(self):
        for key in ('selection', 'report'): self.documents[key][key].pop('analysis_amendment')
        with self.assertRaisesRegex(AssertionError, 'Selection does not bind'): self.verify()

    def test_unamended_legacy_context_requires_no_analysis_artifacts_or_binding(self):
        for key in ('selection', 'report'): self.documents[key][key].pop('analysis_amendment')
        self.assertEqual(verify_analysis_amendment(self.documents, {}, {}), {'present': False})


class BoundModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='afterlight-helper-guards-')
        self.project = Path(self.temp.name) / 'bound'
        self.shadow = Path(self.temp.name) / 'shadow'
        self.original_path = list(sys.path)
        self.original_cache = {name: module for name, module in sys.modules.copy().items() if scientific(name)}
        for name in self.original_cache: sys.modules.pop(name)
        self.sources = self.make_project(self.project)
        self.make_project(self.shadow)

    def tearDown(self):
        for name in list(sys.modules):
            if scientific(name): sys.modules.pop(name)
        sys.modules.update(self.original_cache)
        sys.path[:] = self.original_path
        self.temp.cleanup()

    def make_project(self, directory):
        content = {relative: f'TOKEN = {name!r}\n' for name, relative in PURE_HELPER_FILES.items()}
        content['evaluation/metrics.py'] = 'def identity(): return "verified synthetic helper"\n'
        content['evaluation/protocol.py'] = 'from .metrics import identity\nREFERENCE = identity()\n'
        content['models/residual.py'] = 'from evaluation.protocol import REFERENCE\ndef decision(): return REFERENCE\n'
        content['models/analytical.py'] = 'from .residual import decision\ndef analyze(): return decision()\n'
        content['evaluation/selectors.py'] = 'def choose():\n from models.analytical import analyze\n return analyze()\n'
        content['evaluation/comparison.py'] = 'from .selectors import choose\nRESULT = choose()\n'
        hashes = {}
        for relative, text in content.items():
            path = directory / relative; path.parent.mkdir(parents=True, exist_ok=True)
            raw = text.encode(); path.write_bytes(raw); hashes[relative] = sha(raw)
        return hashes

    def module_at(self, name, directory):
        spec = spec_from_file_location(name, directory / PURE_HELPER_FILES[name])
        module = module_from_spec(spec)
        sys.modules[name] = module
        return module

    def load(self):
        return bound_scientific_modules(self.sources, project=self.project)

    def test_all_nine_actual_module_origins_and_relative_dependencies_are_bound(self):
        modules = self.load()
        self.assertEqual(set(modules), set(PURE_HELPER_FILES))
        self.assertEqual(modules['evaluation.comparison'].RESULT, 'verified synthetic helper')
        for name, module in modules.items():
            expected = (self.project / PURE_HELPER_FILES[name]).resolve()
            self.assertEqual(Path(module.__file__).resolve(), expected)
            self.assertEqual(Path(module.__spec__.origin).resolve(), expected)
            self.assertEqual(Path(module.__spec__.loader.path).resolve(), expected)
        self.assertEqual(Path(modules['models.residual'].decision.__code__.co_filename), self.project / 'models/residual.py')

    def test_sys_path_shadow_packages_are_not_executed_or_used(self):
        for package in ('models', 'evaluation'):
            (self.shadow / package / '__init__.py').write_text('raise RuntimeError("FOREIGN SHADOW EXECUTED")\n', encoding='utf-8')
        sys.path.insert(0, str(self.shadow))
        before = list(sys.path)
        modules = self.load()
        self.assertEqual(modules['evaluation.selectors'].choose(), 'verified synthetic helper')
        self.assertEqual(sys.path, before)

    def test_cached_foreign_package_is_rejected_even_with_identical_source_bytes(self):
        self.module_at('models', self.shadow)
        self.assertEqual((self.shadow / 'models/__init__.py').read_bytes(), (self.project / 'models/__init__.py').read_bytes())
        with self.assertRaisesRegex(ValueError, 'origin/hash mismatch: models'): self.load()

    def test_cached_foreign_submodule_is_rejected(self):
        self.module_at('evaluation.protocol', self.shadow)
        with self.assertRaisesRegex(ValueError, 'origin/hash mismatch: evaluation.protocol'): self.load()

    def test_matching_file_with_foreign_spec_origin_is_rejected(self):
        module = self.module_at('models.residual', self.project)
        module.__spec__.origin = str(self.shadow / 'models/residual.py')
        with self.assertRaisesRegex(ValueError, 'origin/hash mismatch'): self.load()

    def test_matching_file_and_spec_with_foreign_loader_path_is_rejected(self):
        module = self.module_at('models.residual', self.project)
        module.__spec__.loader.path = str(self.shadow / 'models/residual.py')
        with self.assertRaisesRegex(ValueError, 'origin/hash mismatch'): self.load()

    def test_module_with_missing_origin_and_negative_import_cache_are_rejected(self):
        for cached in (None, self.module_at('models', self.project)):
            if cached is not None: cached.__spec__ = None
            sys.modules['models'] = cached
            with self.subTest(cached=cached), self.assertRaisesRegex(ValueError, 'origin/hash mismatch'): self.load()

    def test_unexpected_cached_scientific_submodule_is_rejected(self):
        sys.modules['models.unbound'] = object()
        with self.assertRaisesRegex(ValueError, 'Unexpected scientific helper'): self.load()

    def test_source_digest_mismatch_prevents_any_helper_execution(self):
        (self.project / 'evaluation/metrics.py').write_bytes(b'raise RuntimeError("UNVERIFIED SOURCE EXECUTED")\n')
        with self.assertRaisesRegex(ValueError, 'bytes differ'): self.load()
        self.assertFalse(any(scientific(name) for name in sys.modules))

    def test_repeated_load_recompiles_verified_bytes_instead_of_stale_cached_functions(self):
        first = self.load()
        first['evaluation.metrics'].identity = lambda: 'poisoned cached function'
        second = self.load()
        self.assertIsNot(first['evaluation.metrics'], second['evaluation.metrics'])
        self.assertEqual(second['evaluation.comparison'].RESULT, 'verified synthetic helper')
        self.assertEqual(second['evaluation.selectors'].choose(), 'verified synthetic helper')

    def test_timestamp_valid_but_poisoned_pyc_is_not_executed(self):
        path = self.project / 'evaluation/metrics.py'
        original = path.read_bytes()
        poisoned = original.replace(b'verified', b'poisoned')
        self.assertEqual(len(original), len(poisoned))
        path.write_bytes(poisoned)
        py_compile.compile(str(path), doraise=True)
        cached_stat = path.stat()
        path.write_bytes(original)
        os.utime(path, ns=(cached_stat.st_atime_ns, cached_stat.st_mtime_ns))
        spec = spec_from_file_location('evaluation.metrics', path)
        ordinary = module_from_spec(spec)
        exec(spec.loader.get_code('evaluation.metrics'), ordinary.__dict__)
        self.assertEqual(ordinary.identity(), 'poisoned synthetic helper', 'Fixture must reproduce timestamp-valid stale bytecode')
        modules = self.load()
        self.assertEqual(modules['evaluation.comparison'].RESULT, 'verified synthetic helper')

    def test_partial_execution_failure_restores_preexisting_cache(self):
        original = self.module_at('evaluation', self.project)
        path = self.project / 'evaluation/comparison.py'
        path.write_bytes(b'raise RuntimeError("synthetic failure")\n')
        self.sources['evaluation/comparison.py'] = sha(path.read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'synthetic failure'): self.load()
        self.assertIs(sys.modules['evaluation'], original)
        self.assertEqual({name for name in sys.modules if scientific(name)}, {'evaluation'})


if __name__ == '__main__': unittest.main(verbosity=2)
