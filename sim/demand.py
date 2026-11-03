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

# SUMO lane positions identify the FRONT bumper. A numeric zero places the
# whole body behind the lane start, potentially inside an upstream junction.
# Explicit numeric positions keep shared demand/reference costs reproducible.
# https://sumo.dlr.de/userdoc/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html#departpos
INSERTION_REAR_MARGIN_M = .1
INSERTION_FRONT_MARGIN_M = .1


def departure_lane_lengths(network: dict, edge_id: str, depart_lane: str = 'best') -> list[float]:
    lanes = network['edges'][edge_id]['lanes']
    if not lanes:
        raise ValueError(f'No departure lanes for {edge_id}')
    if depart_lane != 'best':
        if not isinstance(depart_lane,str) or not depart_lane.isdecimal() or int(depart_lane)>=len(lanes):
            raise ValueError('Departure lane must be best or a valid fixed lane index')
        lanes = [lanes[int(depart_lane)]]
    lengths = [network['lanes'][lane]['length_m'] for lane in lanes]
    if any(isinstance(length,bool) or not isinstance(length,(int,float)) or not math.isfinite(length) or length<=0 for length in lengths):
        raise ValueError(f'Invalid actual SUMO departure lane length for {edge_id}')
    return lengths


def validate_insertion_positions(demand: dict, network: dict) -> None:
    """Reject unsupported body placement before SUMO, never drop/relocate rows."""
    for vehicle in demand['vehicles']:
        length = float(TYPES[vehicle['type']]['length'])
        position = vehicle['depart_pos_m']
        if isinstance(position,bool) or not isinstance(position,(int,float)) or not math.isfinite(position):
            raise ValueError(f"{vehicle['id']}: departure front position must be finite")
        lane_lengths = departure_lane_lengths(network,vehicle['route'][0],vehicle.get('depart_lane','best'))
        if position < length+INSERTION_REAR_MARGIN_M-1e-9 or position > min(lane_lengths)-INSERTION_FRONT_MARGIN_M+1e-9:
            raise ValueError(f"{vehicle['id']}: departure must fit the whole {length:g} m vehicle on its first lane "
                             f"with {INSERTION_REAR_MARGIN_M:g} m rear and {INSERTION_FRONT_MARGIN_M:g} m front clearance; "
                             'choose a supported pickup/start edge, do not shift or discard demand')



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
    # The pickup curb is a pedestrian marker. Dispatch uses the adjacent lane,
    # never a teleport from a building/curb into the road.
    vehicles = [{'id': 'ambulance', 'type': 'ambulance', 'depart_s': dispatch_s,
                 'depart_pos_m': depart_pos, 'depart_lane': '0', 'route': ambulance_route,
                 'reference_s': free_flow_reference(ambulance_route, network, 'ambulance', depart_pos)}]
    rng = random.Random(seed)
    longest_civilian = max(float(TYPES[kind]['length']) for kind in ('car','truck','bike'))
    minimum_start_length = longest_civilian+INSERTION_REAR_MARGIN_M+INSERTION_FRONT_MARGIN_M
    candidates = sorted(edge for edge in network['edges'] if min(departure_lane_lengths(network,edge))>=minimum_start_length)
    excluded_starts = sorted(set(network['edges'])-set(candidates))
    if not candidates:
        raise ValueError('No eligible civilian start edges can contain the complete vehicle body; no demand rows were discarded')
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
                # Exogenous hotspot is graph-fixed, never conditioned on the
                # selected ambulance origin/route or candidate action.
                start = candidates[0]
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
        civilian_position = float(TYPES[kind]['length'])+INSERTION_REAR_MARGIN_M
        vehicles.append({'id': f'civilian_{index:05d}', 'type': kind, 'depart_s': round(now, 3),
                         'depart_pos_m': civilian_position, 'depart_lane': 'best', 'route': route,
                         'reference_s': free_flow_reference(route, network, kind, civilian_position)})
        index += 1
    validate_insertion_positions({'vehicles':vehicles},network)
    vehicles.sort(key=lambda v: (v['depart_s'], v['id']))
    return {'schema': 'afterlight.demand.v1', 'seed': seed, 'regime': regime,
            'dispatch_s': dispatch_s, 'demand_end_s': demand_end_s,
            'pickup_id': pickup['id'], 'hospital_id': hospital['id'], 'vehicles': vehicles,
            'reference_definition': 'max(0, arrival - scheduled_departure - external SUMO lane free-flow lower bound); reference excludes internal junctions and acceleration',
            'vehicle_class_note': 'All types including ambulance use passenger permissions. Bike is a compact low-speed motor-traffic proxy, not SUMO bicycle dynamics.',
            'bluelight_device': False,
            'insertion_policy': {'schema':'afterlight.insertion.v1','position_reference':'SUMO front bumper',
                'civilian_position_rule':'vType length + rear margin', 'rear_margin_m':INSERTION_REAR_MARGIN_M,
                'front_margin_m':INSERTION_FRONT_MARGIN_M,'minimum_civilian_start_lane_length_m':minimum_start_length,
                'excluded_short_start_edges':excluded_starts,'vehicle_lengths_m':{kind:float(spec['length']) for kind,spec in TYPES.items()},
                'ambulance_position_rule':'exact nearest curb-to-lane projection; reject insufficient whole-body fit',
                'insertion_checks':'all','depart_speed_mps':0,'max_depart_delay_s':-1,
                'delay_policy':'SUMO queues blocked insertions; all scheduled/not-inserted rows remain accounted'},
            'pickup_projection': {'lane_id': pickup_lane, 'depart_pos_m': depart_pos,
                                  'curb_to_lane_distance_m': anchor_distance, 'method': 'nearest clipped SUMO lane polyline'}}


