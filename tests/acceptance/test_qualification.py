"""Synthetic qualification gate tests; no SUMO, benchmark or child execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import omen_acceptance as runner
from scripts import qualification_gate as gate

SOURCE={'source_commit':'a'*40,'source_dirty':False,'source_code_sha256':'b'*64,'source_files':{}}


def fixture(case='fixture-fixed'):
    config=gate.CASES[case]
    demand={'seed':7,'regime':config['regime'],'dispatch_s':60,'demand_end_s':180,
        'pickup_id':config['pickup_id'],'hospital_id':config['hospital_id'],
        'vehicles':[{'id':'ambulance','route':['edge-a','edge-b']}]}
    metrics={'status':'completed','validity_reasons':[],'accounting':{
        'scheduled':2,'inserted':2,'completed':2,'running':0,'not_inserted':0},
        'ambulance_journey_s':40,'horizon_s':240,'drain_end_s':600,'simulation_step_s':.5}
    return {'scenario':{k:v for k,v in config.items() if k!='policy'}|{'seed':7,'dispatch_s':60,'split':'pilot','route_edges':['edge-a','edge-b']},
        'provenance':SOURCE|{'network_sha256':'c'*64,'demand_sha256':'d'*64,'demand_manifest_sha256':'e'*64},
        'duration_s':600,'step_s':1,'worlds':{
            name:{'policy':'ordinary' if name=='baseline' else config['policy'],'lead_s':10,
                  'status':'completed','metrics':deepcopy(metrics)} for name in ('baseline','afterlight')}},demand


class SemanticGateTests(unittest.TestCase):
    def test_completed_fixed_pair_qualifies_semantically(self):
        replay,demand=fixture();gate.require_completed(replay,'fixture-fixed',SOURCE,demand)

    def test_invalid_or_censored_never_passes_even_with_reconciled_counts(self):
        for status in ('invalid','censored','infrastructure_error'):
            replay,demand=fixture();replay['worlds']['baseline']['status']=status
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'invalid/censored'):
                gate.require_completed(replay,'fixture-fixed',SOURCE,demand)

    def test_reasons_pending_and_missing_ambulance_reject(self):
        for edit in ('reason','pending','ambulance'):
            replay,demand=fixture();m=replay['worlds']['afterlight']['metrics']
            if edit=='reason':m['validity_reasons']=['collision']
            elif edit=='pending':m['accounting']['not_inserted']=1
            else:m['ambulance_journey_s']=None
            with self.subTest(edit=edit),self.assertRaises(ValueError):gate.require_completed(replay,'fixture-fixed',SOURCE,demand)

    def test_requested_parameters_source_route_and_timing_are_bound(self):
        for edit in ('seed','regime','policy','lead','route','source','timing','demand'):
            replay,demand=fixture()
            if edit=='seed':replay['scenario']['seed']=8
            elif edit=='regime':replay['scenario']['regime']='sparse'
            elif edit=='policy':replay['worlds']['afterlight']['policy']='immediate'
            elif edit=='lead':replay['worlds']['afterlight']['lead_s']=20
            elif edit=='route':replay['scenario']['route_edges']=['different']
            elif edit=='source':replay['provenance']['source_commit']='f'*40
            elif edit=='timing':replay['worlds']['baseline']['metrics']['horizon_s']=241
            else:demand['demand_end_s']=179
            with self.subTest(edit=edit),self.assertRaises(ValueError):gate.require_completed(replay,'fixture-fixed',SOURCE,demand)

    def test_profile_is_explicit_nine_ordered_steps_with_fixed_allocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'local-runtime/acceptance/qualification'
            plan=runner.plan(root,output,python='mock-python',profile='traffic-qualification')
            self.assertEqual(len(plan['steps']),9);self.assertEqual(plan['allocation']['worlds'],6)
            self.assertEqual(plan['allocation']['total_simulation_seconds'],3600)
            self.assertIsNone(plan['allocation']['hard_wall_time_limit_s'])
            self.assertEqual([step['id'] for step in plan['steps']][::3],['fixture-fixed-run','fixture-ordinary-run','city-sparse-run'])
            for step in plan['steps'][::3]:
                argv=step['argv'];self.assertEqual(argv[argv.index('--split')+1],'pilot')
                self.assertEqual(argv[argv.index('--seed')+1],'7')
            self.assertFalse(output.exists())


class ArtifactGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.attempt=Path(self.temp.name)
        self.write(self.attempt/'run.json',{'schema':'afterlight.acceptance-run.v1','plan':{'profile':'traffic-qualification'},'source_identity':{'source':SOURCE}})

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def prepare(self,case):
        directory=self.attempt/'traffic'/case;replay,demand=fixture(case)
        self.write(directory/'replay.json',replay);self.write(directory/'demand/demand.json',demand)
        audit={'replay_sha256':hashlib.sha256((directory/'replay.json').read_bytes()).hexdigest(),
               'ordinary_negative_control':'passed' if case=='fixture-ordinary' else 'not_this_policy'}
        self.write(directory/'audit.json',audit)
        return directory,audit

    def run_gate(self,case,audit):
        return gate.qualify(self.attempt,case,audit_fn=lambda directory,write_result:deepcopy(audit) if directory.name==case else json.loads((directory/'audit.json').read_text()),source_fn=lambda:deepcopy(SOURCE))

    def test_exact_replay_audit_required_and_result_is_fresh_only(self):
        directory,audit=self.prepare('fixture-fixed')
        result=self.run_gate('fixture-fixed',audit);self.assertEqual(result['status'],'qualified')
        with self.assertRaises(FileExistsError):self.run_gate('fixture-fixed',audit)
        self.assertEqual(json.loads((directory/'qualification.json').read_text()),result)

    def test_unrelated_audit_or_replay_hash_rejects_without_result(self):
        for mismatch in ('audit','hash'):
            directory,audit=self.prepare('fixture-fixed')
            if mismatch=='audit':audit['extra']='different'
            else:
                audit['replay_sha256']='0'*64;self.write(directory/'audit.json',audit)
            with self.subTest(mismatch=mismatch),self.assertRaisesRegex(ValueError,'exact retained replay'):
                self.run_gate('fixture-fixed',audit)
            self.assertFalse((directory/'qualification.json').exists())

    def test_negative_control_requires_prior_same_inputs_and_actual_pass(self):
        _,first=self.prepare('fixture-fixed');self.run_gate('fixture-fixed',first)
        directory,audit=self.prepare('fixture-ordinary');audit['ordinary_negative_control']='not_this_policy'
        self.write(directory/'audit.json',audit)
        with self.assertRaisesRegex(ValueError,'negative control'):self.run_gate('fixture-ordinary',audit)
        audit['ordinary_negative_control']='passed';self.write(directory/'audit.json',audit)
        previous=self.attempt/'traffic/fixture-fixed/qualification.json';result=json.loads(previous.read_text())
        result['input_hashes']['demand_sha256']='f'*64;self.write(previous,result)
        with self.assertRaisesRegex(ValueError,'Prior qualification record'):self.run_gate('fixture-ordinary',audit)
        self.assertFalse((directory/'qualification.json').exists())

    def test_city_requires_both_raw_predecessors_and_untampered_records(self):
        _,fixed=self.prepare('fixture-fixed');self.run_gate('fixture-fixed',fixed)
        _,ordinary=self.prepare('fixture-ordinary');self.run_gate('fixture-ordinary',ordinary)
        directory,city=self.prepare('city-sparse')
        prior=self.attempt/'traffic/fixture-fixed/replay.json'
        replay=json.loads(prior.read_text());replay['scenario']['seed']=8;self.write(prior,replay)
        with self.assertRaisesRegex(ValueError,'exact retained replay'):self.run_gate('city-sparse',city)
        self.assertFalse((directory/'qualification.json').exists())

    def test_complete_chain_qualifies_and_huge_journey_is_controlled_rejection(self):
        for case in gate.CASES:
            _,audit=self.prepare(case);result=self.run_gate(case,audit)
            self.assertEqual(result['status'],'qualified')
        replay,demand=fixture();replay['worlds']['baseline']['metrics']['ambulance_journey_s']=10**1000
        with self.assertRaises(ValueError):gate.require_completed(replay,'fixture-fixed',SOURCE,demand)


if __name__=='__main__':unittest.main()
