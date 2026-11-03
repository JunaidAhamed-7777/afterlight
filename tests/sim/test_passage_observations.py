"""Pure sampled-passage telemetry fixtures. Execute only on Omen."""
import unittest
from sim.run import observed_junction_passages


class PassageObservationTests(unittest.TestCase):
    def setUp(self):
        self.controls = [{'junction': 'J1', 'route_index': 0, 'incoming_edge': 'a', 'outgoing_edge': 'b'},
                         {'junction': 'J2', 'route_index': 2, 'incoming_edge': 'c', 'outgoing_edge': 'd'}]

    def test_no_observation_before_insertion_or_while_on_approach(self):
        seen = set()
        for index in (-1, 0):
            self.assertEqual(observed_junction_passages(self.controls, seen, 20, index, False), [])
        self.assertEqual(seen, set())

    def test_each_junction_once_at_first_observed_boundary(self):
        seen = set()
        first = observed_junction_passages(self.controls, seen, 20.5, 1, False)
        self.assertEqual([e['junction'] for e in first], ['J1'])
        self.assertEqual(first[0]['t'], 20.5)
        self.assertEqual(first[0]['ambulance_route_index'], 1)
        self.assertEqual(first[0]['controlled_route_index'], 0)
        self.assertEqual(first[0]['time_semantics'], 'first_observed_simulation_boundary_not_exact_crossing')
        self.assertEqual(observed_junction_passages(self.controls, seen, 21, 1, False), [])
        self.assertEqual([e['junction'] for e in observed_junction_passages(self.controls, seen, 30, 3, False)], ['J2'])

    def test_arrival_retains_unsampled_final_passage_evidence(self):
        seen = {'J1'}
        events = observed_junction_passages(self.controls, seen, 35, -1, True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['junction'], 'J2')
        self.assertEqual(events[0]['observation_basis'], 'arrival_notification')
        self.assertIsNone(events[0]['ambulance_route_index'])
        self.assertTrue(events[0]['arrived'])
        self.assertEqual(observed_junction_passages(self.controls, seen, 36, -1, True), [])

    def test_skipped_route_indices_are_logged_in_route_order(self):
        events = observed_junction_passages(self.controls, set(), 40, 3, False)
        self.assertEqual([e['junction'] for e in events], ['J1', 'J2'])

    def test_independent_worlds_produce_equal_observations(self):
        self.assertEqual(observed_junction_passages(self.controls, set(), 40, 3, False),
                         observed_junction_passages(self.controls, set(), 40, 3, False))

    def test_invalid_sampled_state_rejected(self):
        for now, index, arrived in ((float('nan'), 0, False), (-1, 0, False), (1, True, False),
                                    (1, -2, False), (1, 1.5, False), (1, 0, 1)):
            with self.subTest(now=now, index=index, arrived=arrived), self.assertRaises(ValueError):
                observed_junction_passages(self.controls, set(), now, index, arrived)


if __name__ == '__main__':
    unittest.main()
