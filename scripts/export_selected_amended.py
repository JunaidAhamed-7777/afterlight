"""Explicit post-report adapter for the pre-test frozen analysis correction.

Uses unchanged original trace verification, selector decisions, replay assembly
and raw-output audit. Never simulates, refits, resamples or retimes a trace.
Original export.selected_replay remains unchanged in the scientific checkout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('checkout','study','collection','report','amendment','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--case',required=True)
    args=parser.parse_args()
    from run_analysis_amendment import load_amended_analysis
    checkout=args.checkout.resolve(strict=True)
    def local(path):
        result=path.resolve() if path.is_absolute() else (checkout/path).resolve()
        runtime=(checkout/'local-runtime').resolve()
        if result==runtime or not result.is_relative_to(runtime):raise ValueError('Explicit pinned local-runtime paths required')
        return result
    study,collection,report,amendment,output=map(local,(args.study,args.collection,args.report,args.amendment,args.output))
    module,binding,envelope=load_amended_analysis(checkout,study,amendment)
    for protected in (amendment.parent,):
        if output.is_relative_to(protected) or protected.is_relative_to(output):raise ValueError('Export overlaps frozen amendment')
    # Imports have their actual original names and byte-bound source origins.
    global ROOT,read_bytes,digest,load_study,assert_study_runtime,assert_saved_inputs,file_hash
    global _contained,_object,verify_case_traces,assemble_replay,recompute_frozen_decisions,read_network
    from sim.network import ROOT,read_network
    from api.artifacts import read_bytes
    from evaluation.protocol import digest
    from evaluation.study_manifest import load_study,assert_study_runtime,assert_saved_inputs,file_hash
    from evaluation.study_reporting import _contained
    from evaluation.selectors import recompute_frozen_decisions
    from export.selected_replay import _object,verify_case_traces,assemble_replay
    frozen=load_study(study,require_frozen=True)
    source_path=checkout/'export/selected_replay.py'
    if file_hash(source_path)!=frozen['study']['source']['source_files']['export/selected_replay.py']:
        raise ValueError('Original trace export helpers differ from frozen simulation source')
    source_hash=file_hash(Path(__file__).resolve())
    result=export_selected_amended(study,collection,report,args.case,output,analysis_module=module,analysis_binding=binding)
    # Only a successful return establishes ownership of a fresh export directory.
    # Rejections before its mkdir must never add files to an existing input path.
    try:
        _,final_binding,final_envelope=load_amended_analysis(checkout,study,amendment)
        if final_binding!=binding or final_envelope!=envelope or file_hash(Path(__file__).resolve())!=source_hash:
            raise ValueError('Analysis amendment/export source changed during trace export; do not publish output')
    except Exception as error:
        if output.is_dir() and not (output/'export-failure.json').exists():
            with (output/'export-failure.json').open('x') as stream:
                json.dump({'status':'failed_not_publishable','reason':str(error)},stream)
        raise
    print(json.dumps(result,indent=2))


def export_selected_amended(study_directory:Path,collection_directory:Path,report_directory:Path,case_id:str,output:Path, *, analysis_module, analysis_binding)->dict:
    def verify_report_artifacts(study,collection,report):
        return analysis_module.verify_report_artifacts(study,collection,report,analysis_amendment=analysis_binding)
    verify_released_test_collection=analysis_module.verify_released_test_collection
    from sim.audit import audit
    study_directory=study_directory.resolve();collection_directory=collection_directory.resolve();report_directory=report_directory.resolve()
    envelope=load_study(study_directory,require_frozen=True,verify_inputs=True);study=envelope['study'];assert_study_runtime(study)
    report=verify_report_artifacts(study_directory,collection_directory,report_directory)
    verified=verify_released_test_collection(study_directory,collection_directory)
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
    evidence={'analysis_amendment':dict(analysis_binding),'schema':'afterlight.selection-evidence.v1','selector_kind':kind,'selector_sha256':selector['sha256'],
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
    files['selected-export-manifest.json']=encoded({'analysis_export_source_sha256':file_hash(Path(__file__).resolve()),'analysis_amendment':dict(analysis_binding),'schema':'afterlight.selected-export.v1','files_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in files.items()},'selection_evidence':evidence})
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


if __name__=='__main__':main()
