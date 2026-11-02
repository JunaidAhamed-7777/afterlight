"""Run real, separate SUMO worlds with identical explicit external demand.

Execute on the designated test machine, not during cloud implementation.
Outputs retain raw SUMO files, complete lifecycle rows, scalar outcomes, and a
shared-absolute-clock replay. No model or benchmark gain is implied by a run.
"""
from __future__ import annotations
import argparse
from collections import deque
import importlib.metadata
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import traceback

from policies.scheduler import Scheduler, Timing
from policies.timing import request_plan, distinct_schedules
from sim.network import ROOT, binary, build_network, read_network, write_json, sha256
from sim.demand import make_demand, save_demand
from sim.accounting import Accounting, reconcile_tripinfo
from export.replay import SCHEMA, save_replay
from models.analytical import choose_lead
from evaluation.protocol import digest
from sim.identity import episode_identity, run_identity


class OutputPathError(ValueError):
    """Rejected pre-existing output; never write failure records into it."""


def source_commit() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unavailable'


def source_snapshot() -> dict:
    """Record explicit project code identity without exporting local diff contents."""
    files = {}
    for directory in ('sim','policies','models','evaluation','export'):
        for path in sorted((ROOT/directory).rglob('*.py')):
            files[str(path.relative_to(ROOT)).replace('\\','/')] = sha256(path)
    try:
        dirty = bool(subprocess.check_output(['git','status','--porcelain','--','sim','policies','models','evaluation','export','assets/map/city_manifest.json'],cwd=ROOT,text=True).strip())
    except (OSError,subprocess.CalledProcessError):
        dirty = None
    return {'source_commit':source_commit(),'source_dirty':dirty,'source_code_sha256':digest(files),
            'source_files':files}


def route_controls(route: list[str], network: dict) -> list[dict]:
    result = []
    for index, (a, b) in enumerate(zip(route, route[1:])):
        for junction, signal in network['signals'].items():
            links = [link for link in signal['links'] if link['from_edge'] == a and link['to_edge'] == b]
            if not links:
                continue
            # Prefer a phase protecting every lane of the movement. Fall back
            # to a phase serving at least one permitted lane, retaining g/G
            # semantics from SUMO's conflict-checked program.
            candidates = [(i, sum(state[link['index']] in 'gG' for link in links))
                          for i, state in enumerate(signal['greens'])]
            phase, coverage = max(candidates, key=lambda p: (p[1], -p[0]))
            if coverage == 0:
                raise ValueError(f'No legal green for route movement {a}->{b}')
            if any(c['junction'] == junction for c in result):
                raise ValueError('Repeated signal on route unsupported; choose a simple route')
            result.append({'junction': junction, 'phase': phase, 'route_index': index,
                           'incoming_edge': a, 'outgoing_edge': b})
    return result


def phase_queues(conn, signal: dict) -> list[float]:
    result = []
    for state in signal['greens']:
        lanes = {link['from_lane'] for link in signal['links'] if state[link['index']] in 'gG'}
        result.append(float(sum(conn.lane.getLastStepHaltingNumber(lane) for lane in lanes)))
    return result


def snapshot(conn, controls: list[dict], schedulers: dict, network: dict, now: float) -> dict:
    queues, occupancies = [], []
    for c in controls:
        signal = network['signals'][c['junction']]
        lanes = {link['from_lane'] for link in signal['links'] if link['from_edge'] == c['incoming_edge']}
        outgoing = network['edges'][c['outgoing_edge']]['lanes']
        queues.append(float(sum(conn.lane.getLastStepHaltingNumber(lane) for lane in lanes)))
        occupancies.extend(conn.lane.getLastStepOccupancy(lane) / 100 for lane in outgoing)
    return {'t': now, 'queues': queues, 'downstream_occupancy': sum(occupancies)/len(occupancies) if occupancies else 0,
            'phase_elapsed_s': max((now-schedulers[c['junction']].entered_s for c in controls), default=0)}


