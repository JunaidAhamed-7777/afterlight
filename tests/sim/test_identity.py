"""Synthetic identity contracts; these inputs are not simulation evidence.

Execute on Omen only. A demand-realization group outlives ambulance dispatch and
policy variants, while an exact paired input hash must distinguish those inputs.
"""
from __future__ import annotations
import copy
import inspect
import tempfile
import unittest
from pathlib import Path

from sim.demand import save_demand
from sim.identity import episode_identity, run_identity


def specimen() -> dict:
    return {
        'schema': 'afterlight.demand.v1', 'seed': 7, 'regime': 'moderate',
        'dispatch_s': 20.0, 'demand_end_s': 100.0,
        'vehicles': [
            {'id': 'civilian_00000', 'type': 'car', 'depart_s': 2.5,
             'depart_pos_m': 0.0, 'route': ['west', 'east'], 'reference_s': 15.0},
            {'id': 'ambulance', 'type': 'ambulance', 'depart_s': 20.0,
             'depart_pos_m': 30.0, 'depart_lane': '0',
             'route': ['west', 'east'], 'reference_s': 12.0},
        ],
    }


class DemandIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def save(self, demand):
        self.counter += 1
        return save_demand(demand, self.root / str(self.counter))

    def test_dispatch_variants_share_realization_not_exact_input(self):
        first = specimen()
        second = copy.deepcopy(first)
        second['dispatch_s'] = 35.0
        second['vehicles'][1]['depart_s'] = 35.0
        a, b = self.save(first), self.save(second)
        self.assertEqual(a['demand_group_id'], b['demand_group_id'])
        self.assertNotEqual(a['demand_sha256'], b['demand_sha256'])
        self.assertNotEqual(a['demand_manifest_sha256'], b['demand_manifest_sha256'])

    def test_ambulance_route_variants_share_civilian_realization(self):
        first = specimen()
        second = copy.deepcopy(first)
        second['vehicles'][1]['route'] = ['west', 'north']
        second['vehicles'][1]['reference_s'] = 18.0
        a, b = self.save(first), self.save(second)
        self.assertEqual(a['demand_group_id'], b['demand_group_id'])
        self.assertNotEqual(a['demand_sha256'], b['demand_sha256'])

    def test_real_civilian_demand_changes_change_group(self):
        original = specimen()
        original_hash = self.save(original)['demand_group_id']
        for key, value in [('depart_s', 3.0), ('route', ['west', 'north']), ('type', 'truck')]:
            with self.subTest(field=key):
                altered = copy.deepcopy(original)
                altered['vehicles'][0][key] = value
                self.assertNotEqual(original_hash, self.save(altered)['demand_group_id'])

    def test_output_directory_does_not_change_identity(self):
        self.assertEqual(self.save(specimen()), self.save(specimen()))


def episode_inputs() -> dict:
    return {'network_kind': 'fixture', 'regime': 'moderate', 'seed': 7,
            'network_sha256': 'a' * 64, 'demand_sha256': 'b' * 64,
            'dispatch_s': 20.0, 'horizon_s': 120.0, 'drain_s': 180.0,
            'step_s': 0.5}


class EpisodeIdentityTests(unittest.TestCase):
    def test_episode_boundary_excludes_policy_lead_and_presentation(self):
        parameters = inspect.signature(episode_identity).parameters
        for forbidden in ('policy', 'lead_s', 'output', 'split', 'sample_s'):
            self.assertNotIn(forbidden, parameters)
        inputs = episode_inputs()
        episode = episode_identity(**inputs)
        runs = {run_identity(episode, 'fixed', lead) for lead in (0, 5, 10, 20, 30)}
        self.assertEqual(len(runs), 5)
        self.assertEqual(episode_identity(**copy.deepcopy(inputs)), episode)

    def test_dispatch_variants_have_different_episode_and_run_ids(self):
        inputs = episode_inputs()
        first = episode_identity(**inputs)
        second = episode_identity(**{**inputs, 'dispatch_s': 35.0})
        self.assertNotEqual(first, second)
        self.assertNotEqual(run_identity(first, 'fixed', 10), run_identity(second, 'fixed', 10))

    def test_network_demand_and_common_physics_change_episode(self):
        inputs = episode_inputs()
        baseline = episode_identity(**inputs)
        for key, value in [('network_sha256', 'c' * 64), ('demand_sha256', 'd' * 64),
                           ('horizon_s', 150.0), ('drain_s', 200.0), ('step_s', 1.0)]:
            with self.subTest(field=key):
                self.assertNotEqual(baseline, episode_identity(**{**inputs, key: value}))

    def test_numerically_equal_time_representations_share_episode(self):
        inputs = episode_inputs()
        self.assertEqual(episode_identity(**inputs), episode_identity(**{**inputs, 'dispatch_s': 20, 'horizon_s': 120, 'drain_s': 180}))

    def test_policy_worlds_and_actual_selected_action_are_distinct(self):
        episode = episode_identity(**episode_inputs())
        variants = [run_identity(episode, 'ordinary'), run_identity(episode, 'immediate'),
                    run_identity(episode, 'fixed', 0), run_identity(episode, 'analytical', 0)]
        self.assertEqual(len(set(variants)), len(variants))
        self.assertNotEqual(run_identity(episode, 'analytical', 5), run_identity(episode, 'analytical', 10))


if __name__ == '__main__':
    unittest.main()
