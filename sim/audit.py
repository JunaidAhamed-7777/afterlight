"""Audit a completed real-run artifact directory on the test machine."""
from __future__ import annotations
import argparse
import bisect
import json
import hashlib
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from export.replay import validate_replay
from sim.network import read_network, sha256, write_json
from policies.scheduler import Timing, TIME_EPSILON_S
from sim.accounting import Accounting, reconcile_tripinfo


def audit_lifecycle(demand: dict, rows: list[dict], tripinfo_path: Path, metrics: dict) -> None:
    """Cross-check published scalar metrics against retained raw SUMO lifecycle."""
    scheduled={v['id']:v for v in demand['vehicles']}
    if len(rows)!=len(scheduled) or {row['id'] for row in rows}!=set(scheduled):
        raise ValueError('Lifecycle rows must cover every scheduled vehicle exactly once')
    ledger=Accounting(scheduled)
    for row in rows:
        expected=scheduled[row['id']]
        if row['scheduled_depart_s']!=expected['depart_s'] or row['reference_s']!=expected['reference_s'] or row['type']!=expected['type']:
            raise ValueError('Lifecycle input/reference differs from hashed demand manifest')
        if row['actual_depart_s'] is not None: ledger.inserted[row['id']]=row['actual_depart_s']
        if row['arrival_s'] is not None: ledger.completed[row['id']]=row['arrival_s']
    prior_departures,prior_arrivals=dict(ledger.inserted),dict(ledger.completed)
    reasons=reconcile_tripinfo(ledger,tripinfo_path)
    undeclared=set(reasons)-set(metrics.get('validity_reasons',[]))
    if undeclared or ledger.inserted!=prior_departures or ledger.completed!=prior_arrivals:
        raise ValueError(f'Lifecycle timestamps differ from raw SUMO tripinfo: {reasons}')
    if ledger.counts()!=metrics['accounting']:
        raise ValueError('Published counts differ from raw all-demand lifecycle')
    journey=ledger.completed['ambulance']-demand['dispatch_s'] if 'ambulance' in ledger.completed else None
    if journey!=metrics['ambulance_journey_s']:
        raise ValueError('Published ambulance journey differs from raw arrival time')
    expected_mean=ledger.completed_civilian_mean_excess() if metrics['status']=='completed' else None
    if expected_mean!=metrics['civilian_mean_excess_s']:
        raise ValueError('Published civilian mean differs from raw lifecycle/reference')


def audit_outcomes(replay: dict, rows: list[dict]) -> None:
    """Scalar table must be the same evidence as the audited replay, not stale data."""
    if len(rows)!=2:
        raise ValueError('Paired scalar output must contain exactly baseline and AFTERLIGHT rows')
    for name,row in zip(('baseline','afterlight'),rows):
        world=replay['worlds'][name]
        expected={'episode_id':replay['scenario']['episode_id'],
                  'demand_group_id':replay['provenance']['demand_group_id'],
                  'demand_sha256':replay['provenance']['demand_sha256'],
                  'network_sha256':replay['provenance']['network_sha256'],
                  'source_commit':replay['provenance']['source_commit'],
                  'policy':world['policy'],'lead_s':world.get('lead_s'),
                  'observation':world['decision']['observation'],
                  'request_plan':world['decision']['request_plan'],**world['metrics']}
        if row.get('world_id',name)!=name:
            raise ValueError('Scalar world identity/order differs from replay')
        for key,value in expected.items():
            if row.get(key)!=value:
                raise ValueError(f'{name}: scalar outcome {key} differs from audited replay')


def audit_ordinary_negative_control(replay: dict) -> bool:
    """Two fresh ordinary worlds must be identical except wall-clock runtime."""
    baseline,afterlight=replay['worlds']['baseline'],replay['worlds']['afterlight']
    if afterlight['policy']!='ordinary':
        return False
    for field in ('frames','events','decision','status'):
        if baseline[field]!=afterlight[field]:
            raise ValueError(f'Independent ordinary-world negative control differs: {field}')
    metrics=lambda world:{key:value for key,value in world['metrics'].items() if key!='runtime_s'}
    if metrics(baseline)!=metrics(afterlight):
        raise ValueError('Independent ordinary-world negative control metrics differ')
    return True


