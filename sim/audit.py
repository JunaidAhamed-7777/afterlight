"""Audit a completed real-run artifact directory on the test machine."""
from __future__ import annotations
import argparse
import bisect
import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from export.replay import validate_replay
from sim.network import read_network, sha256, write_json
from policies.scheduler import Timing


def audit(directory: Path) -> dict:
    replay = json.loads((directory/'replay.json').read_text(encoding='utf-8'))
    validate_replay(replay)
    network = read_network(directory/'network/network.net.xml')
    if sha256(directory/'demand/demand.rou.xml') != replay['provenance']['demand_sha256']:
        raise ValueError('Paired demand file identity changed')
    net_path = directory/'network/network.net.xml'
    canonical_hash = hashlib.sha256(ET.canonicalize(from_file=net_path,strip_text=True,with_comments=False).encode()).hexdigest()
    if canonical_hash != replay['provenance']['network_sha256'] or sha256(net_path) != replay['provenance']['network_file_sha256']:
        raise ValueError('Retained network differs from provenance')
    timing = Timing()
    checks = []
    for name, world in replay['worlds'].items():
        if name == 'baseline' and any(e['kind'] in ('request_planned','request','priority_green','recovery_requested') for e in world['events']):
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
                actual = next(s['state'] for s in frame['signals'] if s['id'] == junction)
                if actual != expected:
                    raise ValueError(f'{name}/{junction}: frame/event signal mismatch at {frame["t"]}')
        counts = world['metrics']['accounting']
        if counts['scheduled'] != counts['completed']+counts['running']+counts['not_inserted'] or counts['inserted'] != counts['completed']+counts['running']:
            raise ValueError(f'{name}: demand accounting does not reconcile')
        if world['status'] == 'completed' and (counts['running'] or counts['not_inserted'] or world['metrics']['ambulance_journey_s'] is None):
            raise ValueError(f'{name}: falsely completed run')
        for event in world['events']:
            if event['kind'] == 'request_planned' and event['t'] < replay['scenario']['dispatch_s']:
                raise ValueError(f'{name}: priority planned before dispatch')
        checks.append({'world':name,'signal_transition_and_frame_alignment':'passed',
                       'demand_reconciliation':'passed','status':world['status']})
    result = {'schema':'afterlight.audit.v1','run_id':replay['scenario']['id'],
              'replay_sha256':sha256(directory/'replay.json'),'checks':checks,
              'scope':'Artifact consistency and legal schedule timings; not visual QA or traffic-performance superiority'}
    write_json(directory/'audit.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.run),indent=2))


if __name__=='__main__': main()
