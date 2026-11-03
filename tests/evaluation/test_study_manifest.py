"""Synthetic file/contract fixtures only. No SUMO or training execution."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from evaluation.protocol import digest
from evaluation.study_manifest import (prepare_study, freeze_study, load_study, validate_spec,
    file_hash, assert_saved_inputs, validate_study_links, route_membership, validate_pilot_world_binding)
from models.analytical import AnalyticalConfig


def spec_fixture():
    return {'schema':'afterlight.study-spec.v1','study_id':'unit-study','network_kind':'fixture',
        'cases':[{'case_id':split,'split':split,'seed':2000+i,'regime':'heavy' if split=='test' else 'moderate',
                  'dispatch_s':60,'pickup_id':'pickup','hospital_id':'hospital','route_family':'west-east'}
                 for i,split in enumerate(('train','validation','test'))],
        'timing':{'demand_end_s':180,'horizon_s':240,'drain_s':360,'step_s':.5,'sample_s':5,
                  'sensor_lag_s':1,'recovery_window_s':[60,600]},
        'budget':{'max_episodes':3,'max_rollouts':21,'max_wall_time_s':3600,'rationale':'Synthetic unit fixture, not measured evidence'},
        'civilian_weight':1,'analytical_config':asdict(AnalyticalConfig()),
        'model_specification':{'max_depth':3,'min_samples_leaf':5},
        'illustrative_capture':{'case_ids':[],'max_world_bytes':0,'max_total_bytes':0},'heldout_regimes':['heavy'],'heldout_route_families':[]}


class StudyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.output=self.root/'local-runtime/study'
        self.spec=spec_fixture()
        self.source={'source_commit':'a'*40,'source_code_sha256':'b'*64,'source_dirty':False}
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.network.ROOT',self.root))
        stack.enter_context(patch('sim.run.source_snapshot',return_value=self.source))
        stack.enter_context(patch('sim.run.dependency_versions',return_value={'traci':'unit','sumolib':'unit'}))
        self.runner=stack.enter_context(patch('sim.run.run_world',side_effect=AssertionError('no traffic execution')))
        stack.enter_context(patch('sim.network.read_network',return_value={}))
        def build(kind,directory):
            directory.mkdir(parents=True)
            net=directory/'network.net.xml';net.write_text('<net/>')
            manifest={'network_file_sha256':file_hash(net),'network_sha256':hashlib.sha256(
                ET.canonicalize(from_file=net,strip_text=True,with_comments=False).encode()).hexdigest()}
            (directory/'network-manifest.json').write_text(json.dumps(manifest))
            (directory/'graph.json').write_text('{}')
            return manifest
        stack.enter_context(patch('sim.network.build_network',side_effect=build))
        def demand(graph,network,**kwargs):
            return {**kwargs,'vehicles':[
                {'id':'civilian-'+str(kwargs['seed']),'type':'car','depart_s':1,'depart_pos_m':0,'route':['edge']},
                {'id':'ambulance','type':'ambulance','depart_s':kwargs['dispatch_s'],'depart_pos_m':0,'route':['edge']}]}
        stack.enter_context(patch('sim.demand.make_demand',side_effect=demand))
        evidence={'schema':'afterlight.pilot-evidence.v2','seeds':[1001,1002],'dependencies':{'traci':'unit','sumolib':'unit'},'network_sha256':hashlib.sha256(b'<net></net>').hexdigest(),
                  'demand_group_ids':['pilot-group'],'estimated_study_wall_time_s':1,'sumo_version':'synthetic'}
        self.pilot=stack.enter_context(patch('evaluation.study_manifest.validate_pilot_evidence',return_value=evidence))

    def prepared(self):
        return prepare_study(self.spec,self.root/'pilot',self.output)

    def test_prepare_freeze_are_saved_input_only(self):
        envelope=self.prepared()
        frozen=freeze_study(self.output)
        self.assertEqual(frozen['protocol'],envelope['study']['protocol'])
        self.assertEqual(load_study(self.output,require_frozen=True),envelope)
        self.assertEqual(envelope['study']['budget']['split_start_budgets_s'],dict.fromkeys(('train','validation','test'),1200))
        self.runner.assert_not_called()

    def test_spec_rejects_custom_policy_or_unbounded_cases(self):
        for mutate in (lambda s:s['analytical_config'].update(queue_headway_s=3),
                       lambda s:s.update(civilian_weight=2),lambda s:s['budget'].update(max_rollouts=20),
                       lambda s:s['cases'][0].update(regime='heavy'),lambda s:s['timing'].update(sensor_lag_s=0)):
            spec=deepcopy(self.spec);mutate(spec)
            with self.subTest(spec=spec),self.assertRaises(ValueError):validate_spec(spec)

    def test_protocol_execution_contract_mutations_rejected(self):
        study=self.prepared()['study']
        mutations={'horizon_s':241,'drain_end_s':601,'recovery_window_s':[61,600],
            'simulation_step_s':1,'source_code_sha256':'changed','source_commit':'changed',
            'controller_timing':{},'feature_schema':[], 'heldout_regimes':[]}
        for key,value in mutations.items():
            changed=deepcopy(study);changed['protocol'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_study_links(self.output,changed,verify_inputs=False)
        for change in ('sensor_lag_s','unit','order'):
            changed=deepcopy(study);features=changed['protocol']['feature_schema']
            if change=='order':features.reverse()
            else:features[0][change]='changed'
            with self.subTest(feature=change),self.assertRaises(ValueError):validate_study_links(self.output,changed,verify_inputs=False)

    def test_budget_episode_and_path_rebinding_rejected(self):
        study=self.prepared()['study']
        for mutate in (lambda s:s['budget'].update(max_wall_time_s=7200),
                       lambda s:s['budget']['split_start_budgets_s'].update(train=3600),
                       lambda s:s['episodes'][0].update(demand_directory='../elsewhere'),
                       lambda s:s['episodes'][0].update(episode_id='forged')):
            changed=deepcopy(study);mutate(changed)
            with self.assertRaises(ValueError):validate_study_links(self.output,changed,verify_inputs=False)

    def test_input_tamper_or_extra_file_rejected(self):
        study=self.prepared()['study'];extra=self.output/'inputs/extra'
        extra.write_text('extra')
        with self.assertRaises(ValueError):assert_saved_inputs(self.output,study)
        extra.unlink();(self.output/'inputs/network/graph.json').write_text('{"changed":true}')
        with self.assertRaises(ValueError):assert_saved_inputs(self.output,study)

    def test_existing_output_not_overwritten(self):
        self.prepared();before=(self.output/'study.json').read_bytes()
        with self.assertRaises(FileExistsError):self.prepared()
        self.assertEqual((self.output/'study.json').read_bytes(),before)

    def test_freeze_rejects_changed_source(self):
        self.prepared()
        with patch('sim.run.source_snapshot',return_value={**self.source,'source_dirty':True}),self.assertRaises(ValueError):
            freeze_study(self.output)
        self.assertFalse((self.output/'frozen-protocol.json').exists())

    def test_actual_route_overlap_not_disguised_by_family_label(self):
        episodes=[{'ambulance_route':['a','b'],'route_family':'ordinary','split':'train'},
                  {'ambulance_route':['a','b'],'route_family':'unseen','split':'test'}]
        with self.assertRaisesRegex(ValueError,'actual route'):route_membership(episodes,['unseen'])
        episodes[1]['ambulance_route']=['c','d']
        self.assertEqual(len(route_membership(episodes,['unseen'])),2)

    def test_pilot_raw_metrics_and_decisions_bound(self):
        estimates={'version':'synthetic','config':{},'scores':[{'lead_s':5,'analytical_cost_s':10}]}
        raw={'policy':'fixed','lead_s':5,'status':'completed','sumo_version':'unit',
             'metrics':{'runtime_s':1,'queue_samples':[],'accounting':{}},
             'decision':{'observation':{'fixture':True},'request_plan':[]}}
        row={**{k:raw[k] for k in ('policy','lead_s','status','sumo_version')},'simulator_runtime_s':1,'runtime_s':2,
             'queue_samples':[],'accounting':{},**raw['decision'],'analytical_cost_s':10,
             'analytical_config_sha256':digest({'version':'synthetic','config':{}})}
        with patch('evaluation.study_manifest.estimate_candidates',return_value=estimates):
            validate_pilot_world_binding(row,raw,{'civilian_weight':1})
            for key in ('queue_samples','observation','request_plan','simulator_runtime_s','analytical_cost_s','lead_s'):
                changed=deepcopy(row);changed[key]='changed'
                with self.subTest(key=key),self.assertRaises(ValueError):validate_pilot_world_binding(changed,raw,{'civilian_weight':1})

    def test_pilot_metadata_refuses_incomplete_or_relabelled_evidence(self):
        from evaluation.pilot import prepare_plan
        from evaluation.study_manifest import validate_pilot_metadata
        plan=prepare_plan();rows=[]
        for i,case in enumerate(plan['plan']['cases']):
            for policy in plan['plan']['policies']:
                rows.append({'split':'pilot','demand_group_id':f'group-{i}','demand_sha256':f'demand-{i}',**policy})
        execution={'status':'completed','source_dirty':False,'plan_sha256':plan['sha256'],
            'source_code_sha256':self.source['source_code_sha256'],'expected_worlds':84,'runner_invocations':84,
            'unattempted_worlds':0,'audit_failed_worlds':0,'infrastructure_failed_worlds':0,'sumo_version':'unit'}
        summary={'synthetic_fixture':True}
        with patch('evaluation.study_manifest.pilot_summary',return_value=summary):
            self.assertEqual(validate_pilot_metadata(plan,execution,rows,summary,self.spec,self.source),84)
            for key,value in [('runner_invocations',83),('status','failed'),('source_dirty',True),
                              ('source_code_sha256','changed'),('audit_failed_worlds',1)]:
                changed={**execution,key:value}
                with self.subTest(key=key),self.assertRaises(ValueError):
                    validate_pilot_metadata(plan,changed,rows,summary,self.spec,self.source)
            with self.assertRaises(ValueError):
                validate_pilot_metadata(plan,execution,rows,{'stale':True},self.spec,self.source)

    def test_symlinked_runtime_root_rejected_before_output(self):
        outside=self.root/'outside';outside.mkdir()
        runtime=self.root/'local-runtime'
        try:runtime.symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('symlink creation unavailable on this test machine')
        with self.assertRaisesRegex(ValueError,'real directory'):self.prepared()
        self.assertFalse((outside/'study').exists())

    def test_prepare_excludes_reused_pilot_seed_before_output(self):
        self.pilot.return_value['seeds']=[self.spec['cases'][0]['seed']]
        with self.assertRaisesRegex(ValueError,'pilot RNG seed'):self.prepared()
        self.assertFalse(self.output.exists())

    def test_prepare_refuses_legacy_pilot_evidence_without_seed_inventory(self):
        self.pilot.return_value.pop('seeds')
        with self.assertRaisesRegex(ValueError,'seed inventory'):self.prepared()
        self.assertFalse(self.output.exists())

    def test_spec_rejects_qualification_seed_for_all_study_splits(self):
        for index in range(3):
            spec=deepcopy(self.spec);spec['cases'][index]['seed']=7
            with self.subTest(split=spec['cases'][index]['split']),self.assertRaisesRegex(ValueError,'qualification'):
                validate_spec(spec)

    def test_reserved_seed_metadata_is_frozen(self):
        study=self.prepared()['study']
        self.assertEqual(study['protocol']['reserved_qualification_seeds'],[7])
        changed=deepcopy(study);changed['protocol']['reserved_qualification_seeds']=[]
        with self.assertRaisesRegex(ValueError,'reserved_qualification_seeds'):
            validate_study_links(self.output,changed,verify_inputs=False)

    def test_illustrative_capture_contract_frozen_before_outcomes(self):
        self.spec['illustrative_capture']={'case_ids':['test'],'max_world_bytes':1000,'max_total_bytes':6000}
        study=self.prepared()['study']
        self.assertEqual(study['protocol']['illustrative_capture'],self.spec['illustrative_capture'])
        # JSON roundtrip creates independent metadata, as loaded on Omen.
        independent=json.loads(json.dumps(study))
        independent['protocol']['illustrative_capture']={'case_ids':[],'max_world_bytes':0,'max_total_bytes':0}
        with self.assertRaisesRegex(ValueError,'illustrative_capture'):
            validate_study_links(self.output,independent,verify_inputs=False)
