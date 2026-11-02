import unittest
from sim.demand import project_to_lane, make_demand


class DemandTests(unittest.TestCase):
    def test_projects_actual_clipped_lane_not_fraction(self):
        # Canonical road [0,100], clipped SUMO lane [10,90]; curb x25
        # must produce lane arclength15, not canonical fraction .25*80=20.
        position, error = project_to_lane([25, 5, 0], [[10,0],[90,0]])
        self.assertEqual(position, 15)
        self.assertEqual(error, 5)

    def test_civilian_realization_does_not_depend_on_ambulance_route(self):
        from sim.network import fixture_graph
        graph=fixture_graph()
        graph['pickups'].append({'id':'OTHER_PICKUP','edge_id':'N1_J1','position':[-200,100,0]})
        network={'edges':{},'lanes':{}}
        for edge in graph['edges']:
            lane=edge['id']+'_0'
            network['edges'][edge['id']]={'length_m':edge['length_m'],'speed_mps':edge['speed_kph']/3.6,'lanes':[lane]}
            network['lanes'][lane]={'shape':edge['centerline'],'length_m':edge['length_m']}
        first=make_demand(graph,network,seed=7,regime='asymmetric',pickup_id='FIXTURE_PICKUP')
        other=make_demand(graph,network,seed=7,regime='asymmetric',pickup_id='OTHER_PICKUP')
        civilians=lambda demand:[v for v in demand['vehicles'] if v['id']!='ambulance']
        self.assertEqual(civilians(first),civilians(other))

    def test_multisegment_projection(self):
        self.assertEqual(project_to_lane([10,5], [[0,0],[10,0],[10,10]]), (15,0))


if __name__=='__main__': unittest.main()
