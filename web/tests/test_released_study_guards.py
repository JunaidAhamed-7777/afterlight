"""Isolated byte/module guards; no Study pack, HTTP, outcomes or simulation.

The only project-shaped modules executed here are synthetic temporary files.
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import os
import py_compile
import sys
from tempfile import TemporaryDirectory
import unittest

from released_study_pack import PURE_HELPER_FILES, bound_scientific_modules, sha, strict_json


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