def audit_paired_dispatch(replay: dict) -> dict:
    """Check shared history and frozen causal inputs, never refit a predictor.

    Dispatch-boundary signal states may differ legitimately. Only samples and
    events strictly before dispatch are compared. Unknown future policy labels
    still receive the common-history audit, with timing coverage explicit.
    """
    tolerance = 1e-8

    def number(value, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name}: expected a finite nonnegative number')
        try:
            valid = math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f'{name}: expected a finite nonnegative number')
        return value

    dispatch = number(replay['scenario']['dispatch_s'], 'dispatch')
    worlds = replay['worlds']
    if set(worlds) != {'baseline', 'afterlight'} or worlds['baseline']['policy'] != 'ordinary':
        raise ValueError('Paired dispatch audit requires an ordinary baseline and separate AFTERLIGHT world')
    histories = {}
    decisions = {}
    timing_checks = {}
    for name in ('baseline', 'afterlight'):
        world = worlds[name]
        history = {}
        for field in ('frames', 'events'):
            history[field] = [row for row in world[field]
                              if number(row.get('t'), f'{name}/{field} timestamp') < dispatch]
        histories[name] = history
        decision = world.get('decision')
        if not isinstance(decision, dict) or decision.get('kind') != 'dispatch':
            raise ValueError(f'{name}: missing frozen dispatch decision')
        if abs(number(decision.get('t'), f'{name}/decision time') - dispatch) > tolerance:
            raise ValueError(f'{name}: decision was not frozen at dispatch')
        if decision.get('policy') != world['policy']:
            raise ValueError(f'{name}: decision/world policy identity differs')
        dispatch_events = [event for event in world['events'] if event.get('kind') == 'dispatch']
        if dispatch_events != [decision]:
            raise ValueError(f'{name}: dispatch event differs from the unique frozen decision')
        observation = decision.get('observation')
        if not isinstance(observation, dict):
            raise ValueError(f'{name}: missing dispatch observation')
        if number(observation.get('dispatch_s'), f'{name}/observation dispatch') != dispatch:
            raise ValueError(f'{name}: observation belongs to another dispatch')
        lag = number(observation.get('sensor_lag_s'), f'{name}/sensor lag')
        observed = number(observation.get('observed_at_s'), f'{name}/observation time')
        if observed > dispatch - lag + 1e-9:
            raise ValueError(f'{name}: observation violates declared causal sensor lag')
        # Validate the stable observation schema only, not any predictor/model
        # version. Zero lag is an existing supported runner contract: the
        # dispatch observation still precedes this world's priority action.
        from models.residual import DEFAULT_FEATURES, feature_vector
        feature_vector(observation, 0, 0, DEFAULT_FEATURES)
        etas = decision.get('absolute_etas')
        plan = decision.get('request_plan')
        if not isinstance(etas, dict) or not isinstance(plan, dict):
            raise ValueError(f'{name}: frozen ETA/request maps required')
        for junction, eta in etas.items():
            if not isinstance(junction, str) or not junction or number(eta, f'{name}/absolute ETA') < dispatch:
                raise ValueError(f'{name}: ETA must be absolute and at or after dispatch')
        for junction, timestamp in plan.items():
            if not isinstance(junction, str) or not junction:
                raise ValueError(f'{name}: invalid request junction')
            number(timestamp, f'{name}/request time')
        policy = world['policy']
        expected = None
        if policy == 'ordinary':
            expected = {}
        elif policy == 'immediate':
            expected = {junction: dispatch for junction in etas}
        elif policy in ('fixed', 'analytical'):
            from policies.timing import LEADS
            lead = decision.get('selected_lead_s')
            if isinstance(lead, bool) or lead not in LEADS or world.get('lead_s') != lead:
                raise ValueError(f'{name}: frozen selected lead/world lead mismatch')
            expected = {junction: max(dispatch, eta - lead) for junction, eta in etas.items()}
        if expected is not None:
            if set(plan) != set(expected) or any(abs(plan[junction] - timestamp) > tolerance
                                               for junction, timestamp in expected.items()):
                raise ValueError(f'{name}: request plan differs from frozen dispatch/ETA/lead formula')
            timing_checks[name] = 'passed'
        else:
            timing_checks[name] = 'not_checked_for_policy'
        decisions[name] = decision
    if histories['baseline'] != histories['afterlight']:
        raise ValueError('Paired worlds differ before dispatch intervention')
    for field in ('observation', 'absolute_etas'):
        if decisions['baseline'][field] != decisions['afterlight'][field]:
            raise ValueError(f'Paired dispatch {field} differ before policy selection')
    return {'shared_pre_dispatch_history': 'passed', 'shared_causal_observation_and_etas': 'passed',
            'pre_dispatch_frames': len(histories['baseline']['frames']),
            'pre_dispatch_events': len(histories['baseline']['events']),
            'frozen_request_timing': timing_checks}


