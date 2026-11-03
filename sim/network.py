"""Generate SUMO inputs from one canonical graph; never redraw city roads.

Netconvert is run only by an explicit CLI invocation. Coordinates are deliberately
not normalized, preserving Blender/glTF's original scene transform.
"""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
import math
import importlib.metadata
import os
import sys
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def write_xml(path: Path, root: ET.Element) -> None:
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def fixture_graph() -> dict:
    """Three four-way intersections, fixed west-to-east ambulance route."""
    nodes = [{'id': 'W', 'position': [-400, 0, 0], 'signalized': False},
             {'id': 'E', 'position': [400, 0, 0], 'signalized': False}]
    for i, x in enumerate((-200, 0, 200), 1):
        nodes += [{'id': f'J{i}', 'position': [x, 0, 0], 'signalized': True},
                  {'id': f'N{i}', 'position': [x, 180, 0], 'signalized': False},
                  {'id': f'S{i}', 'position': [x, -180, 0], 'signalized': False}]
    positions = {n['id']: n['position'] for n in nodes}
    roads = [('W', 'J1'), ('J1', 'J2'), ('J2', 'J3'), ('J3', 'E')]
    roads += [(f'N{i}', f'J{i}') for i in range(1, 4)]
    roads += [(f'J{i}', f'S{i}') for i in range(1, 4)]
    edges = []
    for a, b in roads:
        for start, end in ((a, b), (b, a)):
            x, y, _ = positions[start]; xx, yy, _ = positions[end]
            edges.append({'id': f'{start}_{end}', 'from_node': start, 'to_node': end,
                          'centerline': [positions[start], positions[end]],
                          'length_m': ((xx-x)**2+(yy-y)**2)**.5, 'lanes': 1,
                          'lane_width_m': 3.25, 'speed_kph': 40, 'permissions': ['passenger']})
    connections = [{'from_edge': a['id'], 'to_edge': b['id'], 'via_node': a['to_node']}
                   for a in edges for b in edges
                   if a['to_node'] == b['from_node'] and a['from_node'] != b['to_node']]
    return {'schema': 'afterlight.fixture.v1', 'nodes': nodes, 'edges': edges,
            'connections': connections, 'pickups': [{'id': 'FIXTURE_PICKUP', 'edge_id': 'W_J1',
            'position': [-360, 0, 0]}], 'hospitals': [{'id': 'FIXTURE_HOSPITAL',
            'name': 'Fixture arrival', 'destination_node': 'E'}]}


def load_graph(kind: str) -> dict:
    if kind == 'fixture':
        return fixture_graph()
    if kind == 'city':
        return json.loads((ROOT / 'assets/map/city_manifest.json').read_text(encoding='utf-8'))
    raise ValueError('Network must be fixture or city')


def shortest_route(graph: dict, start_edge: str, destination_node: str) -> list[str]:
    """Dijkstra over legal edge transitions, not merely node connectivity."""
    edges = {e['id']: e for e in graph['edges']}
    if start_edge not in edges:
        raise ValueError(f'Unknown edge {start_edge}')
    successors = {e: [] for e in edges}
    for c in graph['connections']:
        successors[c['from_edge']].append(c['to_edge'])
    heap = [(edges[start_edge]['length_m'], (start_edge,))]
    distances = {start_edge: edges[start_edge]['length_m']}
    while heap:
        cost, route = heapq.heappop(heap)
        e = route[-1]
        if cost != distances.get(e):
            continue
        if edges[e]['to_node'] == destination_node:
            return list(route)
        for nxt in sorted(successors[e]):
            length = cost + edges[nxt]['length_m']
            if length < distances.get(nxt, float('inf')):
                distances[nxt] = length
                heapq.heappush(heap, (length, (*route, nxt)))
    raise ValueError(f'No permitted route from {start_edge} to {destination_node}')


