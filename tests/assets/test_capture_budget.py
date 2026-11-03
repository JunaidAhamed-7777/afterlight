"""Synthetic packaging arithmetic; no capture, browser or scientific inputs."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('capture_budget', ROOT / 'web/tests/capture_budget.py')
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


def manifest(files):
    return {'files': {name: {'bytes': size} for name, size in files.items()},
            'total_bytes': sum(files.values())}


class CaptureBudget(unittest.TestCase):
    def test_first_video_adds_to_the_complete_existing_inventory(self):
        value = manifest({'city.glb': 20_000_000, 'recordings.gz': 10_000_000})
        result = budget.project_release_budget(value, 6_000_000)
        self.assertEqual(result['current_total_bytes'], 30_000_000)
        self.assertEqual(result['existing_video_bytes'], 0)
        self.assertEqual(result['projected_total_bytes'], 36_000_000)
        self.assertFalse(result['replaces_existing_video'])
        self.assertTrue(result['within_limit'])

    def test_replacement_grows_by_only_the_difference_not_a_second_video(self):
        # Reproduces the retained packaging failure's arithmetic, not traffic.
        value = manifest({'other-public-files': 40_286_058, budget.VIDEO_PATH: 6_670_560})
        result = budget.project_release_budget(value, 6_672_451)
        self.assertEqual(result['current_total_bytes'], 46_956_618)
        self.assertEqual(result['existing_video_bytes'], 6_670_560)
        self.assertEqual(result['new_video_bytes'], 6_672_451)
        self.assertEqual(result['projected_total_bytes'], 46_958_509)
        self.assertTrue(result['replaces_existing_video'])
        self.assertTrue(result['within_limit'])
        self.assertGreater(value['total_bytes'] + 6_672_451, budget.LIMIT_BYTES)

    def test_replacement_can_shrink_the_release(self):
        result = budget.project_release_budget(manifest({'other': 40_000_000, budget.VIDEO_PATH: 8_000_000}), 5_000_000)
        self.assertEqual(result['projected_total_bytes'], 45_000_000)
        self.assertTrue(result['within_limit'])

    def test_limit_is_strict_for_first_video_and_replacement(self):
        for existing in (False, True):
            files = {'other': 44_000_000}
            if existing:
                files[budget.VIDEO_PATH] = 3_000_000
            for new, allowed in ((5_999_999, True), (6_000_000, False), (6_000_001, False)):
                with self.subTest(existing=existing, new=new):
                    result = budget.project_release_budget(manifest(files), new)
                    self.assertEqual(result['projected_total_bytes'], 44_000_000 + new)
                    self.assertEqual(result['limit_bytes'], 50_000_000)
                    self.assertEqual(result['within_limit'], allowed)

    def test_only_the_exact_canonical_video_path_is_replaced(self):
        files = {'other/afterlight-desktop-demo.mp4': 10,
                 'media/afterlight-desktop-demo.mp4.backup': 20,
                 '/media/afterlight-desktop-demo.mp4': 30}
        first = budget.project_release_budget(manifest(files), 40)
        self.assertFalse(first['replaces_existing_video'])
        self.assertEqual(first['projected_total_bytes'], 100)
        files[budget.VIDEO_PATH] = 50
        replacement = budget.project_release_budget(manifest(files), 40)
        self.assertTrue(replacement['replaces_existing_video'])
        self.assertEqual(replacement['existing_video_bytes'], 50)
        self.assertEqual(replacement['projected_total_bytes'], 100)

    def test_zero_byte_counts_are_valid_and_inputs_are_not_mutated(self):
        for value in (manifest({}), manifest({'empty': 0, budget.VIDEO_PATH: 0})):
            with self.subTest(value=value):
                original = deepcopy(value)
                result = budget.project_release_budget(value, 0)
                self.assertEqual(result['projected_total_bytes'], 0)
                self.assertTrue(result['within_limit'])
                self.assertEqual(value, original)

    def test_negative_boolean_fractional_string_and_missing_counts_are_rejected(self):
        for invalid in (-1, True, False, 1.0, 1.25, '1', None):
            for position in ('new_video', 'manifest_total', 'file_bytes'):
                with self.subTest(invalid=invalid, position=position):
                    value = manifest({'other': 1})
                    new = invalid if position == 'new_video' else 1
                    if position == 'manifest_total':
                        value['total_bytes'] = invalid
                    if position == 'file_bytes':
                        value['files']['other']['bytes'] = invalid
                    with self.assertRaises(ValueError):
                        budget.project_release_budget(value, new)

    def test_inconsistent_totals_are_rejected(self):
        for total in (0, 2):
            with self.subTest(total=total):
                value = manifest({'other': 1})
                value['total_bytes'] = total
                with self.assertRaisesRegex(ValueError, 'complete file inventory'):
                    budget.project_release_budget(value, 1)

    def test_malformed_inventory_metadata_is_rejected(self):
        for value in (None, [], {}, {'files': [], 'total_bytes': 0},
                      {'files': {}, 'total_bytes': None},
                      {'files': {'file': {}}, 'total_bytes': 0},
                      {'files': {'file': None}, 'total_bytes': 0},
                      {'files': {1: {'bytes': 0}}, 'total_bytes': 0},
                      {'files': {'': {'bytes': 0}}, 'total_bytes': 0}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                budget.project_release_budget(value, 1)


if __name__ == '__main__':
    unittest.main()