def audit_world_signals(world: dict, network: dict, dispatch_s: float, *, simulation_step_s: float | None = None) -> dict:
    """Pure per-world legal-transition, frozen-plan and sampled-state audit."""
    name=world.get('world_id',world['policy'])
    timing=Timing()
    tolerance=1e-8  # Absolute numerical tolerance, never a whole simulation tick.
    recorded_step=world.get('metrics',{}).get('simulation_step_s')
    for candidate in (simulation_step_s,recorded_step):
        if candidate is not None and (isinstance(candidate,bool) or not isinstance(candidate,(int,float)) or not math.isfinite(candidate) or candidate<=0):
            raise ValueError(f'{name}: invalid integration-step provenance')
    if simulation_step_s is not None and recorded_step is not None and simulation_step_s!=recorded_step:
        raise ValueError(f'{name}: explicit integration step disagrees with recorded metadata')
    step=simulation_step_s if simulation_step_s is not None else recorded_step
    last_event_time={}
    event_groups={junction:[] for junction in network['signals']}
    for event in world['events']:
        t=event.get('t')
        if isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or t<0:
            raise ValueError(f'{name}: event timestamp must be finite and nonnegative')
        junction=event.get('junction')
        if junction is None:
            continue
        if junction not in event_groups:
            raise ValueError(f'{name}: event names unknown signal junction {junction}')
        if t<last_event_time.get(junction,-1):
            raise ValueError(f'{name}/{junction}: event timestamps are not monotonic')
        last_event_time[junction]=t
        event_groups[junction].append(event)
        for field in ('phase','target'):
            if field in event:
                phase=event[field]
                if isinstance(phase,bool) or not isinstance(phase,int) or not 0<=phase<len(network['signals'][junction]['greens']):
                    raise ValueError(f'{name}/{junction}: invalid integer phase index')
        if event['kind']=='green' and 'phase' not in event:
            raise ValueError(f'{name}/{junction}: green event lacks phase index')
    for junction,events in event_groups.items():
        for kind in ('request_planned','request','priority_green','release'):
            if sum(event['kind']==kind for event in events)>1:
                raise ValueError(f'{name}/{junction}: duplicate {kind} event')
    frames=world.get('frames',[])
    if not frames or frames[0].get('t')!=0:
        raise ValueError(f'{name}: signal audit requires frames starting at zero')
    previous=-1.0
    for frame in frames:
        if isinstance(frame['t'],bool) or not isinstance(frame['t'],(int,float)) or not math.isfinite(frame['t']) or frame['t']<=previous:
            raise ValueError(f'{name}: frame timestamps must be finite and strictly increasing')
        previous=frame['t']
    if any(event['t']>frames[-1]['t'] for event in world['events']):
        raise ValueError(f'{name}: event occurs after recorded endpoint')
    if world['policy'] == 'ordinary' and any(e['kind'] in ('request_planned','request','priority_green','recovery_requested') for e in world['events']):
        raise ValueError('Ordinary baseline contains priority/recovery events')
    plan = world['decision']['request_plan']
    planned = {e['junction']:e['request_at_s'] for e in world['events'] if e['kind']=='request_planned'}
    if planned != plan:
        raise ValueError(f'{name}: request events differ from frozen dispatch plan')
    for junction, signal in network['signals'].items():
        events = [e for e in world['events'] if e.get('junction') == junction and e['kind'] in ('green','yellow','all_red')]
        if not events or events[0]['t'] != 0 or events[0]['kind'] != 'green':
            raise ValueError(f'{name}/{junction}: missing initial green')
        for previous, event in zip(events, events[1:]):
            expected_next = {'green':'yellow','yellow':'all_red','all_red':'green'}[previous['kind']]
            minimum = {'green':timing.min_green_s,'yellow':timing.yellow_s,'all_red':timing.all_red_s}[previous['kind']]
            if event['kind'] != expected_next or event['t']-previous['t'] < minimum-1e-8:
                raise ValueError(f'{name}/{junction}: illegal or too-short transition {previous} -> {event}')
        times = [e['t'] for e in events]
        active_phase = 0
        state_by_event = []
        for event in events:
            if event['kind'] == 'green':
                active_phase = event['phase']
                state = signal['greens'][active_phase]
            elif event['kind'] == 'yellow':
                state = ''.join('y' if c in 'gG' else 'r' for c in signal['greens'][active_phase])
            else:
                state = 'r'*len(signal['greens'][active_phase])
            state_by_event.append(state)
        for frame in world['frames']:
            expected = state_by_event[bisect.bisect_right(times,frame['t'])-1]
            matching=[s['state'] for s in frame['signals'] if s['id']==junction]
            if len(matching)!=1:
                raise ValueError(f'{name}/{junction}: missing or duplicate sampled signal')
            actual=matching[0]
            if actual != expected:
                raise ValueError(f'{name}/{junction}: frame/event signal mismatch at {frame["t"]}')
    for junction,events in event_groups.items():
        by_kind={event['kind']:event for event in events if event['kind'] in ('request_planned','request','priority_green','release')}
        planned_event=by_kind.get('request_planned')
        if planned_event is None:
            if by_kind:
                raise ValueError(f'{name}/{junction}: priority activity has no frozen plan')
            continue
        request_at=planned_event.get('request_at_s')
        if isinstance(request_at,bool) or not isinstance(request_at,(int,float)) or not math.isfinite(request_at) or request_at<planned_event['t']-tolerance or planned_event['t']<dispatch_s-tolerance:
            raise ValueError(f'{name}/{junction}: invalid frozen request timestamp')
        request_event=by_kind.get('request')
        onset=by_kind.get('priority_green')
        release=by_kind.get('release')
        if request_event is not None:
            if request_event['t']<request_at-tolerance:
                raise ValueError(f'{name}/{junction}: request happened before its frozen due time')
            if request_event.get('phase')!=planned_event.get('phase'):
                raise ValueError(f'{name}/{junction}: request phase differs from frozen plan')
        if onset is not None:
            if request_event is None or onset['t']<request_event['t']-tolerance:
                raise ValueError(f'{name}/{junction}: priority green precedes its request')
            if onset.get('phase')!=planned_event.get('phase'):
                raise ValueError(f'{name}/{junction}: priority green differs from requested phase')
        if release is not None and (release['t']<planned_event['t']-tolerance or (onset is not None and release['t']<onset['t']-tolerance)):
            raise ValueError(f'{name}/{junction}: release precedes plan or priority onset')
        if step is not None:
            endpoint=frames[-1]['t']
            quantized=lambda t:math.ceil((t-TIME_EPSILON_S)/step)*step
            # The runner explicitly advances every controller at the common
            # endpoint before capturing the final frame. Endpoint deadlines
            # therefore require their activation/release evidence too.
            if request_event is None and quantized(request_at)<=endpoint+tolerance and (release is None or release['t']>=request_at-tolerance):
                raise ValueError(f'{name}/{junction}: due priority request was never issued')
            if request_event is not None and request_event['t']>quantized(request_at)+tolerance:
                raise ValueError(f'{name}/{junction}: request exceeded integration-step quantization')
            if request_event is not None:
                deadline=quantized(request_at+timing.request_timeout_s)
                if (release is None and endpoint>=deadline-tolerance) or (release is not None and release['t']>deadline+tolerance):
                    raise ValueError(f'{name}/{junction}: priority request exceeded release timeout')
            if onset is not None:
                # Validated integration grids divide the hold duration; do
                # not grant an additional whole step to a green hold.
                deadline=onset['t']+timing.max_hold_s
                if (release is None and endpoint>=deadline-tolerance) or (release is not None and release['t']>deadline+tolerance):
                    raise ValueError(f'{name}/{junction}: priority green exceeded maximum hold')
    return {'priority_deadline_audit':'passed' if step is not None else 'not_checked_missing_integration_step',
            'simulation_step_s':step}


