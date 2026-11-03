"""Warm in-process inference timing on every retained validation snapshot.

No simulator, fitting, test-outcome read, model selection or performance promotion.
The complete analytical estimate, feature construction, tree/hash checks and
five-candidate choice are timed. File loading and provenance audits are outside
the interval. Each original snapshot is used; outcomes are never predictor inputs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
from statistics import median, mean
import subprocess
import sys
import time


def timing_summary(samples):
    if not samples or any(isinstance(value,bool) or not isinstance(value,int) or value<0 for value in samples):
        raise ValueError('Nonempty nonnegative integer nanosecond samples required')
    ordered=sorted(samples)
    return {'samples':len(samples),'mean_ms':mean(samples)/1e6,'median_ms':median(samples)/1e6,
            'p95_ms':ordered[math.ceil(.95*len(samples))-1]/1e6,
            'min_ms':ordered[0]/1e6,'max_ms':ordered[-1]/1e6,
            'percentile_method':'nearest rank ceil(0.95*n) over timing calls, not traffic episodes'}


def process_context():
    command="@{cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);active_sumo_processes=@(Get-Process sumo -ErrorAction SilentlyContinue).Count} | ConvertTo-Json -Depth 4 -Compress"
    result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('checkout','study','selection','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--load-context',required=True,choices=('no-active-sumo','concurrent-sumo'))
    args=parser.parse_args()
    checkout=args.checkout.resolve(strict=True);sys.path.insert(0,str(checkout))
    from evaluation.protocol import digest
    from evaluation.study_manifest import load_study,assert_study_runtime,file_hash,read_json
    from evaluation.study_reporting import verify_selection_artifacts,_contained
    from models.analytical import AnalyticalConfig,estimate_candidates
    from models.residual import choose_candidate
    from evaluation.selectors import recompute_frozen_decisions
    from sim.network import ROOT
    if ROOT.resolve()!=checkout:raise ValueError('Simulation imports must originate in the explicit original checkout')
    runtime_path=checkout/'local-runtime'
    if runtime_path.is_symlink() or not runtime_path.resolve().is_relative_to(checkout):
        raise ValueError('Original local-runtime must not redirect outside its checkout')
    def local(path):
        result=path.resolve() if path.is_absolute() else (checkout/path).resolve()
        runtime=(checkout/'local-runtime').resolve()
        if result==runtime or not result.is_relative_to(runtime):raise ValueError('Explicit pinned local-runtime paths required')
        return result
    study_dir,selection_dir,output=map(local,(args.study,args.selection,args.output))
    if output.parent!=(checkout/'local-runtime').resolve():
        raise ValueError('Timing output must be a fresh direct child of original local-runtime')
    for protected in (study_dir,selection_dir):
        if output.is_relative_to(protected) or protected.is_relative_to(output):raise ValueError('Timing output overlaps frozen inputs')
    if output.exists():raise FileExistsError('Timing output must be fresh')
    study=load_study(study_dir,require_frozen=True,verify_inputs=True)
    selection=verify_selection_artifacts(study_dir,selection_dir)
    assert_study_runtime(study['study'])
    if selection['selection']['status']!='learned_ready':raise ValueError('A genuinely fitted frozen selector is required')
    model_path=_contained(selection_dir,'model.json');model=read_json(model_path)
    validation_path=_contained(selection_dir,'validation-candidates.json');rows=read_json(validation_path)
    snapshots={}
    for row in rows:
        if row['split']!='validation':raise ValueError('Only original retained validation snapshots are permitted')
        eid=row['episode_id'];observation=row['observation']
        if eid in snapshots and digest(snapshots[eid])!=digest(observation):raise ValueError('Candidate snapshots differ within a case')
        snapshots[eid]=observation
    expected={episode['episode_id'] for episode in study['study']['episodes'] if episode['split']=='validation'}
    if set(snapshots)!=expected:raise ValueError('Every original validation case must be included')
    observations=[(eid,snapshots[eid]) for eid in sorted(snapshots)]
    config=AnalyticalConfig(**study['study']['protocol']['analytical_estimator']['config'])
    names=[field['name'] for field in study['study']['protocol']['feature_schema']]
    comparison_path=_contained(selection_dir,'learned-vs-analytical.json')
    comparison=read_json(comparison_path)
    selected,analytical=recompute_frozen_decisions(rows,{'sha256':digest(study['study']['protocol']),
        'protocol':study['study']['protocol']},comparison)
    def decide(observation,model):
        estimates=estimate_candidates(observation,config)
        return choose_candidate(observation,{row['lead_s']:row['analytical_cost_s'] for row in estimates['scores']},names,model)['lead_s']
    source_sha=file_hash(Path(__file__).resolve());model_sha=file_hash(model_path);validation_sha=file_hash(validation_path)
    before=process_context()
    if args.load_context=='no-active-sumo' and before['active_sumo_processes']:
        raise ValueError('Declared no-active-SUMO timing requires no active SUMO process')
    if args.load_context=='concurrent-sumo' and not before['active_sumo_processes']:
        raise ValueError('Declared concurrent-SUMO timing requires an active SUMO process')
    variants=[('analytical',None),('learned',model)]
    decisions={};samples={name:[] for name,_ in variants}
    started=datetime.now(timezone.utc).isoformat()
    for _ in range(20):
        for eid,observation in observations:
            for name,variant in variants:decisions[name,eid]=decide(observation,variant)
    if any(decisions['learned',eid]!=selected[eid] or decisions['analytical',eid]!=analytical[eid] for eid,_ in observations):
        raise ValueError('Timing decisions differ from the original frozen comparison')
    for repeat in range(200):
        for eid,observation in observations:
            # Alternate method order to reduce a fixed order/load advantage.
            for name,variant in (variants if repeat%2==0 else list(reversed(variants))):
                stamp=time.perf_counter_ns();lead=decide(observation,variant);elapsed=time.perf_counter_ns()-stamp
                if lead!=decisions[name,eid]:raise ValueError('Frozen selector choice changed during timing')
                samples[name].append(elapsed)
    after=process_context()
    if args.load_context=='no-active-sumo' and after['active_sumo_processes']:
        raise ValueError('SUMO began during the declared no-active-SUMO measurement')
    assert_study_runtime(study['study'])
    if (verify_selection_artifacts(study_dir,selection_dir)!=selection or file_hash(model_path)!=model_sha or
            file_hash(validation_path)!=validation_sha or file_hash(Path(__file__).resolve())!=source_sha):
        raise ValueError('Frozen inference inputs/source changed during measurement')
    report={'schema':'afterlight.frozen-selector-latency.v1','scope':'warm in-process Python decision on every frozen validation snapshot; not browser, cloud or simulator latency',
        'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'load_context':args.load_context,
        'hardware_before':before,'hardware_after':after,'python':platform.python_version(),'platform':platform.platform(),
        'simulation_source':study['study']['source'],'benchmark_source_sha256':source_sha,
        'study_sha256':study['sha256'],'protocol_sha256':digest(study['study']['protocol']),
        'selection_sha256':selection['sha256'],'model_file_sha256':model_sha,'model_sha256':model['sha256'],
        'comparison_file_sha256':file_hash(comparison_path),'comparison_sha256':comparison['sha256'],
        'validation_file_sha256':validation_sha,'validation_snapshots':len(observations),'warmups_per_snapshot_per_variant':20,
        'timed_calls_per_snapshot_per_variant':200,'method_order':'alternating by repetition, fixed sorted episode order',
        'timed_work':'fresh analytical five-lead estimate + feature construction + original JSON model/hash validation + candidate choice',
        'excluded_work':'file loading, source/selection provenance audits, fitting, simulator execution, UI and network',
        'variants':{name:{**timing_summary(values),'samples_ns':values} for name,values in samples.items()},
        'decisions':[{'episode_id':eid,**{name:decisions[name,eid] for name,_ in variants}} for eid,_ in observations],
        'test_outcomes_read':False,'model_fitting_performed':False,'automatic_benefit_claim':False}
    output.mkdir(parents=True,exist_ok=False)
    with (output/'timing.json').open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({key:value for key,value in report.items() if key not in {'simulation_source','decisions','variants'}},indent=2))
    print(json.dumps({name:timing_summary(values) for name,values in samples.items()},indent=2))


if __name__=='__main__':main()