def binary_candidates(name: str) -> list[Path]:
    """Discover only the active interpreter's installed SUMO package/entrypoints."""
    if name not in ('sumo','netconvert'):
        raise ValueError('Unsupported SUMO executable')
    suffixes = ('.exe','') if os.name == 'nt' else ('','.exe')
    candidates = []
    # Absolute venv Python invocation does not activate Scripts/bin on PATH.
    # Wheel console launchers may live beside the interpreter instead of under
    # the package SUMO_HOME. Prefer that interpreter-local installation.
    for base in (Path(sys.executable).parent,Path(sys.prefix)/'Scripts',Path(sys.prefix)/'bin'):
        candidates.extend(base/(name+suffix) for suffix in suffixes)
    if os.environ.get('SUMO_HOME'):
        base=Path(os.environ['SUMO_HOME'])/'bin'
        candidates.extend(base/(name+suffix) for suffix in suffixes)
    try:
        import sumo
        home = getattr(sumo,'SUMO_HOME',None)
        if home:
            for base in (Path(home)/'bin',Path(home)):
                candidates.extend(base/(name+suffix) for suffix in suffixes)
        if getattr(sumo,'__file__',None):
            for base in (Path(sumo.__file__).parent/'bin',Path(sumo.__file__).parent):
                candidates.extend(base/(name+suffix) for suffix in suffixes)
    except ImportError:
        pass
    # Distribution RECORD is the supported exact inventory; no drive or home
    # directory scan, guessed download, global install, or PATH modification.
    try:
        distribution = importlib.metadata.distribution('eclipse-sumo')
        accepted = {name+suffix for suffix in suffixes}
        for item in distribution.files or ():
            if Path(str(item)).name.lower() in accepted:
                candidates.append(Path(distribution.locate_file(item)))
    except importlib.metadata.PackageNotFoundError:
        pass
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    return list(dict.fromkeys(path.resolve() for path in candidates))


def binary(name: str) -> str:
    candidates = binary_candidates(name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    try:
        version = importlib.metadata.version('eclipse-sumo')
    except importlib.metadata.PackageNotFoundError:
        version = 'not installed in this interpreter'
    raise RuntimeError(f'{name} unavailable for {sys.executable}; eclipse-sumo={version}. '
                       'Install requirements-sim.txt with this same Python interpreter, or set session SUMO_HOME to the verified official portable package; '
                       'run python -m sim.environment for scoped package diagnostics.')


def edge_direction(edge: dict, *, at_end: bool) -> tuple[float, float]:
    """Use the junction-adjacent nonzero segment of canonical geometry."""
    segments = list(zip(edge['centerline'], edge['centerline'][1:]))
    for a, b in reversed(segments) if at_end else segments:
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if not math.isfinite(length):
            raise ValueError(f'Nonfinite junction tangent for {edge["id"]}')
        if length > 1e-9:
            return dx/length, dy/length
    raise ValueError(f'No finite nonzero junction tangent for {edge["id"]}')


def connection_lane_pairs(incoming: dict, outgoing: dict) -> list[tuple[int, int]]:
    """Conservative right-hand turn allocation without changing edge topology.

    SUMO lane zero is rightmost. A right turn uses the outer lanes; a left turn
    uses the inner lanes, including the destination lane on a widening turn.
    This avoids the old all-lanes-to-all-turns layout and its orphaned inner
    destination lanes at arterial boundary junctions. Straight movements and
    same-road forward bends keep lane order, with explicit monotone fan-in/out
    only when counts differ. Same-road identity never permits a U-turn.
    Netconvert still creates turn curves and conflict-checked signal programs.
    """
    if incoming['to_node'] != outgoing['from_node']:
        raise ValueError('Canonical connection endpoints do not meet')
    ni, no = incoming['lanes'], outgoing['lanes']
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in (ni, no)):
        raise ValueError('Positive integer lane counts required')
    ax, ay = edge_direction(incoming, at_end=True)
    bx, by = edge_direction(outgoing, at_end=False)
    cross, dot = ax*by-ay*bx, ax*bx+ay*by
    # Road identity describes a forward continuation, not permission to reverse.
    # Reject graph reversals/180-degree geometry before the same-road override.
    if incoming['from_node'] == outgoing['to_node'] or (abs(cross) <= 1e-9 and dot <= 0):
        raise ValueError('U-turn lane allocation is not supported by the canonical contract')
    road_id = incoming.get('road_id')
    same_road = isinstance(road_id, str) and bool(road_id) and road_id == outgoing.get('road_id')
    if same_road:
        return [(min(lane, ni-1), min(lane, no-1)) for lane in range(max(ni, no))]
    if cross > 1e-9:
        return [(ni-1, no-1)]
    if cross < -1e-9:
        return [(0, 0)]
    return [(min(lane, ni-1), min(lane, no-1)) for lane in range(max(ni, no))]