def audit(directory: Path, *, write_result: bool = True) -> dict:
    replay = json.loads((directory/'replay.json').read_text(encoding='utf-8'))
    validate_replay(replay)
    network = read_network(directory/'network/network.net.xml')
    if sha256(directory/'demand/demand.rou.xml') != replay['provenance']['demand_sha256']:
        raise ValueError('Paired demand file identity changed')
    net_path = directory/'network/network.net.xml'
    canonical_hash = hashlib.sha256(ET.canonicalize(from_file=net_path,strip_text=True,with_comments=False).encode()).hexdigest()
    if canonical_hash != replay['provenance']['network_sha256'] or sha256(net_path) != replay['provenance']['network_file_sha256']:
        raise ValueError('Retained network differs from provenance')
    demand_path=directory/'demand/demand.json'
    if sha256(demand_path)!=replay['provenance']['demand_manifest_sha256']:
        raise ValueError('Retained demand manifest differs from provenance')
    demand=json.loads(demand_path.read_text(encoding='utf-8'))
    checks = []
    for name, world in replay['worlds'].items():
        signal_audit=audit_world_signals(world,network,replay['scenario']['dispatch_s'])
        lifecycle=json.loads((directory/name/'lifecycle.json').read_text(encoding='utf-8'))
        audit_lifecycle(demand,lifecycle,directory/name/'tripinfo.xml',world['metrics'])
        counts = world['metrics']['accounting']
        if counts['scheduled'] != counts['completed']+counts['running']+counts['not_inserted'] or counts['inserted'] != counts['completed']+counts['running']:
            raise ValueError(f'{name}: demand accounting does not reconcile')
        if world['status'] == 'completed' and (counts['running'] or counts['not_inserted'] or world['metrics']['ambulance_journey_s'] is None):
            raise ValueError(f'{name}: falsely completed run')
        checks.append({'world':name,**signal_audit,'signal_transition_and_frame_alignment':'passed',
                       'demand_reconciliation':'passed','raw_tripinfo_metric_agreement':'passed','status':world['status']})
    paired_dispatch=audit_paired_dispatch(replay)
    negative_control=audit_ordinary_negative_control(replay)
    audit_outcomes(replay,json.loads((directory/'outcomes.json').read_text(encoding='utf-8')))
    result = {'schema':'afterlight.audit.v1','run_id':replay['scenario']['id'],
              'replay_sha256':sha256(directory/'replay.json'),'checks':checks,
              'scalar_table_agreement':'passed',
              'paired_dispatch_causality':paired_dispatch,
              'ordinary_negative_control':'passed' if negative_control else 'not_this_policy',
              'scope':'Artifact consistency and legal schedule timings; not visual QA or traffic-performance superiority'}
    if write_result:
        write_json(directory/'audit.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.run),indent=2))


if __name__=='__main__': main()
