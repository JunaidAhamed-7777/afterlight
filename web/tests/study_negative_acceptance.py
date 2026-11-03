"""Desktop Study-panel negative flows; never supplies positive study metrics.

The initial404 is the actual served unpublished state. Later isolated GET faults
contain only missing/malformed/invalid publication bytes, never a valid summary.
Checks cancellation and preservation of a genuine paused public recording.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, ready, returning_visit, seek, source_identity, verify_served_build


FETCH_OBSERVER = """(() => {
  window.__studyFetch=[];const original=window.fetch.bind(window);
  window.fetch=(input,options)=>{
    const url=typeof input==='string'?input:input?.url??String(input);
    if(!new URL(url,location.href).pathname.includes('/study/'))return original(input,options);
    const row={url,aborted:Boolean(options?.signal?.aborted),abortEvents:0};window.__studyFetch.push(row);
    options?.signal?.addEventListener('abort',()=>{row.aborted=true;row.abortEvents++;},{once:true});
    return original(input,options).then(response=>{row.status=response.status;return response;},error=>{row.rejected=error.name;throw error;});
  };
})()"""


def state(page):
    return page.evaluate("""() => {
      const c=document.querySelector('.three-host canvas');const box=document.querySelector('.stage-column').getBoundingClientRect();
      return {title:document.querySelector('.stage-title').textContent,time:document.querySelector('#timeline').value,
        playLabel:document.querySelector('.play-button').getAttribute('aria-label'),
        world:document.querySelector('.stage-actions .segmented button[aria-pressed=true]')?.textContent,
        ambulanceFollow:document.querySelector('.follow-ambulance').getAttribute('aria-pressed'),
        ghostFollow:document.querySelector('.follow-ghost').getAttribute('aria-pressed'),
        cameraTarget:c.dataset.cameraTarget,zoom:c.dataset.cameraZoom,
        stage:{x:box.x,y:box.y,width:box.width,height:box.height},
        document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],viewport:[innerWidth,innerHeight]};
    }""")


def preserved(page, baseline):
    after=state(page)
    for field in ('title','time','playLabel','world','ambulanceFollow','ghostFollow','cameraTarget','zoom','stage'):
        assert baseline[field]==after[field],('Study flow changed recording or map',field,baseline[field],after[field])
    assert after['document'][0]<=after['viewport'][0]+1 and after['document'][1]<=after['viewport'][1]+1,after
    return after


def no_metrics(page):
    expect(page.locator('.study-comparison,.study-counts,.study-deltas,.study-downloads')).to_have_count(0)


def keyboard_retry(page):
    before=len(page.evaluate('window.__studyFetch'))
    page.get_by_role('button',name='Retry study',exact=True).focus()
    page.keyboard.press('Enter')
    # Wait for this request generation to finish, rather than accepting the
    # previous error still present before the loading effect commits.
    page.wait_for_function("n=>window.__studyFetch.length>n&&window.__studyFetch.slice(n).every(r=>r.status||r.rejected)&&document.querySelector('.study-results')?.getAttribute('aria-busy')==='false'",arg=before,timeout=30000)


def readable_error(page):
    message=page.locator('.study-results [role=status]').inner_text()
    assert 'study' in message.lower(),('Error needs study-specific context',message)
    assert not re.search(r'\btrace\b|position\s+\d+|line\s+\d+|column\s+\d+|expected property|unexpected token|unterminated',message,re.I),message
    return message


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:5199/')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--build-manifest',type=Path)
    args=parser.parse_args()
    address=urlsplit(args.base_url)
    if address.username or address.password or not ((address.scheme=='http' and address.hostname in {'localhost','127.0.0.1'}) or (address.scheme=='https' and address.hostname and address.hostname.endswith('.vercel.app'))):
        parser.error('Use the local product or its HTTPS Vercel deployment')
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/'local-runtime').resolve()):parser.error('Use fresh local-runtime output')
    output.mkdir(parents=True,exist_ok=False)
    report={'status':'pending','scope':__doc__,'started_utc':datetime.now(timezone.utc).isoformat(),'base_url':args.base_url,
            'source_before':source_identity(),'cases':[],'study_responses':[],'page_errors':[],'requests':[]}
    playwright=browser=context=page=None
    held=[]
    try:
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(channel='chrome',headless=False,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        report['browser_version']=browser.version
        context=browser.new_context(viewport={'width':1440,'height':810},device_scale_factor=1)
        returning_visit(context);context.add_init_script(FETCH_OBSERVER)
        manifest=json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:report['served_build_before']=verify_served_build(context,args.base_url,manifest)
        catalog=context.request.get(urljoin(args.base_url,'replays/catalog.json')).json()
        entry=next(e for e in catalog['runs'] if e['seed']==7)
        report['genuine_recording']=entry
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('request',lambda r:report['requests'].append({'method':r.method,'url':r.url}))
        def response_seen(response):
            if '/study/' in urlsplit(response.url).path:
                report['study_responses'].append({'url':response.url,'status':response.status,'accept':response.request.headers.get('accept')})
        page.on('response',response_seen)
        page.goto(args.base_url,wait_until='domcontentloaded');ready(page)
        page.evaluate("document.title='AFTERLIGHT Study negative-flow check — automated browser'")
        expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
        seek(page,180.5);page.locator('.follow-ambulance').click()
        expect(page.locator('.follow-ambulance')).to_have_attribute('aria-pressed','true')
        page.wait_for_timeout(600)
        baseline=state(page);report['preserved_recording_baseline']=baseline
        assert not page.evaluate('window.__studyFetch'),'Study fetched eagerly before its subview mounted'
        page.get_by_role('button',name='Results',exact=True).click()
        expect(page.get_by_role('button',name='This run',exact=True)).to_have_attribute('aria-pressed','true')
        expect(page.locator('.evidence')).to_be_visible()
        assert not page.evaluate('window.__studyFetch'),'This run fetched Study evidence'
        page.get_by_role('button',name='Study',exact=True).click()
        expect(page.get_by_role('heading',name='Study not published',exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_role('button',name='Study',exact=True)).to_be_focused()
        no_metrics(page);preserved(page,baseline)
        assert report['study_responses'] and report['study_responses'][-1]['status']==404
        assert report['study_responses'][-1]['accept']=='application/json'
        keyboard_retry(page)
        expect(page.get_by_role('heading',name='Study not published',exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_role('button',name='Retry study',exact=True)).to_be_focused()
        no_metrics(page);preserved(page,baseline)
        page.screenshot(path=str(output/'actual-404-unpublished.png'),full_page=True)
        report['cases'].append({'case':'actual-unpublished404-and-retry','native_response_404':True,'no_eager_fetch':True,'no_placeholder_metrics':True,'genuine_recording_preserved':True,'initial_error_did_not_steal_Study_tab_focus':True,'keyboard_retry_focus_restored':True})

        mode={'kind':'malformed-manifest'}
        body=b'{}'
        def publication():
            payload=b'{' if mode['kind']=='malformed-summary' else b'{"schema":"qa.invalid"}' if mode['kind']=='schema-invalid-summary' else body
            transport={'schema':'afterlight.study-summary-manifest.v1','url':'summary.json','sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
            if mode['kind']=='byte-count-mismatch':transport['bytes']+=1
            if mode['kind']=='checksum-mismatch':transport['sha256']='0'*64
            return payload,transport
        def manifest_route(route):
            kind=mode['kind']
            if kind=='hold-manifest':held.append(route);return
            if kind=='malformed-manifest':data=b'{'
            elif kind=='schema-invalid-manifest':data=b'{"schema":"qa.invalid"}'
            elif kind=='oversized-manifest':data=b' '*(17*1024)
            else:data=json.dumps(publication()[1]).encode()
            route.fulfill(status=200,content_type='application/json',body=data)
        def summary_route(route):
            if mode['kind']=='hold-summary':held.append(route);return
            route.fulfill(status=404 if mode['kind']=='missing-summary' else 200,content_type='application/json',body=publication()[0])
        page.route('**/study/manifest.json',manifest_route);page.route('**/study/summary.json',summary_route)
        for name,fragment in [('malformed-manifest','study'),('schema-invalid-manifest','manifest'),('oversized-manifest','study'),
                              ('byte-count-mismatch','byte count'),('checksum-mismatch','checksum'),('malformed-summary','study'),
                              ('schema-invalid-summary','summary'),('missing-summary','summary request failed (404)')]:
            mode['kind']=name
            keyboard_retry(page)
            expect(page.get_by_role('heading',name='Study evidence unavailable',exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('.study-results [role=status]')).to_contain_text(re.compile(re.escape(fragment),re.I))
            no_metrics(page);preserved(page,baseline)
            message=readable_error(page)
            expect(page.get_by_role('button',name='Retry study',exact=True)).to_be_focused()
            focus=page.evaluate("({tag:document.activeElement?.tagName,text:document.activeElement?.textContent?.trim().slice(0,100),retryFocused:document.activeElement?.textContent?.trim()==='Retry study'})")
            report['cases'].append({'case':name,'deliberate_invalid_GET_response_only':True,'visible_error':message,'readable_study_specific_copy':True,'no_placeholder_metrics':True,'genuine_recording_preserved':True,'focus_after_retry':focus})
            if name in ('checksum-mismatch','schema-invalid-summary'):page.screenshot(path=str(output/(name+'.png')),full_page=True)

        page.get_by_role('button',name='This run',exact=True).click()
        mode['kind']='schema-invalid-summary'
        page.get_by_role('button',name='Study',exact=True).click()
        expect(page.get_by_role('heading',name='Study evidence unavailable',exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_role('button',name='Study',exact=True)).to_be_focused()
        no_metrics(page);preserved(page,baseline)
        report['cases'].append({'case':'initial-summary-error-does-not-steal-focus','Study_tab_remains_focused':True,'no_placeholder_metrics':True})

        for stage in ('manifest','summary'):
            mode['kind']='hold-'+stage
            page.get_by_role('button',name='Retry study',exact=True).focus();page.keyboard.press('Enter')
            page.wait_for_function("stage=>window.__studyFetch.some(r=>r.url.endsWith('/study/'+stage+'.json')&&!r.aborted&&!r.status)",arg=stage,timeout=10000)
            expect(page.get_by_role('heading',name='Loading study evidence…',exact=True)).to_be_visible()
            # Use actual Tab navigation to leave the loading Study panel.
            tabs=0
            while not page.locator('.follow-ambulance').evaluate('e=>e===document.activeElement') and tabs<60:
                page.keyboard.press('Tab');tabs+=1
            expect(page.locator('.follow-ambulance')).to_be_focused()
            for route in held:
                route.fulfill(status=200,content_type='application/json',body=b'{')
            held.clear()
            expect(page.get_by_role('heading',name='Study evidence unavailable',exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('.follow-ambulance')).to_be_focused()
            no_metrics(page);preserved(page,baseline);readable_error(page)
            report['cases'].append({'case':'retry-'+stage+'-does-not-steal-outside-focus','actual_Tab_navigation_count':tabs,'outside_Follow_control_remains_focused':True,'no_placeholder_metrics':True})

        for stage in ('manifest','summary'):
            for destination in ('This run','Simulation'):
                mode['kind']='hold-'+stage
                if not page.locator('.study-results').count():
                    page.get_by_role('button',name='Results',exact=True).click()
                    if page.get_by_role('button',name='Study',exact=True).get_attribute('aria-pressed')!='true':page.get_by_role('button',name='Study',exact=True).click()
                else:page.get_by_role('button',name='Retry study',exact=True).click()
                page.wait_for_function("stage=>window.__studyFetch.some(r=>r.url.endsWith('/study/'+stage+'.json')&&!r.aborted&&!r.status)",arg=stage,timeout=10000)
                index=page.evaluate("stage=>window.__studyFetch.findLastIndex(r=>r.url.endsWith('/study/'+stage+'.json')&&!r.aborted&&!r.status)",stage)
                expect(page.get_by_role('heading',name='Loading study evidence…',exact=True)).to_be_visible()
                page.get_by_role('button',name=destination,exact=True).click()
                page.wait_for_function('index=>window.__studyFetch[index].aborted',arg=index,timeout=5000)
                no_metrics(page);preserved(page,baseline)
                # Finish the deliberately held test routes after cancellation;
                # no valid summary is ever supplied, including a late response.
                for route in held:
                    try:route.fulfill(status=200,content_type='application/json',body=b'{}')
                    except Exception:pass
                held.clear();page.wait_for_timeout(80)
                expect(page.locator('.study-results')).to_have_count(0)
                report['cases'].append({'case':'cancel-'+stage+'-via-'+destination,'actual_fetch_signal_aborted':True,'no_late_study_UI':True,'genuine_recording_clock_follow_camera_preserved':True})
        assert not report['page_errors'],report['page_errors']
        assert all(r['method'] in {'GET','HEAD'} for r in report['requests']),report['requests']
        report['fetch_observation']=page.evaluate('window.__studyFetch')
        if manifest:report['served_build_after']=verify_served_build(context,args.base_url,manifest)
        report['status']='passed_Study_negative_flows_and_actual_cancellation'
    except Exception as error:
        report.update(status='failed',error=str(error))
        if page is not None:
            try:page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception:pass
        raise
    finally:
        if context is not None:
            for route in held:
                try:route.abort()
                except Exception:pass
            context.unroute_all(behavior='ignoreErrors');context.close()
        if browser is not None:browser.close()
        if playwright is not None:playwright.stop()
        report['source_after']=source_identity();report['source_stable']=report['source_before']==report['source_after']
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ('status','error','browser_version')},indent=2))


if __name__=='__main__':main()
