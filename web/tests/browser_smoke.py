"""Reproducible Omen-only browser checks; never a traffic benchmark.

Requires a running local viewer and already-installed Python Playwright + Chrome.
No browser download, profile reuse, sandbox-disabling flag, or external site is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path("local-runtime/browser-smoke"))
    parser.add_argument("--catalog-path", choices=("/replays/catalog.json", "/api/catalog"), default="/replays/catalog.json")
    parser.add_argument("--channel", choices=("chrome", "msedge"), default="chrome")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This script is restricted to the local AFTERLIGHT viewer")
    args.output.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    errors: list[str] = []
    report = {"scope": "Local browser smoke; not SUMO validity, complete accessibility audit, or performance benchmark", "platform": platform.platform(), "channel": args.channel, "checks": checks, "page_errors": errors}

    def passed(name: str, detail: object = None) -> None:
        checks.append({"name": name, "passed": True, "detail": detail})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(args.base_url, wait_until="networkidle")
            expect(page.get_by_role("heading", name=re.compile(r"One city.*Two futures", re.S))).to_be_visible()
            page.wait_for_selector(".three-host canvas", timeout=30000)
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            expect(page.locator(".city-fallback")).to_have_count(0)
            passed("original_city_glb_drawn_without_fallback")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Desktop horizontal overflow"
            passed("desktop_no_horizontal_overflow")
            page.get_by_label("Find a pickup", exact=True).fill("P050")
            expect(page.get_by_label("Pickup point", exact=True).locator("option[value=P050]")).to_have_count(1)
            page.get_by_label("Pickup point", exact=True).select_option("P050")
            page.get_by_label("Destination hospital", exact=True).select_option("HOSP_EAST")
            expect(page.locator(".map-location")).to_contain_text("P050")
            expect(page.locator(".map-location")).to_contain_text("Eastbank General")
            passed("canonical_pickup_search_and_hospital_selection")
            page.get_by_label("Find a pickup", exact=True).fill("")
            page.get_by_role("button", name="Reset camera to city overview").click()
            page.screenshot(path=str(args.output / "desktop.png"), full_page=True)

            # This error injection changes only a GET response in this ephemeral test context.
            catalog_pattern = "**" + args.catalog_path
            page.route(catalog_pattern, lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"smoke injected outage"}'))
            page.reload(wait_until="networkidle")
            expect(page.get_by_role("button", name="Retry catalog")).to_be_visible()
            page.unroute(catalog_pattern)
            page.get_by_role("button", name="Retry catalog").click()
            expect(page.get_by_role("button", name="Retry catalog")).to_have_count(0)
            passed("catalog_failure_and_retry")

            # A real recording, if catalogued, is inspected; no synthetic trace is injected.
            all_recordings = page.locator(".recording-list button")
            if all_recordings.count():
                page.get_by_text("All available recordings", exact=False).click()
                all_recordings.first.click()
                expect(page.locator(".mode-label")).to_contain_text("Recorded simulation", timeout=30000)
                expect(page.get_by_label("Absolute simulation time", exact=True)).to_be_enabled()
                timeline = page.get_by_label("Absolute simulation time", exact=True)
                timeline.focus()
                timeline.press("End")
                maximum = float(timeline.get_attribute("max"))
                expect(page.locator(".timeline-label output")).to_contain_text(f"{maximum:.1f}")
                timeline.press("Home")
                timeline.press("ArrowRight")
                expect(page.locator(".timeline-label output")).to_contain_text("0.1")
                page.get_by_role("button", name="Baseline", exact=True).click()
                expect(page.locator(".legend")).to_contain_text("Solid: ordinary baseline world")
                page.get_by_role("button", name="Afterlight", exact=True).click()
                expect(page.locator(".legend")).to_contain_text("Ghost: baseline, separate traffic world")
                page.screenshot(path=str(args.output / "recording.png"), full_page=True)
                passed("real_catalogued_recording_shared_seek_and_world_labels")
                # Return to asset inspection for the renderer context-loss check.
                page.get_by_label("Recorded experiment", exact=True).select_option("")
            else:
                expect(page.get_by_role("button", name="Play recording", exact=True)).to_be_disabled()
                expect(page.get_by_role("heading", name="No outcome claims yet")).to_be_visible()
                passed("empty_library_has_no_fake_playback_or_outcomes")

            page.wait_for_selector(".three-host canvas", timeout=30000)
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            supported = page.evaluate("""() => {
                const canvas=document.querySelector('.three-host canvas');
                const gl=canvas.getContext('webgl2');
                const extension=gl?.getExtension('WEBGL_lose_context');
                if(!extension) return false;
                extension.loseContext(); return true;
            }""")
            assert supported, "WEBGL_lose_context unavailable; context recovery not tested"
            expect(page.get_by_role("button", name="Retry 3D city")).to_be_visible()
            expect(page.locator(".city-fallback")).to_be_visible()
            page.get_by_role("button", name="Retry 3D city").click()
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            expect(page.locator(".city-fallback")).to_have_count(0)
            passed("webgl_context_loss_keeps_preview_and_recovers")

            page.set_viewport_size({"width": 390, "height": 844})
            page.emulate_media(reduced_motion="reduce")
            expect(page.get_by_label("Reduced motion", exact=True)).to_be_checked()
            expect(page.get_by_label("Follow ambulance", exact=True)).to_be_disabled()
            page.evaluate("scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
            assert page.locator(".stage").bounding_box()["y"] < 200, "Mobile city is buried below settings"
            page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
            passed("mobile_city_first_no_overflow_reduced_motion")
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.tagName")
            assert focused in {"A", "BUTTON", "INPUT", "SELECT", "SUMMARY"}, focused
            passed("keyboard_focus_enters_interactive_html", focused)
            assert not errors, errors
            passed("no_uncaught_browser_errors")
            report["status"] = "passed"
        except Exception as exc:
            report["status"] = "failed"
            report["failure"] = str(exc)
            page.screenshot(path=str(args.output / "failure.png"), full_page=True)
            raise
        finally:
            report["completed_at_unix"] = time.time()
            report["user_agent"] = page.evaluate("navigator.userAgent")
            (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            context.close()
            browser.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
