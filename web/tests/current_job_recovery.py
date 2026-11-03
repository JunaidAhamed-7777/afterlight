"""Recover one retained terminal job through the current UI using GETs only.

This deliberately records separate frontend and historical simulator identities.
It does not replace the old source-bound preview acceptance, change the original
journal, submit or retry a job, or generate traffic. A different canonical map
must leave historical traffic hidden while keeping its evidence readable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, returning_visit, source_identity


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(path: Path):
    result = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise ValueError("Redirected evidence paths are unsupported")
        if item.is_file(): result[item.relative_to(path).as_posix()] = sha(item.read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:5184/")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    acceptance, output = args.acceptance.resolve(), args.output.resolve()
    runtime = (ROOT / "local-runtime").resolve()
    if not output.is_relative_to(runtime) or output.is_relative_to(acceptance) or acceptance.is_relative_to(output):
        parser.error("Use explicitly selected retained evidence and a separate fresh local-runtime output")
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or url.username or url.password:
        parser.error("Use the current loopback viewer configured with the journal's exact API origin")
    journal_bytes = (acceptance / "journal.json").read_bytes()
    journal = json.loads(journal_bytes)
    if journal["state"] not in {"terminal_verified", "recovery_verified"}:
        parser.error("Only an already verified terminal job may be recovered")
    identifier = journal["request"]["request_id"]
    directory = acceptance / "jobs" / identifier
    before = inventory(directory)
    if before != journal["terminal_evidence"]["raw_files_sha256"]:
        parser.error("Retained job raw inventory differs from terminal evidence")
    replay_bytes = (directory / "replay.json").read_bytes()
    replay = json.loads(replay_bytes)
    expected_job = json.loads((directory / "job.json").read_bytes())
    api = journal["base_url"]
    origin = f"{url.scheme}://{url.netloc}"
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": __doc__, "status": "pending", "started_utc": datetime.now(timezone.utc).isoformat(),
              "frontend_source_before": source_identity(), "simulator_source_commit": replay["provenance"]["source_commit"],
              "job_id": identifier, "api_origin": api, "viewer_url": args.base_url,
              "journal_sha256": sha(journal_bytes), "replay_sha256": sha(replay_bytes), "replay_bytes": len(replay_bytes),
              "requests": [], "checks": [], "page_errors": []}
    playwright = browser = page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        context = browser.new_context(viewport={"width": 1440, "height": 810}, service_workers="block")
        returning_visit(context)
        responses = []
        replay_bodies = []
        page = context.new_page()
        page.add_init_script("""(() => {
          const Original=window.Worker;window.__verifiedJobWorkers=[];
          window.Worker=class extends Original {
            constructor(...args){super(...args);this.addEventListener('message',e=>{
              if(e.data?.type==='loaded')window.__verifiedJobWorkers.push({url:this.__jobUrl,expectedSha256:this.__expectedSha256,scenario:e.data.replay?.scenario?.id});
            });}
            postMessage(message,...args){this.__jobUrl=message?.url;this.__expectedSha256=message?.expectedSha256;return super.postMessage(message,...args);}
          };
        })()""")
        page.on("request", lambda r: report["requests"].append({"method": r.method, "url": r.url}))
        def observed_response(response):
            responses.append(response)
            if response.url == api + "/api/jobs/" + identifier + "/replay":
                # Read while its dedicated worker still exists; the product
                # terminates that worker immediately after successful loading.
                try: replay_bodies.append(response.body())
                except Exception as error: replay_bodies.append({"unavailable": str(error)})
        page.on("response", observed_response)
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
        page.goto(origin + "/favicon.svg", wait_until="load")
        saved = {"id": identifier, "parameters": expected_job["parameters"]}
        key = "afterlight.local-job:" + api
        page.evaluate("v => sessionStorage.setItem(v.key, JSON.stringify(v.saved))", {"key": key, "saved": saved})
        canonical = context.request.get(origin + "/assets/map/city_manifest.json").body()
        report["current_map_sha256"] = sha(canonical)
        report["recorded_map_sha256"] = replay["provenance"]["canonical_map_sha256"]
        mismatched = report["current_map_sha256"] != report["recorded_map_sha256"]
        independent = context.request.get(api + "/api/jobs/" + identifier + "/replay")
        assert independent.ok and independent.body() == replay_bytes
        for attempt in range(2):
            responses.clear()
            replay_bodies.clear()
            if attempt == 0: page.goto(args.base_url, wait_until="domcontentloaded")
            else: page.reload(wait_until="domcontentloaded")
            open_button = page.get_by_role("button", name="Open completed recording", exact=True)
            expect(open_button).to_be_visible(timeout=90000)
            expect(page.locator(".generation-status")).to_contain_text("Execution finished")
            expect(page.locator(".generation-status")).to_contain_text("seed 7")
            open_button.click()
            expect(page.locator("#timeline")).to_be_enabled(timeout=30000)
            assert float(page.locator("#timeline").get_attribute("max")) == replay["duration_s"]
            if mismatched:
                expect(page.locator(".fixture-view")).to_contain_text("another map")
                expect(page.locator(".three-host canvas")).to_have_count(0)
            else:
                expect(page.locator(".three-host canvas")).to_be_visible(timeout=30000)
                expect(page.locator(".fixture-view")).to_have_count(0)
            page.get_by_role("button", name="Results", exact=True).click()
            expect(page.locator(".evidence tbody tr").first.locator("td")).to_have_text(["completed", "completed"])
            page.screenshot(path=str(output / f"retained-job-recovery-{attempt + 1}.png"), full_page=True)
            job_gets = replay_gets = 0
            for response in responses:
                if response.url == api + "/api/jobs/" + identifier:
                    assert response.status == 200 and response.json() == expected_job
                    job_gets += 1
                elif response.url == api + "/api/jobs/" + identifier + "/replay":
                    assert response.status == 200
                    replay_gets += 1
            assert job_gets >= 1 and replay_gets >= 1, (job_gets, replay_gets)
            available = [body for body in replay_bodies if isinstance(body,bytes)]
            assert all(body == replay_bytes for body in available), "Observed worker response bytes differ"
            worker_loads = page.evaluate("window.__verifiedJobWorkers")
            matching = [w for w in worker_loads if w["url"] == api + "/api/jobs/" + identifier + "/replay"]
            if expected_job.get("replay_sha256"):
                assert matching and all(w["expectedSha256"] == sha(replay_bytes) and w["scenario"] == replay["scenario"]["id"] for w in matching), "Job checksum was not bound to the successful worker load"
            assert json.loads(page.evaluate("key => sessionStorage.getItem(key)", key)) == saved
            report["checks"].append({"pass": "initial saved job recovery" if attempt == 0 else "same-tab reload recovery",
                                     "job_gets": job_gets, "exact_replay_gets": replay_gets,
                                     "browser_response_body_capture_available": bool(available),
                                     "expected_sha_bound_to_successful_worker": bool(matching),
                                     "historical_traffic_hidden_for_different_map": mismatched})
        for request in report["requests"]:
            address = urlsplit(request["url"])
            assert request["method"] in {"GET", "HEAD"}, request
            assert f"{address.scheme}://{address.netloc}" in {origin, api}, request
        assert not report["page_errors"], report["page_errors"]
        assert inventory(directory) == before, "Original raw job files changed"
        independent = context.request.get(api + "/api/jobs/" + identifier + "/replay")
        assert independent.ok and independent.body() == replay_bytes
        assert (acceptance / "journal.json").read_bytes() == journal_bytes, "Original journal changed"
        report.update(status="passed_current_ui_retained_job_recovery", browser_post_count=0,
                      original_raw_files_unchanged=True, original_journal_unchanged=True,
                      exact_independent_server_bytes_verified_before_after=True,
                      identity_method="Observed successful worker requests bind the original job SHA. Independent GETs verify exact raw bytes before/after. Some Chrome worker response bodies are unavailable after worker termination.")
    except Exception as error:
        report.update(status="failed", error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report["frontend_source_after"] = source_identity()
        report["frontend_source_stable"] = report["frontend_source_before"] == report["frontend_source_after"]
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: report.get(k) for k in ("status", "error", "checks", "browser_post_count", "frontend_source_stable")}, indent=2))


if __name__ == "__main__": main()
