"""Measure headed desktop dense-replay loading and retained JS heap on switching.

Reports natural heap observations and separately labeled forced-GC retention
samples. It does not claim total GPU/process memory or cross-device guarantees.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from urllib.request import urlopen
from urllib.parse import urljoin
from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, ready, returning_visit, source_identity, verify_served_build


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",default="http://127.0.0.1:5188/")
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--build-manifest",type=Path)
    parser.add_argument("--headless",action="store_true",help="Heap-only supplementary run; no GPU performance claim")
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to((ROOT/"local-runtime").resolve()):parser.error("Use fresh local-runtime output")
    output.mkdir(parents=True,exist_ok=False)
    with urlopen(urljoin(args.base_url,"replays/catalog.json")) as response:entries=json.load(response)["runs"]
    assert len(entries)>=2,"Two genuine recordings are required"
    report={"scope":__doc__,"status":"pending","headless":args.headless,"source_before":source_identity(),"samples":[],"page_errors":[]}
    playwright=browser=page=None
    try:
        playwright=sync_playwright().start()
        browser=playwright.chromium.launch(channel="chrome",headless=args.headless,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        context=browser.new_context(viewport={"width":1920,"height":1080},device_scale_factor=1)
        returning_visit(context)
        manifest=json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:
            report["served_production_build"]=manifest
            report["served_build_before"]=verify_served_build(context,args.base_url,manifest)
        page=context.new_page();page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
        page.add_init_script("window.__loadTasks=[];new PerformanceObserver(l=>window.__loadTasks.push(...l.getEntries().map(e=>({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true});")
        cdp=context.new_cdp_session(page);cdp.send("Performance.enable")
        started=time.perf_counter();page.goto(args.base_url,wait_until="domcontentloaded");ready(page)
        expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
        def sample(entry,label,seconds):
            natural={m["name"]:m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
            cdp.send("HeapProfiler.collectGarbage")
            retained={m["name"]:m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
            row={"label":label,"recording_id":entry["id"],"load_seconds":seconds,
                "natural_js_heap_used_bytes":natural["JSHeapUsedSize"],"forced_gc_retained_js_heap_bytes":retained["JSHeapUsedSize"],
                "render":page.locator('.three-host canvas').evaluate("c=>JSON.parse(c.dataset.renderInfo)"),
                "main_thread_long_tasks":page.evaluate("window.__loadTasks")}
            report["samples"].append(row)
        sample(entries[0],"initial",time.perf_counter()-started)
        for index,entry in enumerate([entries[1],entries[0],entries[1],entries[0]],1):
            page.evaluate("window.__loadTasks=[]")
            started=time.perf_counter()
            page.locator('.recording-card').filter(has_text=entry['title']).click()
            expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
            expect(page.locator('.stage-title')).to_have_text(entry['title'])
            sample(entry,f"switch-{index}",time.perf_counter()-started)
        retained=[s["forced_gc_retained_js_heap_bytes"] for s in report["samples"] if s["recording_id"]==entries[0]["id"]]
        assert max(retained)-min(retained)<32*1024*1024,("Repeated same-recording retained heap drift exceeds32MiB",retained)
        for name in ('geometries','textures'):
            assert len({s['render'][name] for s in report['samples'][1:]})==1,("Renderer resource count drift",name)
        assert not report['page_errors'],report['page_errors']
        page.screenshot(path=str(output/'after-four-switches.png'),full_page=True)
        if manifest:report['served_build_after']=verify_served_build(context,args.base_url,manifest)
        report['status']='passed_dense_replay_loading_and_bounded_retention'
    except Exception as error:
        report.update(status='failed',error=str(error))
        if page is not None:
            try:page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception:pass
        raise
    finally:
        if browser is not None:browser.close()
        if playwright is not None:playwright.stop()
        report['source_after']=source_identity();report['source_stable']=report['source_before']==report['source_after']
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps({k:report.get(k) for k in ('status','error','samples')},indent=2))


if __name__=='__main__':main()
