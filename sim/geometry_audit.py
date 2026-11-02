"""Measure canonical stop-line targets against existing SUMO lane endpoints.

Read-only geometry inspection; never invokes SUMO or changes either network.
An advisory review threshold is not traffic validity or a safety tolerance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from sim.network import read_network, sha256

NUMERIC_TOLERANCE_M = 0.05
REVIEW_THRESHOLD_M = 0.5


def point_xy(value) -> tuple[float, float]:
    if len(value) < 2 or any(not math.isfinite(float(v)) for v in value[:2]):
        raise ValueError('Finite XY coordinates required')
    return float(value[0]), float(value[1])


def final_tangent(shape) -> tuple[float, float]:
    """Last nonzero canonical segment, not the node chord or SUMO turn curve."""
    for a, b in reversed(list(zip(shape, shape[1:]))):
        ax, ay = point_xy(a)
        bx, by = point_xy(b)
        length = math.hypot(bx-ax, by-ay)
        if length > 1e-12:
            return (bx-ax)/length, (by-ay)/length
    raise ValueError('Canonical edge has no nonzero final segment')


def audit_stop_lines(graph: dict, network: dict, *, provenance: dict) -> dict:
    """Return every signalized incoming lane, including signed discrepancies.

    Positive setback is upstream from the canonical destination node; positive
    lateral displacement is left of the final canonical travel tangent.
    0.05 m classifies numerical agreement only. Absolute setback discrepancies
    above 0.5 m receive a review flag; smaller nonnumeric differences still need
    reconciliation before exact city-alignment acceptance. No outcome is used.
    """
    for key in ('network_sha256', 'network_file_sha256', 'canonical_map_sha256'):
        if not isinstance(provenance.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', provenance[key]):
            raise ValueError(f'Explicit SHA-256 provenance required: {key}')
    nodes = {node['id']: node for node in graph['nodes']}
    rows = []
    for edge in graph['edges']:
        node = nodes[edge['to_node']]
        if not node['signalized']:
            continue
        target = edge.get('stop_line', {}).get('distance_before_node_m')
        if target is None or not math.isfinite(target) or target < 0:
            raise ValueError(f'Missing/invalid canonical stop-line target: {edge["id"]}')
        tx, ty = final_tangent(edge['centerline'])
        nx, ny = point_xy(node['position'])
        imported = network['edges'][edge['id']]
        if not imported['lanes']:
            raise ValueError(f'No imported lanes: {edge["id"]}')
        for lane_id in imported['lanes']:
            shape = network['lanes'][lane_id]['shape']
            if not shape:
                raise ValueError(f'Empty imported lane shape: {lane_id}')
            ex, ey = point_xy(shape[-1])
            setback = (nx-ex)*tx + (ny-ey)*ty
            lateral = (ex-nx)*(-ty) + (ey-ny)*tx
            delta = setback-target
            rows.append({'junction_id': node['id'], 'edge_id': edge['id'], 'lane_id': lane_id,
                         'canonical_node_xy_m': [nx, ny], 'canonical_final_tangent_xy': [tx, ty],
                         'actual_lane_endpoint_xy_m': [ex, ey], 'target_setback_m': target,
                         'actual_signed_setback_m': setback, 'signed_lateral_offset_m': lateral,
                         'setback_delta_m': delta, 'within_numeric_tolerance': abs(delta) <= NUMERIC_TOLERANCE_M,
                         'review_required': abs(delta) > REVIEW_THRESHOLD_M})
    rows.sort(key=lambda row: (row['junction_id'], row['edge_id'], row['lane_id']))
    mismatch = sum(not row['within_numeric_tolerance'] for row in rows)
    return {'schema': 'afterlight.stop-line-audit.v1', 'provenance': dict(provenance),
            'numeric_tolerance_m': NUMERIC_TOLERANCE_M, 'review_threshold_m': REVIEW_THRESHOLD_M,
            'status': 'reconciliation_required' if mismatch else ('numeric_agreement' if rows else 'no_signalized_lanes'),
            'lane_count': len(rows), 'nonnumeric_difference_count': mismatch,
            'review_flag_count': sum(row['review_required'] for row in rows), 'lanes': rows,
            'scope': 'Geometry measurement only; generated SUMO endpoints remain runtime truth. No mutation, traffic invalidation, or safety certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--network', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() in (args.graph.resolve(), args.network.resolve()):
        raise ValueError('Output must not replace either input')
    graph = json.loads(args.graph.read_text(encoding='utf-8'))
    network = read_network(args.network)
    provenance = {'network_sha256': hashlib.sha256(ET.canonicalize(from_file=args.network, strip_text=True, with_comments=False).encode()).hexdigest(),
                  'network_file_sha256': sha256(args.network), 'canonical_map_sha256': sha256(args.graph)}
    report = audit_stop_lines(graph, network, provenance=provenance)
    serialized = json.dumps(report, indent=2, allow_nan=False) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves prior evidence and never rewrites inputs.
    with args.output.open('x', encoding='utf-8') as handle:
        handle.write(serialized)
    print(json.dumps({'output': str(args.output), 'status': report['status'], 'lane_count': report['lane_count']}))


if __name__ == '__main__':
    main()
