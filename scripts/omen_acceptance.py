"""Recorded Omen acceptance steps; plan/status never execute tests.

Default: units and networks only. Traffic requires an explicit qualification profile.
No build, fitting, retries, resume, cancellation or process kill.
An interrupted record is UNKNOWN, not proof that its child process has stopped.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import time

# Enforce read-only imports even if the operator omitted Python's -B flag.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')
INPUT_DIRS = ('api','scripts','tests','web/src','web/tests','web/scripts','assets/exports','assets/src','preview/site','preview/licenses','licenses')
INPUT_FILES = ('web/package.json','web/package-lock.json','web/tsconfig.json','web/index.html','web/public/favicon.svg',
               'web/vite.config.ts','web/vite.config.js','web/vite.config.mjs','preview/manifest.json')
SOURCE_SUFFIXES = {'.py','.ts','.tsx','.js','.mjs','.cjs','.json','.css','.html','.glb'}


def now() -> str:return datetime.now(timezone.utc).isoformat()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _safe(root: Path, relative: str) -> Path:
    pure=PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or '\\' in relative:
        raise ValueError('Unsafe acceptance path')
    path=root
    for part in pure.parts:
        path=path/part
        if _redirected(path):raise ValueError('Acceptance paths must not use symlinks/junctions')
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Acceptance path escapes checkout')
    return path


def _base(root: Path) -> Path:
    return _safe(root,'local-runtime/acceptance')


def _output(root: Path, output: Path) -> Path:
    base=_base(root).resolve();target=output.absolute()
    if target.parent.resolve()!=base or not SAFE_NAME.fullmatch(target.name) or _redirected(target):
        raise ValueError('Use one new local-runtime/acceptance/<safe-id> directory')
    return target


def _atomic(path: Path, value: object) -> None:
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def _git(root: Path,*args: str) -> bytes:
    return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.PIPE)


def _json_bytes(path: Path) -> tuple[bytes,dict]:
    from api.artifacts import read_bytes, parse_json_object
    payload=read_bytes(path,limit=4*1024*1024)
    return payload,parse_json_object(payload)


def _node_metadata(root: Path, project: dict, lock: dict) -> dict:
    declared={**project.get('dependencies',{}),**project.get('devDependencies',{})}
    packages={}
    for name,specification in sorted(declared.items()):
        if not re.fullmatch(r'(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+',name):raise ValueError('Unsafe package name')
        payload,metadata=_json_bytes(_safe(root,f'web/node_modules/{name}/package.json'))
        locked=lock.get('packages',{}).get('node_modules/'+name,{})
        if not isinstance(metadata.get('version'),str) or locked.get('version')!=metadata['version']:
            raise ValueError(f'Installed Node package metadata differs from lock: {name}')
        packages[name]={'version':metadata['version'],'declared':specification,'package_json_sha256':hashlib.sha256(payload).hexdigest()}
    installed_lock=_safe(root,'web/node_modules/.package-lock.json')
    return {'packages':packages,'installed_lock_sha256':hashlib.sha256(_json_bytes(installed_lock)[0]).hexdigest() if installed_lock.is_file() else None,
            'verification_scope':'Declared direct-package versions and package/lock metadata only; installed dependency code tree is NOT verified'}


def capture_identity(root: Path) -> dict:
    """Pin backend plus actual API/test/frontend/asset inputs, not Git stat cache."""
    from sim.source_identity import source_snapshot, blob_id
    source=source_snapshot(root)
    if source['source_dirty'] is not False or source['source_commit']=='unavailable':
        raise ValueError('Acceptance requires clean verifiable committed simulation source')
    bootstrap={}
    bootstrap['preview/manifest.json'],preview=_json_bytes(_safe(root,'preview/manifest.json'))
    bootstrap['web/package.json'],project=_json_bytes(_safe(root,'web/package.json'))
    bootstrap['web/package-lock.json'],lock=_json_bytes(_safe(root,'web/package-lock.json'))
    manifest_inputs={}
    for section in ('source_files','output_files','runtime_assets'):
        rows=preview.get(section)
        if not isinstance(rows,dict):raise ValueError('Preview manifest lacks input identity sections')
        for name,expected in rows.items():
            if not isinstance(name,str) or not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected):
                raise ValueError('Invalid preview input identity')
            _safe(root,name)
            if name in manifest_inputs and manifest_inputs[name]!=expected:raise ValueError('Conflicting preview input hashes')
            manifest_inputs[name]=expected
    scope=(*INPUT_DIRS,*INPUT_FILES,*sorted(manifest_inputs))
    tree_raw=_git(root,'ls-tree','-r','-z','--full-tree',source['source_commit'],'--',*scope)
    index_raw=_git(root,'ls-files','--stage','-z','--',*scope)
    algorithm=_git(root,'rev-parse','--show-object-format').decode().strip()
    tree={};index={}
    for entry in tree_raw.split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,kind,oid=metadata.decode().split(' ');name=os.fsdecode(name)
        if kind!='blob' or mode not in {'100644','100755'} or name in tree:raise ValueError('Unsupported acceptance tree entry')
        tree[name]=(mode,oid)
    for entry in index_raw.split(b'\0'):
        if not entry:continue
        metadata,name=entry.split(b'\t',1);mode,oid,stage=metadata.decode().split(' ');name=os.fsdecode(name)
        if stage!='0' or name in index:raise ValueError('Unmerged acceptance source index')
        index[name]=(mode,oid)
    if tree!=index or _git(root,'ls-files','--others','--exclude-standard','-z','--',*scope):
        raise ValueError('Acceptance inputs have staged or untracked edits')
    actual={}
    for relative,(mode,oid) in sorted(tree.items()):
        path=_safe(root,relative);payload=bootstrap[relative] if relative in bootstrap else path.read_bytes()
        if blob_id(payload,algorithm)!=oid:raise ValueError(f'Acceptance input differs from HEAD: {relative}')
        if os.name!='nt' and bool(path.stat().st_mode & 0o111)!=(mode=='100755'):raise ValueError('Acceptance input mode differs from HEAD')
        actual[relative]=hashlib.sha256(payload).hexdigest()
    if any(actual.get(name)!=expected for name,expected in manifest_inputs.items()):
        raise ValueError('Preview manifest-bound input differs from actual committed bytes')
    for relative in INPUT_FILES:
        if _safe(root,relative).exists() and relative not in tree:raise ValueError(f'Uncommitted acceptance configuration: {relative}')
    # Ignored executable/config additions are not covered by git --others.
    for directory in INPUT_DIRS:
        start=_safe(root,directory)
        for current,folders,files in os.walk(start,followlinks=False):
            parent=Path(current)
            for name in folders:
                if _redirected(parent/name):raise ValueError('Redirected acceptance input directory')
            folders[:]=[name for name in folders if name!='__pycache__']
            for name in files:
                relative=(parent/name).relative_to(root).as_posix()
                if Path(name).suffix.casefold() in SOURCE_SUFFIXES and relative not in tree:
                    raise ValueError(f'Ignored acceptance source is not committed: {relative}')
    if _git(root,'rev-parse','--verify','HEAD').decode().strip()!=source['source_commit'] or _git(root,'ls-files','--stage','-z','--',*scope)!=index_raw:
        raise ValueError('Acceptance source/index changed during identity capture')
    dependencies=_node_metadata(root,project,lock)
    # Detect edits during capture, not merely edits between acceptance steps.
    for relative,expected in actual.items():
        path=_safe(root,relative)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Acceptance input changed during identity capture')
        if os.name!='nt' and bool(path.stat().st_mode & 0o111)!=(tree[relative][0]=='100755'):
            raise ValueError('Acceptance input mode changed during identity capture')
    return {'source':source,'acceptance_files':actual,'acceptance_input_sha256':digest(actual),'node_dependency_metadata':dependencies}


def plan(root: Path, output: Path, *, python: str | None = None, node: str | None = None, profile: str = 'units-network') -> dict:
    output=_output(root,output)
    python=python or sys.executable
    if profile=='traffic-qualification':
        steps=[]
        from scripts.qualification_gate import CASES
        for case,settings in CASES.items():
            directory=output/'traffic'/case
            argv=[python,'-B','-m','sim.run','--network',settings['network_kind'],'--output',str(directory),
                '--seed','7','--regime',settings['regime'],'--policy',settings['policy'],'--lead','10',
                '--pickup',settings['pickup_id'],'--hospital',settings['hospital_id'],'--dispatch','60',
                '--demand-end','180','--horizon','240','--drain','360','--step','0.5','--sample','1','--split','pilot']
            steps.extend([
                {'id':case+'-run','argv':argv,'cwd':str(root)},
                {'id':case+'-audit','argv':[python,'-B','-m','sim.audit','--run',str(directory)],'cwd':str(root)},
                {'id':case+'-qualify','argv':[python,'-B','-m','scripts.qualification_gate','--attempt',str(output),'--case',case],'cwd':str(root)}])
        return {'schema':'afterlight.acceptance-plan.v1','profile':profile,'steps':steps,'output_directory':str(output),
            'allocation':{'worlds':6,'simulation_seconds_per_world':600,'total_simulation_seconds':3600,'hard_wall_time_limit_s':None},
            'scope':'Exploratory traffic qualification only; no benchmark, study, fitting or held-out access; no timeout/kill'}
    if profile!='units-network':raise ValueError('Unknown acceptance profile')
    node=node or shutil.which('node')
    if not node:raise ValueError('Existing Node executable required; this runner never installs dependencies')
    steps=[]
    for group in ('sim','evaluation','api','assets','preview','acceptance'):
        steps.append({'id':'python-'+group,'argv':[python,'-B','-m','unittest','discover','-s','tests/'+group,'-v'],'cwd':str(root)})
    guards = root/'web/tests/test_released_study_guards.py'
    if not guards.is_file():raise ValueError('Missing released-study guard unit tests')
    steps.append({'id':'python-study-proof-guards','argv':[python,'-B',str(guards)],'cwd':str(root)})
    files=sorted((root/'web/tests').glob('*.test.ts'))
    if not files:raise ValueError('No committed frontend Node unit tests found')
    steps.append({'id':'node-units','argv':[node,'--experimental-strip-types','--test',*[str(path) for path in files]],'cwd':str(root/'web')})
    for kind in ('fixture','city'):
        steps.append({'id':'network-'+kind,'argv':[python,'-B','-m','sim.network','--kind',kind,'--output',str(output/'networks'/kind)],'cwd':str(root)})
    return {'schema':'afterlight.acceptance-plan.v1','profile':profile,'steps':steps,'output_directory':str(output),
            'scope':'Python/Node units and network conversion only; no build, browser, traffic, training or held-out access'}


def status(root: Path, output: Path) -> dict:
    output=_output(root,output)
    path=_safe(output,'run.json')
    from api.artifacts import ArtifactError, read_bytes, parse_json_object
    try:
        record=parse_json_object(read_bytes(path,limit=8*1024*1024))
    except (ArtifactError,OSError,ValueError,RecursionError) as error:
        return {'state':'unresolved','directory':str(output),'reason':str(error),
                'interpretation':'Missing/invalid record is not completion; do not rerun until local process state is resolved'}
    if not isinstance(record,dict) or record.get('schema')!='afterlight.acceptance-run.v1':
        return {'state':'unresolved','directory':str(output),'reason':'Unknown acceptance record schema'}
    state=record.get('status')
    steps=record.get('steps',[])
    if not isinstance(steps,list) or not steps or not all(isinstance(step,dict) for step in steps):
        return {'state':'unresolved','directory':str(output),'reason':'Malformed step inventory'}
    unresolved=any(step.get('status') in {'launching','running','unresolved'} for step in steps)
    if state not in {'completed','failed'} or unresolved or record.get('active_child_pid') is not None:
        state='unresolved'
    if state=='completed' and (not steps or any(step.get('status')!='completed' or step.get('exit_code')!=0 for step in steps)):
        state='unresolved'
    return {'state':state,'directory':str(output),'record':record,
            'interpretation':'Recorded state only. No process liveness was inferred or test re-executed.'}


def _refuse_unresolved(root: Path) -> None:
    base=_base(root)
    if not base.exists():return
    for child in sorted(base.iterdir()):
        if not child.is_dir() or _redirected(child) or not SAFE_NAME.fullmatch(child.name):
            raise ValueError('Unknown entry in acceptance directory; resolve locally before new execution')
        if status(root,child)['state']=='unresolved':
            raise ValueError(f'Unresolved earlier acceptance attempt: {child.name}; inspect local process state, never assume disconnect means finished')


def execute(root: Path, output: Path, expected_commit: str, *, confirm_no_active_runs: bool,
            identity_fn=None, popen_fn=None, node: str | None = None, profile: str = 'units-network') -> dict:
    if not confirm_no_active_runs:
        raise ValueError('Explicit operator confirmation that no prior/manual run is active is required; this runner does not detect unrelated processes')
    if not isinstance(expected_commit,str) or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})',expected_commit):
        raise ValueError('An exact expected source commit is required')
    root=root.resolve();output=_output(root,output)
    if output.exists():raise FileExistsError('Acceptance output already exists; no retry/resume/overwrite')
    _refuse_unresolved(root)
    identity_fn=identity_fn or capture_identity
    popen_fn=popen_fn or subprocess.Popen
    identity=identity_fn(root)
    if identity['source'].get('source_dirty') is not False or identity['source'].get('source_commit')!=expected_commit:
        raise ValueError('Actual clean source does not match expected commit')
    specification=plan(root,output,node=node,profile=profile)
    output.mkdir(parents=True,exist_ok=False)
    for directory in ('tmp','node-cache','steps'): (output/directory).mkdir()
    overrides={'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(output/'tmp'),'TEMP':str(output/'tmp'),'TMP':str(output/'tmp'),
               'NODE_COMPILE_CACHE':str(output/'node-cache')}
    env={**os.environ,**overrides}
    manifest={'schema':'afterlight.acceptance-run.v1','status':'running','expected_commit':expected_commit,
        'source_identity':identity,'source_identity_sha256':digest(identity),'plan':specification,'plan_sha256':digest(specification),
        'operator_confirmed_no_active_runs':True,'concurrency_guard':'none; unrelated/manual processes must be resolved by operator',
        'runner_pid':os.getpid(),'python':sys.version,'platform':platform.platform(),'started_utc':now(),
        'env_overrides':overrides,'active_child_pid':None,'steps':[dict(step,status='planned') for step in specification['steps']]}
    active=None
    try:
        _atomic(output/'run.json',manifest)
        for step in manifest['steps']:
            if identity_fn(root)!=identity:raise ValueError('Source changed before acceptance step; stop without launching')
            folder=output/'steps'/step['id'];folder.mkdir()
            step.update(status='launching',launch_requested_utc=now(),stdout=str((folder/'stdout.log').relative_to(output)),stderr=str((folder/'stderr.log').relative_to(output)))
            _atomic(folder/'step.json',step);_atomic(output/'run.json',manifest)
            start=time.perf_counter()
            with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
                try:
                    active=popen_fn(step['argv'],cwd=step['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,shell=False)
                except Exception as error:
                    step.update(status='unresolved',launch_error=str(error),finished_record_utc=now())
                    _atomic(folder/'step.json',step)
                    raise
                step.update(status='running',child_pid=active.pid,started_utc=now())
                manifest['active_child_pid']=active.pid
                _atomic(folder/'step.json',step);_atomic(output/'run.json',manifest)
                code=active.wait()
                active=None;manifest['active_child_pid']=None
                stdout.flush();stderr.flush();os.fsync(stdout.fileno());os.fsync(stderr.fileno())
            step.update(exit_code=code,finished_utc=now(),wall_time_s=time.perf_counter()-start,
                        stdout_bytes=(folder/'stdout.log').stat().st_size,stderr_bytes=(folder/'stderr.log').stat().st_size)
            try:
                after=identity_fn(root)
                if after!=identity:raise ValueError('Source changed during acceptance step; result is not pinned-source evidence')
                step['source_after_sha256']=digest(after)
            except Exception as error:
                step.update(status='invalid_source',identity_error=str(error));_atomic(folder/'step.json',step)
                raise
            step['status']='completed' if code==0 else 'failed'
            _atomic(folder/'step.json',step);_atomic(output/'run.json',manifest)
            if code!=0:raise RuntimeError(f"Acceptance stopped at {step['id']} with exit {code}; later steps not started")
        manifest['status']='completed'
        return manifest
    except BaseException as error:
        uncertain = active is not None or any(step['status'] in {'launching','running','unresolved'} for step in manifest['steps'])
        manifest.update(status='unresolved' if uncertain else 'failed',error=str(error),error_type=type(error).__name__)
        # Never kill/cancel a child or label an interrupted wait as completed.
        raise
    finally:
        manifest['finished_record_utc']=now()
        _atomic(output/'run.json',manifest)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--execute',action='store_true');mode.add_argument('--status',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',choices=('units-network','traffic-qualification'),default='units-network')
    parser.add_argument('--expected-commit')
    parser.add_argument('--confirm-no-active-runs',action='store_true')
    args=parser.parse_args()
    if args.plan:result=plan(ROOT,args.output,profile=args.profile)
    elif args.status:result=status(ROOT,args.output)
    else:result=execute(ROOT,args.output,args.expected_commit,confirm_no_active_runs=args.confirm_no_active_runs,profile=args.profile)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
