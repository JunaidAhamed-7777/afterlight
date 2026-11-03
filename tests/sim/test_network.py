import unittest
from sim.network import fixture_graph, load_graph, shortest_route


class NetworkTests(unittest.TestCase):
    def test_fixture_route(self):
        self.assertEqual(shortest_route(fixture_graph(), 'W_J1', 'E'),
                         ['W_J1', 'J1_J2', 'J2_J3', 'J3_E'])

    def test_city_all_200_permitted_routes(self):
        graph = load_graph('city')
        allowed = {(c['from_edge'], c['to_edge']) for c in graph['connections']}
        self.assertEqual(len(graph['pickups']), 100)
        self.assertEqual(len(graph['hospitals']), 2)
        for p in graph['pickups']:
            for h in graph['hospitals']:
                route = shortest_route(graph, p['edge_id'], h['destination_node'])
                self.assertTrue(all(pair in allowed for pair in zip(route, route[1:])))

    def test_expansion_preserves_street_scale_and_places_diagonal_hospitals(self):
        graph=load_graph('city')
        old=graph['expansion']['original_bounds'];bounds=graph['bounds']
        area=lambda b:(b['max'][0]-b['min'][0])*(b['max'][1]-b['min'][1])
        self.assertEqual(area(bounds),4*area(old))
        self.assertEqual(sum(n.get('kind')=='primary_intersection' for n in graph['nodes']),81)
        primary={n['id'] for n in graph['nodes'] if n.get('kind')=='primary_intersection'}
        main=[e['length_m'] for e in graph['edges'] if e['from_node'] in primary and e['to_node'] in primary]
        self.assertTrue(main);self.assertLessEqual(max(main),245)
        buildings={b['id']:b for b in graph['buildings']}
        centres=[buildings[h['building_id']]['center'] for h in graph['hospitals']]
        self.assertLess(centres[0][0]*centres[1][0],0)
        self.assertLess(centres[0][1]*centres[1][1],0)

    def test_no_ghost_in_network(self):
        graph = fixture_graph()
        self.assertFalse(any('ghost' in e['id'] for e in graph['edges']))


if __name__ == '__main__': unittest.main()