def dispatch_observation(demand: dict, network: dict, controls: list[dict], sensed: dict,
                         sensor_lag_s: float) -> tuple[dict, dict[str, float]]:
    ambulance = next(v for v in demand['vehicles'] if v['id'] == 'ambulance')
    route = ambulance['route']
    cumulative = 0.0
    travel_times = {}
    route_distance = 0.0
    for i, edge in enumerate(route):
        length = max(0, network['edges'][edge]['length_m'] - (ambulance['depart_pos_m'] if i == 0 else 0))
        route_distance += length
        cumulative += length / min(network['edges'][edge]['speed_mps'], 13.89)
        travel_times[i] = cumulative
    queue_delay = 0.0
    etas = {}
    for c, queue in zip(controls, sensed['queues']):
        queue_delay += queue * 2.0
        etas[c['junction']] = demand['dispatch_s'] + travel_times[c['route_index']] + queue_delay
    values = {'queue_sum_veh': sum(sensed['queues']), 'queue_max_veh': max(sensed['queues'], default=0),
              'downstream_occupancy': sensed['downstream_occupancy'], 'route_distance_m': route_distance,
              'route_junction_count': len(controls), 'eta_remaining_s': cumulative + queue_delay,
              'phase_elapsed_s': sensed['phase_elapsed_s']}
    return {'dispatch_s': demand['dispatch_s'], 'sensor_lag_s': sensor_lag_s,
            'observed_at_s': sensed['t'], 'values': values,
            'eta_formula': 'dispatch + external lane free-flow time + 2 seconds per observed queued route vehicle; frozen'}, etas


def pose_frame(conn, network: dict, now: float) -> dict:
    vehicles = []
    for vid in conn.vehicle.getIDList():
        x, y = conn.vehicle.getPosition(vid)
        vehicles.append({'id': vid, 'type': conn.vehicle.getTypeID(vid), 'x': round(x, 4), 'y': round(y, 4),
                         'z': 0.0, 'angle_deg': round(conn.vehicle.getAngle(vid), 4),
                         'speed_mps': round(conn.vehicle.getSpeed(vid), 4),
                         'length_m': conn.vehicle.getLength(vid),
                         'width_m': conn.vehicle.getWidth(vid)})
    signals = [{'id': j, 'state': conn.trafficlight.getRedYellowGreenState(j), 'links': [{k: link[k] for k in ('index','from_edge','to_edge','from_lane','to_lane')} for link in s['links']]}
               for j, s in network['signals'].items()]
    return {'t': now, 'vehicles': vehicles, 'signals': signals,
            'queue_count': sum(v['speed_mps'] < .1 for v in vehicles if v['id'] != 'ambulance')}


