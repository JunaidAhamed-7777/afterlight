"""Omen-only UI protocol fixture: NO simulator and NO traffic traces are used.

Use a viewer built/started with VITE_API_BASE=http://127.0.0.1:8765.
All /api calls are intercepted inside a fresh browser context. The test models
an interrupted POST response and an explicit idempotent retry. It never claims
simulation success, never publishes recordings, and never contacts a real runner.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from browser_camera_checks import assert_overview_fits, assert_favicon_served, assert_camera_exploration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path("local-runtime/generation-ui-protocol"))
    parser.add_argument("--channel", choices=("chrome", "msedge"), default="chrome")
    parser.add_argument("--include-mobile", action="store_true", help="Optional legacy responsive checks; desktop is the acceptance target")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only the loopback AFTERLIGHT viewer is permitted")
    args.output.mkdir(parents=True, exist_ok=True)
    requests: list[dict] = []
    status_reads: list[str] = []
    hold_recovery = {"enabled": False}
    held_routes = []
    report = {"scope": "SYNTHETIC UI PROTOCOL TEST ONLY; no SUMO execution, traffic trace, or outcome measurement", "requests": requests, "status_reads": status_reads, "headless": args.headless}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=args.channel, headless=args.headless, chromium_sandbox=True,
            ignore_default_args=[
                "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                "--enable-unsafe-swiftshader", "--unsafely-disable-devtools-self-xss-warnings",
                "--disable-ipc-flooding-protection", "--disable-client-side-phishing-detection",
            ],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        def respond(route, status: int, value: dict) -> None:
            route.fulfill(status=status, content_type="application/json", body="" if status == 204 else json.dumps(value),
                          headers={"Access-Control-Allow-Origin": f"{parsed.scheme}://{parsed.netloc}", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"})

        def api(route) -> None:
            request = route.request
            path = urlsplit(request.url).path
            if request.method == "OPTIONS":
                respond(route, 204, {})
            elif path == "/api/health":
                respond(route, 200, {"status": "ready", "generation_available": True})
            elif path == "/api/catalog":
                respond(route, 200, {"schema": "afterlight.catalog.v1", "runs": []})
            elif path == "/api/runs" and request.method == "POST":
                body = request.post_data_json
                requests.append(body)
                if len(requests) == 1:
                    route.abort("failed")  # A response loss, not a fake simulation outcome.
                else:
                    respond(route, 202, {"id": body["request_id"], "status": "queued", "parameters": {k: v for k, v in body.items() if k != "request_id"}})
            elif path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                status_reads.append(job_id)
                if hold_recovery["enabled"]:
                    held_routes.append(route)
                    return
                if len(requests) < 2:
                    respond(route, 404, {"error": "Synthetic fixture: request not received"})
                else:
                    body = requests[0]
                    respond(route, 200, {"id": job_id, "status": "failed", "parameters": {k: v for k, v in body.items() if k != "request_id"},
                                        "error": "Synthetic UI protocol failure fixture — no simulator ran", "message": "Synthetic protocol fixture"})
            else:
                respond(route, 404, {"error": "Synthetic fixture has no such endpoint"})

        page.route("**/api/**", api)
        try:
            page.goto(args.base_url, wait_until="networkidle")
            expect(page.get_by_role("heading", name="Run a local experiment")).to_be_visible(timeout=15000)
            expect(page.get_by_role("button", name="Generate paired run", exact=True)).to_be_enabled()
            page.get_by_role("button", name="Generate paired run", exact=True).click()
            retry = page.get_by_role("button", name="Retry exact saved request", exact=True)
            expect(retry).to_be_visible(timeout=15000)
            assert len(requests) == 1, "An interrupted POST must not be automatically submitted again"
            original = requests[0]
            assert len(original["request_id"]) == 32
            assert original["request_id"] in status_reads, "Read-only recovery must use the known ID"
            stored = page.evaluate("Object.values(sessionStorage).find(value=>value.includes('request_id')||value.includes('parameters'))")
            assert stored and original["request_id"] in stored, "Request identity/settings must be saved before retry"
            # Route controls outside the disabled generation form may change; retry must not.
            page.get_by_label("Pickup point", exact=True).select_option("P002")
            page.get_by_label("Destination hospital", exact=True).select_option("HOSP_EAST")
            retry.click()
            expect(page.locator(".generation-status")).to_contain_text("Execution failed", timeout=15000)
            assert len(requests) == 2 and requests[0] == requests[1], "Retry must retain exact ID and original settings"
            expect(page.locator(".generation-status")).to_contain_text("no simulator ran")
            expect(page.get_by_role("heading", name="No outcome claims yet")).to_be_visible()
            expect(page.get_by_role("button", name="Open completed recording")).to_have_count(0)
            report["local_generation_city_fit"] = assert_overview_fits(page)
            report["favicon"] = assert_favicon_served(page)
            report["camera_exploration"] = assert_camera_exploration(page)
            page.set_viewport_size({"width": 760, "height": 1200})
            report["tall_generation_city_fit"] = assert_overview_fits(page)
            if args.include_mobile:
                page.set_viewport_size({"width": 390, "height": 844})
                report["optional_mobile_generation_city_fit"] = assert_overview_fits(page)
            page.set_viewport_size({"width": 1440, "height": 1000})
            assert_overview_fits(page)
            page.screenshot(path=str(args.output / "synthetic-protocol-only.png"), full_page=True)
            # Reload with a persisted job and deliberately hold its GET response.
            hold_recovery["enabled"] = True
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Run a local experiment")).to_be_visible()
            deadline = time.monotonic() + 5
            while not held_routes and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert held_routes, "Saved-job recovery GET was not observed"
            expect(page.get_by_role("button", name="Generate paired run", exact=True)).to_be_disabled()
            assert len(requests) == 2, "Recovery must not create a new job"
            page.screenshot(path=str(args.output / "recovery-locked-synthetic-protocol-only.png"), full_page=True)
            hold_recovery["enabled"] = False
            original_body = requests[0]
            respond(held_routes.pop(), 200, {"id": original_body["request_id"], "status": "failed", "parameters": {k:v for k,v in original_body.items() if k!="request_id"}, "error": "Synthetic failed history; no simulator ran"})
            expect(page.get_by_role("button", name="Generate paired run", exact=True)).to_be_enabled()
            report["saved_job_recovery_locked_new_submissions"] = True
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["failure"] = str(exc)
            page.screenshot(path=str(args.output / "failure-synthetic-protocol-only.png"), full_page=True)
            raise
        finally:
            (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            context.close()
            browser.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
