"""Package predeclared frozen-selector traces offline; never rerun or fit.

The displayed selected world remains a FIXED-policy recorded rollout. Only its
viewer world_id is aliased; the frozen selector's choice is separate evidence.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from api.artifacts import read_bytes, parse_json_object
from evaluation.protocol import digest
from evaluation.study_manifest import load_study, assert_study_runtime, assert_saved_inputs, file_hash
from evaluation.study_reporting import _contained, verify_released_test_collection
from evaluation.selectors import recompute_frozen_decisions
from export.replay import SCHEMA, validate_replay
from sim.network import ROOT, read_network

LEADS=(0,5,10,20,30)


def _object(path:Path,limit:int=8*1024*1024)->tuple[bytes,dict]:
    payload=read_bytes(path,limit=limit)
    return payload,parse_json_object(payload)


def verify_case_traces(collection:Path,study_envelope:dict,verified:dict,case_id:str)->dict:
    study=study_envelope['study'];contract=study['spec']['illustrative_capture']
    if case_id not in contract['case_ids']:raise ValueError('Case was not predeclared for illustrative capture')
    episodes=[e for e in study['episodes'] if e['case_id']==case_id and e['split']=='test']
    if len(episodes)!=1:raise ValueError('Illustrative case must identify one frozen test episode')
    episode=episodes[0];binding=verified['manifest']['illustrative_capture']
    if binding.get('contract')!=contract or binding.get('manifest_file')!='traces.json':raise ValueError('Trace contract/manifest mismatch')
    payload,envelope=_object(_contained(collection,'traces.json'))
    if hashlib.sha256(payload).hexdigest()!=binding.get('manifest_sha256'):raise ValueError('Trace manifest exact hash mismatch')
    traces=envelope['traces']
    if envelope.get('sha256')!=digest(traces) or traces.get('schema')!='afterlight.illustrative-traces.v1':raise ValueError('Trace envelope hash/schema mismatch')
    expected={'study_sha256':study_envelope['sha256'],'protocol_sha256':digest(study['protocol']),
              'source':study['source'],'split':'test','contract':contract}
    if any(traces.get(k)!=v for k,v in expected.items()):raise ValueError('Trace provenance differs from frozen study')
    for key in ('charged_bytes','retained_bytes','status'):
        if traces.get(key)!=binding.get(key):raise ValueError('Trace budget/status differs from collection')
    for key in ('charged_bytes','retained_bytes'):
        value=traces.get(key)
        if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Malformed trace byte accounting')
    if traces['retained_bytes']>contract['max_total_bytes'] or traces['retained_bytes']>traces['charged_bytes']:
        raise ValueError('Trace retained byte budget exceeded')
    entries=traces['entries'];required={('ordinary',None),*(('fixed',lead) for lead in LEADS)}
    selected=[e for e in entries if e['case_id']==case_id]
    if len(selected)!=6 or {(e['policy'],e['lead_s']) for e in selected}!=required:raise ValueError('All six illustrative traces required without duplicates')
    result={}
    for entry in selected:
        policy,lead=entry['policy'],entry['lead_s'];suffix=policy+(f'-{lead}' if lead is not None else '')
        relative=f'worlds/{case_id}/{suffix}/rich-world.json'
        if entry.get('state')!='retained' or entry.get('file')!=relative or entry.get('reason') is not None:
            raise ValueError('Illustrative trace unavailable; never rerun or substitute another candidate')
        if any(entry.get(k)!=episode[k] for k in ('episode_id','demand_sha256','network_sha256')):raise ValueError('Trace episode/input identity mismatch')
        raw,world=_object(_contained(collection,relative),contract['max_world_bytes'])
        if len(raw)!=entry.get('bytes') or hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):raise ValueError('Rich world exact byte identity mismatch')
        rows=[row for row in verified['rows'] if row['episode_id']==episode['episode_id'] and row['policy']==policy and row['lead_s']==lead]
        if len(rows)!=1 or rows[0].get('illustrative_trace')!=entry:raise ValueError('Scientific row trace reference mismatch')
        row=rows[0];directory=row['raw_world_directory']
        if directory!=str(Path(relative).parent).replace('\\','/'):raise ValueError('Trace raw world directory mismatch')
        raw_outcome,outcome=_object(_contained(collection,directory+'/outcome.json'))
        if hashlib.sha256(raw_outcome).hexdigest()!=row['raw_files_sha256']['outcome.json']:raise ValueError('Original outcome hash differs from verified collection')
        if {k:v for k,v in world.items() if k!='frames'}!=outcome:raise ValueError('Rich world differs from audited original outcome')
        raw_signal,signal=_object(_contained(collection,directory+'/signal-audit-input.json'))
        if hashlib.sha256(raw_signal).hexdigest()!=row['raw_files_sha256']['signal-audit-input.json']:raise ValueError('Original signal hash differs from verified collection')
        projected={key:world[key] for key in ('policy','status','events','decision','metrics')}
        projected['frames']=[{'t':f['t'],'signals':f['signals']} for f in world['frames']]
        if projected!=signal:raise ValueError('Rich trace differs from audited signal frames')
        if world.get('policy')!=policy or world.get('lead_s')!=lead:raise ValueError('Rich trace policy/lead mismatch')
        result[(policy,lead)]={'world':world,'row':row,'entry':entry,'bytes':raw}
    return {'episode':episode,'traces':result,'manifest_sha256':hashlib.sha256(payload).hexdigest()}


def assemble_replay(study_envelope:dict,episode:dict,pair:dict,network:dict,demand:dict,selection_evidence:dict)->dict:
    study=study_envelope['study'];timing=study['spec']['timing'];manifest=study['network']['manifest']
    worlds={}
    for alias,item in pair.items():
        world=deepcopy(item['world']);world['world_id']=alias;worlds[alias]=world
    provenance={**study['source'],**{k:manifest[k] for k in ('network_sha256','network_file_sha256','network_hash_definition','canonical_map_sha256')},
        **{k:episode[k] for k in ('demand_sha256','demand_manifest_sha256','demand_group_id')},
        'sumo_version':study['pilot_evidence']['sumo_version'],'dependencies':study['dependencies'],
        'model_sha256':selection_evidence['model_sha256'],
        'verification':'Exact frozen-study traces, offline selector choice; fixed-policy physics unchanged'}
    scenario={'id':'selected-'+digest({'episode':episode['episode_id'],'selection':selection_evidence['selection_sha256'],'trace':selection_evidence['trace_manifest_sha256']})[:40],
        'episode_id':episode['episode_id'],'network_kind':study['spec']['network_kind'],'seed':episode['seed'],
        'pickup_id':episode['pickup_id'],'hospital_id':episode['hospital_id'],'dispatch_s':episode['dispatch_s'],
        'regime':episode['regime'],'split':'test','route_edges':next(v['route'] for v in demand['vehicles'] if v['id']=='ambulance')}
    replay={'schema':SCHEMA,'mode':'recorded','scenario':scenario,'provenance':provenance,
        'coordinates':{'source':'canonical XY meters','position_reference':'front_bumper','render':'[x,z,-y]',
                       'angle_deg':'SUMO navigation: clockwise from north; 0=+Y,90=+X'},
        'duration_s':timing['horizon_s']+timing['drain_s'],'step_s':timing['sample_s'],
        'network_geometry':{'signals':[{'id':j,'position':signal['position'],'links':signal['links']} for j,signal in network['signals'].items()]},
        'worlds':worlds,'selection_evidence':selection_evidence}
    validate_replay(replay)
    return replay


def export_selected(study_directory:Path,collection_directory:Path,report_directory:Path,case_id:str,output:Path)->dict:
    from evaluation.study_reporting import verify_report_artifacts
    from sim.audit import audit
    study_directory=study_directory.resolve();collection_directory=collection_directory.resolve();report_directory=report_directory.resolve()
    envelope=load_study(study_directory,require_frozen=True,verify_inputs=True);study=envelope['study'];assert_study_runtime(study)
    verified=verify_released_test_collection(study_directory,collection_directory)
    report=verify_report_artifacts(study_directory,collection_directory,report_directory)
    context=verified['release_context'];release=context['release']['release'];selection_directory=context['selection_directory']
    captured=verify_case_traces(collection_directory,envelope,verified,case_id);episode=captured['episode']
    comparator='learned-vs-fixed.json' if release['mode']=='learned' else 'analytical-vs-fixed.json'
    _,frozen=_object(_contained(selection_directory,comparator))
    if file_hash(_contained(selection_directory,comparator))!=release['comparison_artifacts_sha256'][comparator]:raise ValueError('Frozen comparator changed')
    choices,_=recompute_frozen_decisions(verified['candidate_rows'],{'sha256':digest(study['protocol']),'protocol':study['protocol']},frozen)
    lead=choices[episode['episode_id']];selector=frozen['selectors']['selected'];kind=selector['selector']['kind']
    if kind not in ('residual_tree','analytical'):raise ValueError('Selected replay requires released learned or analytical selector')
    model=selector['selector'].get('model')
    pair={'baseline':captured['traces'][('ordinary',None)],'afterlight':captured['traces'][('fixed',lead)]}
    evidence={'schema':'afterlight.selection-evidence.v1','selector_kind':kind,'selector_sha256':selector['sha256'],
        'model_sha256':model['sha256'] if model else None,'model_file_sha256':release['selected_model_sha256'],
        'study_sha256':envelope['sha256'],'protocol_sha256':digest(study['protocol']),'release_sha256':context['release']['sha256'],
        'report_sha256':report['sha256'],'selection_sha256':release['selection_sha256'],'trace_manifest_sha256':captured['manifest_sha256'],
        'collection_manifest_sha256':file_hash(_contained(collection_directory,'collection.json')),
        'comparison_artifact_sha256':release['comparison_artifacts_sha256'][comparator],
        'case_id':case_id,'episode_id':episode['episode_id'],'selected_lead_s':lead,
        'source_world_aliases':{alias:{'original_world_id':item['world']['world_id'],'trace_sha256':item['entry']['sha256'],'trace_file':item['entry']['file']} for alias,item in pair.items()},
        'interpretation':'Frozen selector chose a predeclared recorded fixed-lead candidate using only lagged observations. No live ML controller, new rollout, retiming or benefit claim. Invalid/censored outcomes remain visible.'}
    network_dir=_contained(study_directory,study['network']['directory']);demand_dir=_contained(study_directory,episode['demand_directory'])
    _,demand=_object(_contained(demand_dir,'demand.json'));network=read_network(_contained(network_dir,'network.net.xml'))
    replay=assemble_replay(envelope,episode,pair,network,demand,evidence)
    runtime=ROOT/'local-runtime'
    if runtime.is_symlink() or not runtime.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Runtime root redirected')
    output=output.absolute()
    if not output.resolve().is_relative_to(runtime.resolve()) or output.resolve()==runtime.resolve():raise ValueError('Export must stay in ignored local-runtime')
    _contained(runtime,output.relative_to(runtime).as_posix())
    for protected in (study_directory,collection_directory,report_directory,selection_directory):
        if output.resolve().is_relative_to(protected) or protected.is_relative_to(output.resolve()):raise ValueError('Export cannot overlap frozen evidence')
    if output.exists():raise FileExistsError('Selected replay output must be fresh; no overwrite')
    # Snapshot exact source bytes before output creation. All original raw files
    # remain unchanged; copied rich-world/outcome preserve original identities.
    files={}
    for folder,destination in ((network_dir,'network'),(demand_dir,'demand')):
        for path in folder.iterdir():
            safe=_contained(folder,path.name)
            if not safe.is_file():raise ValueError('Unexpected non-file frozen input')
            files[destination+'/'+path.name]=safe.read_bytes()
    outcomes=[]
    for alias,item in pair.items():
        for filename,expected in item['row']['raw_files_sha256'].items():
            payload=read_bytes(_contained(collection_directory,item['row']['raw_world_directory']+'/'+filename))
            if hashlib.sha256(payload).hexdigest()!=expected:raise ValueError('Original raw output changed')
            files[alias+'/'+filename]=payload
        files[alias+'/rich-world.json']=item['bytes']
        outcomes.append({**item['row'],**item['world']['metrics'],'world_id':alias})
    files['original-collection-outcomes.json']=read_bytes(_contained(collection_directory,'outcomes.json'))
    def encoded(value):return (json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode()
    files['replay.json']=encoded(replay);files['outcomes.json']=encoded(outcomes)
    files['selection-evidence.json']=encoded(evidence)
    files['selected-export-manifest.json']=encoded({'schema':'afterlight.selected-export.v1','files_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in files.items()},'selection_evidence':evidence})
    assert_study_runtime(study);assert_saved_inputs(study_directory,study)
    if verify_report_artifacts(study_directory,collection_directory,report_directory)!=report:raise ValueError('Report evidence changed during export')
    if verify_case_traces(collection_directory,envelope,verified,case_id)!=captured:raise ValueError('Illustrative traces changed during export')
    output.mkdir(parents=True,exist_ok=False)
    try:
        for relative,payload in files.items():
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(payload)
        result=audit(output,write_result=True)
        assert_study_runtime(study)
        return {'status':'exported','replay':str(output/'replay.json'),'audit':result,'selection_evidence':evidence,
                'publication':'Offline local export only; public-size review and catalog registration remain separate'}
    except Exception as error:
        with (output/'export-failure.json').open('x',encoding='utf-8') as stream:json.dump({'status':'infrastructure_error','reason':str(error)},stream)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','collection','report','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--case',required=True)
    args=parser.parse_args();print(json.dumps(export_selected(args.study,args.collection,args.report,args.case,args.output),indent=2))


if __name__=='__main__':main()
