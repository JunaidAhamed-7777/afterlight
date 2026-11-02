"""Generate SUMO inputs from one canonical graph; never redraw city roads.

Netconvert is run only by an explicit CLI invocation. Coordinates are deliberately
not normalized, preserving Blender/glTF's original scene transform.
"""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
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


def binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    # eclipse-sumo wheels expose SUMO_HOME through the sumo package.
    try:
        import sumo
        base = Path(sumo.SUMO_HOME)
        for suffix in ('.exe', ''):
            candidate = base / 'bin' / (name + suffix)
            if candidate.is_file():
                return str(candidate)
    except (ImportError, AttributeError):
        pass
    raise RuntimeError(f'{name} is unavailable. Install the pinned eclipse-sumo package in the active venv.')


def build_network(kind: str, output: Path) -> dict:
    graph = load_graph(kind)
    output.mkdir(parents=True, exist_ok=True)
    nodes = ET.Element('nodes')
    for n in graph['nodes']:
        ET.SubElement(nodes, 'node', id=n['id'], x=str(n['position'][0]), y=str(n['position'][1]),
                      type='traffic_light' if n['signalized'] else 'priority')
    edges = ET.Element('edges')
    edge_by_id = {e['id']: e for e in graph['edges']}
    for e in graph['edges']:
        ET.SubElement(edges, 'edge', id=e['id'], **{'from': e['from_node'], 'to': e['to_node'],
                      'numLanes': str(e['lanes']), 'width': str(e['lane_width_m']),
                      'speed': str(e['speed_kph']/3.6), 'allow': 'passenger',
                      'spreadType': 'right', 'shape': ' '.join(f'{p[0]},{p[1]}' for p in e['centerline'])})
    connections = ET.Element('connections')
    for c in graph['connections']:
        # Explicit legal edge pairs; netconvert builds lane-level turn geometry.
        # Each incoming lane maps proportionally to an outgoing lane. No U-turns
        # are introduced; every lane receives a permitted successor.
        a, b = edge_by_id[c['from_edge']], edge_by_id[c['to_edge']]
        for lane in range(a['lanes']):
            ET.SubElement(connections, 'connection', **{'from': a['id'], 'to': b['id'],
                          'fromLane': str(lane), 'toLane': str(min(lane, b['lanes'] - 1))})
    write_xml(output / 'nodes.nod.xml', nodes)
    write_xml(output / 'edges.edg.xml', edges)
    write_xml(output / 'connections.con.xml', connections)
    command = [binary('netconvert'), '--node-files', str(output/'nodes.nod.xml'),
               '--edge-files', str(output/'edges.edg.xml'), '--connection-files', str(output/'connections.con.xml'),
               '--output-file', str(output/'network.net.xml'), '--offset.disable-normalization', 'true',
               '--no-turnarounds', 'true', '--tls.default-type', 'static', '--tls.green.time', '25',
               '--tls.yellow.time', '3', '--tls.allred.time', '1']
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    (output/'netconvert.stdout.txt').write_text(completed.stdout, encoding='utf-8')
    (output/'netconvert.stderr.txt').write_text(completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'netconvert failed ({completed.returncode}): {completed.stderr}')
    metadata = {'schema': 'afterlight.network.v1', 'kind': kind, 'network_sha256': hashlib.sha256(ET.canonicalize(from_file=output/'network.net.xml', strip_text=True, with_comments=False).encode()).hexdigest(),
                'network_file_sha256': sha256(output/'network.net.xml'),
                'network_hash_definition': 'canonical XML excluding generator timestamp/path comments and insignificant whitespace',
                'graph_sha256': hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest(),
                'command': command, 'netconvert_version': subprocess.check_output([binary('netconvert'), '--version'], text=True).splitlines()[0],
                'coordinate_normalization': False, 'validation_status': 'generated_not_acceptance_tested'}
    write_json(output/'network-manifest.json', metadata)
    write_json(output/'graph.json', graph)
    return metadata


def read_network(path: Path) -> dict:
    root = ET.parse(path).getroot()
    location = root.find('location')
    if location is not None and location.get('netOffset', '0,0') not in ('0.00,0.00', '0,0'):
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
    return {'edges': edges, 'signals': signals, 'lanes': lanes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('fixture', 'city'), default='fixture')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_network(args.kind, args.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