def routes_element(demand: dict) -> ET.Element:
    """One deterministic XML definition for saving and read-only binding checks."""
    root = ET.Element('routes')
    for name, properties in TYPES.items():
        node = ET.SubElement(root, 'vType', id=name, vClass='passenger', sigma='0.5',
                            speedFactor='1.0', speedDev='0.0', minGap='2.5', tau='1.0', **properties)
        ET.SubElement(node, 'param', key='has.bluelight.device', value='false')
    for v in demand['vehicles']:
        node = ET.SubElement(root, 'vehicle', id=v['id'], type=v['type'], depart=str(v['depart_s']),
                            departPos=str(v['depart_pos_m']), departSpeed='0', departLane=v.get('depart_lane', 'best'), insertionChecks='all')
        ET.SubElement(node, 'route', edges=' '.join(v['route']))
    return root


def validate_saved_demand(demand: dict, network: dict, directory: Path) -> None:
    """Bind the files SUMO consumes to the safe immutable declared realization.

    Reject stale or altered inputs; never rewrite evidence to make it pass.
    Explicit insertionChecks=all merely pins SUMO's normal default safety checks.
    """
    validate_insertion_positions(demand,network)
    saved = json.loads((directory/'demand.json').read_text(encoding='utf-8'))
    if saved != demand:
        raise ValueError('Saved demand JSON differs from supplied immutable realization')
    expected = ET.canonicalize(ET.tostring(routes_element(demand),encoding='unicode'),strip_text=True)
    actual = ET.canonicalize((directory/'demand.rou.xml').read_text(encoding='utf-8'),strip_text=True)
    if actual != expected:
        raise ValueError('Saved SUMO route XML differs from safe demand/types/departures/insertion checks; retain evidence and regenerate a NEW run')


def save_demand(demand: dict, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory/'demand.json', demand)
    write_xml(directory/'demand.rou.xml', routes_element(demand))
    civilian_realization = [v for v in demand['vehicles'] if v['id'] != 'ambulance']
    group_hash = hashlib.sha256(json.dumps(civilian_realization, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'demand_sha256': sha256(directory/'demand.rou.xml'),
            'demand_manifest_sha256': sha256(directory/'demand.json'),
            'demand_group_id': group_hash}