def lane_connections(graph: dict) -> list[dict]:
    edges = {edge['id']: edge for edge in graph['edges']}
    result = []
    for connection in graph['connections']:
        a, b = edges[connection['from_edge']], edges[connection['to_edge']]
        result.extend({'from': a['id'], 'to': b['id'], 'fromLane': str(i), 'toLane': str(j)}
                      for i, j in connection_lane_pairs(a, b))
    return result


def build_network(kind: str, output: Path) -> dict:
    from policies.scheduler import timing_for_network
    timing = timing_for_network(kind)
    if kind == 'city':
        map_bytes=(ROOT/'assets/map/city_manifest.json').read_bytes()
        graph=json.loads(map_bytes)
        canonical_map_sha256=hashlib.sha256(map_bytes).hexdigest()
    else:
        graph=load_graph(kind)
        canonical_map_sha256=None
    output.mkdir(parents=True, exist_ok=True)
    nodes = ET.Element('nodes')
    for n in graph['nodes']:
        ET.SubElement(nodes, 'node', id=n['id'], x=str(n['position'][0]), y=str(n['position'][1]),
                      type='traffic_light' if n['signalized'] else 'priority')
    edges = ET.Element('edges')
    for e in graph['edges']:
        ET.SubElement(edges, 'edge', id=e['id'], **{'from': e['from_node'], 'to': e['to_node'],
                      'numLanes': str(e['lanes']), 'width': str(e['lane_width_m']),
                      'speed': str(e['speed_kph']/3.6), 'allow': 'passenger',
                      'spreadType': 'right', 'shape': ' '.join(f'{p[0]},{p[1]}' for p in e['centerline'])})
    connections = ET.Element('connections')
    for connection in lane_connections(graph):
        ET.SubElement(connections, 'connection', **connection)
    write_xml(output / 'nodes.nod.xml', nodes)
    write_xml(output / 'edges.edg.xml', edges)
    write_xml(output / 'connections.con.xml', connections)
    command = [binary('netconvert'), '--node-files', str(output/'nodes.nod.xml'),
               '--edge-files', str(output/'edges.edg.xml'), '--connection-files', str(output/'connections.con.xml'),
               '--output-file', str(output/'network.net.xml'), '--offset.disable-normalization', 'true',
               '--no-turnarounds', 'true', '--tls.default-type', 'static', '--tls.green.time', '25',
               '--tls.yellow.time', format(timing.yellow_s,'g'), '--tls.allred.time', format(timing.all_red_s,'g')]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    (output/'netconvert.stdout.txt').write_text(completed.stdout, encoding='utf-8')
    (output/'netconvert.stderr.txt').write_text(completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'netconvert failed ({completed.returncode}): {completed.stderr}')
    validate_imported_network(graph,read_network(output/'network.net.xml'))
    metadata = {'schema': 'afterlight.network.v1', 'kind': kind, 'network_sha256': hashlib.sha256(ET.canonicalize(from_file=output/'network.net.xml', strip_text=True, with_comments=False).encode()).hexdigest(),
                'network_file_sha256': sha256(output/'network.net.xml'),
                'network_hash_definition': 'canonical XML excluding generator timestamp/path comments and insignificant whitespace',
                'graph_sha256': hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
                'canonical_map_sha256': canonical_map_sha256,
                'command': command, 'netconvert_version': subprocess.check_output([binary('netconvert'), '--version'], text=True).splitlines()[0],
                'coordinate_normalization': False,
                'lane_connection_policy': 'right-hand-inner-left-outer-right-straight-order-v1',
                'validation_status': 'generated_not_acceptance_tested'}
    write_json(output/'network-manifest.json', metadata)
    write_json(output/'graph.json', graph)
    return metadata


