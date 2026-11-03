"""Deterministic placement/XML contracts, not a replacement for real SUMO reruns."""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from sim.demand import (TYPES, INSERTION_REAR_MARGIN_M, INSERTION_FRONT_MARGIN_M,
    departure_lane_lengths, free_flow_reference, make_demand, save_demand, validate_insertion_positions, validate_saved_demand)
from sim.network import fixture_graph, shortest_route


def fixture():
    graph=fixture_graph();network={'edges':{},'lanes':{}}
    for edge in graph['edges']:
        lane=edge['id']+'_0'
        network['edges'][edge['id']]={'length_m':edge['length_m'],'speed_mps':edge['speed_kph']/3.6,'lanes':[lane]}
        network['lanes'][lane]={'shape':edge['centerline'],'length_m':edge['length_m']}
    return graph,network


class InsertionTests(unittest.TestCase):
    def test_all_generated_civilians_fit_whole_body_and_use_offset_reference(self):
        graph,network=fixture()
        demand=make_demand(graph,network,seed=7)
        validate_insertion_positions(demand,network)
        civilians=[v for v in demand['vehicles'] if v['id']!='ambulance']
        self.assertTrue(civilians)
        self.assertEqual(sorted(v['id'] for v in civilians),[f'civilian_{i:05d}' for i in range(len(civilians))])
        for vehicle in civilians:
            length=float(TYPES[vehicle['type']]['length'])
            self.assertEqual(vehicle['depart_pos_m'],length+INSERTION_REAR_MARGIN_M)
            self.assertGreaterEqual(vehicle['depart_pos_m']-length,INSERTION_REAR_MARGIN_M-1e-9)
            self.assertEqual(vehicle['reference_s'],free_flow_reference(vehicle['route'],network,vehicle['type'],vehicle['depart_pos_m']))
            self.assertLess(vehicle['reference_s'],free_flow_reference(vehicle['route'],network,vehicle['type'],0))

    def test_zero_front_departure_is_rejected_for_truck(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        vehicle=deepcopy(next(v for v in demand['vehicles'] if v['id']!='ambulance'))
        vehicle.update(type='truck',depart_pos_m=0)
        with self.assertRaisesRegex(ValueError,'fit the whole'):
            validate_insertion_positions({'vehicles':[vehicle]},network)

    def test_numeric_nan_bool_and_infinite_positions_rejected(self):
        graph,network=fixture();vehicle=make_demand(graph,network,seed=7)['vehicles'][0]
        for bad in (math.nan,math.inf,True,-1):
            with self.subTest(position=bad),self.assertRaises(ValueError):
                validate_insertion_positions({'vehicles':[{**vehicle,'depart_pos_m':bad}]},network)

    def test_short_start_edge_excluded_without_dropping_generated_rows(self):
        graph,network=fixture()
        # A fake network-only edge cannot be routed by the canonical graph; it
        # must be filtered before routing rather than silently consume demand.
        network['edges']['tiny']={'length_m':2,'speed_mps':5,'lanes':['tiny_0']}
        network['lanes']['tiny_0']={'length_m':2,'shape':[[0,0],[2,0]]}
        actual=make_demand(graph,network,seed=7)
        del network['edges']['tiny'];del network['lanes']['tiny_0']
        reference=make_demand(graph,network,seed=7)
        self.assertEqual(actual['vehicles'],reference['vehicles'])
        self.assertEqual(actual['insertion_policy']['excluded_short_start_edges'],['tiny'])

    def test_all_possible_best_lanes_must_fit_longest_civilian(self):
        graph,network=fixture();edge=next(iter(network['edges']))
        network['edges'][edge]['lanes'].append('short_lane')
        network['lanes']['short_lane']={'length_m':2,'shape':[[0,0],[2,0]]}
        self.assertEqual(min(departure_lane_lengths(network,edge)),2)
        demand=make_demand(graph,network,seed=7)
        self.assertIn(edge,demand['insertion_policy']['excluded_short_start_edges'])
        self.assertTrue(all(v['route'][0]!=edge for v in demand['vehicles'] if v['id']!='ambulance'))

    def test_no_eligible_starts_fails_explicitly(self):
        graph,network=fixture()
        for lane in network['lanes'].values():lane['length_m']=1
        with self.assertRaisesRegex(ValueError,'No eligible civilian start'):
            make_demand(graph,network,seed=7)

    def test_ambulance_near_start_is_rejected_not_relocated(self):
        graph,network=fixture()
        pickup=graph['pickups'][0]
        lane=network['edges'][pickup['edge_id']]['lanes'][0]
        pickup['position']=[*network['lanes'][lane]['shape'][0][:2],0]
        original=deepcopy(pickup['position'])
        with self.assertRaisesRegex(ValueError,'ambulance.*fit the whole'):
            make_demand(graph,network,seed=7)
        self.assertEqual(pickup['position'],original)

    def test_ambulance_near_lane_end_is_rejected_not_clamped(self):
        graph,network=fixture();pickup=graph['pickups'][0]
        lane=network['edges'][pickup['edge_id']]['lanes'][0]
        pickup['position']=[*network['lanes'][lane]['shape'][-1][:2],0]
        with self.assertRaisesRegex(ValueError,'ambulance.*fit the whole'):
            make_demand(graph,network,seed=7)

    def test_repeat_world_demand_is_identical_and_dispatch_changes_only_ambulance(self):
        graph,network=fixture()
        a=make_demand(graph,network,seed=7,dispatch_s=60)
        self.assertEqual(a,make_demand(graph,network,seed=7,dispatch_s=60))
        b=make_demand(graph,network,seed=7,dispatch_s=70)
        civilians=lambda d:[v for v in d['vehicles'] if v['id']!='ambulance']
        self.assertEqual(civilians(a),civilians(b))

    def test_saved_xml_preserves_every_schedule_and_all_insertion_checks(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        with tempfile.TemporaryDirectory() as directory:
            save_demand(demand,Path(directory))
            root=ET.parse(Path(directory)/'demand.rou.xml').getroot()
        rows=root.findall('vehicle')
        self.assertEqual(len(rows),len(demand['vehicles']))
        for row,expected in zip(rows,demand['vehicles']):
            self.assertEqual(row.get('id'),expected['id'])
            self.assertEqual(float(row.get('depart')),expected['depart_s'])
            self.assertEqual(float(row.get('departPos')),expected['depart_pos_m'])
            self.assertEqual(row.get('insertionChecks'),'all')
            self.assertEqual(row.get('departSpeed'),'0')
        self.assertTrue(all(v.find("param[@key='has.bluelight.device']").get('value')=='false' for v in root.findall('vType')))
        self.assertEqual(demand['insertion_policy']['max_depart_delay_s'],-1)
        self.assertEqual(demand['insertion_policy']['position_reference'],'SUMO front bumper')

    def test_saved_xml_matches_exact_safe_realization(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        with tempfile.TemporaryDirectory() as directory:
            save_demand(demand,Path(directory))
            validate_saved_demand(demand,network,Path(directory))

    def test_stale_or_edited_xml_never_bypasses_safe_json(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        mutations=[('vehicle','departPos','0'),('vType','length','99'),('vType','accel','99'),('vType','minGap','0'),('vehicle','insertionChecks','none'),
                   ('vehicle','depart','999'),('vehicle/route','edges','invalid route'),('vehicle','type','truck')]
        for selector,key,value in mutations:
            with self.subTest(selector=selector,key=key),tempfile.TemporaryDirectory() as directory:
                directory=Path(directory);save_demand(demand,directory)
                path=directory/'demand.rou.xml';tree=ET.parse(path)
                element=tree.getroot().find(selector)
                if element.get(key)==value:value='different'
                element.set(key,value);tree.write(path,encoding='utf-8')
                before=path.read_bytes()
                with self.assertRaisesRegex(ValueError,'Saved SUMO route XML differs'):
                    validate_saved_demand(demand,network,directory)
                self.assertEqual(path.read_bytes(),before,'Failed validation must never repair/overwrite evidence')

    def test_unexpected_privileged_xml_param_is_rejected(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);save_demand(demand,directory)
            path=directory/'demand.rou.xml';tree=ET.parse(path)
            ET.SubElement(tree.getroot().find('vehicle'),'param',key='has.bluelight.device',value='true')
            tree.write(path,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Saved SUMO route XML differs'):
                validate_saved_demand(demand,network,directory)

    def test_missing_xml_is_rejected_not_regenerated(self):
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);save_demand(demand,directory)
            path=directory/'demand.rou.xml';path.unlink()
            with self.assertRaises(FileNotFoundError):validate_saved_demand(demand,network,directory)
            self.assertFalse(path.exists())

    def test_runner_rejects_stale_xml_before_sumo_binary(self):
        import sys
        from types import SimpleNamespace
        from sim.run import run_world
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,{'traci':SimpleNamespace()}),patch('sim.run.binary') as binary:
            directory=Path(directory);save_demand(demand,directory)
            path=directory/'demand.rou.xml';tree=ET.parse(path)
            tree.getroot().find('vehicle').set('departPos','0');tree.write(path,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Saved SUMO route XML differs'):
                run_world(world_id='synthetic-preflight',policy='ordinary',lead_s=0,network_dir=directory,
                    demand_dir=directory,demand=demand,network=network,output=directory/'world',horizon_s=240,drain_s=360)
            binary.assert_not_called()

    def test_runner_rejects_unsafe_saved_position_before_sumo_binary(self):
        import sys
        from types import SimpleNamespace
        from sim.run import run_world
        graph,network=fixture();demand=make_demand(graph,network,seed=7)
        next(v for v in demand['vehicles'] if v['id']!='ambulance')['depart_pos_m']=0
        with tempfile.TemporaryDirectory() as directory,patch.dict(sys.modules,{'traci':SimpleNamespace()}),patch('sim.run.binary') as binary:
            with self.assertRaisesRegex(ValueError,'fit the whole'):
                run_world(world_id='synthetic-preflight',policy='ordinary',lead_s=0,network_dir=Path(directory),
                    demand_dir=Path(directory),demand=demand,network=network,output=Path(directory)/'world',horizon_s=240,drain_s=360)
            binary.assert_not_called()

    def test_unroutable_eligible_network_fails_instead_of_discarding_demand(self):
        graph,network=fixture()
        route=shortest_route(graph,graph['pickups'][0]['edge_id'],graph['hospitals'][-1]['destination_node'])
        with patch('sim.demand.shortest_route',side_effect=[route,*([ValueError('no route')]*100)]):
            with self.assertRaisesRegex(ValueError,'Unable to sample'):
                make_demand(graph,network,seed=7)


if __name__=='__main__':unittest.main()
