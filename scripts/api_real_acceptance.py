"""Explicit Omen real-API qualification client; never manages server processes.

One unique fixed exploratory request/job; explicit same-ID probes after known acknowledgment.
No automatic POST retry after uncertainty. Status
is GET-only. A client monitoring deadline never kills an active SUMO process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import platform
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from uuid import uuid4

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from api.artifacts import MAX_REPLAY_BYTES, read_bytes, parse_json_object
from api.jobs import parameters, load_job_artifact
from scripts.omen_acceptance import _safe, _atomic, capture_identity, now

PARAMETERS={'network':'city','seed':7,'regime':'sparse','policy':'fixed','lead':10,'pickup':'P001','hospital':'HOSP_EAST'}


def capture_api_identity(root: Path) -> dict:
    """Explicit HTTP-only identity, independent of a browser/preview build.

    The historical full-preview guard remains the default. This alternative
    pins the actual committed simulator, API, acceptance client and Python/SUMO
    runtime; it makes no frontend build or browser-integration claim.
    """
    from sim.source_identity import source_snapshot, blob_id
    from sim.run import dependency_versions
    source=source_snapshot(root)
    if source.get('source_dirty') is not False or source.get('source_commit')=='unavailable':
        raise ValueError('HTTP-only acceptance requires clean committed simulation source')
    scope=('api','scripts/api_real_acceptance.py','scripts/omen_acceptance.py','requirements-sim.txt')
    def git(*args):
        return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.PIPE)
    tree={};index={}
    for entry in git('ls-tree','-r','-z','--full-tree',source['source_commit'],'--',*scope).split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,kind,oid=metadata.decode().split(' ')
        relative=os.fsdecode(name)
        if kind!='blob' or mode not in {'100644','100755'} or relative in tree:
            raise ValueError('Unsupported API acceptance source tree')
        tree[relative]=(mode,oid)
    index_raw=git('ls-files','--stage','-z','--',*scope)
    for entry in index_raw.split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,oid,stage=metadata.decode().split(' ')
        relative=os.fsdecode(name)
        if stage!='0' or relative in index:raise ValueError('Unmerged API acceptance source')
        index[relative]=(mode,oid)
    if tree!=index or git('ls-files','--others','--exclude-standard','-z','--',*scope):
        raise ValueError('API acceptance source contains staged or untracked changes')
    if not {'api/server.py','api/jobs.py','scripts/api_real_acceptance.py'}<=tree.keys():
        raise ValueError('API acceptance source inventory is incomplete')
    algorithm=git('rev-parse','--show-object-format').decode().strip()
    actual={}
    for relative,(mode,oid) in tree.items():
        path=_safe(root,relative);payload=path.read_bytes()
        if blob_id(payload,algorithm)!=oid:
            raise ValueError(f'API acceptance input differs from HEAD: {relative}')
        if os.name!='nt' and bool(path.stat().st_mode&0o111)!=(mode=='100755'):
            raise ValueError('API acceptance input mode differs from HEAD')
        actual[relative]=hashlib.sha256(payload).hexdigest()
    for path in (root/'api').rglob('*.py'):
        relative=path.relative_to(root).as_posix()
        if relative not in tree:raise ValueError('Ignored API source is not committed')
    dependencies=dependency_versions()
    if source_snapshot(root)!=source or git('ls-files','--stage','-z','--',*scope)!=index_raw:
        raise ValueError('API acceptance source changed while capturing identity')
    if any(hashlib.sha256(_safe(root,name).read_bytes()).hexdigest()!=value for name,value in actual.items()):
        raise ValueError('API acceptance input changed while capturing identity')
    payload=json.dumps(actual,sort_keys=True,separators=(',',':')).encode()
    return {'source':source,'api_files_sha256':actual,'api_input_sha256':hashlib.sha256(payload).hexdigest(),
            'python_version':platform.python_version(),'simulation_dependencies':dependencies,
            'verification_scope':'HTTP lifecycle/idempotency/restart and raw evidence only; no preview or browser acceptance'}


def location(output:Path)->Path:
    output=output.absolute();runtime=ROOT/'local-runtime'
    if not output.is_relative_to(runtime) or output==runtime:raise ValueError('Use a new checkout local-runtime output directory')
    return _safe(ROOT,output.relative_to(ROOT).as_posix()).resolve()


def origin(value:str)->str:
    url=urlsplit(value)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost'} or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
        raise ValueError('Use a plain loopback API origin')
    if url.port is None or not 1024<=url.port<=65535:raise ValueError('Explicit unprivileged API port required')
    return f'http://{url.hostname}:{url.port}'


def http(origin_url:str,method:str,path:str,body:bytes|None=None)->tuple[int,bytes]:
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=Request(origin(origin_url)+path,data=body,method=method,headers={
        'Origin':'http://127.0.0.1:5173','Content-Type':'application/json','Accept':'application/json'})
    opener=build_opener(ProxyHandler({}),NoRedirect())
    try:response=opener.open(request,timeout=20)
    except HTTPError as error:response=error
    with response:
        payload=response.read(MAX_REPLAY_BYTES+1)
        if len(payload)>MAX_REPLAY_BYTES:raise ValueError('API response exceeds canonical replay cap')
        return response.code,payload


def prepare(output:Path,base_url:str,expected_commit:str,*,identity_fn=capture_identity)->dict:
    output=location(output)
    if output.exists():raise FileExistsError('New acceptance output required; never overwrite/retry an existing attempt')
    base_url=origin(base_url)
    if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',expected_commit):raise ValueError('Exact source commit required')
    identity=identity_fn(ROOT)
    if identity['source'].get('source_dirty') is not False or identity['source'].get('source_commit')!=expected_commit:raise ValueError('Source does not match clean expected checkpoint')
    request={**PARAMETERS,'request_id':uuid4().hex}
    parameters(PARAMETERS)
    value={'schema':'afterlight.real-api-acceptance.v1','state':'prepared','base_url':base_url,'source_identity':identity,
        'request':request,'created_utc':now(),'requests':[],
        'scope':'One seed-7 pilot/exploration paired run; never held-out data or benchmark gain',
        'restart_evidence':'Manual server restart is an operator assertion; API does not expose a process instance identifier'}
    output.mkdir(parents=True,exist_ok=False);(output/'jobs').mkdir();(output/'responses').mkdir()
    _atomic(output/'request.json',request);_atomic(output/'journal.json',value)
    return value


def load(output:Path)->tuple[Path,dict]:
    output=location(output)
    journal=parse_json_object(read_bytes(_safe(output,'journal.json'),limit=1024*1024),limit=1024*1024)
    request=parse_json_object(read_bytes(_safe(output,'request.json'),limit=16384),limit=16384)
    if journal.get('schema')!='afterlight.real-api-acceptance.v1' or journal.get('request')!=request:
        raise ValueError('Acceptance journal/request identity mismatch')
    if {k:v for k,v in request.items() if k!='request_id'}!=PARAMETERS or not re.fullmatch('[0-9a-f]{32}',request.get('request_id','')):
        raise ValueError('Only the exact prepared exploratory request is allowed')
    origin(journal['base_url'])
    return output,journal


def bind_job(job:dict,journal:dict)->None:
    if job.get('id')!=journal['request']['request_id'] or job.get('parameters')!=PARAMETERS or job.get('status') not in {'queued','running','completed','failed'}:
        raise ValueError('API job differs from exact saved request')
    created=job.get('created_at')
    if isinstance(created,bool) or not isinstance(created,(int,float)) or not math.isfinite(created):raise ValueError('API job lacks finite creation identity')
    acknowledged=journal.get('acknowledged_job')
    if acknowledged is not None and created!=acknowledged.get('created_at'):
        raise ValueError('API job creation identity changed after acknowledgment')


def status(output:Path,*,transport=http)->dict:
    """Read-only observation, including after an uncertain POST or disconnect."""
    output,journal=load(output);identifier=journal['request']['request_id']
    code,payload=transport(journal['base_url'],'GET','/api/jobs/'+identifier)
    if code!=200:return {'state':'unresolved','http_status':code,'request_id':identifier,'interpretation':'No POST retry authorized; resolve actual server/process state'}
    job=parse_json_object(payload);bind_job(job,journal)
    return {'state':job['status'],'job':job,'interpretation':'GET-only observation; no simulator was submitted or restarted'}


def raw_inventory(output:Path,identifier:str)->dict:
    jobs=_safe(output,'jobs')
    if any(path.name!=identifier for path in jobs.iterdir()):raise ValueError('Unexpected additional job directory; possible duplicate work')
    directory=_safe(jobs,identifier)
    if not directory.is_dir():raise ValueError('Expected real job directory missing')
    result={}
    for current,folders,files in os.walk(directory,followlinks=False):
        parent=Path(current)
        for name in folders:_safe(directory,(parent/name).relative_to(directory).as_posix())
        for name in sorted(files):
            safe=_safe(directory,(parent/name).relative_to(directory).as_posix())
            result[safe.relative_to(directory).as_posix()]=hashlib.sha256(read_bytes(safe)).hexdigest()
    return result


def verified_terminal(output:Path,journal:dict,job:dict,call)->dict:
    from sim.audit import audit
    bind_job(job,journal)
    if job['status']!='completed':raise ValueError('API did not complete a real replay; raw failure remains retained')
    if not re.fullmatch('[0-9a-f]{64}',job.get('replay_sha256','')):raise ValueError('Terminal API job lacks exact replay hash')
    identifier=job['id'];directory=_safe(output,'jobs/'+identifier)
    payload,replay,checksum=load_job_artifact(_safe(directory,'replay.json'),PARAMETERS,job.get('replay_sha256'))
    if replay['scenario'].get('split')!='pilot' or replay['scenario'].get('seed')!=7:raise ValueError('Real API acceptance cannot consume held-out/nonqualification data')
    source=journal['source_identity']['source']
    if any(replay['provenance'].get(key)!=value for key,value in source.items()):raise ValueError('Real API replay source differs from prepared checkpoint')
    result=audit(directory,write_result=False)
    if result['replay_sha256']!=checksum:raise ValueError('Raw replay/audit checksum mismatch')
    if any(world['status']!='completed' or world['metrics']['status']!='completed' or world['metrics']['validity_reasons'] for world in replay['worlds'].values()):
        raise ValueError('Traffic invalid/censored: preserve outcome, do not call API qualification successful')
    code,served=call('GET',f'/api/jobs/{identifier}/replay')
    if code!=200 or served!=payload:raise ValueError('Served replay bytes differ from exact audited raw recording')
    return {'replay_sha256':checksum,'replay_bytes':len(payload),'audit':result,'raw_files_sha256':raw_inventory(output,identifier),
            'job_identity':{key:job.get(key) for key in ('id','created_at','started_at','finished_at','replay_sha256')}}


def execute(output:Path,*,confirm_no_active_runs:bool,monitor_s:int=900,transport=http,identity_fn=capture_identity,
            clock=time.monotonic,sleep=time.sleep)->dict:
    output,journal=load(output)
    if not confirm_no_active_runs:raise ValueError('Operator must resolve all prior/manual process uncertainty first')
    if journal['state']!='prepared':raise ValueError('This attempt was already started; use GET-only status, never retry POST automatically')
    if isinstance(monitor_s,bool) or not isinstance(monitor_s,int) or not 1<=monitor_s<=3600:raise ValueError('Client monitor window must be 1..3600 seconds')
    if identity_fn(ROOT)!=journal['source_identity']:raise ValueError('Prepared source changed')
    if list(_safe(output,'jobs').iterdir()):raise ValueError('Prepared dedicated job directory is not empty')
    # Exclusive claim precedes mutable journal writes and all network access;
    # concurrent invocations cannot race duplicate POST probes/response files.
    with _safe(output,'run-started.json').open('x',encoding='utf-8') as stream:
        json.dump({'request_id':journal['request']['request_id'],'started_utc':now()},stream)
        stream.flush();os.fsync(stream.fileno())
    journal.update(state='started',operator_confirmed_no_active_runs=True,started_utc=now(),monitor_window_s=monitor_s)
    _atomic(output/'journal.json',journal)
    def call(method,path,body=None):return recorded_call(output,journal,transport,method,path,body)
    request=json.dumps(journal['request'],sort_keys=True,separators=(',',':')).encode()
    deadline=clock()+monitor_s
    try:
        code,payload=call('GET','/api/health');health=parse_json_object(payload)
        if code!=200 or health.get('generation_available') is not True:raise ValueError('Actual API generation is not enabled')
        code,payload=call('POST','/api/runs',request)
        if code!=202:raise ValueError('Initial POST not acknowledged; do not automatically submit again')
        first=parse_json_object(payload);bind_job(first,journal)
        journal['acknowledged_job']=first;_atomic(output/'journal.json',journal)
        # Only a known valid acknowledgment authorizes this explicit identical
        # idempotency probe. A lost/malformed first response never reaches here.
        code,payload=call('POST','/api/runs',request)
        if code!=202:raise ValueError('Identical acknowledged request was not accepted idempotently')
        repeated=parse_json_object(payload);bind_job(repeated,journal)
        if repeated.get('created_at')!=first.get('created_at'):raise ValueError('Identical request created a different job')
        job=repeated
        while job['status'] in {'queued','running'}:
            if clock()>=deadline:raise TimeoutError('Client observation window ended; job may still run, no kill or POST retry')
            sleep(1)
            code,payload=call('GET','/api/jobs/'+first['id'])
            if code!=200:raise ValueError('Job state unavailable; leave attempt unresolved')
            job=parse_json_object(payload);bind_job(job,journal)
        journal['terminal_job']=job
        journal['terminal_evidence']=verified_terminal(output,journal,job,call)
        if identity_fn(ROOT)!=journal['source_identity']:raise ValueError('Source changed during genuine API acceptance')
        journal['state']='terminal_verified'
    except (Exception, KeyboardInterrupt) as error:
        transport_uncertain=bool(journal['requests'] and journal['requests'][-1]['state']=='uncertain')
        unresolved=isinstance(error,KeyboardInterrupt) or transport_uncertain or journal.get('terminal_job') is None
        journal.update(state='unresolved' if unresolved else 'failed',error=str(error),error_type=type(error).__name__,
            failure_kind='observation_uncertain' if unresolved else ('observed_terminal_job_failure' if journal['terminal_job']['status']=='failed' else 'acceptance_evidence_or_traffic_invalid'))
        raise
    finally:
        journal['last_record_utc']=now();_atomic(output/'journal.json',journal)
    return journal


def recorded_call(output,journal,transport,method,path,body=None):
    index=len(journal['requests'])
    record={'method':method,'path':path,'state':'sending','started_utc':now(),'request_sha256':hashlib.sha256(body).hexdigest() if body else None}
    journal['requests'].append(record);_atomic(output/'journal.json',journal)
    try:
        code,payload=transport(journal['base_url'],method,path,body)
        filename=f'responses/{index:03d}.bin'
        with _safe(output,filename).open('xb') as stream:stream.write(payload)
        record.update(state='responded',http_status=code,response_file=filename,response_sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload),finished_utc=now())
        return code,payload
    except (Exception, KeyboardInterrupt) as error:
        record.update(state='uncertain',error=str(error),error_type=type(error).__name__);raise
    finally:_atomic(output/'journal.json',journal)


def verify_recovery(output:Path,*,confirm_server_restarted_after_terminal:bool,transport=http,identity_fn=capture_identity)->dict:
    output,journal=load(output)
    if not confirm_server_restarted_after_terminal:raise ValueError('Manual restart after terminal completion must be explicitly confirmed')
    if journal['state']!='terminal_verified':raise ValueError('Recovery requires an already verified terminal run, never uncertain/in-progress work')
    if identity_fn(ROOT)!=journal['source_identity']:raise ValueError('Prepared source changed; no recovery acceptance under another source')
    marker=_safe(output,'recovery-started.json')
    with marker.open('x',encoding='utf-8') as stream:json.dump({'operator_confirmed_restart':True,'started_utc':now()},stream)
    def call(method,path,body=None):return recorded_call(output,journal,transport,method,path,body)
    try:
        identifier=journal['request']['request_id'];before=raw_inventory(output,identifier)
        if before!=journal['terminal_evidence']['raw_files_sha256']:raise ValueError('Retained terminal evidence changed before recovery')
        code,payload=call('GET','/api/jobs/'+identifier)
        if code!=200:raise ValueError('Terminal persisted job not recovered; no POST permitted')
        job=parse_json_object(payload);bind_job(job,journal)
        recovered=verified_terminal(output,journal,job,call)
        if recovered!=journal['terminal_evidence']:raise ValueError('Recovered terminal job/replay differs from original evidence')
        request=json.dumps(journal['request'],sort_keys=True,separators=(',',':')).encode()
        code,payload=call('POST','/api/runs',request)
        if code!=202:raise ValueError('Recovered terminal exact request was not idempotent')
        repeated=parse_json_object(payload);bind_job(repeated,journal)
        if repeated['status']!='completed' or {key:repeated.get(key) for key in recovered['job_identity']}!=recovered['job_identity']:
            raise ValueError('Recovery idempotency probe changed terminal job identity')
        if raw_inventory(output,identifier)!=before or identity_fn(ROOT)!=journal['source_identity']:
            raise ValueError('Recovery changed raw evidence/job inventory or source')
        journal.update(state='recovery_verified',restart_operator_assertion=True)
    except (Exception, KeyboardInterrupt) as error:
        journal.update(state='recovery_unresolved',recovery_error=str(error),error_type=type(error).__name__);raise
    finally:_atomic(output/'journal.json',journal)
    return journal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','run','status','verify-recovery'))
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--base-url',default='http://127.0.0.1:8765')
    parser.add_argument('--expected-commit');parser.add_argument('--monitor-seconds',type=int,default=900)
    parser.add_argument('--confirm-no-active-runs',action='store_true');parser.add_argument('--confirm-server-restarted-after-terminal',action='store_true')
    parser.add_argument('--api-only',action='store_true',help='explicit HTTP-only source identity; preserves historical full-preview guard by default')
    args=parser.parse_args()
    identity=capture_api_identity if args.api_only else capture_identity
    if args.phase=='prepare':result=prepare(args.output,args.base_url,args.expected_commit or '',identity_fn=identity)
    elif args.phase=='run':result=execute(args.output,confirm_no_active_runs=args.confirm_no_active_runs,monitor_s=args.monitor_seconds,identity_fn=identity)
    elif args.phase=='status':result=status(args.output)
    else:result=verify_recovery(args.output,confirm_server_restarted_after_terminal=args.confirm_server_restarted_after_terminal,identity_fn=identity)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
