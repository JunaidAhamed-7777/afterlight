"""Synthetic orchestration tests only; never invoke SUMO."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.collector import collect_split, _input_directory
from evaluation.pilot import PilotAuditError
from models.analytical import AnalyticalConfig
from dataclasses import asdict


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.study_dir=self.root/'local-runtime/study'
        self.output=self.root/'local-runtime/attempt'
        demand_dir=self.study_dir/'inputs/demand/case'
        demand_dir.mkdir(parents=True)
        (demand_dir/'demand.json').write_text(json.dumps({'dispatch_s':2,'vehicles':[{'id':'civilian'},{'id':'ambulance'}]}))
        episode={'episode_id':'episode','case_id':'case','demand_group_id':'group','split':'train','regime':'sparse',
            'seed':7,'dispatch_s':2,'pickup_id':'pickup','hospital_id':'hospital','route_family':'route',
            'demand_sha256':'demand','network_sha256':'network','demand_directory':'inputs/demand/case'}
        self.estimator={'version':'unit-fixture','config':asdict(AnalyticalConfig())}
        self.study={'source':{'source_commit':'commit','source_code_sha256':'source'},'dependencies':{'sumo':'unit'},
            'episodes':[episode],'network':{'directory':'inputs/network'},'pilot_evidence':{'sumo_version':'unit'},
            'budget':{'max_rollouts':7,'max_wall_time_s':1000,'split_start_budgets_s':{'train':1000}},
            'protocol':{'analytical_estimator':self.estimator,'queue_scope':'synthetic fixture'},
            'spec':{'timing':{'horizon_s':10,'drain_s':10,'step_s':.5,'sample_s':1,'sensor_lag_s':1,'recovery_window_s':[2,20]},
                    'analytical_config':asdict(AnalyticalConfig())}}

    def mocks(self, *, version='unit', audit_error=None, runtime_changes=None):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('sim.network.read_network',return_value={}))
        stack.enter_context(patch('evaluation.collector.load_study',return_value={'sha256':'study','study':self.study}))
        runtime=stack.enter_context(patch('evaluation.collector.assert_study_runtime',side_effect=runtime_changes))
        stack.enter_context(patch('evaluation.collector.assert_saved_inputs'))
        audit=stack.enter_context(patch('evaluation.collector.audit_pilot_world',side_effect=audit_error))
        stack.enter_context(patch('models.analytical.estimate_candidates',return_value={**self.estimator,
            'scores':[{'lead_s':lead,'analytical_cost_s':1} for lead in (0,5,10,20,30)]}))
        def run(**kwargs):
            kwargs['output'].mkdir(parents=True)
            (kwargs['output']/'outcome.json').write_text('{"synthetic_unit_fixture":true}')
            return {'sumo_version':version,'status':'completed','policy':kwargs['policy'],'events':[], 'frames':[{'t':0,'signals':[]},{'t':20,'signals':[]}], 'metrics':{'status':'completed','validity_reasons':[],
                'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
                'ambulance_journey_s':3,'civilian_mean_excess_s':1,'runtime_s':.1,'horizon_s':10,'drain_end_s':20,
                'queue_samples':[{'t':0,'queue_count':0},{'t':20,'queue_count':0}]},
                'decision':{'request_plan':{},'observation':{'synthetic_unit_fixture':True}}}
        runner=stack.enter_context(patch('sim.run.run_world',side_effect=run))
        return runner,audit,runtime

    def records(self):
        return json.loads((self.output/'outcomes.json').read_text()),json.loads((self.output/'collection.json').read_text())

    def test_test_split_is_rejected_without_mutation(self):
        with self.assertRaisesRegex(ValueError,'test requires'):
            collect_split(self.study_dir,'test',self.output)
        self.assertFalse(self.output.exists())

    def test_complete_split_retains_seven_worlds_and_five_candidates(self):
        runner,audit,_=self.mocks()
        result=collect_split(self.study_dir,'train',self.output)
        rows,manifest=self.records()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(runner.call_count,7);self.assertEqual(audit.call_count,7)
        self.assertEqual(len(rows),7);self.assertEqual(manifest['unattempted_worlds'],0)
        self.assertTrue(all(len(row['signal_audit_input_sha256'])==64 for row in rows))
        self.assertTrue((self.output/rows[0]['raw_world_directory']/'signal-audit-input.json').is_file())
        candidates=json.loads((self.output/'candidate-outcomes.json').read_text())
        self.assertEqual([row['lead_s'] for row in candidates],[0,5,10,20,30])
        self.assertTrue(all(row['recovery_excess_queue_area_vehicle_s']==0 for row in rows))
        self.assertEqual(runner.call_args.kwargs['demand_dir'],self.study_dir/'inputs/demand/case')

    def test_wrong_actual_version_retains_failure_and_unattempted_inventory(self):
        runner,audit,_=self.mocks(version='changed')
        with self.assertRaises(RuntimeError):collect_split(self.study_dir,'train',self.output)
        rows,manifest=self.records()
        self.assertEqual(len(rows),1);self.assertEqual(audit.call_count,0)
        self.assertEqual(rows[0]['status'],'infrastructure_error')
        self.assertIsNone(rows[0]['ambulance_journey_s'])
        self.assertEqual(rows[0]['accounting']['completed'],1)
        self.assertEqual(manifest['unattempted_worlds'],6)
        self.assertEqual(len(manifest['world_inventory']),7)
        self.assertTrue((self.output/rows[0]['raw_world_directory']/'outcome.json').exists())

    def test_failed_audit_cannot_produce_finite_objective(self):
        self.mocks(audit_error=PilotAuditError('synthetic bad signal'))
        with self.assertRaises(RuntimeError):collect_split(self.study_dir,'train',self.output)
        rows,_=self.records()
        self.assertEqual(rows[0]['status'],'invalid')
        self.assertIn('evidence_audit_failed',rows[0]['validity_reasons'])
        self.assertIsNone(rows[0]['civilian_mean_excess_s'])

    def test_existing_attempt_is_never_overwritten(self):
        self.mocks();self.output.mkdir(parents=True)
        sentinel=self.output/'preserve';sentinel.write_text('original')
        with self.assertRaises(FileExistsError):collect_split(self.study_dir,'train',self.output)
        self.assertEqual(list(self.output.iterdir()),[sentinel])
        self.assertEqual(sentinel.read_text(),'original')

    def test_runtime_change_before_world_is_retained_without_invocation(self):
        runner,_,_=self.mocks(runtime_changes=[None,ValueError('changed dependency')])
        with self.assertRaises(RuntimeError):collect_split(self.study_dir,'train',self.output)
        rows,manifest=self.records()
        self.assertEqual(runner.call_count,0)
        self.assertEqual(len(rows),1)
        self.assertEqual(manifest['unattempted_worlds'],7)
        self.assertIsNone(rows[0]['signal_audit_input_sha256'])

    def test_first_runner_failure_keeps_null_signal_hash_and_failure_row(self):
        runner,_,_=self.mocks()
        runner.side_effect=RuntimeError('synthetic runner failure')
        with self.assertRaises(RuntimeError):collect_split(self.study_dir,'train',self.output)
        rows,manifest=self.records()
        self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]['signal_audit_input_sha256'])
        self.assertEqual(rows[0]['status'],'infrastructure_error')
        self.assertEqual(manifest['runner_invocations'],1)
        self.assertEqual(manifest['unattempted_worlds'],6)

    def test_split_budget_is_proportional_not_whole_study_allowance(self):
        self.mocks()
        other=deepcopy(self.study['episodes'][0])
        other.update(episode_id='other',case_id='other',split='validation')
        self.study['episodes'].append(other)
        self.study['budget']['split_start_budgets_s']={'train':500,'validation':500}
        result=collect_split(self.study_dir,'train',self.output)
        self.assertEqual(result['split_start_budget_s'],500)

    def test_runtime_root_symlink_is_rejected_without_output_mutation(self):
        self.mocks()
        runtime_path=self.root/'local-runtime'
        original_is_symlink=Path.is_symlink
        def redirected(path):
            return True if path==runtime_path else original_is_symlink(path)
        with patch.object(Path,'is_symlink',redirected),self.assertRaisesRegex(ValueError,'must not redirect'):
            collect_split(self.study_dir,'train',self.output)
        self.assertFalse(self.output.exists())

    def test_input_paths_cannot_escape_frozen_directory(self):
        for relative in ('../elsewhere','/tmp/elsewhere','inputs/../../elsewhere','inputs\\demand'):
            with self.subTest(relative=relative),self.assertRaises(ValueError):
                _input_directory(self.study_dir,relative)


if __name__=='__main__':unittest.main()
