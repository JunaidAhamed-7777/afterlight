"""Synthetic summary contract tests, never experiment/benchmark evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from scripts.export_study_summary import project_summary, assert_no_overlap


def fixtures(mode='learned'):
    source = {'source_commit': 'f'*40, 'source_code_sha256': 'a'*64}
    episodes = [dict(split='train', demand_group_id='train'),
                dict(split='validation', demand_group_id='validation'),
                dict(split='test', demand_group_id='test1'), dict(split='test', demand_group_id='test2')]
    study = {'sha256': '1'*64, 'study': {'source': source, 'episodes': episodes,
             'protocol': {'heldout_regimes': ['heavy'], 'heldout_route_families': ['unseen'], 'civilian_weight': 1}}}
    comparison = {'episodes': 2, 'demand_groups': 2, 'paired_feasible_episodes': 1,
                  'selected_failures': 1, 'comparator_failures': 0,
                  'selected_status_counts': {'completed': 1, 'censored': 1},
                  'comparator_status_counts': {'completed': 2}, 'changed_action_rate': .5,
                  'conditional_mean_delta_j_s': -1.5,
                  'uncertainty': {'interval': None, 'groups': 1, 'reason': 'insufficient independent demand groups'},
                  'records': [dict(conditional_delta_ambulance_s=-2., civilian_delta_s=.5),
                              dict(conditional_delta_ambulance_s=None, civilian_delta_s=None)]}
    ids = ['learned-vs-fixed', 'learned-vs-analytical'] if mode == 'learned' else ['analytical-vs-fixed']
    report = {'sha256': '2'*64, 'report': {'status': 'audited_released_test_evidence',
              'automatic_benefit_claim': False, 'mode': mode, 'source': source,
              'study_sha256': study['sha256'], 'selection_sha256': '3'*64, 'release_sha256': '4'*64,
              'protocol_sha256': '5'*64, 'test_attempt_sha256': '6'*64,
              'all_world_status_counts': {'completed': 12, 'censored': 2},
              'comparisons': {key: deepcopy(comparison) for key in ids}, 'created_utc': 'synthetic-only'}}
    selection = {'sha256': '3'*64, 'selection': {'source': source, 'validation_fixed_selection': {'lead_s': 5}}}
    release = {'sha256': '4'*64, 'release': {'selected_model_sha256': 'c'*64 if mode == 'learned' else None}}
    artifacts = [{'kind': 'report', 'url': 'report.json', 'sha256': 'b'*64, 'bytes': 1}]
    if mode == 'learned': artifacts.append({'kind': 'model', 'url': 'model.json', 'sha256': 'c'*64, 'bytes': 1})
    return study, report, selection, release, artifacts


class StudySummaryContractTests(unittest.TestCase):
    def test_failures_stay_headline_and_means_use_only_finite_pairs(self):
        result = project_summary(*fixtures())
        self.assertEqual(result['counts'], dict(train=1, validation=1, test=2, test_worlds=14, test_demand_groups=2))
        self.assertEqual(result['scope'], 'offline_cached_candidate_selection')
        self.assertFalse(result['automatic_benefit_claim'])
        first = result['comparisons'][0]
        self.assertEqual(first['selected_failures'], 1)
        self.assertEqual(first['paired_feasible_episodes'], 1)
        self.assertEqual(first['mean_delta_j_s'], -1.5)
        self.assertEqual(first['mean_delta_ambulance_s'], -2)
        self.assertEqual(first['mean_delta_civilian_s'], .5)
        self.assertIsNone(first['interval_95_j_s'])
        self.assertEqual(first['selected_status_counts'], dict(completed=1, censored=1, invalid=0, infrastructure_error=0))

    def test_baseline_only_has_no_model_or_learned_label(self):
        result = project_summary(*fixtures('baseline_only'))
        self.assertIsNone(result['provenance']['model_sha256'])
        self.assertEqual([item['id'] for item in result['comparisons']], ['analytical-vs-fixed'])
        self.assertEqual(result['comparisons'][0]['selected_label'], 'Analytical')

    def test_incomplete_comparators_worlds_or_model_identity_cannot_publish(self):
        values = fixtures(); values[1]['report']['comparisons'].pop('learned-vs-analytical')
        with self.assertRaisesRegex(ValueError, 'comparator set'): project_summary(*values)
        values = fixtures(); values[1]['report']['all_world_status_counts']['completed'] -= 1
        with self.assertRaisesRegex(ValueError, 'seven-world'): project_summary(*values)
        values = fixtures(); values[4][-1]['sha256'] = 'd'*64
        with self.assertRaisesRegex(ValueError, 'model bytes'): project_summary(*values)

    def test_infrastructure_failure_cannot_be_a_complete_published_study(self):
        values = fixtures()
        for item in values[1]['report']['comparisons'].values():
            item['selected_status_counts'] = {'completed': 1, 'infrastructure_error': 1}
        with self.assertRaisesRegex(ValueError, 'Infrastructure failures'): project_summary(*values)

    def test_publication_never_adds_files_inside_a_frozen_selection(self):
        selection = Path('local-runtime/synthetic-selection').resolve()
        for destination in (selection, selection/'publication', selection.parent):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, 'frozen selection'):
                    assert_no_overlap(destination, (selection,))
        assert_no_overlap(selection.parent/'synthetic-public-pack', (selection,))

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the cross-language viewer contract')
    def test_python_projection_is_accepted_by_the_production_typescript_validator(self):
        module = (Path(__file__).resolve().parents[2]/'web/src/studySummary.ts').as_uri()
        code = ('import fs from "node:fs"; import {validateStudySummary} from '+json.dumps(module)+';'
                'validateStudySummary(JSON.parse(fs.readFileSync(0,"utf8")));')
        for mode in ('learned', 'baseline_only'):
            with self.subTest(mode=mode):
                result = subprocess.run([shutil.which('node'), '--experimental-strip-types', '--input-type=module', '-e', code],
                                        input=json.dumps(project_summary(*fixtures(mode))), capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
