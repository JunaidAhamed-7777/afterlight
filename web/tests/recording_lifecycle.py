"""Desktop boot and worker cancellation checks with genuine retained recordings.

Only an isolated browser's GET responses are held or replaced. Catalog entries
point at exact supplied genuine bytes; no traffic, metrics or source evidence
is synthesized or published. No simulator job or POST is permitted.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, digest, ready, returning_visit, source_identity, verify_served_build


def real_entry(raw: bytes, name: str):
    replay = json.loads(raw); scenario = replay["scenario"]; world = replay["worlds"]["afterlight"]
    entry = {"id": scenario["id"], "title": name, "url": "retained-genuine.json", "seed": scenario["seed"],
             "pickup_id": scenario["pickup_id"], "hospital_id": scenario["hospital_id"], "policy": world["policy"],
             "lead_s": world.get("lead_s"), "duration_s": replay["duration_s"], "sha256": digest(raw), "bytes": len(raw)}
    return entry, replay


def boot_case(browser, base_url, raw: bytes, name: str, output: Path):
    entry, replay = real_entry(raw, name)
    context = browser.new_context(viewport={"width": 1440, "height": 810})
    returning_visit(context)
    held = []; errors = []
    context.route("**/replays/catalog.json", lambda route: route.fulfill(content_type="application/json", body=json.dumps({"schema":"afterlight.catalog.v1","runs":[entry]})))
    context.route("**/replays/retained-genuine.json", lambda route: route.fulfill(content_type="application/json", body=raw))
    # The evidence-only view must open even if the original city load has not
    # completed. The retained request is aborted on closing this test context.
    context.route("**/assets/exports/city_enhanced.glb", lambda route: held.append(route))
    page = context.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base_url, wait_until="domcontentloaded")
    expect(page.locator(".fixture-view")).to_be_visible(timeout=60000)
    expect(page.locator(".boot-screen")).to_have_count(0)
    expect(page.locator("#timeline")).to_be_enabled()
    assert held, "City load was not held; evidence-only boot boundary not exercised"
    assert float(page.locator("#timeline").get_attribute("max")) == replay["duration_s"]
    page.get_by_role("button", name="Results", exact=True).click()
    expect(page.locator(".evidence tbody tr").first.locator("td")).to_have_text([replay["worlds"][w]["status"] for w in ("afterlight", "baseline")])
    page.screenshot(path=str(output/f"initial-{name}.png"), full_page=True)
    assert not errors, errors
    for route in held:
        try: route.abort()
        except Exception: pass
    page.wait_for_timeout(50)
    context.unroute_all(behavior="ignoreErrors")
    context.close()
    return {"case": name, "genuine_replay_sha256": digest(raw), "bytes": len(raw), "city_glb_deliberately_held": True,
            "boot_unblocked": True, "timeline_and_actual_results_accessible": True}


def cancellation_case(browser, base_url, entry, output):
    context = browser.new_context(viewport={"width": 1440, "height": 810})
    returning_visit(context)
    held = []; errors = []
    pattern = "**/replays/" + entry["url"]
    context.route(pattern, lambda route: held.append(route))
    page = context.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("""(() => {
      const Original=window.Worker;window.__workerLifecycle={created:0,terminated:0,messages:0};
      window.Worker=class extends Original {
        constructor(...args){super(...args);window.__workerLifecycle.created++;this.addEventListener('message',()=>window.__workerLifecycle.messages++);}
        terminate(){window.__workerLifecycle.terminated++;return super.terminate();}
      };
    })()""")
    page.goto(base_url, wait_until="domcontentloaded"); ready(page)
    cancel = page.get_by_role("button", name="Cancel", exact=True)
    expect(cancel).to_be_visible(timeout=30000)
    assert held, "A real recording worker request was not held"
    cancel.click()
    page.wait_for_function("window.__workerLifecycle.terminated>=1")
    expect(page.locator("#timeline")).to_be_disabled()
    canceled = page.evaluate("window.__workerLifecycle")
    assert canceled["created"] == canceled["terminated"] == 1 and canceled["messages"] == 0, canceled
    context.unroute(pattern)
    # Terminated worker fetches are already canceled. Explicitly finish any
    # still-held test routes before opening a fresh genuine request.
    for route in held:
        try: route.abort()
        except Exception: pass
    page.locator(".recording-card").filter(has_text=entry["title"]).click()
    expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
    page.wait_for_function("window.__workerLifecycle.terminated>=2")
    loaded = page.evaluate("window.__workerLifecycle")
    assert loaded == {"created": 2, "terminated": 2, "messages": 1}, loaded
    expect(page.locator(".stage-notice.error")).to_have_count(0)
    expect(page.locator(".stage-title")).to_contain_text(entry["title"])
    page.screenshot(path=str(output/"worker-canceled-then-genuine-reloaded.png"), full_page=True)
    assert not errors, errors
    context.unroute_all(behavior="ignoreErrors")
    context.close()
    return {"canceled": canceled, "loaded": loaded, "no_stale_replay_or_error": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5186/")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--historical-city", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-manifest", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/"local-runtime").resolve()): parser.error("Use fresh local-runtime output")
    output.mkdir(parents=True, exist_ok=False)
    with urlopen(urljoin(args.base_url,"replays/catalog.json")) as response: entry = json.load(response)["runs"][0]
    report = {"scope": __doc__, "status": "pending", "source_before": source_identity(), "checks": []}
    playwright = browser = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:
            report["served_production_build"] = manifest
            context = browser.new_context(); report["served_build_before"] = verify_served_build(context,args.base_url,manifest); context.close()
        for path, name in [(args.fixture,"fixture"),(args.historical_city,"historical-map")]:
            raw = path.read_bytes()
            report["checks"].append(boot_case(browser,args.base_url,raw,name,output))
            del raw; gc.collect()
        report["checks"].append(cancellation_case(browser,args.base_url,entry,output))
        if manifest:
            context = browser.new_context(); report["served_build_after"] = verify_served_build(context,args.base_url,manifest); context.close()
        report["status"] = "passed_genuine_evidence_only_boot_and_worker_cancel"
    except Exception as error:
        report.update(status="failed",error=str(error)); raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report["source_after"] = source_identity(); report["source_stable"] = report["source_before"] == report["source_after"]
        (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({k:report.get(k) for k in ("status","error","checks","source_stable")},indent=2))


if __name__ == "__main__": main()
