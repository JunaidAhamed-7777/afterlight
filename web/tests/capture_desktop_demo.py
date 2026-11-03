"""Capture actual desktop browser pixels; default is a short unpublished dry run.

Final mode performs a roughly 70-second returning-user walkthrough after real
asset loading. Native 25 fps browser video is encoded to silent H.264 with no
overlays, generated scenes, retiming, interpolated frames, or substituted data.
Do not invoke final mode until the post-Canva frontend is ready.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, decoded_recording, digest, open_recording, ready, returning_visit, seek, source_identity, verify_served_build
from released_study_pack import load_released_public_pack


def fetched(url):
    with urlopen(url,timeout=40) as response:return response.read(128*1024*1024+1)


def probe(path,ffprobe):
    completed=subprocess.run([ffprobe,'-v','error','-show_format','-show_streams','-of','json',str(path)],check=True,capture_output=True,text=True,timeout=30)
    return json.loads(completed.stdout)


def encode(source,output,ffmpeg,ffprobe):
    original=probe(source,ffprobe)
    # A new page's native recorder can prepend a white about:blank frame.
    # Inspect at most the first second and omit only this empty prefix, never
    # the real loading screen or a pause inside the product walkthrough.
    sample=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-i',str(source),'-t','1',
                           '-vf','scale=64:36','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],
                          check=True,capture_output=True,timeout=30).stdout
    frame_bytes=64*36*3
    blank_frames=None
    for index in range(len(sample)//frame_bytes):
        pixels=sample[index*frame_bytes:(index+1)*frame_bytes]
        nonwhite=sum(min(pixels[i:i+3])<240 for i in range(0,frame_bytes,3))
        if nonwhite>64*36*.05:
            blank_frames=index;break
    assert blank_frames is not None,'Capture opening remained blank for a second; inspect startup before publishing'
    removed_seconds=blank_frames/25
    duration=float(original['format']['duration'])-removed_seconds
    bitrate=min(900000,int(7_200_000*8*.92/max(duration,1)))
    target=output/'afterlight-desktop-demo.mp4'
    common=[ffmpeg,'-hide_banner','-loglevel','warning','-y','-ss',str(removed_seconds),'-i',str(source),'-map','0:v:0','-an',
            '-c:v','libx264','-preset','slow','-b:v',str(bitrate),'-pix_fmt','yuv420p','-r','25',
            '-passlogfile',str(output/'x264-pass')]
    with (output/'encoding.log').open('wb') as log:
        subprocess.run(common+['-pass','1','-f','null',os.devnull],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        subprocess.run(common+['-pass','2','-movflags','+faststart',str(target)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    encoded=probe(target,ffprobe)
    video=[s for s in encoded['streams'] if s['codec_type']=='video']
    assert len(video)==1 and video[0]['codec_name']=='h264' and video[0]['pix_fmt']=='yuv420p'
    assert not any(s['codec_type']=='audio' for s in encoded['streams'])
    assert target.stat().st_size<=8_000_000,'Compressed video exceeds8MB; do not publish'
    assert abs(float(encoded['format']['duration'])-duration)<.15,'Encoding changed recorded duration'
    return target,{'source':original,'encoded':encoded,'target_video_bitrate_bps':bitrate,'bytes':target.stat().st_size,'sha256':digest(target.read_bytes()),
                   'empty_leading_frames_removed':blank_frames,'empty_prefix_removed_seconds':removed_seconds,
                   'method':'Two-pass H.264 compression at native25fps and viewport resolution. Only a verified leading empty about:blank prefix is omitted; actual product loading and walkthrough timing are retained. Silent, no crop, overlays, retiming or generated/interpolated frames.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:5182/')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--mode',choices=('dry-run','final'),default='dry-run')
    parser.add_argument('--width',type=int,choices=(1280,1600),default=1280)
    parser.add_argument('--build-manifest',type=Path)
    parser.add_argument('--study-manifest-sha256',help='Required for final mode: exact completed public Study manifest SHA-256')
    args=parser.parse_args()
    address=urlsplit(args.base_url)
    if address.username or address.password or not ((address.scheme=='http' and address.hostname in {'localhost','127.0.0.1'}) or (address.scheme=='https' and address.hostname and address.hostname.endswith('.vercel.app'))):
        parser.error('Use the local product or its HTTPS Vercel deployment')
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'local-runtime').resolve()):parser.error('Use fresh local-runtime output')
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:parser.error('Install the official FFmpeg tooling before capturing; both ffmpeg and ffprobe must be on PATH')
    if args.mode=='final' and not args.study_manifest_sha256:parser.error('Final mode requires the actual released Study manifest SHA-256; there is no placeholder fallback')
    output.mkdir(parents=True,exist_ok=False)
    # Default capability checks do not open any Study data. Final mode is
    # explicitly release-gated and independently verifies the real public pack.
    study_pack=load_released_public_pack(args.base_url,args.study_manifest_sha256) if args.mode=='final' else None
    catalog_bytes=fetched(urljoin(args.base_url,'replays/catalog.json'));catalog=json.loads(catalog_bytes)
    entries=catalog['runs']
    assert len(entries)>=2,'Two genuine hospital recordings are required'
    chosen=[next(e for e in entries if e['seed']==seed) for seed in (7,8)]
    preflight=[]
    for entry in chosen:
        raw=decoded_recording(fetched(urljoin(urljoin(args.base_url,'replays/'),entry['url'])))
        assert digest(raw)==entry['sha256'] and len(raw)==entry['bytes']
        replay=json.loads(raw);del raw
        assert replay['mode']=='recorded' and replay['step_s']==.5
        assert replay['scenario']['id']==entry['id'] and replay['scenario']['hospital_id']==entry['hospital_id']
        active=replay['worlds']['afterlight']['frames'];ordinary=replay['worlds']['baseline']['frames']
        ordinary_times={f['t'] for f in ordinary if any(v['id']=='ambulance' for v in f['vehicles'])}
        common=[f for f in active if f['t'] in ordinary_times and any(v['id']=='ambulance' for v in f['vehicles'])]
        assert common
        safe=[f for f in common if f['t']>replay['scenario']['dispatch_s']+15 and f['t']+55<common[-1]['t']]
        start=max(safe or common,key=lambda f:len(f['vehicles']))['t']
        compare=common[len(common)//3]['t']
        preflight.append({'id':entry['id'],'decoded_sha256':entry['sha256'],'decoded_bytes':entry['bytes'],
                          'step_s':replay['step_s'],'hospital_id':entry['hospital_id'],'overview_time_s':start,'comparison_time_s':compare})
        del replay,active,ordinary,common,safe;gc.collect()
    assert preflight[0]['hospital_id']!=preflight[1]['hospital_id']
    viewport={'width':args.width,'height':args.width*9//16}
    report={'status':'pending','mode':args.mode,'publication':'UNPUBLISHED_CAPABILITY_CHECK' if args.mode=='dry-run' else 'FINAL_CAPTURE_AWAITING_PIXEL_REVIEW',
            'scope':__doc__,'started_utc':datetime.now(timezone.utc).isoformat(),'base_url':args.base_url,
            'source_before':source_identity(),'catalog_sha256':digest(catalog_bytes),'genuine_recordings':preflight,
            'viewport_css':viewport,'device_pixel_ratio':1,'native_video_fps':25,'actions':[],'page_errors':[],
            'released_Study':study_pack,'study_responses':[]}
    browser=playwright=context=page=None
    try:
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(channel='chrome',headless=False,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        report['browser_version']=browser.version
        context=browser.new_context(viewport=viewport,device_scale_factor=1,record_video_dir=output/'native',record_video_size=viewport,record_video_fps=25)
        returning_visit(context)
        manifest=json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:report['served_build_before']=verify_served_build(context,args.base_url,manifest)
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        # Restore only this capture's own native window. A minimized recorder can
        # otherwise produce one-frame-per-second traffic despite a healthy app.
        # Keep native rendering and throttling behavior; do not force GPU flags.
        session=context.new_cdp_session(page)
        try:
            window=session.send('Browser.getWindowForTarget')
            report['native_window_before']=window['bounds']
            if window['bounds']['windowState']=='minimized':
                session.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
            report['native_window_after']=session.send('Browser.getWindowBounds',{'windowId':window['windowId']})['bounds']
        finally:session.detach()
        page.bring_to_front()
        page.wait_for_function("document.visibilityState==='visible' && document.hasFocus()",timeout=15000)
        page.add_init_script("""(() => {
          const state = event => ({event,visibility:document.visibilityState,focused:document.hasFocus()});
          const q = window.__captureLifecycle = {enabled:false,events:[],state};
          document.addEventListener('visibilitychange', () => {if(q.enabled)q.events.push(state('visibilitychange'));});
          for(const event of ['focus','blur'])window.addEventListener(event, () => {if(q.enabled)q.events.push(state(event));});
        })();""")
        def study_response(response):
            if study_pack and response.url in (study_pack['manifest_url'],study_pack['summary_url']):
                data=response.body();report['study_responses'].append({'url':response.url,'status':response.status,'bytes':len(data),'sha256':digest(data)})
        page.on('response',study_response)
        video=page.video;assert video
        capture_started=time.perf_counter()
        page.goto(args.base_url,wait_until='domcontentloaded');ready(page);open_recording(page,chosen[0])
        page.evaluate("document.title='AFTERLIGHT demo capture — automated browser'")
        expect(page.locator('.mode-label')).to_contain_text('Recorded')
        expect(page.get_by_role('combobox',name='Playback speed',exact=True)).to_be_visible()
        assert page.locator('.generation-wrap').count()==0,'Capture the public recording viewer, not local generation'
        page.locator('canvas').focus()
        page.wait_for_function("document.visibilityState==='visible' && document.hasFocus()",timeout=15000)
        page.evaluate("() => {const q=window.__captureLifecycle;q.events=[q.state('start')];q.enabled=true;}")
        started=time.perf_counter()
        def note(action):
            report['actions'].append({'walkthrough_seconds':round(time.perf_counter()-started,3),'action':action,
                                      'recorded_time_s':float(page.locator('#timeline').input_value()),'speed':page.get_by_role('combobox',name='Playback speed',exact=True).input_value(),
                                      'recorded_label':page.locator('.mode-label').inner_text()})
        def until(seconds):
            remaining=seconds-(time.perf_counter()-started)
            if remaining>0:page.wait_for_timeout(remaining*1000)
        def play():
            button=page.get_by_role('button',name='Play recording',exact=True)
            if button.count():button.click()
        def pause():
            button=page.get_by_role('button',name='Pause recording',exact=True)
            if button.count():button.click()
        def shot(name):page.screenshot(path=str(output/(name+'.png')),full_page=True)
        seek(page,preflight[0]['overview_time_s'])
        if args.mode=='final':shot('00-workspace-explore')
        page.get_by_role('button',name='Full city',exact=True).click()
        page.get_by_role('combobox',name='Playback speed',exact=True).select_option('2')
        play();note('Full city: genuine Cross-city recording at2x')
        if args.mode=='dry-run':
            page.wait_for_timeout(2000);pause();shot('dry-run-actual-browser')
        else:
            shot('01-city-overview');until(8)
            page.locator('.follow-ambulance').click();expect(page.locator('.follow-ambulance')).to_have_attribute('aria-pressed','true')
            note('Follow Ambulance: Afterlight');until(20);shot('02-priority-follow');until(24)
            pause();seek(page,preflight[0]['comparison_time_s']);note('Pause and seek to an actual comparison time');until(28)
            page.get_by_role('button',name='Ordinary',exact=True).click();page.locator('.follow-ambulance').click();play()
            note('Inspect Ordinary traffic world and follow its ambulance');until(35);shot('03-ordinary-world');until(36)
            page.locator('.follow-ghost').click();expect(page.get_by_role('button',name='Afterlight',exact=True)).to_have_attribute('aria-pressed','true')
            note('Follow Ghost: ordinary response over the Afterlight scene');until(42);shot('04-ghost-comparison')
            pause();page.get_by_role('button',name='Settings',exact=True).click()
            page.get_by_role('checkbox',name='Show baseline ghost',exact=False).uncheck();note('Inspect ghost visibility setting');until(46)
            page.locator('.follow-ghost').click();note('Follow Ghost restores the overlay');until(48)
            open_recording(page,chosen[1]);seek(page,preflight[1]['comparison_time_s'])
            page.locator('.follow-ambulance').click();page.get_by_role('combobox',name='Playback speed',exact=True).select_option('2');play()
            note('Switch to the genuine Westhaven hospital recording');until(59);shot('05-westhaven-response');until(62)
            pause();page.get_by_role('button',name='Results',exact=True).click()
            page.get_by_role('button',name='This run',exact=True).click()
            expect(page.locator('.evidence:not(.study-results)')).to_be_visible()
            report['recorded_results_layout']=page.locator('.evidence-table-wrap').evaluate("""table => ({
              overflow:table.scrollWidth>table.clientWidth,
              statusCells:[...table.querySelectorAll('tbody tr:first-child td')].map(cell=>{
                const range=document.createRange();range.selectNodeContents(cell);
                return {text:cell.textContent,lines:range.getClientRects().length,overflow:cell.scrollWidth>cell.clientWidth};
              })
            })""")
            assert not report['recorded_results_layout']['overflow']
            assert len(report['recorded_results_layout']['statusCells'])==2
            assert all(row['lines']==1 and not row['overflow'] for row in report['recorded_results_layout']['statusCells']),'Run status split within a word'
            note('Read actual This run results');shot('06-recorded-results');until(65)
            page.locator('.settings-scroll').evaluate("e=>e.scrollTo({top:Math.min(360,e.scrollHeight),behavior:'instant'})")
            note('Inspect civilian delay and vehicle accounting');shot('07-traffic-accounting');until(67)
            page.get_by_role('button',name='Study',exact=True).click()
            expect(page.get_by_role('heading',name='Offline selector results' if study_pack['summary']['mode']=='learned' else 'Analytical baseline results',exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('.study-counts dd')).to_have_text([f"{study_pack['summary']['counts'][key]:,}" for key in ('test','test_demand_groups','test_worlds')])
            expect(page.locator('.study-comparison')).to_have_count(len(study_pack['summary']['comparisons']))
            for url,expected in ((study_pack['manifest_url'],study_pack['manifest_sha256']),(study_pack['summary_url'],study_pack['manifest']['sha256'])):
                assert any(row['url']==url and row['status']==200 and row['sha256']==expected for row in report['study_responses']),('Final video did not load the real released Study',url)
            note('Inspect the actual released Study report')
            until(max(70,time.perf_counter()-started+2.5));shot('08-released-study')
        report['captured_wall_seconds']=time.perf_counter()-capture_started
        report['walkthrough_lifecycle']=page.evaluate("() => {const q=window.__captureLifecycle;q.events.push(q.state('end'));q.enabled=false;return q.events;}")
        report['foreground_qualified']=all(row['visibility']=='visible' and row['focused'] for row in report['walkthrough_lifecycle'])
        assert report['foreground_qualified'],'Capture lost foreground visibility/focus; retain it privately and inspect before publishing'
        assert not report['page_errors'],report['page_errors']
        context.close();context=None
        source=Path(video.path())
        if manifest:
            context=browser.new_context()
            report['served_build_after']=verify_served_build(context,args.base_url,manifest)
            context.close();context=None
        browser.close();browser=None
        target,encoding=encode(source,output,ffmpeg,ffprobe)
        report['native_video_relative_path']=source.relative_to(output).as_posix()
        report['encoded_video_relative_path']=target.name;report['encoding']=encoding
        stream=next(s for s in encoding['encoded']['streams'] if s['codec_type']=='video')
        assert [stream['width'],stream['height']]==[viewport['width'],viewport['height']],'Video was scaled instead of1:1 capture'
        if args.mode=='final':
            duration=float(encoding['encoded']['format']['duration'])
            assert 60<=duration<=90,('Final walkthrough must remain60–90s including actual loading',duration)
            if manifest:assert manifest['total_bytes']+encoding['bytes']<50_000_000,'Combined build and video exceed50MB'
        report['status']='passed_unpublished_capture_capability' if args.mode=='dry-run' else 'captured_final_walkthrough_pending_pixel_review'
    except Exception as error:
        report.update(status='failed',error=str(error))
        raise
    finally:
        if context is not None:context.close()
        if browser is not None:browser.close()
        if playwright is not None:playwright.stop()
        report['source_after']=source_identity();report['source_stable']=report['source_before']==report['source_after']
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ('status','mode','error','captured_wall_seconds','encoded_video_relative_path')},indent=2))


if __name__=='__main__':main()
