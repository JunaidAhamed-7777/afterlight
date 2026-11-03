"""Mocked interruption evidence only; execute on Omen, never starts SUMO."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evaluation.pilot import execute_plan, prepare_plan


class PilotInterruptTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.output=Path(temporary.name)/'pilot'
        self.plan=prepare_plan(seeds_per_regime=1)
        stack=ExitStack();self.addCleanup(stack.close)
        source={'source_commit':'a'*40,'source_code_sha256':'b'*64,'source_dirty':False}
        stack.enter_context(patch('sim.run.source_snapshot',return_value=source))
        self.dependencies=stack.enter_context(patch('sim.run.dependency_versions',return_value={'traci':'unit'}))
        def build(kind,directory):
            directory.mkdir(parents=True);(directory/'graph.json').write_text('{}')
            return {'network_sha256':'network'}
        stack.enter_context(patch('sim.network.build_network',side_effect=build))
        stack.enter_context(patch('sim.network.read_network',return_value={}))
        stack.enter_context(patch('sim.demand.make_demand',return_value={
            'dispatch_s':60,'vehicles':[{'id':'ambulance'},{'id':'civilian'}]}))
        stack.enter_context(patch('sim.demand.save_demand',return_value={'demand_group_id':'group','demand_sha256':'demand'}))
        self.audit=stack.enter_context(patch('evaluation.pilot.audit_pilot_world'))
        stack.enter_context(patch('models.analytical.estimate_candidates',return_value={'version':'unit','config':{},'scores':[]}))
        def run(**kwargs):
            kwargs['output'].mkdir(parents=True)
            (kwargs['output']/'raw-marker.txt').write_text('preserve partial evidence')
            return {'policy':kwargs['policy'],'status':'completed','sumo_version':'unit',
                'events':[],'frames':[{'t':0,'signals':[]}],
                'decision':{'observation':{},'request_plan':{}},
                'metrics':{'status':'completed','runtime_s':1,'validity_reasons':[],
                    'ambulance_journey_s':10,'civilian_mean_excess_s':0,
                    'accounting':{'scheduled':1,'inserted':1,'completed':1,'running':0,'not_inserted':0}}}
        self.runner=stack.enter_context(patch('sim.run.run_world',side_effect=run))

    def read(self):
        return (json.loads((self.output/'execution.json').read_text()),
                json.loads((self.output/'outcomes.json').read_text()))

    def assert_interrupted(self,invoked,recorded):
        manifest,rows=self.read()
        self.assertEqual(manifest['status'],'interrupted')
        self.assertEqual(manifest['runner_invocations'],invoked)
        self.assertEqual(manifest['recorded_worlds'],recorded)
        self.assertEqual(len(rows),recorded)
        self.assertEqual(manifest['unattempted_worlds'],28-invoked)
        self.assertEqual(manifest['unrecorded_worlds'],28-recorded)
        self.assertEqual(len(manifest['world_inventory']),28)
        self.assertGreaterEqual(manifest['runtime_total_s'],0)
        self.assertTrue(manifest['finished_utc'])
        self.assertFalse((self.output/'pilot-summary.json').exists())
        self.assertEqual(manifest['interrupted_world']['state'],'interrupted')
        self.assertNotIn('outcome_status',manifest['interrupted_world'])
        return manifest,rows

    def test_interrupt_during_world_preserves_prior_rows_and_partial_files(self):
        original=self.runner.side_effect
        def interrupt_second(**kwargs):
            world=original(**kwargs)
            if kwargs['policy']=='immediate':raise KeyboardInterrupt
            return world
        self.runner.side_effect=interrupt_second
        with self.assertRaises(KeyboardInterrupt):execute_plan(self.plan,self.output)
        manifest,rows=self.assert_interrupted(2,1)
        self.assertEqual(rows[0]['policy'],'ordinary')
        self.assertEqual(manifest['world_inventory'][0]['state'],'recorded')
        self.assertEqual(manifest['interrupted_world']['policy'],'immediate')
        self.assertTrue((self.output/manifest['interrupted_world']['raw_world_directory']/'raw-marker.txt').exists())
        self.assertTrue(all(item['state']=='unattempted' for item in manifest['world_inventory'][2:]))
        with self.assertRaises(FileExistsError):execute_plan(self.plan,self.output)
        self.assertEqual(self.runner.call_count,2)

    def test_preflight_interrupt_never_claims_simulator_invocation(self):
        self.dependencies.side_effect=[{'traci':'unit'},KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt):execute_plan(self.plan,self.output)
        manifest,_=self.assert_interrupted(0,0)
        self.assertFalse(manifest['interrupted_world']['runner_invoked'])
        self.runner.assert_not_called()

    def test_audit_interrupt_does_not_promote_returned_world_to_outcome(self):
        self.audit.side_effect=KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):execute_plan(self.plan,self.output)
        manifest,_=self.assert_interrupted(1,0)
        directory=self.output/manifest['interrupted_world']['raw_world_directory']
        self.assertTrue((directory/'signal-audit-input.json').exists())
        self.assertTrue((directory/'raw-marker.txt').exists())