def run_world(*, world_id: str, policy: str, lead_s: int, network_dir: Path, demand_dir: Path,
              demand: dict, network: dict, output: Path, horizon_s: float, drain_s: float,
              step_s: float = .5, sample_s: float = 1.0, sensor_lag_s: float = 1.0) -> dict:
    import traci
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    parameters = (horizon_s, drain_s, step_s, sample_s, sensor_lag_s)
    if any(not math.isfinite(v) for v in parameters) or step_s <= 0 or sample_s <= 0 or drain_s < 0 or sensor_lag_s < 0:
        raise ValueError('Timing values must be finite; step/sample positive, drain/lag nonnegative')
    if demand['dispatch_s'] < sensor_lag_s:
        raise ValueError('Dispatch must allow the declared sensor lag')
    end_s = horizon_s + drain_s
    if horizon_s < demand['demand_end_s'] or end_s <= demand['dispatch_s']:
        raise ValueError('Common horizon must cover all scheduled demand')
    if sample_s < step_s or abs(sample_s / step_s - round(sample_s / step_s)) > 1e-9:
        raise ValueError('Sample interval must be a positive integer multiple of simulation step')
    if any(abs(t/step_s-round(t/step_s)) > 1e-9 for t in (end_s, horizon_s, demand['dispatch_s'])):
        raise ValueError('Dispatch, horizon and common endpoint must align with simulation step')
    command = [binary('sumo'), '--net-file', str(network_dir/'network.net.xml'),
               '--route-files', str(demand_dir/'demand.rou.xml'), '--step-length', str(step_s),
               '--seed', str(demand['seed']), '--begin', '0', '--end', str(end_s),
               '--time-to-teleport', '-1', '--collision.action', 'warn', '--collision.check-junctions', 'true',
               '--max-depart-delay', '-1', '--device.bluelight.probability', '0',
               '--tripinfo-output', str(output/'tripinfo.xml'), '--tripinfo-output.write-unfinished', 'true',
               '--tripinfo-output.write-undeparted', 'true', '--no-step-log', 'true',
               '--duration-log.disable', 'true', '--error-log', str(output/'sumo-errors.log')]
    write_json(output/'command.json', command)
    label = f'afterlight_{world_id}_{time.time_ns()}'
    conn = None
    ledger = Accounting({v['id']: v for v in demand['vehicles']})
    frames, queue_samples, events, reasons = [], [], [], []
    controls = route_controls(next(v['route'] for v in demand['vehicles'] if v['id'] == 'ambulance'), network)
    schedulers = {j: Scheduler(j, tuple(s['greens'])) for j, s in network['signals'].items()}
    observations = deque()
    decision = None
    horizon_accounting = None
    burden_vehicle_s = 0.0
    drain_burden_vehicle_s = 0.0
    sumo_stdout = None
    try:
        sumo_stdout = open(output/'sumo-stdout.txt', 'w', encoding='utf-8')
        traci.start(command, label=label, stdout=sumo_stdout)
        conn = traci.getConnection(label)
        sumo_version = conn.getVersion()[1]
        for j, scheduler in schedulers.items():
            conn.trafficlight.setRedYellowGreenState(j, scheduler.state)
        observations.append(snapshot(conn, controls, schedulers, network, 0))
        queue_samples.append({'t': 0.0, 'queue_count': 0})
        total_steps = round(end_s / step_s)
        for step in range(total_steps):
            now = round(step * step_s, 9)
            if decision is None and now >= demand['dispatch_s']:
                sensed = next((o for o in reversed(observations) if o['t'] <= now-sensor_lag_s+1e-9), None)
                if sensed is None:
                    raise ValueError('No lagged observation available at dispatch')
                observation, etas = dispatch_observation(demand, network, controls, sensed, sensor_lag_s)
                analytical = choose_lead(observation)
                selected_lead = analytical['lead_s'] if policy == 'analytical' else lead_s
                if policy not in ('ordinary', 'fixed', 'immediate', 'analytical'):
                    raise ValueError(f'Policy {policy} is not implemented in this runner checkpoint')
                plan = {} if policy == 'ordinary' else request_plan(now, etas, lead_s=selected_lead, immediate=policy == 'immediate')
                decision = {'t': now, 'kind': 'dispatch', 'policy': policy, 'selected_lead_s': selected_lead if policy in ('fixed','analytical') else None,
                            'candidate_prediction': analytical,
                            'observation': observation, 'absolute_etas': etas, 'request_plan': plan,
                            'effective_candidate_count': len(distinct_schedules(now, etas))}
                events.append(decision)
                for c in controls:
                    if c['junction'] in plan:
                        schedulers[c['junction']].plan(plan[c['junction']], c['phase'], planned_at_s=now)
            ambulance_active = 'ambulance' in conn.vehicle.getIDList()
            route_index = conn.vehicle.getRouteIndex('ambulance') if ambulance_active else -1
            ambulance_arrived = 'ambulance' in ledger.completed
            control_by_junction = {c['junction']: c for c in controls}
            for j, scheduler in schedulers.items():
                c = control_by_junction.get(j)
                passed = c is not None and (ambulance_arrived or route_index > c['route_index'])
                state = scheduler.advance(now, passed=passed, queues=phase_queues(conn, network['signals'][j]))
                conn.trafficlight.setRedYellowGreenState(j, state)
            # Signal state at timestamp t is the state after boundary control,
            # never the stale pre-transition state from the previous step.
            observations[-1] = snapshot(conn, controls, schedulers, network, now)
            if step % round(sample_s/step_s) == 0:
                frames.append(pose_frame(conn, network, now))
            conn.simulationStep()
            current = round((step + 1) * step_s, 9)
            departed_ids = conn.simulation.getDepartedIDList()
            arrived_ids = conn.simulation.getArrivedIDList()
            ledger.depart(departed_ids, current)
            ledger.arrive(arrived_ids, current)
            if 'ambulance' in departed_ids:
                events.append({'t': current, 'kind': 'ambulance_inserted', 'insertion_delay_s': current-demand['dispatch_s']})
            if 'ambulance' in arrived_ids:
                events.append({'t': current, 'kind': 'ambulance_arrived', 'journey_s': current-demand['dispatch_s']})
            for kind, ids in (('collision', conn.simulation.getCollidingVehiclesIDList()),
                              ('teleport', conn.simulation.getStartingTeleportIDList())):
                if ids:
                    reasons.append(kind)
                    events.append({'t': current, 'kind': kind, 'vehicle_ids': list(ids)})
            observations.append(snapshot(conn, controls, schedulers, network, current))
            while len(observations) > 1 and observations[1]['t'] < current-sensor_lag_s-step_s:
                observations.popleft()
            queued = sum(conn.vehicle.getSpeed(v) < .1 for v in conn.vehicle.getIDList() if v != 'ambulance')
            pending_due = sum(v['depart_s'] <= current and vid not in ledger.inserted
                              for vid, v in ledger.scheduled.items() if vid != 'ambulance')
            if current <= horizon_s:
                burden_vehicle_s += (queued + pending_due) * step_s
            else:
                drain_burden_vehicle_s += (queued + pending_due) * step_s
            queue_samples.append({'t': current, 'queue_count': queued})
            if abs(current-horizon_s) < 1e-8:
                horizon_accounting = ledger.counts()
        # Close the exact common endpoint with its own legal boundary update.
        ambulance_active = 'ambulance' in conn.vehicle.getIDList()
        route_index = conn.vehicle.getRouteIndex('ambulance') if ambulance_active else -1
        for j, scheduler in schedulers.items():
            c = control_by_junction.get(j)
            passed = c is not None and ('ambulance' in ledger.completed or route_index > c['route_index'])
            conn.trafficlight.setRedYellowGreenState(j, scheduler.advance(end_s, passed=passed, queues=phase_queues(conn, network['signals'][j])))
        frames.append(pose_frame(conn, network, end_s))
        events.extend(event for scheduler in schedulers.values() for event in scheduler.events)
        physical = set(conn.vehicle.getIDList())
        expected_running = set(ledger.inserted) - set(ledger.completed)
        if physical != expected_running:
            reasons.append('vehicle_inventory_mismatch')
        # Flush SUMO output before deriving exact trip metrics. List notifications
        # are discovery-step times; tripinfo is authoritative for actual times.
        conn.close()
        conn = None
        reasons.extend(reconcile_tripinfo(ledger, output/'tripinfo.xml'))
        for event in events:
            if event['kind'] == 'ambulance_inserted' and 'ambulance' in ledger.inserted:
                event['detected_at_s'] = event['t']
                event['t'] = ledger.inserted['ambulance']
                event['insertion_delay_s'] = event['t']-demand['dispatch_s']
            elif event['kind'] == 'ambulance_arrived' and 'ambulance' in ledger.completed:
                event['detected_at_s'] = event['t']
                event['t'] = ledger.completed['ambulance']
                event['journey_s'] = event['t']-demand['dispatch_s']
        events.sort(key=lambda event: (event['t'], event.get('junction', ''), event['kind']))
        counts = ledger.counts()
        fully_drained = counts['completed'] == counts['scheduled'] and 'ambulance' in ledger.completed
        status = 'invalid' if reasons else ('completed' if fully_drained else 'censored')
        metrics = {'status': status, 'validity_reasons': sorted(set(reasons)),
                   'ambulance_journey_s': ledger.completed.get('ambulance', 0)-demand['dispatch_s'] if 'ambulance' in ledger.completed else None,
                   'civilian_mean_excess_s': ledger.completed_civilian_mean_excess() if status == 'completed' else None,
                   'accounting': counts, 'horizon_accounting': horizon_accounting,
                   'horizon_s': horizon_s, 'drain_end_s': end_s, 'queue_samples': queue_samples,
                   'common_horizon_burden_vehicle_s': burden_vehicle_s,
                   'drain_burden_vehicle_s': drain_burden_vehicle_s,
                   'runtime_s': time.perf_counter()-started,
                   'civilian_reference_definition': demand['reference_definition'],
                   'trip_time_source': 'SUMO tripinfo departure/arrival; list-event discovery timestamps retained separately'}
        result = {'world_id': world_id, 'policy': policy, 'lead_s': decision['selected_lead_s'] if decision else None,
                  'status': status, 'metrics': metrics, 'events': events, 'frames': frames,
                  'decision': decision, 'sumo_version': sumo_version}
        write_json(output/'lifecycle.json', ledger.rows())
        write_json(output/'outcome.json', {k:v for k,v in result.items() if k != 'frames'})
        return result
    except Exception as exc:
        write_json(output/'failure.json', {'status': 'infrastructure_error', 'reason': str(exc),
                   'traceback': traceback.format_exc(), 'accounting': ledger.counts(),
                   'runtime_s': time.perf_counter()-started, 'policy': policy})
        raise
    finally:
        if conn is not None:
            conn.close()
        if sumo_stdout is not None:
            sumo_stdout.close()


