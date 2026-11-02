"""Strict paired-evidence packaging; the baseline is a distinct world, not a ghost vehicle."""
from __future__ import annotations
import math
from pathlib import Path
from sim.network import write_json, sha256

SCHEMA = 'afterlight.replay.v1'


def validate_replay(replay: dict) -> None:
    if replay.get('schema') != SCHEMA or replay.get('mode') != 'recorded':
        raise ValueError('Unsupported replay schema/mode')
    duration, cadence = replay.get('duration_s'), replay.get('step_s')
    if not isinstance(duration, (int,float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Positive finite duration required')
    if not isinstance(cadence, (int,float)) or not math.isfinite(cadence) or cadence <= 0:
        raise ValueError('Positive finite sample cadence required')
    if replay.get('coordinates', {}).get('position_reference') != 'front_bumper':
        raise ValueError('Explicit front-bumper coordinate contract required')
    if replay.get('scenario', {}).get('network_kind') not in ('fixture','city'):
        raise ValueError('Explicit network kind required')
    provenance = replay.get('provenance', {})
    if any(not provenance.get(k) for k in ('source_commit','network_sha256','demand_sha256','sumo_version')):
        raise ValueError('Missing run provenance')
    worlds = replay.get('worlds', {})
    if set(worlds) != {'afterlight', 'baseline'}:
        raise ValueError('Exactly two independent worlds required')
    clocks = []
    for name, world in worlds.items():
        if world.get('world_id') != name or world.get('status') not in ('completed','censored','invalid','infrastructure_error'):
            raise ValueError('Invalid world identity/status')
        if not world.get('frames') or world['frames'][0]['t'] != 0:
            raise ValueError('Trace must contain frames beginning at absolute time zero')
        previous = -1.0
        times = []
        for frame in world['frames']:
            t = frame['t']
            if not math.isfinite(t) or t <= previous:
                raise ValueError(f'{name}: timestamps must be strictly increasing')
            if previous >= 0 and not math.isclose(t-previous, cadence, abs_tol=1e-8):
                if t != duration or not 0 < t-previous < cadence:
                    raise ValueError('Trace has an undeclared sampling gap')
            previous = t
            times.append(t)
            ids = set()
            for v in frame['vehicles']:
                if v['id'] in ids or 'ghost' in v['id'].lower():
                    raise ValueError('Duplicate or ghost physical vehicle ID')
                ids.add(v['id'])
                for key in ('x', 'y', 'z', 'angle_deg', 'speed_mps', 'length_m'):
                    if not math.isfinite(v[key]):
                        raise ValueError(f'Nonfinite pose field {key}')
                if v['length_m'] <= 0 or v['speed_mps'] < 0:
                    raise ValueError('Invalid vehicle dimensions/speed')
        clocks.append(times)
    if clocks[0] != clocks[1]:
        raise ValueError('Paired worlds must use the same absolute clock')
    if clocks[0] and replay['duration_s'] != clocks[0][-1]:
        raise ValueError('Duration does not match shared trace endpoint')
    if worlds['baseline']['policy'] != 'ordinary':
        raise ValueError('Baseline world must use ordinary control')


def save_replay(path: Path, replay: dict) -> dict:
    validate_replay(replay)
    write_json(path, replay)
    return {'sha256': sha256(path), 'bytes': path.stat().st_size, 'schema': SCHEMA,
            'duration_s': replay['duration_s'], 'step_s': replay['step_s']}
