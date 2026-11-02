"""Pure route-phase selection tests; execute only on designated Omen host."""
import unittest

from sim.run import route_controls


def network(greens, lane_count=1):
    return {'signals': {'J': {
        'greens': greens,
        'links': [{'index': i, 'from_edge': 'incoming', 'to_edge': 'outgoing',
                   'from_lane': f'incoming_{i}', 'to_lane': f'outgoing_{i}'}
                  for i in range(lane_count)],
    }}}


class RouteControlTests(unittest.TestCase):
    def selected(self, greens, lane_count=1):
        return route_controls(['incoming', 'outgoing'], network(greens, lane_count))[0]['phase']

    def test_equal_coverage_prefers_protected_over_permissive(self):
        self.assertEqual(self.selected(['g', 'G']), 1)
        self.assertEqual(self.selected(['gg', 'Gg'], 2), 1)

    def test_all_lane_coverage_precedes_partial_protected_service(self):
        self.assertEqual(self.selected(['Gr', 'gg'], 2), 1)

    def test_equal_coverage_and_protection_keep_first_phase(self):
        self.assertEqual(self.selected(['Gg', 'gG'], 2), 0)

    def test_missing_legal_green_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No legal green'):
            self.selected(['r', 'r'])


if __name__ == '__main__':
    unittest.main()
