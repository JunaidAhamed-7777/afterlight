"""Explicit exploratory traffic qualification; never a benchmark-gain claim."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from api.artifacts import read_bytes, parse_json_object
from scripts.omen_acceptance import _safe, digest
from evaluation.metrics import finite

CASES={
    'fixture-fixed':{'network_kind':'fixture','policy':'fixed','regime':'moderate','pickup_id':'FIXTURE_PICKUP','hospital_id':'FIXTURE_HOSPITAL'},
    'fixture-ordinary':{'network_kind':'fixture','policy':'ordinary','regime':'moderate','pickup_id':'FIXTURE_PICKUP','hospital_id':'FIXTURE_HOSPITAL'},
    'city-sparse':{'network_kind':'city','policy':'fixed','regime':'sparse','pickup_id':'P001','hospital_id':'HOSP_EAST'},
}


def require_completed(replay:dict, case:str, source:dict, demand:dict) -> None:
    """Pure semantic gate in addition to the full raw-artifact audit."""
    expected=CASES[case];scenario=replay['scenario'];provenance=replay['provenance']
    for key in ('network_kind','regime','pickup_id','hospital_id'):
        if scenario.get(key)!=expected[key]:raise ValueError(f'Qualification {key} mismatch')
    if scenario.get('seed')!=7 or scenario.get('dispatch_s')!=60 or scenario.get('split')!='pilot':
        raise ValueError('Qualification seed/dispatch/exploratory split mismatch')
    if replay.get('duration_s')!=600 or replay.get('step_s')!=1:
        raise ValueError('Qualification sample/duration mismatch')
    if source.get('source_dirty') is not False or any(provenance.get(k)!=v for k,v in source.items()):
        raise ValueError('Qualification source identity mismatch')
    for key,value in {'seed':7,'regime':expected['regime'],'dispatch_s':60,'demand_end_s':180,
                      'pickup_id':expected['pickup_id'],'hospital_id':expected['hospital_id']}.items():
        if demand.get(key)!=value:raise ValueError('Qualification demand parameters mismatch')
    ambulances=[v for v in demand['vehicles'] if v['id']=='ambulance']
    if len(ambulances)!=1 or scenario.get('route_edges')!=ambulances[0]['route']:
        raise ValueError('Qualification route differs from saved demand')
    if set(replay['worlds'])!={'baseline','afterlight'}:raise ValueError('Qualification requires exactly two independent worlds')
    for name,world in replay['worlds'].items():
        metrics=world['metrics'];counts=metrics['accounting']
        policy='ordinary' if name=='baseline' else expected['policy']
        if world.get('policy')!=policy or (policy=='fixed' and world.get('lead_s')!=10):
            raise ValueError('Qualification policy/lead mismatch')
        if world.get('status')!='completed' or metrics.get('status')!='completed' or metrics.get('validity_reasons')!=[]:
            raise ValueError('Qualification refuses invalid/censored/incomplete world; raw evidence retained')
        if any(isinstance(counts.get(k),bool) or not isinstance(counts.get(k),int) or counts[k]<0
               for k in ('scheduled','inserted','completed','running','not_inserted')):
            raise ValueError('Qualification accounting malformed')
        if counts['running'] or counts['not_inserted'] or counts['scheduled']!=counts['completed'] or counts['inserted']!=counts['completed']:
            raise ValueError('Qualification requires every scheduled civilian completed')
        journey=metrics.get('ambulance_journey_s')
        finite(journey,'qualification ambulance journey')
        if any(metrics.get(k)!=v for k,v in {'horizon_s':240,'drain_end_s':600,'simulation_step_s':.5}.items()):
            raise ValueError('Qualification common timing mismatch')


def _validated_result(attempt:Path,case:str,source:dict,audit_fn)->dict:
    """Validate raw evidence and the fixed predecessor chain; never create files."""
    directory=_safe(attempt,'traffic/'+case)
    replay_bytes=read_bytes(_safe(directory,'replay.json'));replay=parse_json_object(replay_bytes)
    existing=parse_json_object(read_bytes(_safe(directory,'audit.json')))
    actual=audit_fn(directory,write_result=False)
    if existing!=actual or actual.get('replay_sha256')!=hashlib.sha256(replay_bytes).hexdigest():
        raise ValueError('Qualification audit does not bind the exact retained replay')
    demand=parse_json_object(read_bytes(_safe(directory,'demand/demand.json')))
    require_completed(replay,case,source,demand)
    if case in {'fixture-ordinary','city-sparse'}:
        predecessor='fixture-fixed' if case=='fixture-ordinary' else 'fixture-ordinary'
        # Ordinary recursively validates fixed; city therefore checks BOTH prior
        # raw pairs and exact successful records, not an editable status string.
        prior=_validated_result(attempt,predecessor,source,audit_fn)
        recorded=parse_json_object(read_bytes(_safe(attempt,'traffic/'+predecessor+'/qualification.json')))
        if recorded!=prior:raise ValueError('Prior qualification record differs from freshly audited evidence')
        if case=='fixture-ordinary':
            if actual.get('ordinary_negative_control')!='passed':raise ValueError('Independent ordinary negative control did not pass')
            for key in ('network_sha256','demand_sha256','demand_manifest_sha256'):
                if prior['input_hashes'][key]!=replay['provenance'][key]:raise ValueError('Fixture negative control inputs differ')
        elif prior['negative_control']!='passed':raise ValueError('City requires earlier qualified ordinary negative control')
    if read_bytes(_safe(directory,'replay.json'))!=replay_bytes:
        raise ValueError('Qualification replay changed during gate')
    result={'schema':'afterlight.traffic-qualification.v1','status':'qualified','case':case,'source':source,
        'replay_sha256':hashlib.sha256(replay_bytes).hexdigest(),'audit_sha256':digest(actual),
        'input_hashes':{key:replay['provenance'][key] for key in ('network_sha256','demand_sha256','demand_manifest_sha256')},
        'negative_control':actual['ordinary_negative_control'],
        'interpretation':'Exploratory software/traffic qualification only; not benchmark gain or real-world safety evidence'}
    return result


def qualify(attempt:Path,case:str,*,audit_fn=None,source_fn=None)->dict:
    from sim.audit import audit
    from sim.run import source_snapshot
    audit_fn=audit_fn or audit;source_fn=source_fn or source_snapshot
    result_path=_safe(attempt,'traffic/'+case+'/qualification.json')
    if result_path.exists():raise FileExistsError('Qualification evidence exists; no overwrite/retry')
    journal=parse_json_object(read_bytes(_safe(attempt,'run.json')))
    if journal.get('schema')!='afterlight.acceptance-run.v1' or journal.get('plan',{}).get('profile')!='traffic-qualification':
        raise ValueError('Qualification requires its recorded explicit acceptance profile')
    source=journal['source_identity']['source']
    if source_fn()!=source:raise ValueError('Source changed since qualification launch')
    result=_validated_result(attempt,case,source,audit_fn)
    if source_fn()!=source:raise ValueError('Source changed during qualification gate')
    # Exclusive final creation: another invocation can never replace prior evidence.
    import json,os
    with result_path.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',required=True,type=Path);parser.add_argument('--case',choices=tuple(CASES),required=True)
    args=parser.parse_args()
    from scripts.omen_acceptance import _output
    import json
    print(json.dumps(qualify(_output(ROOT,args.attempt),args.case),indent=2))


if __name__=='__main__':main()
