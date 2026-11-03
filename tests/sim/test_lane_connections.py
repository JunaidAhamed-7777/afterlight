"""Canonical lane allocation fixtures; execution belongs on Omen."""
import copy
import unittest
from sim.network import connection_lane_pairs, fixture_graph, lane_connections, load_graph


def edge(identifier, start, end, shape, lanes):
    return {'id': identifier, 'from_node': start, 'to_node': end, 'centerline': shape, 'lanes': lanes}


class LaneConnectionTests(unittest.TestCase):
    def test_turns_use_inner_left_outer_right(self):
        incoming = edge('in', 'W', 'J', [[-10,0],[0,0]], 2)
        left = edge('left', 'J', 'N', [[0,0],[0,10]], 2)
        right = edge('right', 'J', 'S', [[0,0],[0,-10]], 2)
        self.assertEqual(connection_lane_pairs(incoming, left), [(1,1)])
        self.assertEqual(connection_lane_pairs(incoming, right), [(0,0)])
        incoming['lanes'] = 1
        self.assertEqual(connection_lane_pairs(incoming, left), [(0,1)])

    def test_straight_lane_order_and_count_changes(self):
        incoming = edge('in', 'W', 'J', [[-10,0],[0,0]], 2)
        outgoing = edge('out', 'J', 'E', [[0,0],[10,0]], 2)
        self.assertEqual(connection_lane_pairs(incoming, outgoing), [(0,0),(1,1)])
        incoming['lanes'] = 1
        self.assertEqual(connection_lane_pairs(incoming, outgoing), [(0,0),(0,1)])
        incoming['lanes'], outgoing['lanes'] = 2, 1
        self.assertEqual(connection_lane_pairs(incoming, outgoing), [(0,0),(1,0)])

    def test_adjacent_segments_and_duplicate_endpoints(self):
        incoming = edge('in', 'W', 'J', [[-10,0],[0,0],[0,10],[0,10]], 2)
        outgoing = edge('out', 'J', 'E', [[0,10],[0,10],[10,10]], 2)
        self.assertEqual(connection_lane_pairs(incoming, outgoing), [(0,0)])

    def test_same_road_bend_keeps_forward_lane_order(self):
        incoming = edge('in', 'W', 'J', [[-10,0],[0,0]], 2)
        outgoing = edge('out', 'J', 'N', [[0,0],[0,10]], 2)
        incoming['road_id'] = outgoing['road_id'] = 'curving_arterial'
        self.assertEqual(connection_lane_pairs(incoming, outgoing), [(0,0),(1,1)])

    def test_same_road_identity_does_not_permit_uturn(self):
        incoming = edge('in', 'W', 'J', [[-10,0],[0,0]], 2)
        outgoing = edge('back', 'J', 'W', [[0,0],[-10,0]], 2)
        incoming['road_id'] = outgoing['road_id'] = 'arterial'
        with self.assertRaisesRegex(ValueError, 'U-turn'):
            connection_lane_pairs(incoming, outgoing)
        outgoing['to_node'] = 'different_id_same_reverse_direction'
        with self.assertRaisesRegex(ValueError, 'U-turn'):
            connection_lane_pairs(incoming, outgoing)

    def test_canonical_pairs_and_coordinates_preserved(self):
        graph = load_graph('city'); before = copy.deepcopy(graph)
        result = lane_connections(graph)
        self.assertEqual({(c['from'],c['to']) for c in result},
                         {(c['from_edge'],c['to_edge']) for c in graph['connections']})
        self.assertEqual(graph, before)

    def test_six_reported_boundary_inner_lanes_have_incoming_connections(self):
        result = lane_connections(load_graph('city'))
        incoming = {(c['to'],c['toLane']) for c in result}
        for identifier in ('H10_0_F','H13_2_R','H30_0_F','H33_2_R','V20_0_F','V23_0_R'):
            with self.subTest(edge=identifier):
                self.assertIn((identifier,'1'), incoming)

    def test_reported_crossroad_left_turns_no_longer_use_outer_lane(self):
        graph = load_graph('city'); edges = {e['id']:e for e in graph['edges']}
        reported = {'V21_0_R','V20_0_F','H12_0_R','H11_2_F',
                    'V23_0_R','V22_0_F','H32_0_R','H31_2_F'}
        for c in graph['connections']:
            if c['from_edge'] not in reported:
                continue
            a,b = edges[c['from_edge']],edges[c['to_edge']]
            av = [a['centerline'][-1][i]-a['centerline'][-2][i] for i in (0,1)]
            bv = [b['centerline'][1][i]-b['centerline'][0][i] for i in (0,1)]
            if av[0]*bv[1]-av[1]*bv[0] > 0:
                with self.subTest(connection=c):
                    self.assertEqual(connection_lane_pairs(a,b),[(a['lanes']-1,b['lanes']-1)])

    def test_single_lane_fixture_keeps_all_connections(self):
        graph = fixture_graph(); result = lane_connections(graph)
        self.assertEqual(len(result),len(graph['connections']))
        self.assertTrue(all(c['fromLane']==c['toLane']=='0' for c in result))

    def test_degenerate_and_uturn_geometry_rejected(self):
        incoming = edge('in','W','J',[[-10,0],[0,0]],1)
        with self.assertRaisesRegex(ValueError,'U-turn'):
            connection_lane_pairs(incoming,edge('back','J','W',[[0,0],[-10,0]],1))
        with self.assertRaisesRegex(ValueError,'tangent'):
            connection_lane_pairs(incoming,edge('bad','J','E',[[0,0],[0,0]],1))


if __name__=='__main__': unittest.main()
