"""Omen-only inspection of genuine exploratory city replay instance matrices.

No simulation, synthetic traffic, public catalog mutation, benchmark or held-out
access. Matrix agreement is NOT pixel-level road/stopline visual certification.
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, quote
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from api.artifacts import read_bytes, parse_json_object
from sim.audit import audit

TOLERANCE_M=1e-4
UNSAFE_DEFAULTS=[
    '--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage',
    '--enable-unsafe-swiftshader','--unsafely-disable-devtools-self-xss-warnings',
    '--disable-ipc-flooding-protection','--disable-client-side-phishing-detection',
]


def safe_path(path:Path)->Path:
    absolute=path.absolute();runtime=ROOT/'local-runtime'
    if not absolute.is_relative_to(runtime):raise ValueError('Use checkout local-runtime paths only')
    current=ROOT
    for part in absolute.relative_to(ROOT).parts:
        current=current/part
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):raise ValueError('Redirected artifact paths are forbidden')
    if not absolute.resolve().is_relative_to(runtime.resolve()):raise ValueError('Artifact path escapes runtime')
    return absolute.resolve()


def sampled_vehicles(frames:list,time_s:float)->list:
    """Independent Python implementation of declared sampled-pose interpolation."""
    times=[frame['t'] for frame in frames];index=bisect_right(times,time_s)-1
    if index<0 or time_s>times[-1]:return []
    left=frames[index]
    if left['t']==time_s or index+1==len(frames):return left['vehicles']
    right=frames[index+1];alpha=(time_s-left['t'])/(right['t']-left['t'])
    next_by_id={vehicle['id']:vehicle for vehicle in right['vehicles']};result=[]
    for original in left['vehicles']:
        following=next_by_id.get(original['id']);vehicle=dict(original)
        if following is not None and following['type']==original['type']:
            distance=math.sqrt(sum((following[key]-original[key])**2 for key in ('x','y','z')))
            limit=max(original['speed_mps'],following['speed_mps'],1)*(right['t']-left['t'])*2+original['length_m']*2+5
            if distance<=limit:
                for key in ('x','y','z'):vehicle[key]=original[key]+(following[key]-original[key])*alpha
                turn=((following['angle_deg']-original['angle_deg']+540)%360)-180
                vehicle['angle_deg']=original['angle_deg']+turn*alpha
        result.append(vehicle)
    return result


def ambulance(vehicles:list)->dict|None:
    return next((vehicle for vehicle in vehicles if vehicle['id']=='ambulance'),None)


def sample_times(replay:dict)->tuple[list[float],bool]:
    baseline=replay['worlds']['baseline']['frames'];active=replay['worlds']['afterlight']['frames']
    common=[frame['t'] for frame in active if ambulance(frame['vehicles']) and ambulance(sampled_vehicles(baseline,frame['t']))]
    # Native timeline has 0.1-second precision; never silently request an
    # unrepresentable time or retime one world to match the other.
    common=[value for value in common if abs(value*10-round(value*10))<1e-8]
    if not common:raise ValueError('No representable sampled time has both ambulances; retain this coverage limitation')
    fractional=None
    for left,right in zip(active,active[1:]):
        middle=math.floor((left['t']+right['t'])*5)/10
        if not left['t']<middle<right['t']:continue
        if all(ambulance(sampled_vehicles(frames,left['t'])) and ambulance(sampled_vehicles(frames,right['t'])) for frames in (active,baseline)):
            fractional=middle;break
    chosen=[common[0],common[-1]]
    chosen.append(fractional if fractional is not None else common[len(common)//2])
    return sorted(set(chosen)),fractional is not None


def close_number(actual,expected,label):
    if isinstance(actual,bool) or not isinstance(actual,(int,float)) or not math.isfinite(actual) or abs(actual-expected)>TOLERANCE_M:
        raise AssertionError(f'{label}: actual {actual!r}, expected {expected!r}, tolerance {TOLERANCE_M}')


def check_layer(snapshot:dict,vehicles:list,label:str)->dict:
    if snapshot.get('source')!='InstancedMesh matrices and baked geometry bounds':raise AssertionError('Telemetry is not sourced from rendered instance matrices')
    expected_counts=Counter(vehicle['type'] for vehicle in vehicles);types=snapshot['types']
    for kind in set(types)|set(expected_counts):
        item=types.get(kind,{'count':0,'primitiveCounts':[]});expected=expected_counts[kind]
        if item['count']!=expected or any(count!=expected for count in item['primitiveCounts']):raise AssertionError(f'{label}/{kind}: rendered logical/primitive counts differ from raw replay')
        if expected and not item['primitiveCounts']:raise AssertionError('Visible raw vehicles have no rendered primitive matrices')
    expected_ambulance=ambulance(vehicles);actual=snapshot['ambulances']
    if len(actual)!=(1 if expected_ambulance else 0):raise AssertionError(f'{label}: rendered ambulance count mismatch')
    result={'counts':dict(expected_counts),'ambulance':None}
    if expected_ambulance is not None:
        vehicle=expected_ambulance;rendered=actual[0]
        if rendered.get('consistentMatrices') is not True:raise AssertionError('Ambulance primitives disagree on actual instance transform')
        angle=math.radians(vehicle['angle_deg']);length=vehicle['length_m']
        expected={'center':[vehicle['x']-math.sin(angle)*length/2,-vehicle['y']+math.cos(angle)*length/2],
                  'nose':[vehicle['x'],-vehicle['y']],
                  'rear':[vehicle['x']-math.sin(angle)*length,-vehicle['y']+math.cos(angle)*length]}
        for key,xz in expected.items():
            close_number(rendered[key][0],xz[0],label+'/'+key+'/x');close_number(rendered[key][2],xz[1],label+'/'+key+'/z')
        close_number(rendered['length'],length,label+'/length')
        if 'width_m' in vehicle:close_number(rendered['width'],vehicle['width_m'],label+'/width')
        if not rendered['primitiveMatrices'] or any(len(matrix)!=16 or any(not math.isfinite(value) for value in matrix) for matrix in rendered['primitiveMatrices']):raise AssertionError('Missing/nonfinite actual instance matrices')
        result['ambulance']={'raw_front_bumper':vehicle,'expected_xz':expected,'rendered':rendered}
    return result


def inspect(page,time_s:float,world:str,ghost:bool)->dict:
    page.wait_for_function('''({time,world,ghost}) => {
        const text=document.querySelector('.three-host canvas')?.dataset.vehicleInspection;
        if(!text)return false;const value=JSON.parse(text);
        return Math.abs(value.absoluteTime-time)<1e-8 && value.world===world && value.ghostRequested===ghost;
    }''',arg={'time':time_s,'world':world,'ghost':ghost},timeout=30000)
    return page.locator('.three-host canvas').evaluate('(canvas)=>JSON.parse(canvas.dataset.vehicleInspection)')



def verify_served_preview(base)->dict:
    from scripts.serve_preview import verify
    manifest=verify()  # Read-only exact local source/output/runtime-asset hashes.
    if base.path not in ('','/','/index.html','/local.html'):
        raise ValueError('Use the committed preview root, index.html or local.html entrypoint')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,request,fp,code,message,headers,newurl):
            return None  # Never follow a local server redirect to another origin.
    opener=build_opener(ProxyHandler({}),NoRedirect())
    origin=f'{base.scheme}://{base.netloc}'
    served={}
    outputs={name:expected for name,expected in manifest['output_files'].items() if name.startswith('preview/site/')}
    if not outputs or 'preview/site/index.html' not in outputs:raise ValueError('Committed preview output inventory missing')
    requests=[('/'+name.removeprefix('preview/site/'),name,expected) for name,expected in sorted(outputs.items())]
    # The exact served city/vehicle/map bytes matter too: correct JS cannot
    # make a stale GLB or canonical map acceptable. Catalog is intentionally
    # isolated by the browser route and is never part of this asset inventory.
    for name,expected in sorted(manifest['runtime_assets'].items()):
        if not name.startswith(('assets/exports/','assets/map/','assets/previews/')):
            raise ValueError('Unexpected runtime asset route in committed preview')
        requests.append(('/'+name,name,expected))
    entry=base.path or '/';entry_file='preview/site/'+('index.html' if entry=='/' else entry.lstrip('/'))
    requests.append((entry,entry_file,outputs[entry_file]))
    for route,name,expected in requests:
        size=(ROOT/name).stat().st_size
        with opener.open(origin+quote(route,safe='/'),timeout=30) as response:
            payload=response.read(size+1)
            if response.status!=200 or len(payload)!=size or hashlib.sha256(payload).hexdigest()!=expected:
                raise ValueError(f'Served viewer differs from committed preview: {route}')
        served[route]={'sha256':expected,'bytes':size}
    return {'manifest_source_commit':manifest['source_commit'],
            'manifest_sha256':hashlib.sha256((ROOT/'preview/manifest.json').read_bytes()).hexdigest(),
            'served_output_files':{route:value for route,value in served.items() if route.lstrip('/') not in manifest['runtime_assets']},
            'served_runtime_assets':{route:value for route,value in served.items() if route.lstrip('/') in manifest['runtime_assets']},
            'runtime_asset_hashes':manifest['runtime_assets'],
            'scope':'Local manifest/source/runtime assets verified; served preview/site outputs and runtime GLB/map/preview assets independently fetched and hashed. Recorded simulator source is a separate identity.'}


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--base-url',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    base=urlsplit(args.base_url)
    if base.scheme!='http' or base.hostname not in {'127.0.0.1','localhost','::1'} or base.username or base.password:parser.error('Loopback HTTP viewer required')
    run=safe_path(args.run);output=safe_path(args.output)
    protected=run.parent  # Includes fixed/ordinary predecessors re-audited below.
    if output==protected or output.is_relative_to(protected) or protected.is_relative_to(output):raise ValueError('Output cannot overlap traffic qualification or predecessor evidence')
    if output.exists():raise FileExistsError('Visual acceptance output must be fresh; never overwrite prior evidence')
    output.mkdir(parents=True,exist_ok=False)
    report={'schema':'afterlight.real-replay-visual.v1','status':'running','scope':'Exploratory real-city recorded instance-matrix checks; not traffic gain, frame-rate benchmark or pixel-level stopline certification',
        'run':str(run),'base_url':args.base_url,'platform':platform.platform(),'checks':[],
        'page_errors':[],'console_errors':[],'blocked_external_requests':[],
        'manual_visual_review':'Road/stopline/lane alignment and screenshot aesthetics remain separate human visual review; Y is authored geometry midpoint plus renderer lift, not compared to SUMO ground z'}
    page=None;browser=None;context=None;playwright=None
    try:
        # Require the successful exploratory qualification gate BEFORE opening
        # replay outcomes. No manual override or held-out inspection mode exists.
        gate_path=safe_path(run/'qualification.json')
        qualification=parse_json_object(read_bytes(gate_path,limit=1024*1024),limit=1024*1024)
        import re
        if (qualification.get('schema')!='afterlight.traffic-qualification.v1' or qualification.get('status')!='qualified'
                or qualification.get('case')!='city-sparse' or not re.fullmatch('[0-9a-f]{64}',qualification.get('replay_sha256',''))):
            raise ValueError('An existing qualified city-sparse exploration gate is required before replay access')
        if run.name!='city-sparse' or run.parent.name!='traffic':raise ValueError('Use the original traffic-qualification city-sparse directory')
        source=qualification.get('source',{})
        if source.get('source_dirty') is not False or not re.fullmatch('[0-9a-f]{40}',source.get('source_commit','')):
            raise ValueError('Qualification gate lacks genuine clean source identity')
        payload=read_bytes(safe_path(run/'replay.json'))
        if hashlib.sha256(payload).hexdigest()!=qualification['replay_sha256']:
            raise ValueError('Replay bytes differ from prior qualification gate; outcomes not decoded')
        replay=parse_json_object(payload);scenario=replay['scenario']
        if scenario.get('split')!='pilot' or scenario.get('seed')!=7 or scenario.get('network_kind')!='city':raise ValueError('This harness accepts only seed-7 pilot/exploratory city qualification, never train/validation/test')
        for path in run.rglob('*'):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Raw run evidence contains redirected paths')
        provenance=replay['provenance']
        if provenance.get('source_dirty') is not False or not re.fullmatch('[0-9a-f]{40}',provenance.get('source_commit','')):raise ValueError('A real clean recorded source commit is required')
        canonical=hashlib.sha256((ROOT/'assets/map/city_manifest.json').read_bytes()).hexdigest()
        if provenance.get('canonical_map_sha256')!=canonical:raise ValueError('Recorded canonical map differs from viewer source map')
        digest=hashlib.sha256(payload).hexdigest();audit_result=audit(run,write_result=False)
        from scripts.qualification_gate import _validated_result
        # Reuse the fixed seed/policy/timing/source contract and both predecessor
        # gates. This audits retained files only; it never launches SUMO.
        def retained_audit(directory,*,write_result):
            return audit_result if directory.resolve()==run else audit(directory,write_result=False)
        if _validated_result(run.parent.parent,'city-sparse',source,retained_audit)!=qualification:
            raise ValueError('Qualification record differs from re-audited fixed exploration contract')
        if audit_result['replay_sha256']!=digest or read_bytes(run/'replay.json')!=payload:raise ValueError('Replay bytes changed during raw evidence audit')
        for world in replay['worlds'].values():
            if world['status']!='completed' or world['metrics']['status']!='completed' or world['metrics']['validity_reasons']:raise ValueError('Visual qualification requires both worlds valid completed; no invalid trace promotion')
        viewer=verify_served_preview(base)
        report['viewer_provenance']=viewer
        times,fractional=sample_times(replay)
        report.update(replay_sha256=digest,replay_bytes=len(payload),source_commit=provenance['source_commit'],audit=audit_result,
            sample_times=times,fractional_sample_available=fractional,canonical_map_sha256=canonical)
        identity=scenario['id'];recording_path='/replays/real-qualification.json'
        entry={'id':identity,'title':'Audited local seed-7 city qualification','url':recording_path,
            'seed':scenario['seed'],'pickup_id':scenario['pickup_id'],'hospital_id':scenario['hospital_id'],
            'policy':replay['worlds']['afterlight']['policy'],'lead_s':replay['worlds']['afterlight']['lead_s'],
            'duration_s':replay['duration_s'],'sha256':digest,'bytes':len(payload),'source_commit':provenance['source_commit']}
        catalog=json.dumps({'schema':'afterlight.catalog.v1','runs':[entry]})
        from playwright.sync_api import sync_playwright,expect
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(channel='chrome',headless=False,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        context=browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1)
        def route_request(route):
            url=urlsplit(route.request.url)
            if url.scheme in {'http','https'} and url.hostname not in {'127.0.0.1','localhost','::1'}:
                report['blocked_external_requests'].append(route.request.url);route.abort();return
            if url.path in {'/replays/catalog.json','/api/catalog'}:
                route.fulfill(status=200,content_type='application/json',body=catalog,headers={'Cache-Control':'no-store','Access-Control-Allow-Origin':f'{base.scheme}://{base.netloc}'});return
            if url.path==recording_path:
                route.fulfill(status=200,content_type='application/json',body=payload,headers={'Cache-Control':'no-store','Access-Control-Allow-Origin':f'{base.scheme}://{base.netloc}'});return
            route.continue_()
        context.route('**/*',route_request)
        page=context.new_page();page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
        page.on('console',lambda message:report['console_errors'].append(message.text) if message.type=='error' else None)
        query=dict(parse_qsl(base.query));query['inspect']='1'
        page.goto(urlunsplit((base.scheme,base.netloc,base.path,urlencode(query),'')),wait_until='networkidle')
        select=page.get_by_label('Recorded experiment',exact=True);expect(select).to_be_visible(timeout=30000)
        select.select_option(identity)
        expect(page.locator('.mode-label')).to_contain_text('Recorded simulation',timeout=30000)
        page.wait_for_selector('.three-host canvas',timeout=30000)
        page.wait_for_function("!document.querySelector('.canvas-status')",timeout=30000)
        expect(page.locator('.city-fallback')).to_have_count(0)
        ghost_toggle=page.get_by_label('Show baseline ghost',exact=True)
        for index,time_s in enumerate(times):
            page.get_by_role('button',name='Afterlight',exact=True).click();ghost_toggle.check()
            page.locator('#timeline').evaluate('''(element,time) => {
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(element,String(time));
                element.dispatchEvent(new Event('input',{bubbles:true}));element.dispatchEvent(new Event('change',{bubbles:true}));
            }''',time_s)
            active=sampled_vehicles(replay['worlds']['afterlight']['frames'],time_s)
            baseline=sampled_vehicles(replay['worlds']['baseline']['frames'],time_s)
            snapshot=inspect(page,time_s,'afterlight',True)
            check={'time_s':time_s,'active':check_layer(snapshot['active'],active,'afterlight'),
                   'ghost':check_layer(snapshot['ghost'],[ambulance(baseline)] if ambulance(baseline) else [],'ghost')}
            ghost_toggle.uncheck();hidden=inspect(page,time_s,'afterlight',False)
            check_layer(hidden['active'],active,'afterlight-ghost-off');check_layer(hidden['ghost'],[],'hidden-ghost')
            if hidden['active']!=snapshot['active']:raise AssertionError('Ghost toggle changed active-world instance state')
            page.get_by_role('button',name='Baseline',exact=True).click();ordinary=inspect(page,time_s,'baseline',False)
            check['ordinary']=check_layer(ordinary['active'],baseline,'ordinary');check_layer(ordinary['ghost'],[],'baseline-ghost-hidden')
            page.get_by_role('button',name='Afterlight',exact=True).click();ghost_toggle.check()
            restored=inspect(page,time_s,'afterlight',True)
            check_layer(restored['active'],active,'restored-afterlight');check_layer(restored['ghost'],[ambulance(baseline)] if ambulance(baseline) else [],'restored-ghost')
            # A baseline-only vehicle type may leave a reusable zero-count batch
            # behind; compare physical slots/matrices, not cache key inventories.
            if restored['active']['ambulances']!=snapshot['active']['ambulances'] or restored['ghost']['ambulances']!=snapshot['ghost']['ambulances']:raise AssertionError('World/ghost switching retimed or changed original ambulance instance matrices')
            page.screenshot(path=str(output/f'real-city-{index+1}.png'),full_page=True)
            report['checks'].append(check)
        if report['page_errors'] or report['console_errors'] or report['blocked_external_requests']:raise AssertionError('Browser error or unexpected external network access; inspect retained diagnostics')
        if verify_served_preview(base)!=viewer:raise ValueError('Viewer provenance changed during inspection')
        report['status']='passed_matrix_checks_manual_visual_review_pending'
        context.close();context=None;browser.close();browser=None
    except Exception as error:
        report.update(status='failed',error=str(error),error_type=type(error).__name__)
        if page is not None:
            try:page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception as capture_error:report['screenshot_error']=str(capture_error)
        raise
    finally:
        # Browser resources only: never terminate a simulator or unrelated task.
        if context is not None:
            try:context.close()
            except Exception:pass
        if browser is not None:
            try:browser.close()
            except Exception:pass
        if playwright is not None:
            try:playwright.stop()
            except Exception:pass
        with (output/'report.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
