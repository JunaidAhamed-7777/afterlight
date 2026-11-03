"""Synthetic released-report tests; never create real test releases or run SUMO."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from evaluation.protocol import digest
from evaluation.study_reporting import _released_test_context, verify_released_test_collection, report_study


class ReleasedTestGateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.study=self.root/'local-runtime/study';self.study.mkdir(parents=True)
        self.collection=self.root/'local-runtime/test-attempt'
        release={'study_sha256':'study','protocol_sha256':'protocol','expected_worlds':7,
            'selection_directory':'selection','mode':'baseline_only'}
        self.release={'sha256':digest(release),'release':release}
        (self.study/'test-release.json').write_text(json.dumps(self.release))
        self.claim={'schema':'afterlight.test-attempt.v1','release_sha256':self.release['sha256'],
            'study_sha256':'study','protocol_sha256':'protocol','expected_worlds':7,
            'state':'claimed_before_first_test_world','output_directory':'test-attempt'}
        self.save()
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('evaluation.study_release.load_test_release',return_value=self.release))
        self.reader=stack.enter_context(patch('evaluation.study_reporting._verify_collection_evidence',return_value={'rows':[{}]*7}))

    def save(self):
        (self.study/'test-attempt.json').write_text(json.dumps({'sha256':digest(self.claim),'attempt':self.claim}))

    def test_claim_binding_precedes_any_outcomes(self):
        self.claim['release_sha256']='wrong';self.save()
        with self.assertRaisesRegex(ValueError,'outcomes not opened'):
            verify_released_test_collection(self.study,self.collection)
        self.reader.assert_not_called()

    def test_wrong_output_path_cannot_open_other_test_collection(self):
        with self.assertRaisesRegex(ValueError,'claimed output'):
            verify_released_test_collection(self.study,self.root/'local-runtime/other')
        self.reader.assert_not_called()

    def test_success_passes_exact_release_claim_manifest_keys(self):
        result=verify_released_test_collection(self.study,self.collection)
        required=self.reader.call_args.kwargs['required_manifest']
        self.assertEqual(required['release_sha256'],self.release['sha256'])
        self.assertEqual(required['test_attempt_sha256'],digest(self.claim))
        self.assertEqual(required['release_mode'],'baseline_only')
        self.assertEqual(len(result['rows']),7)

    def test_release_claim_drift_rejected_after_verification(self):
        original=_released_test_context(self.study,self.collection)
        changed={**original,'attempt_file_sha256':'changed'}
        with patch('evaluation.study_reporting._released_test_context',side_effect=[original,changed]),self.assertRaisesRegex(ValueError,'changed'):
            verify_released_test_collection(self.study,self.collection)

    def test_incomplete_released_world_inventory_rejected(self):
        self.reader.return_value={'rows':[{}]*6}
        with self.assertRaisesRegex(ValueError,'world count'):verify_released_test_collection(self.study,self.collection)


class ReportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.study_dir=self.root/'local-runtime/study';self.collection=self.root/'local-runtime/test'
        self.selection=self.root/'local-runtime/selection';self.selection.mkdir(parents=True)
        self.output=self.root/'local-runtime/report'
        pair={'sha256':'pair','selectors':{}}
        pair_path=self.selection/'analytical-vs-fixed.json';pair_path.write_text(json.dumps(pair))
        from evaluation.study_manifest import file_hash
        self.release={'mode':'baseline_only','selection_sha256':'selection',
            'comparison_artifacts_sha256':{'analytical-vs-fixed.json':file_hash(pair_path)}}
        self.context={'release':{'sha256':'release','release':self.release},'attempt':{'sha256':'attempt'},
            'selection_directory':self.selection,'release_file_sha256':'release-file','attempt_file_sha256':'attempt-file'}
        self.study={'source':{'source_commit':'unit'},'dependencies':{},'pilot_evidence':{'sumo_version':'unit'},
            'spec':{'civilian_weight':1},'protocol':{'recovery_window_s':[0,20]}}
        base={'episode_id':'episode','demand_group_id':'group','regime':'heavy','status':'completed','validity_reasons':[],
            'ambulance_journey_s':10,'civilian_mean_excess_s':1,'recovery_excess_queue_area_vehicle_s':2,
            'accounting':{'scheduled':2,'inserted':2,'completed':2,'running':0,'not_inserted':0}}
        candidates=[{**base,'policy':'fixed','lead_s':lead} for lead in (0,5,10,20,30)]
        self.verified={'release_context':self.context,'candidate_rows':candidates,'files_sha256':{},
            'rows':[*candidates,{**base,'policy':'ordinary'},{**base,'policy':'immediate'}]}
        self.comparison={'records':[{'episode_id':'episode','demand_group_id':'group','selected_lead_s':0,
            'comparator_lead_s':5,'selected_infeasible':False,'comparator_infeasible':False,'paired_delta_j_s':0}]}
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('evaluation.study_reporting.load_study',return_value={'sha256':'study','study':self.study}))
        stack.enter_context(patch('evaluation.study_reporting.assert_study_runtime'))
        stack.enter_context(patch('evaluation.study_reporting.verify_released_test_collection',return_value=self.verified))
        stack.enter_context(patch('evaluation.study_reporting._released_test_context',return_value=self.context))
        stack.enter_context(patch('evaluation.selectors.recompute_frozen_decisions',return_value=({'episode':0},{'episode':5})))
        stack.enter_context(patch('evaluation.comparison.paired_decision_report',side_effect=lambda *a,**k:deepcopy(self.comparison)))
        stack.enter_context(patch('evaluation.study_reporting.objective',side_effect=lambda row,weight:11 if row['status']=='completed' else None))
        self.fit=stack.enter_context(patch('models.residual.fit_residual',side_effect=AssertionError('no fitting')))
        self.runner=stack.enter_context(patch('sim.run.run_world',side_effect=AssertionError('no simulation')))

    def report(self):return report_study(self.study_dir,self.collection,self.output)

    def test_report_has_context_uncertainty_and_no_automatic_gain(self):
        result=self.report()['report']
        self.assertFalse(result['automatic_benefit_claim'])
        self.assertEqual(result['all_world_status_counts'],{'completed':7})
        self.assertEqual(set(result['context_policies']),{'ordinary','immediate'})
        comparison=result['comparisons']['analytical-vs-fixed']
        self.assertIsNone(comparison['uncertainty']['interval'])
        self.assertEqual(comparison['uncertainty']['reason'],'insufficient independent demand groups')
        self.assertEqual(comparison['conditional_mean_delta_recovery_vehicle_s'],0)
        self.assertTrue((self.output/'report.json').is_file())
        self.fit.assert_not_called();self.runner.assert_not_called()

    def test_failed_selected_policy_has_no_finite_conditional_recovery(self):
        self.comparison['records'][0]['selected_infeasible']=True
        self.comparison['records'][0]['paired_delta_j_s']=None
        result=self.report()['report']['comparisons']['analytical-vs-fixed']
        self.assertIsNone(result['records'][0]['conditional_delta_recovery_vehicle_s'])
        self.assertIsNone(result['conditional_mean_delta_recovery_vehicle_s'])

    def test_negative_finite_context_objective_is_not_rejected(self):
        with patch('evaluation.study_reporting.objective',return_value=-1):
            result=self.report()['report']
        self.assertEqual(result['context_policies']['ordinary']['conditional_mean_j_s'],-1)
        self.assertEqual(result['context_policies']['ordinary']['failures'],0)

    def test_existing_report_not_overwritten(self):
        self.report();before=(self.output/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):self.report()
        self.assertEqual((self.output/'report.json').read_bytes(),before)

    def test_changed_frozen_comparator_blocks_report(self):
        (self.selection/'analytical-vs-fixed.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'comparator artifact changed'):self.report()
        self.assertFalse(self.output.exists())
