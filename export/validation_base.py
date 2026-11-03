"""Base replay-v1 structure shared by publication and local HTTP boundaries.

Checks presentation contracts, not benchmark validity, favorable outcomes, or
training provenance. Optional decision/geometry fields remain optional in v1.
"""
from __future__ import annotations
import math
import re


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise ValueError(f'{label} must be a list')
    return value


def _string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f'{label} must be a nonempty string')
    return value


def _number(value, label, *, nonnegative=False, positive=False, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be a finite number, not a boolean')
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or (nonnegative and value < 0) or (positive and value <= 0) or (integer and value != int(value)):
        raise ValueError(f'{label} is outside its numeric contract')
    return value


def _point(value, label):
    point = _array(value, label)
    if len(point) < 2:
        raise ValueError(f'{label} needs at least XY coordinates')
    for coordinate in point:
        _number(coordinate, label)


def _decision(value, duration):
    decision = _object(value, 'decision')
    if 't' in decision:
        if _number(decision['t'], 'decision time', nonnegative=True) > duration:
            raise ValueError('Decision is outside the recording')
    if 'request_plan' in decision:
        for junction, timestamp in _object(decision['request_plan'], 'request plan').items():
            _string(junction, 'request junction')
            # Frozen requests beyond the playback horizon can be legitimate in
            # censored recordings; never clamp them into the visible interval.
            _number(timestamp, 'planned request time', nonnegative=True)


def validate_base_replay(value: object) -> None:
    replay = _object(value, 'replay')
    if replay.get('schema') != 'afterlight.replay.v1' or replay.get('mode') != 'recorded':
        raise ValueError('Unsupported replay schema/mode')
    duration = _number(replay.get('duration_s'), 'duration', positive=True)
    cadence = _number(replay.get('step_s'), 'sample cadence', positive=True)
    coordinates = _object(replay.get('coordinates'), 'coordinates')
    if any(coordinates.get(key) != expected for key, expected in {
        'source': 'canonical XY meters', 'position_reference': 'front_bumper', 'render': '[x,z,-y]'
    }.items()):
        raise ValueError('Unsupported coordinate contract')
    scenario = _object(replay.get('scenario'), 'scenario')
    if scenario.get('network_kind') not in ('fixture', 'city'):
        raise ValueError('Explicit network kind required')
    for key in ('id', 'pickup_id', 'hospital_id'):
        _string(scenario.get(key), f'scenario {key}')
    _number(scenario.get('seed'), 'scenario seed')
    _number(scenario.get('dispatch_s'), 'dispatch time', nonnegative=True)
    if 'route_edges' in scenario:
        for edge in _array(scenario['route_edges'], 'route edges'):
            _string(edge, 'route edge')
    provenance = _object(replay.get('provenance'), 'provenance')
    for key in ('source_commit', 'sumo_version'):
        _string(provenance.get(key), key)
    for key in ('network_sha256', 'demand_sha256'):
        if not re.fullmatch(r'[a-fA-F0-9]{64}', _string(provenance.get(key), key)):
            raise ValueError(f'Invalid {key}')
    geometry = None
    if 'network_geometry' in replay:
        geometry = {}
        supplied = _object(replay['network_geometry'], 'network geometry')
        for item in _array(supplied.get('signals'), 'signal geometry'):
            signal = _object(item, 'signal geometry entry')
            identifier = _string(signal.get('id'), 'signal geometry identity')
            if identifier in geometry:
                raise ValueError('Duplicate signal geometry identity')
            _point(signal.get('position'), 'signal position')
            indices = []
            for item_link in _array(signal.get('links'), 'controlled links'):
                link = _object(item_link, 'controlled link')
                indices.append(_number(link.get('index'), 'controlled link index', nonnegative=True, integer=True))
                for key in ('from_edge', 'to_edge', 'from_lane', 'to_lane'):
                    _string(link.get(key), f'controlled link {key}')
                _point(link.get('stop_line'), 'stop line')
                for key in ('incoming_shape', 'outgoing_shape'):
                    shape = _array(link.get(key), key)
                    if len(shape) < 2:
                        raise ValueError('Controlled link shape needs two points')
                    for point in shape:
                        _point(point, key)
            # Multiple movements may share a SUMO signal index. Do not reject
            # those valid grouped links or assume index count equals state size.
            geometry[identifier] = max(indices, default=-1)
    worlds = _object(replay.get('worlds'), 'worlds')
    if set(worlds) != {'afterlight', 'baseline'}:
        raise ValueError('Exactly two independent worlds required')
    clocks = []
    state_lengths = {}
    for name, item_world in worlds.items():
        world = _object(item_world, name)
        if world.get('world_id') != name or world.get('status') not in ('completed', 'censored', 'invalid', 'infrastructure_error'):
            raise ValueError('Invalid world identity/status')
        _string(world.get('policy'), 'world policy')
        metrics = _object(world.get('metrics'), 'world metrics')
        if 'status' in metrics and metrics['status'] != world['status']:
            raise ValueError('outer world status differs from metric status')
        if 'decision' in world:
            _decision(world['decision'], duration)
        for item_event in _array(world.get('events'), 'world events'):
            event = _object(item_event, 'event')
            _string(event.get('kind'), 'event kind')
            t = _number(event.get('t'), 'event time', nonnegative=True)
            if t > duration:
                raise ValueError('Event is outside recording')
            if 'request_at_s' in event and _number(event['request_at_s'], 'planned request time') < t:
                raise ValueError('Planned request precedes planning event')
        frames = _array(world.get('frames'), 'world frames')
        if not frames:
            raise ValueError('World requires recorded frames')
        times = []
        for item_frame in frames:
            frame = _object(item_frame, 'frame')
            t = _number(frame.get('t'), 'frame time', nonnegative=True)
            if t > duration or (times and t <= times[-1]):
                raise ValueError('Frame times must increase within the recording')
            if times:
                delta = t-times[-1]
                regular = abs(delta-cadence) <= max(1e-8, 1e-9*abs(cadence))
                if not regular and not (t == duration and 0 < delta < cadence):
                    raise ValueError('Trace has an undeclared sampling gap')
            times.append(t)
            _number(frame.get('queue_count'), 'queue count', nonnegative=True, integer=True)
            signals = set()
            for item_signal in _array(frame.get('signals'), 'frame signals'):
                signal = _object(item_signal, 'frame signal')
                identifier = _string(signal.get('id'), 'signal identity')
                state = _string(signal.get('state'), 'signal state')
                if identifier in signals or not re.fullmatch(r'[rRyYgGoOuUs]+', state):
                    raise ValueError('Duplicate or invalid signal state')
                signals.add(identifier)
                if geometry is not None:
                    if identifier not in geometry or geometry[identifier] >= len(state):
                        raise ValueError('Signal state does not cover controlled-link geometry')
                    if identifier in state_lengths and state_lengths[identifier] != len(state):
                        raise ValueError('Signal state length changed across paired frames')
                    state_lengths[identifier] = len(state)
            if geometry is not None and signals != set(geometry):
                raise ValueError('Frame signal inventory differs from network geometry')
            ids = set()
            for item_vehicle in _array(frame.get('vehicles'), 'frame vehicles'):
                vehicle = _object(item_vehicle, 'vehicle')
                identifier = _string(vehicle.get('id'), 'vehicle identity')
                kind = vehicle.get('type')
                if identifier in ids or 'ghost' in identifier.lower() or kind not in ('ambulance', 'car', 'truck', 'bike') or ((identifier == 'ambulance') != (kind == 'ambulance')):
                    raise ValueError('Invalid physical vehicle or ambulance identity')
                ids.add(identifier)
                for key in ('x', 'y', 'z', 'angle_deg'):
                    _number(vehicle.get(key), f'vehicle {key}')
                _number(vehicle.get('speed_mps'), 'vehicle speed', nonnegative=True)
                _number(vehicle.get('length_m'), 'vehicle length', positive=True)
                if 'width_m' in vehicle:
                    _number(vehicle['width_m'], 'vehicle width', positive=True)
        if times[0] != 0 or times[-1] != duration:
            raise ValueError('World does not cover absolute recording horizon')
        clocks.append(times)
    if clocks[0] != clocks[1]:
        raise ValueError('Paired worlds must use the same absolute clock')
    if worlds['baseline']['policy'] != 'ordinary':
        raise ValueError('Baseline must use ordinary control')
