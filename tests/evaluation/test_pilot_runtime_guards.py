"""Pure/mocked runtime-integrity contracts; no SUMO execution or measured data.

Execute only on Omen. Fake world data stays inside temporary test directories.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evaluation.pilot import prepare_plan, execute_plan, PilotAuditError
from sim.audit import audit_world_signals


def legal_world(policy='ordinary', version='SUMO 1.28.0'):
    return {'world_id':policy,'policy':policy,'sumo_version':version,'status':'completed',
            'decision':{'observation':{},'request_plan':{}},
            'events':[{'t':0,'kind':'green','junction':'J','phase':0},
                      {'t':8,'kind':'yellow','junction':'J','phase':0},
                      {'t':11,'kind':'all_red','junction':'J'},
                      {'t':12,'kind':'green','junction':'J','phase':1}],
            'frames':[{'t':t,'signals':[{'id':'J','state':state}],'vehicles':[]}
                      for t,state in ((0,'Gr'),(8,'yr'),(11,'rr'),(12,'rG'))],
            'metrics':{'status':'completed','validity_reasons':[],
                       'ambulance_journey_s':10,'civilian_mean_excess_s':0,
                       'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0},
                       'horizon_s':240,'drain_end_s':600,'runtime_s':1,
                       'queue_samples':[{'t':0,'queue_count':0},{'t':600,'queue_count':0}]}}


NETWORK={'signals':{'J':{'greens':['Gr','rG']}}}
DEPENDENCIES={'traci':'1.28.0','sumolib':'1.28.0','eclipse-sumo':None,'sumo-data':None}
SOURCE={'source_commit':'a'*40,'source_dirty':False,'source_code_sha256':'b'*64,'source_files':{}}


class WorldSignalAuditTests(unittest.TestCase):
    def test_legal_states_and_transitions_pass(self):
        audit_world_signals(legal_world(),NETWORK,60)

    def test_short_yellow_cannot_be_eligible(self):
        world=legal_world();world['events'][2]['t']=10
        with self.assertRaisesRegex(ValueError,'too-short'):
            audit_world_signals(world,NETWORK,60)

    def test_stale_sampled_signal_is_rejected(self):
        world=legal_world();world['frames'][1]['signals'][0]['state']='Gr'
        with self.assertRaisesRegex(ValueError,'frame/event'):
            audit_world_signals(world,NETWORK,60)

    def test_empty_frames_cannot_bypass_audit(self):
        world=legal_world();world['frames']=[]
        with self.assertRaisesRegex(ValueError,'frames starting at zero'):
            audit_world_signals(world,NETWORK,60)

    def test_missing_signal_sample_is_explicitly_rejected(self):
        world=legal_world();world['frames'][0]['signals']=[]
        with self.assertRaisesRegex(ValueError,'missing or duplicate'):
            audit_world_signals(world,NETWORK,60)

    def test_ordinary_cannot_contain_priority_events(self):
        world=legal_world();world['events'].append({'t':12,'kind':'request','junction':'J'})
        with self.assertRaisesRegex(ValueError,'Ordinary'):
            audit_world_signals(world,NETWORK,60)

    def test_bad_event_timestamps_and_unknown_junction_are_rejected(self):
        for value in (float('nan'),float('inf'),-1,True):
            world=legal_world();world['events'][0]['t']=value
            with self.subTest(time=value),self.assertRaisesRegex(ValueError,'timestamp'):
                audit_world_signals(world,NETWORK,60)
        world=legal_world();world['events'][0]['junction']='unknown'
        with self.assertRaisesRegex(ValueError,'unknown signal'):
            audit_world_signals(world,NETWORK,60)
        world=legal_world();world['events'][1],world['events'][2]=world['events'][2],world['events'][1]
        with self.assertRaisesRegex(ValueError,'not monotonic'):
            audit_world_signals(world,NETWORK,60)

    def test_phase_index_cannot_use_python_negative_index_or_bool(self):
        for phase in (-1,2,True,0.0):
            world=legal_world();world['events'][0]['phase']=phase
            with self.subTest(phase=phase),self.assertRaisesRegex(ValueError,'phase index'):
                audit_world_signals(world,NETWORK,60)

    def priority_world(self):
        world=legal_world('fixed')
        world['metrics']['simulation_step_s']=.5
        world['metrics']['drain_end_s']=100
        world['decision']['request_plan']={'J':20}
        world['frames'].append({'t':100,'signals':[{'id':'J','state':'rG'}],'vehicles':[]})
        world['events'] += [
            {'t':12,'kind':'request_planned','junction':'J','phase':1,'request_at_s':20},
            {'t':20,'kind':'request','junction':'J','phase':1},
            {'t':20,'kind':'priority_green','junction':'J','phase':1},
            {'t':55,'kind':'release','junction':'J','reason':'max_hold'}]
        return world

    def test_duplicate_plans_are_not_hidden_by_dictionary_collapse(self):
        world=self.priority_world();world['events'].insert(5,deepcopy(world['events'][4]))
        with self.assertRaisesRegex(ValueError,'duplicate request_planned'):
            audit_world_signals(world,NETWORK,12)

    def test_priority_hold_is_audited_with_actual_integration_step(self):
        world=self.priority_world()
        self.assertEqual(audit_world_signals(world,NETWORK,12)['priority_deadline_audit'],'passed')
        world['events'][-1]['t']=55.5
        with self.assertRaisesRegex(ValueError,'maximum hold'):
            audit_world_signals(world,NETWORK,12)
        world=self.priority_world();world['events'].pop()
        with self.assertRaisesRegex(ValueError,'maximum hold'):
            audit_world_signals(world,NETWORK,12)

    def test_request_timeout_is_independent_of_visual_sample_cadence(self):
        world=self.priority_world()
        world['events']=[event for event in world['events'] if event['kind'] not in ('priority_green','release')]
        world['frames'][-1]['t']=111
        with self.assertRaisesRegex(ValueError,'release timeout'):
            audit_world_signals(world,NETWORK,12)

    def test_missing_step_is_reported_and_conflicting_step_rejected(self):
        world=legal_world()
        self.assertEqual(audit_world_signals(world,NETWORK,60)['priority_deadline_audit'],
                         'not_checked_missing_integration_step')
        world['metrics']['simulation_step_s']=.5
        with self.assertRaisesRegex(ValueError,'disagrees'):
            audit_world_signals(world,NETWORK,60,simulation_step_s=1)

    def test_nextafter_request_time_accepts_numeric_tie_not_early_action(self):
        world=self.priority_world()
        due=math.nextafter(20.0,math.inf)
        world['decision']['request_plan']['J']=due
        world['events'][4]['request_at_s']=due
        self.assertEqual(audit_world_signals(world,NETWORK,12)['priority_deadline_audit'],'passed')
        world['events'][5]['t']=19.5
        with self.assertRaisesRegex(ValueError,'before its frozen due'):
            audit_world_signals(world,NETWORK,12)

    def test_controlled_endpoint_requires_activation_and_release(self):
        world=self.priority_world()
        world['decision']['request_plan']['J']=100
        world['events'][4]['request_at_s']=100
        world['events']=world['events'][:5]
        with self.assertRaisesRegex(ValueError,'never issued'):
            audit_world_signals(world,NETWORK,12)
        world['events'].append({'t':100,'kind':'request','junction':'J','phase':1})
        audit_world_signals(world,NETWORK,12)
        world=self.priority_world();world['frames'][-1]['t']=55
        audit_world_signals(world,NETWORK,12)
        world['events'].pop()
        with self.assertRaisesRegex(ValueError,'maximum hold'):
            audit_world_signals(world,NETWORK,12)
        world=self.priority_world()
        world['events']=[e for e in world['events'] if e['kind'] not in ('priority_green','release')]
        world['frames'][-1]['t']=110
        with self.assertRaisesRegex(ValueError,'release timeout'):
            audit_world_signals(world,NETWORK,12)
        world['events'].append({'t':110,'kind':'release','junction':'J','reason':'request_timeout'})
        audit_world_signals(world,NETWORK,12)


class PilotRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.output=Path(self.temp.name)/'pilot'
        self.envelope=prepare_plan(seeds_per_regime=1)
        self.expected=len(self.envelope['plan']['cases'])*7

    def mocks(self, versions=None, dependencies=None, audit_error=None):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('sim.run.source_snapshot',return_value=deepcopy(SOURCE)))
        dependency_mock=stack.enter_context(patch('sim.run.dependency_versions',
            side_effect=dependencies if dependencies is not None else None,
            return_value=deepcopy(DEPENDENCIES)))
        def build(kind,directory):
            directory.mkdir(parents=True);(directory/'graph.json').write_text('{}')
            return {'network_sha256':'n'*64}
        stack.enter_context(patch('sim.network.build_network',side_effect=build))
        stack.enter_context(patch('sim.network.read_network',return_value=deepcopy(NETWORK)))
        stack.enter_context(patch('sim.demand.make_demand',return_value={
            'dispatch_s':60,'vehicles':[{'id':'ambulance'},{'id':'c1'}]}))
        stack.enter_context(patch('sim.demand.save_demand',return_value={
            'demand_group_id':'group','demand_sha256':'d'*64}))
        sequence=iter(versions or ['SUMO 1.28.0']*self.expected)
        def run(**kwargs):
            world=legal_world(kwargs['policy'],next(sequence))
            world['world_id']=kwargs['world_id']
            kwargs['output'].mkdir(parents=True)
            (kwargs['output']/'outcome.json').write_text(json.dumps(world))
            return world
        runner=stack.enter_context(patch('sim.run.run_world',side_effect=run))
        audited=stack.enter_context(patch('evaluation.pilot.audit_pilot_world',side_effect=audit_error))
        stack.enter_context(patch('models.analytical.estimate_candidates',return_value={
            'version':'unit-fixture','config':{},'scores':[{'lead_s':lead,'analytical_cost_s':1} for lead in (0,5,10,20,30)]}))
        return runner,dependency_mock,audited

    def records(self):
        return (json.loads((self.output/'outcomes.json').read_text()),
                json.loads((self.output/'execution.json').read_text()))

    def test_dependency_change_before_world_stops_without_running(self):
        changed={**DEPENDENCIES,'traci':'different'}
        runner,deps,audit=self.mocks(dependencies=[DEPENDENCIES,changed])
        with self.assertRaises(RuntimeError):execute_plan(self.envelope,self.output)
        rows,manifest=self.records()
        self.assertEqual(runner.call_count,0);self.assertEqual(audit.call_count,0)
        self.assertEqual(rows[0]['status'],'infrastructure_error')
        self.assertIsNone(rows[0]['ambulance_journey_s'])
        self.assertEqual(rows[0]['dependencies_before'],changed)
        self.assertIsNone(rows[0]['signal_audit_input_sha256'])
        self.assertEqual(manifest['runner_invocations'],0)
        self.assertEqual(manifest['preflight_rejected_worlds'],1)
        self.assertEqual(manifest['unattempted_worlds'],self.expected)

    def test_dependency_change_during_world_retains_actual_accounting(self):
        changed={**DEPENDENCIES,'sumolib':'different'}
        runner,deps,audit=self.mocks(dependencies=[DEPENDENCIES,DEPENDENCIES,changed])
        with self.assertRaises(RuntimeError):execute_plan(self.envelope,self.output)
        rows,manifest=self.records()
        self.assertEqual(runner.call_count,1);self.assertEqual(audit.call_count,0)
        self.assertEqual(rows[0]['status'],'infrastructure_error')
        self.assertEqual(rows[0]['accounting']['completed'],1)
        self.assertEqual(rows[0]['dependencies_after'],changed)
        self.assertIsNone(rows[0]['civilian_mean_excess_s'])
        self.assertTrue((self.output/rows[0]['raw_world_directory']/'outcome.json').exists())

    def test_changed_sumo_version_is_not_pooled_with_first_world(self):
        runner,deps,audit=self.mocks(versions=['SUMO 1.28.0','SUMO different'])
        with self.assertRaises(RuntimeError):execute_plan(self.envelope,self.output)
        rows,manifest=self.records()
        self.assertEqual(runner.call_count,2);self.assertEqual(audit.call_count,1)
        self.assertEqual(rows[0]['status'],'completed')
        self.assertEqual(rows[1]['status'],'infrastructure_error')
        self.assertEqual(rows[1]['sumo_version'],'SUMO different')
        self.assertEqual(manifest['sumo_version'],'SUMO 1.28.0')
        self.assertEqual(manifest['unattempted_worlds'],self.expected-2)
        self.assertEqual(deps.call_count,5) # startup, before/after each world

    def test_consistent_traffic_invalid_world_keeps_its_invalid_outcome(self):
        runner,deps,audit=self.mocks(versions=['SUMO 1.28.0','SUMO different'])
        original=runner.side_effect
        def collision_world(**kwargs):
            world=original(**kwargs)
            world['status']='invalid';world['metrics']['status']='invalid'
            world['metrics']['validity_reasons']=['collision']
            world['metrics']['civilian_mean_excess_s']=None
            return world
        runner.side_effect=collision_world
        with self.assertRaises(RuntimeError):execute_plan(self.envelope,self.output)
        rows,manifest=self.records()
        self.assertEqual(rows[0]['status'],'invalid')
        self.assertEqual(rows[0]['audit_status'],'passed')
        self.assertEqual(rows[0]['validity_reasons'],['collision'])

    def test_audit_failure_has_no_finite_target_and_preserves_raw_world(self):
        runner,deps,audit=self.mocks(audit_error=PilotAuditError('synthetic illegal transition'))
        with self.assertRaises(PilotAuditError):execute_plan(self.envelope,self.output)
        rows,manifest=self.records()
        self.assertEqual(len(rows[0]['signal_audit_input_sha256']),64)
        evidence=json.loads((self.output/rows[0]['raw_world_directory']/'signal-audit-input.json').read_text())
        self.assertTrue(evidence['frames'])
        self.assertNotIn('vehicles',evidence['frames'][0])
        self.assertEqual(evidence['status'],'completed')
        self.assertEqual(audit.call_count,1)
        self.assertTrue(audit.call_args.args[0]['frames'])
        self.assertEqual(rows[0]['status'],'invalid')
        self.assertEqual(rows[0]['audit_status'],'failed')
        self.assertIn('evidence_audit_failed',rows[0]['validity_reasons'])
        self.assertIsNone(rows[0]['ambulance_journey_s'])
        self.assertIsNone(rows[0]['civilian_mean_excess_s'])
        self.assertEqual(manifest['status'],'invalid_evidence')
        self.assertEqual(manifest['audit_failed_worlds'],1)
        raw=self.output/rows[0]['raw_world_directory']/'outcome.json'
        self.assertEqual(json.loads(raw.read_text())['metrics']['ambulance_journey_s'],10)


if __name__=='__main__':unittest.main()