def run_pair(args) -> dict:
    output = args.output.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise OutputPathError('Output path already exists; choose a new path to preserve prior evidence') from exc
    if isinstance(args.seed,bool) or not isinstance(args.seed,int) or not 0 <= args.seed <= 2**31-1:
        raise ValueError('Seed must be an integer from 0 to 2147483647')
    source = source_snapshot()
    network_dir = output/'network'
    network_manifest = build_network(args.network, network_dir)
    graph = json.loads((network_dir/'graph.json').read_text(encoding='utf-8'))
    network = read_network(network_dir/'network.net.xml')
    demand = make_demand(graph, network, seed=args.seed, regime=args.regime,
                         dispatch_s=args.dispatch, demand_end_s=args.demand_end,
                         pickup_id=args.pickup, hospital_id=args.hospital)
    demand_dir = output/'demand'
    hashes = save_demand(demand, demand_dir)
    common = dict(network_dir=network_dir, demand_dir=demand_dir, demand=demand, network=network,
                  horizon_s=args.horizon, drain_s=args.drain, step_s=args.step, sample_s=args.sample)
    worlds = {}
    for world_id, policy in [('baseline', 'ordinary'), ('afterlight', args.policy)]:
        worlds[world_id] = run_world(world_id=world_id, policy=policy, lead_s=args.lead,
                                    output=output/world_id, **common)
    if source_snapshot() != source:
        raise RuntimeError('Project source changed during the pair; raw worlds retained, replay publication refused')
    episode_id = episode_identity(network_kind=args.network,regime=args.regime,seed=args.seed,
        network_sha256=network_manifest['network_sha256'],demand_sha256=hashes['demand_sha256'],
        dispatch_s=args.dispatch,horizon_s=args.horizon,drain_s=args.drain,step_s=args.step)
    # Scientific episode/action identity is stable across code revisions; the
    # public recording ID also names its source revision so a corrected capture
    # never overwrites older evidence with the same experiment parameters.
    scenario_id = run_identity(episode_id,args.policy,worlds['afterlight']['lead_s']) + '-' + source['source_code_sha256'][:12]
    provenance = {**source, 'network_sha256': network_manifest['network_sha256'],
                  'canonical_map_sha256': network_manifest['canonical_map_sha256'],
                  'network_file_sha256': network_manifest['network_file_sha256'],
                  'network_hash_definition': network_manifest['network_hash_definition'],
                  **hashes, 'sumo_version': worlds['baseline']['sumo_version'],
                  'dependencies': {n:importlib.metadata.version(n) for n in ('traci','sumolib','eclipse-sumo')},
                  'model_sha256': None, 'verification': 'real SUMO execution; benchmark interpretation requires evaluation gates'}
    replay = {'schema': SCHEMA, 'mode': 'recorded',
              'scenario': {'id': scenario_id, 'episode_id': episode_id, 'network_kind': args.network, 'seed': args.seed,
                'pickup_id': demand['pickup_id'], 'hospital_id': demand['hospital_id'],
                'dispatch_s': args.dispatch, 'regime': args.regime, 'split': args.split,
                'route_edges': next(v['route'] for v in demand['vehicles'] if v['id'] == 'ambulance')},
              'coordinates': {'source': 'canonical XY meters', 'position_reference': 'front_bumper',
                'render': '[x,z,-y]', 'angle_deg': 'SUMO navigation: clockwise from north; 0=+Y,90=+X'},
              'provenance': provenance,
              'network_geometry': {'signals': [{'id':j, 'position':s['position'], 'links':s['links']} for j,s in network['signals'].items()]},
              'duration_s': args.horizon+args.drain, 'step_s': args.sample,
              'worlds': worlds}
    replay_metadata = save_replay(output/'replay.json', replay)
    write_json(output/'replay-manifest.json', replay_metadata)
    scalar_rows = []
    for world in worlds.values():
        scalar_rows.append({'episode_id': episode_id, 'run_id': run_identity(episode_id,world['policy'],world['lead_s']), 'demand_group_id': hashes['demand_group_id'],
            'split': args.split, 'policy': world['policy'], 'lead_s': world['lead_s'],
            **world['metrics'], 'demand_sha256': hashes['demand_sha256'],
            'network_sha256': network_manifest['network_sha256'], 'source_commit': provenance['source_commit'],
            'decision': world['decision'],
            'observation': world['decision']['observation'],
            'request_plan': world['decision']['request_plan'],
            'analytical_cost_s': next((r['analytical_cost_s'] for r in world['decision']['candidate_prediction']['analytical']['scores'] if r['lead_s'] == world['lead_s']), None),
            'analytical_config_sha256': digest({k: world['decision']['candidate_prediction']['analytical'][k] for k in ('version','config')})})
    write_json(output/'outcomes.json', scalar_rows)
    return {'scenario_id': scenario_id, 'replay': str(output/'replay.json'),
            'world_status': {w:d['status'] for w,d in worlds.items()}, **replay_metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', choices=('fixture','city'), default='fixture')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--regime', choices=('sparse','moderate','heavy','asymmetric'), default='moderate')
    parser.add_argument('--policy', choices=('fixed','immediate','ordinary','analytical'), default='fixed')
    parser.add_argument('--lead', type=int, choices=(0,5,10,20,30), default=10)
    parser.add_argument('--dispatch', type=float, default=60)
    parser.add_argument('--demand-end', type=float, default=180)
    parser.add_argument('--horizon', type=float, default=240)
    parser.add_argument('--drain', type=float, default=360)
    parser.add_argument('--step', type=float, default=.5)
    parser.add_argument('--sample', type=float, default=1)
    parser.add_argument('--pickup')
    parser.add_argument('--hospital')
    parser.add_argument('--split', choices=('pilot','train','validation','test'), default='pilot')
    args = parser.parse_args()
    try:
        result = run_pair(args)
    except OutputPathError as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output/'pair-failure.json', {'status':'infrastructure_error','reason':str(exc),
                  'source_commit':source_commit(),'traceback':traceback.format_exc()})
        raise SystemExit(f'Run failed; retained failure record: {exc}') from exc
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