def read_network(path: Path) -> dict:
    root = ET.parse(path).getroot()
    location = root.find('location')
    if location is not None and any(abs(float(v)) > 1e-8 for v in location.get('netOffset','0,0').split(',')):
        raise ValueError('SUMO changed the canonical coordinate origin')
    edges = {}
    lanes = {}
    for lane in root.findall('./edge/lane'):
        lanes[lane.attrib['id']] = {'shape': [[float(v) for v in point.split(',')] for point in lane.attrib['shape'].split()],
                                    'length_m': float(lane.attrib['length']), 'speed_mps': float(lane.attrib['speed'])}
    junction_positions = {j.attrib['id']: [float(j.attrib['x']), float(j.attrib['y']), 0.0] for j in root.findall('junction')}
    for edge in root.findall('edge'):
        if edge.get('function') == 'internal':
            continue
        lane = edge.find('lane')
        if lane is not None:
            edges[edge.attrib['id']] = {'length_m': float(lane.attrib['length']),
                'speed_mps': float(lane.attrib['speed']), 'from': edge.get('from'), 'to': edge.get('to'),
                'lanes': [l.attrib['id'] for l in edge.findall('lane')]}
    signals = {}
    for tl in root.findall('tlLogic'):
        greens = list(dict.fromkeys(p.attrib['state'] for p in tl.findall('phase')
                      if any(c in 'gG' for c in p.attrib['state']) and all(c in 'rRgG' for c in p.attrib['state'])))
        if not greens:
            raise ValueError(f'No usable green states at {tl.attrib["id"]}')
        signals[tl.attrib['id']] = {'greens': greens, 'links': [],
            'position': junction_positions.get(tl.attrib['id'])}
    for c in root.findall('connection'):
        if c.get('tl') in signals:
            signals[c.attrib['tl']]['links'].append({'index': int(c.attrib['linkIndex']),
                'from_edge': c.attrib['from'], 'to_edge': c.attrib['to'],
                'from_lane': f'{c.attrib["from"]}_{c.attrib["fromLane"]}',
                'to_lane': f'{c.attrib["to"]}_{c.attrib["toLane"]}',
                'incoming_shape': lanes[f'{c.attrib["from"]}_{c.attrib["fromLane"]}']['shape'],
                'outgoing_shape': lanes[f'{c.attrib["to"]}_{c.attrib["toLane"]}']['shape'],
                'stop_line': lanes[f'{c.attrib["from"]}_{c.attrib["fromLane"]}']['shape'][-1],
                'turn': c.get('dir'), 'via_lane': c.get('via')})
    connections = [{'from_edge':c.attrib['from'],'to_edge':c.attrib['to']} for c in root.findall('connection')
                   if c.attrib['from'] in edges and c.attrib['to'] in edges]
    return {'edges': edges, 'signals': signals, 'lanes': lanes, 'connections':connections}


def validate_imported_network(graph: dict, network: dict) -> None:
    """Exact external graph identity and legal-transition coverage after conversion."""
    if set(network['edges']) != {e['id'] for e in graph['edges']}:
        raise ValueError('SUMO conversion changed canonical external edge IDs')
    canonical = {(c['from_edge'],c['to_edge']) for c in graph['connections']}
    actual = {(c['from_edge'],c['to_edge']) for c in network['connections']}
    if canonical != actual:
        missing, extra = sorted(canonical-actual),sorted(actual-canonical)
        raise ValueError(f'SUMO transition mismatch: missing={missing}, extra={extra}')
    for edge in graph['edges']:
        imported = network['edges'][edge['id']]
        if imported['from'] != edge['from_node'] or imported['to'] != edge['to_node']:
            raise ValueError(f'Canonical endpoint changed for {edge["id"]}')
        if imported['length_m'] <= 0 or imported['speed_mps'] <= 0:
            raise ValueError(f'Invalid generated lane for {edge["id"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('fixture', 'city'), default='fixture')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_network(args.kind, args.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
