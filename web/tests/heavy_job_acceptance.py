"""GET-only recovery, local 256 MiB transport, and heap checks for one real heavy job.

Uses an explicitly supplied, already audited terminal journal. It never submits
or retries a simulation. Its censored traffic outcomes remain censored; this is
a desktop transport/resource check, not held-out performance evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, source_identity, verify_served_build


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(path):
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError("Redirected evidence paths are unsupported")
        if item.is_file(): result[item.relative_to(path).as_posix()] = file_sha(item)
    return result


def served_replay(url, expected_bytes, expected_sha):
    checksum = hashlib.sha256(); count = 0
    with urlopen(url, timeout=60) as response:
        assert response.status == 200
        while chunk := response.read(1024 * 1024):
            count += len(chunk); checksum.update(chunk)
    assert count == expected_bytes and checksum.hexdigest() == expected_sha, "Independent GET differs from the audited original recording"
    return {"bytes":count,"sha256":checksum.hexdigest(),"method":"GET","streamed_without_retaining_trace":True}


WORKER_OBSERVER = """(() => {
  localStorage.setItem('afterlight.onboarding.v1',JSON.stringify({version:1,status:'completed'}));
  window.__heavyQA={created:0,terminated:0,posts:[],loads:[],longTasks:[]};
  new PerformanceObserver(list=>window.__heavyQA.longTasks.push(...list.getEntries().map(e=>({startMs:e.startTime,durationMs:e.duration})))).observe({type:'longtask',buffered:true});
  const Original=window.Worker;
  window.Worker=class extends Original {
    constructor(...args){super(...args);window.__heavyQA.created++;
      this.addEventListener('message',e=>{if(e.data?.type==='loaded')window.__heavyQA.loads.push({
        url:this.__url,expectedSha256:this.__sha,decodedLimit:this.__limit,scenario:e.data.replay?.scenario?.id,
        worldStatus:{afterlight:e.data.replay?.worlds?.afterlight?.status,baseline:e.data.replay?.worlds?.baseline?.status}});});}
    postMessage(message,...args){this.__url=message?.url;this.__sha=message?.expectedSha256;this.__limit=message?.decodedLimit;
      window.__heavyQA.posts.push({url:this.__url,expectedSha256:this.__sha,decodedLimit:this.__limit,published:Boolean(message?.entry)});
      return super.postMessage(message,...args);}
    terminate(){window.__heavyQA.terminated++;return super.terminate();}
  };
})()"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-manifest", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "local-runtime").resolve()): parser.error("Use fresh local-runtime output")
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1","localhost"} or url.username or url.password:
        parser.error("Use the current loopback viewer compiled against this journal's API")
    journal_path = args.journal.resolve()
    journal_bytes = journal_path.read_bytes(); journal = json.loads(journal_bytes)
    if journal["state"] != "transport_and_raw_audit_verified": parser.error("The heavy job must already have passed its independent raw/HTTP audit")
    expected_job = journal["job"]; identifier = expected_job["id"]
    assert expected_job["status"] == "completed" and identifier == journal["request"]["request_id"]
    expected_bytes, expected_sha = journal["replay_bytes"], journal["replay_sha256"]
    assert 128 * 1024 * 1024 < expected_bytes <= 256 * 1024 * 1024
    directory = journal_path.parent.parent / "jobs" / identifier
    assert file_sha(directory / "replay.json") == expected_sha == file_sha(journal_path.parent / "served-replay.json")
    raw_before = inventory(directory)
    outcomes = {row["world_id"]:row for row in json.loads((directory / "outcomes.json").read_bytes())}
    assert all(outcomes[w]["status"] == "censored" and outcomes[w]["civilian_mean_excess_s"] is None and outcomes[w]["civilian_excess_p95_s"] is None for w in ("afterlight","baseline"))
    api = journal["base_url"].rstrip("/")
    api_url = urlsplit(api)
    assert api_url.scheme == "http" and api_url.hostname in {"127.0.0.1","localhost"} and not api_url.username and not api_url.password
    replay_url = api + "/api/jobs/" + identifier + "/replay"
    output.mkdir(parents=True, exist_ok=False)
    report = {"status":"pending","scope":__doc__,"started_utc":datetime.now(timezone.utc).isoformat(),
              "viewer_url":args.base_url,"api_origin":api,"job_id":identifier,"journal_sha256":hashlib.sha256(journal_bytes).hexdigest(),
              "genuine_recording":{"bytes":expected_bytes,"sha256":expected_sha,"scenario_id":expected_job["result"]["scenario_id"],"world_status":expected_job["result"]["world_status"]},
              "source_before":source_identity(),"samples":[],"requests":[],"blocked_requests":[],"page_errors":[]}
    browser = playwright = page = None
    try:
        report["independent_GET_before"] = served_replay(replay_url, expected_bytes, expected_sha)
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome",headless=False,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        report["browser_version"] = browser.version
        context = browser.new_context(viewport={"width":1440,"height":810},device_scale_factor=1,service_workers="block")
        context.add_init_script(WORKER_OBSERVER)
        def readonly(route):
            if route.request.method not in {"GET","HEAD"}:
                report["blocked_requests"].append({"method":route.request.method,"url":route.request.url}); route.abort()
            else: route.continue_()
        context.route(api + "/api/**",readonly)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:
            report["served_build_before"] = verify_served_build(context,args.base_url,manifest)
        page = context.new_page()
        page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
        page.on("request",lambda r:report["requests"].append({"method":r.method,"url":r.url}))
        cdp = context.new_cdp_session(page); cdp.send("Performance.enable")
        origin = f"{url.scheme}://{url.netloc}"
        page.goto(origin + "/favicon.svg",wait_until="load")
        saved = {"id":identifier,"parameters":expected_job["parameters"]}; key = "afterlight.local-job:" + api
        page.evaluate("v=>sessionStorage.setItem(v.key,JSON.stringify(v.saved))",{"key":key,"saved":saved})

        def sample(label, seconds):
            natural = {m["name"]:m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
            cdp.send("HeapProfiler.collectGarbage")
            retained = {m["name"]:m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}
            report["samples"].append({"label":label,"load_seconds":seconds,
                "natural_js_heap_used_bytes":natural["JSHeapUsedSize"],"forced_gc_retained_js_heap_bytes":retained["JSHeapUsedSize"],
                "render":page.locator('.three-host canvas').evaluate("c=>JSON.parse(c.dataset.renderInfo)"),
                "long_tasks":page.evaluate("window.__heavyQA.longTasks")})

        def recover(label, reload=False):
            started = time.perf_counter()
            if reload: page.reload(wait_until="domcontentloaded")
            else: page.goto(args.base_url,wait_until="domcontentloaded")
            page.evaluate("document.title='AFTERLIGHT heavy recording check — automated browser'")
            button = page.get_by_role("button",name="Open completed recording",exact=True)
            expect(button).to_be_visible(timeout=120000)
            expect(page.locator('.generation-status')).to_contain_text("Execution finished")
            expect(page.locator('.generation-status')).to_contain_text(f"seed {expected_job['parameters']['seed']}")
            worker_ready_seconds = time.perf_counter() - started
            button.click()
            expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
            assert float(page.locator('#timeline').get_attribute('max')) == expected_job['result']['duration_s']
            page.wait_for_function("document.querySelector('.three-host canvas')?.dataset.renderInfo && !document.querySelector('.canvas-status') && !document.querySelector('.boot-screen')",timeout=90000)
            expect(page.locator('.fixture-view')).to_have_count(0)
            page.get_by_role('button',name='Results',exact=True).click()
            expect(page.locator('.evidence tbody tr').first.locator('td')).to_have_text([outcomes[w]['status'] for w in ('afterlight','baseline')])
            for title, unavailable in (('Civilian mean excess time','—'),('Civilian 95th percentile','Unavailable')):
                row = page.get_by_role('row').filter(has=page.get_by_role('rowheader',name=title,exact=True))
                expect(row.locator('td')).to_have_text([unavailable,unavailable])
            expect(page.locator('.evidence .inline-warning')).to_be_visible()
            expect(page.locator('.result-summary p')).to_have_count(0)
            workers = page.evaluate('window.__heavyQA')
            local = [w for w in workers['loads'] if w['url']==replay_url]
            assert local and all(w['expectedSha256']==expected_sha and w['decodedLimit']==256*1024*1024 and w['scenario']==expected_job['result']['scenario_id'] for w in local),workers
            assert workers['created']==workers['terminated'],workers
            assert json.loads(page.evaluate('key=>sessionStorage.getItem(key)',key))==saved
            report.setdefault('recovery',[]).append({'label':label,'worker_ready_seconds':worker_ready_seconds,'open_to_results_seconds':time.perf_counter()-started-worker_ready_seconds,
                'explicit_256MiB_local_limit':True,'exact_expected_sha_bound':True,'world_statuses_censored':True,'undefined_civilian_mean_is_dash_and_tail_unavailable':True,'no_completed_run_benefit_claim':True,
                'worker_observation':{k:workers[k] for k in ('created','terminated','posts','loads')}})
            sample(label,time.perf_counter()-started)
            page.screenshot(path=str(output/f'{label}.png'),full_page=True)

        recover('initial-heavy-recovery')
        page.get_by_role('button',name='Simulation',exact=True).click()
        entries = context.request.get(api + '/api/catalog').json()['runs']
        local_title = 'Local ' + expected_job['parameters']['policy'] + ' run'
        for index, title in enumerate([entries[0]['title'],local_title,entries[1]['title'],local_title],1):
            page.evaluate('window.__heavyQA.longTasks=[]')
            started = time.perf_counter()
            page.locator('.recording-card').filter(has_text=title).click()
            expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
            expect(page.locator('.stage-title')).to_have_text(title)
            sample('switch-' + str(index) + ('-heavy' if title==local_title else '-public'),time.perf_counter()-started)
        retained = [s['forced_gc_retained_js_heap_bytes'] for s in report['samples'] if s['label']=='initial-heavy-recovery' or s['label'].endswith('-heavy')]
        assert max(retained)-min(retained)<64*1024*1024,('Repeated heavy-recording retained heap drift exceeds64MiB',retained)
        resources = report['samples'][1:]
        for name in ('geometries','textures'):
            assert len({s['render'][name] for s in resources})==1,('Renderer resource count drift',name)
        public_posts = [p for p in page.evaluate('window.__heavyQA.posts') if p['published']]
        assert public_posts and all(p['decodedLimit']==128*1024*1024 for p in public_posts),public_posts
        report['public_128MiB_limit_preserved'] = True
        report['switching_worker_observation'] = page.evaluate('({created:window.__heavyQA.created,terminated:window.__heavyQA.terminated,posts:window.__heavyQA.posts,loads:window.__heavyQA.loads})')
        assert report['switching_worker_observation']['created']==report['switching_worker_observation']['terminated']
        recover('same-tab-heavy-reload',reload=True)
        assert not report['page_errors'] and not report['blocked_requests'],(report['page_errors'],report['blocked_requests'])
        assert all(r['method'] in {'GET','HEAD'} for r in report['requests']),report['requests']
        if manifest: report['served_build_after'] = verify_served_build(context,args.base_url,manifest)
        report['independent_GET_after'] = served_replay(replay_url,expected_bytes,expected_sha)
        assert inventory(directory)==raw_before,'Original job files changed'
        assert journal_path.read_bytes()==journal_bytes,'Original client journal changed'
        report.update(status='passed_heavy_GET_only_recovery_and_bounded_retention',browser_POST_attempts=0,
                      original_job_files_unchanged=True,original_journal_unchanged=True,
                      interpretation='Natural and forced-GC main JavaScript heap only; not total browser/GPU memory. Censored heavy traffic is an explored transport fixture, not a completed-run benchmark.')
    except Exception as error:
        report.update(status='failed',error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report['source_after']=source_identity();report['source_stable']=report['source_before']==report['source_after']
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ('status','error','browser_POST_attempts','public_128MiB_limit_preserved')},indent=2))


if __name__=='__main__': main()
