"""Pre-generate explicit exogenous demand once, before either paired world runs."""
from __future__ import annotations
import math
import hashlib
import json
from pathlib import Path
import random
import xml.etree.ElementTree as ET
from sim.network import shortest_route, write_json, write_xml, sha256

TYPES = {
    'car': {'length': '4.4', 'width': '1.8', 'maxSpeed': '13.89', 'accel': '2.6', 'decel': '4.5'},
    'truck': {'length': '7.2', 'width': '2.4', 'maxSpeed': '11.11', 'accel': '1.5', 'decel': '4.0'},
    'bike': {'length': '1.8', 'width': '0.6', 'maxSpeed': '8.33', 'accel': '1.8', 'decel': '4.0'},
    'ambulance': {'length': '5.8', 'width': '2.2', 'maxSpeed': '13.89', 'accel': '2.6', 'decel': '4.5'},
}
RATES = {'sparse': .18, 'moderate': .55, 'heavy': 1.2, 'asymmetric': .7}


def pickup_fraction(graph: dict, pickup: dict) -> float:
    edge = next(e for e in graph['edges'] if e['id'] == pickup['edge_id'])
    a, b = edge['centerline'][0], edge['centerline'][-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    return min(.98, max(.02, ((pickup['position'][0]-a[0])*dx + (pickup['position'][1]-a[1])*dy)/(dx*dx+dy*dy)))


def project_to_lane(position: list[float], shape: list[list[float]]) -> tuple[float, float]:
    """Nearest XY projection onto actual clipped SUMO lane, return arclength/error."""
    best = (float('inf'), 0.0)
    travelled = 0.0
    for a, b in zip(shape, shape[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if not length:
            continue
        fraction = max(0.0, min(1.0, ((position[0]-a[0])*dx+(position[1]-a[1])*dy)/(length*length)))
        error = math.hypot(position[0]-(a[0]+fraction*dx), position[1]-(a[1]+fraction*dy))
        candidate = (error, travelled+fraction*length)
        best = min(best, candidate)
        travelled += length
    if not math.isfinite(best[0]):
        raise ValueError('Degenerate lane geometry')
    return best[1], best[0]


def free_flow_reference(route: list[str], network: dict, vehicle_type: str, depart_pos: float = 0) -> float:
    """Declared lower-bound reference: external lane length / min(edge, type speed).

    Excludes intersection-internal lane length and acceleration. Thus this is a
    reproducible network free-flow lower bound, not a calibrated no-traffic run.
    Raw travel times are retained so this convention can be audited/replaced
    before any frozen held-out study.
    """
    limit = float(TYPES[vehicle_type]['maxSpeed'])
    return sum(max(0, network['edges'][e]['length_m'] - (depart_pos if i == 0 else 0)) /
               min(network['edges'][e]['speed_mps'], limit) for i, e in enumerate(route))


def make_demand(graph: dict, network: dict, *, seed: int, regime: str = 'moderate',
                dispatch_s: float = 60, demand_end_s: float = 180,
                pickup_id: str | None = None, hospital_id: str | None = None) -> dict:
    if regime not in RATES or not math.isfinite(dispatch_s) or not math.isfinite(demand_end_s) or dispatch_s < 1 or demand_end_s <= dispatch_s:
        raise ValueError('Invalid regime, dispatch or demand horizon')
    pickups = {p['id']: p for p in graph['pickups']}
    hospitals = {h['id']: h for h in graph['hospitals']}
    pickup = pickups[pickup_id or next(iter(pickups))]
    hospital = hospitals[hospital_id or list(hospitals)[-1]]
    ambulance_route = shortest_route(graph, pickup['edge_id'], hospital['destination_node'])
    pickup_lane = network['edges'][pickup['edge_id']]['lanes'][0]
    depart_pos, anchor_distance = project_to_lane(pickup['position'], network['lanes'][pickup_lane]['shape'])
    depart_pos = min(depart_pos, network['lanes'][pickup_lane]['length_m']-.1)
    # The pickup curb is a pedestrian marker. Dispatch uses the adjacent lane,
    # never a teleport from a building/curb into the road.
    vehicles = [{'id': 'ambulance', 'type': 'ambulance', 'depart_s': dispatch_s,
                 'depart_pos_m': depart_pos, 'depart_lane': '0', 'route': ambulance_route,
                 'reference_s': free_flow_reference(ambulance_route, network, 'ambulance', depart_pos)}]
    rng = random.Random(seed)
    candidates = sorted(network['edges'])
    endpoints = sorted(n['id'] for n in graph['nodes'] if not n['signalized'])
    now = 0.0
    index = 0
    while True:
        now += rng.expovariate(RATES[regime])
        if now >= demand_end_s:
            break
        route = None
        for _ in range(100):
            start = rng.choice(candidates)
            if regime == 'asymmetric' and rng.random() < .7:
                start = ambulance_route[0]
            end = rng.choice(endpoints)
            try:
                candidate = shortest_route(graph, start, end)
            except ValueError:
                continue
            if len(candidate) >= 2:
                route = candidate
                break
        if route is None:
            raise ValueError('Unable to sample a permitted civilian route')
        kind = rng.choices(('car', 'truck', 'bike'), weights=(.82, .1, .08))[0]
        vehicles.append({'id': f'civilian_{index:05d}', 'type': kind, 'depart_s': round(now, 3),
                         'depart_pos_m': 0.0, 'route': route,
                         'reference_s': free_flow_reference(route, network, kind)})
        index += 1
    vehicles.sort(key=lambda v: (v['depart_s'], v['id']))
    return {'schema': 'afterlight.demand.v1', 'seed': seed, 'regime': regime,
            'dispatch_s': dispatch_s, 'demand_end_s': demand_end_s,
            'pickup_id': pickup['id'], 'hospital_id': hospital['id'], 'vehicles': vehicles,
            'reference_definition': 'max(0, arrival - scheduled_departure - external SUMO lane free-flow lower bound); reference excludes internal junctions and acceleration',
            'vehicle_class_note': 'All types including ambulance use passenger permissions. Bike is a compact low-speed motor-traffic proxy, not SUMO bicycle dynamics.',
            'bluelight_device': False,
            'pickup_projection': {'lane_id': pickup_lane, 'depart_pos_m': depart_pos,
                                  'curb_to_lane_distance_m': anchor_distance, 'method': 'nearest clipped SUMO lane polyline'}}


def save_demand(demand: dict, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory/'demand.json', demand)
    root = ET.Element('routes')
    for name, properties in TYPES.items():
        node = ET.SubElement(root, 'vType', id=name, vClass='passenger', sigma='0.5',
                            speedFactor='1.0', speedDev='0.0', minGap='2.5', tau='1.0', **properties)
        ET.SubElement(node, 'param', key='has.bluelight.device', value='false')
    for v in demand['vehicles']:
        node = ET.SubElement(root, 'vehicle', id=v['id'], type=v['type'], depart=str(v['depart_s']),
                            departPos=str(v['depart_pos_m']), departSpeed='0', departLane=v.get('depart_lane', 'best'))
        ET.SubElement(node, 'route', edges=' '.join(v['route']))
    write_xml(directory/'demand.rou.xml', root)
    civilian_realization = [v for v in demand['vehicles'] if v['id'] != 'ambulance']
    group_hash = hashlib.sha256(json.dumps(civilian_realization, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'demand_sha256': sha256(directory/'demand.rou.xml'),
            'demand_manifest_sha256': sha256(directory/'demand.json'),
            'demand_group_id': group_hash}
