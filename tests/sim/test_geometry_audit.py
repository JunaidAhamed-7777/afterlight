"""Pure geometry fixtures; execute only on designated Omen host."""
import copy
import unittest
from sim.geometry_audit import audit_stop_lines, final_tangent

PROVENANCE = {key: 'a'*64 for key in ('network_sha256', 'network_file_sha256', 'canonical_map_sha256')}


def fixture():
    graph = {'nodes': [{'id': 'J', 'position': [100, 100, 0], 'signalized': True}],
             'edges': [{'id': 'in', 'to_node': 'J', 'centerline': [[0, 0], [100, 0], [100, 100], [100, 100]],
                        'stop_line': {'distance_before_node_m': 12}}]}
    network = {'edges': {'in': {'lanes': ['in_0', 'in_1']}},
               'lanes': {'in_0': {'shape': [[103, 0], [103, 88]]},
                         'in_1': {'shape': [[106, 0], [106, 88]]}}}
    return graph, network


class StopLineAuditTests(unittest.TestCase):
    def test_cardinal_final_tangents(self):
        for endpoint, expected in (([10, 0], (1, 0)), ([-10, 0], (-1, 0)),
                                   ([0, 10], (0, 1)), ([0, -10], (0, -1))):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(final_tangent([[0, 0], endpoint]), expected)

    def test_final_nonzero_tangent_and_all_lanes(self):
        graph, network = fixture()
        report = audit_stop_lines(graph, network, provenance=PROVENANCE)
        self.assertEqual(report['lane_count'], 2)
        self.assertEqual(report['status'], 'numeric_agreement')
        self.assertEqual(report['lanes'][0]['actual_signed_setback_m'], 12)
        self.assertEqual(report['lanes'][0]['signed_lateral_offset_m'], -3)
        self.assertEqual(report['lanes'][0]['canonical_final_tangent_xy'], [0, 1])
        self.assertEqual(report['provenance'], PROVENANCE)

    def test_signed_downstream_endpoint_and_review_flag(self):
        graph, network = fixture()
        network['lanes']['in_0']['shape'][-1] = [103, 102]
        report = audit_stop_lines(graph, network, provenance=PROVENANCE)
        self.assertEqual(report['lanes'][0]['actual_signed_setback_m'], -2)
        self.assertEqual(report['lanes'][0]['setback_delta_m'], -14)
        self.assertTrue(report['lanes'][0]['review_required'])
        self.assertEqual(report['status'], 'reconciliation_required')

    def test_numeric_and_review_thresholds_are_distinct(self):
        graph, network = fixture()
        network['lanes']['in_0']['shape'][-1] = [103, 87.99]
        network['lanes']['in_1']['shape'][-1] = [106, 87.5]
        report = audit_stop_lines(graph, network, provenance=PROVENANCE)
        self.assertTrue(report['lanes'][0]['within_numeric_tolerance'])
        self.assertFalse(report['lanes'][1]['within_numeric_tolerance'])
        self.assertFalse(report['lanes'][1]['review_required'])
        self.assertEqual(report['status'], 'reconciliation_required')

    def test_read_only_and_mandatory_hashes(self):
        graph, network = fixture()
        before = copy.deepcopy((graph, network, PROVENANCE))
        audit_stop_lines(graph, network, provenance=PROVENANCE)
        self.assertEqual((graph, network, PROVENANCE), before)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            audit_stop_lines(graph, network, provenance={})

    def test_degenerate_geometry_and_missing_target_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonzero'):
            final_tangent([[0, 0], [0, 0]])
        graph, network = fixture()
        del graph['edges'][0]['stop_line']
        with self.assertRaisesRegex(ValueError, 'target'):
            audit_stop_lines(graph, network, provenance=PROVENANCE)


if __name__ == '__main__':
    unittest.main()
