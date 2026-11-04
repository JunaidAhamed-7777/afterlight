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
from browser_camera_checks import assert_overview_fits, assert_favicon_served, assert_camera_exploration
from browser_map_selection_checks import assert_map_selection, assert_replay_map_lock
from desktop_product_acceptance import ready, returning_visit, switch_section


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path("local-runtime/browser-smoke"))
    parser.add_argument("--catalog-path", choices=("/replays/catalog.json", "/api/catalog"), default="/replays/catalog.json")
    parser.add_argument("--include-mobile", action="store_true", help="Optional legacy responsive checks; desktop is the acceptance target")
    parser.add_argument("--headless", action="store_true", help="Supplementary headless capture; headed GPU QA is the default")
    parser.add_argument("--channel", choices=("chrome", "msedge"), default="chrome")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("This script is restricted to the local AFTERLIGHT viewer")
    args.output.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    errors: list[str] = []
    report = {"scope": "Local browser smoke; not SUMO validity, complete accessibility audit, or performance benchmark", "platform": platform.platform(), "channel": args.channel, "headless": args.headless, "checks": checks, "page_errors": errors}

    def passed(name: str, detail: object = None) -> None:
        checks.append({"name": name, "passed": True, "detail": detail})

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=args.channel, headless=args.headless, chromium_sandbox=True,
            ignore_default_args=[
                "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                "--enable-unsafe-swiftshader", "--unsafely-disable-devtools-self-xss-warnings",
                "--disable-ipc-flooding-protection", "--disable-client-side-phishing-detection",
            ],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        returning_visit(context)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(args.base_url, wait_until="networkidle")
            expect(page.get_by_role("link", name="AFTERLIGHT home", exact=True)).to_be_visible()
            ready(page)
            switch_section(page, "Run")
            disclosure = page.locator('.route-control')
            if disclosure.get_attribute('open') is None: disclosure.locator('summary').click()
            leave = page.get_by_role('button', name='Leave recording & explore', exact=True)
            if leave.count(): leave.click()
            expect(page.locator('#pickup-search')).to_have_count(0)
            expect(page.get_by_role('button', name='Play selected journey', exact=True)).to_be_enabled()
            page.wait_for_selector(".three-host canvas", timeout=30000)
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            expect(page.locator(".city-fallback")).to_have_count(0)
            passed("original_city_glb_drawn_without_fallback")
            passed("desktop_original_city_fits", assert_overview_fits(page))
            passed("original_favicon_served", assert_favicon_served(page))
            passed("perspective_camera_xyz_and_keyboard", assert_camera_exploration(page))
            passed("canonical_map_pick_click_drag_cancel", assert_map_selection(page))
            canvas = page.locator(".three-host canvas")
            canvas.focus()
            original_zoom = float(canvas.get_attribute("data-camera-zoom"))
            canvas.press("Shift+Equal")
            page.wait_for_function("value => Number(document.querySelector('.three-host canvas').dataset.cameraZoom)>value", arg=original_zoom)
            previous_target = canvas.get_attribute("data-camera-target")
            canvas.press("ArrowRight")
            page.wait_for_function("value => document.querySelector('.three-host canvas').dataset.cameraTarget!==value", arg=previous_target)
            canvas.press("0")
            passed("scoped_keyboard_camera_zoom_pan_and_reset")

            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Desktop horizontal overflow"
            passed("desktop_no_horizontal_overflow")
            expect(page.locator('#pickup-search')).to_have_count(0)
            expect(page.get_by_label("Pickup point", exact=True).locator("option[value=P050]")).to_have_count(1)
            page.get_by_label("Pickup point", exact=True).select_option("P050")
            page.get_by_label("Destination hospital", exact=True).select_option("HOSP_EAST")
            expect(page.locator(".map-location")).to_contain_text("P050")
            expect(page.locator(".map-location")).to_contain_text("Eastbank General")
            passed("canonical_pickup_dropdown_and_hospital_selection")
            page.get_by_role("button", name="Reset camera to city overview").click()
            page.screenshot(path=str(args.output / "desktop.png"), full_page=True)

            # This error injection changes only a GET response in this ephemeral test context.
            catalog_pattern = "**" + args.catalog_path
            page.route(catalog_pattern, lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"smoke injected outage"}'))
            page.reload(wait_until="networkidle")
            workspace = page.get_by_role('button', name='Open workspace', exact=True)
            if workspace.count(): workspace.click()
            expect(page.get_by_role("button", name="Retry catalog")).to_be_visible()
            page.unroute(catalog_pattern)
            page.get_by_role("button", name="Retry catalog").click()
            expect(page.get_by_role("button", name="Retry catalog")).to_have_count(0)
            passed("catalog_failure_and_retry")

            # A real recording, if catalogued, is inspected; no synthetic trace is injected.
            all_recordings = page.locator(".recording-list button")
            if all_recordings.count():
                all_recordings.first.click()
                expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
                assert_replay_map_lock(page)
                passed("recording_blocks_map_route_changes")
                expect(page.get_by_label("Simulation time", exact=True)).to_be_enabled()
                timeline = page.get_by_label("Simulation time", exact=True)
                timeline.focus()
                timeline.press("End")
                maximum = float(timeline.get_attribute("max"))
                expect(page.locator(".timeline-label output")).to_contain_text(f"{maximum:.1f}")
                timeline.press("Home")
                timeline.press("ArrowRight")
                expect(page.locator(".timeline-label output")).to_contain_text("0.1")
                city_recording = page.locator(".fixture-view").count() == 0
                baseline_button = page.get_by_role("button", name="Ordinary", exact=True)
                baseline_button.click()
                expect(baseline_button).to_have_attribute("aria-pressed", "true")
                if city_recording:
                    expect(page.locator(".legend")).to_contain_text("Ordinary ambulance")
                else:
                    expect(page.locator(".fixture-view")).to_be_visible()
                    expect(page.locator(".legend")).to_have_count(0)
                page.get_by_role("button", name="Afterlight", exact=True).click()
                if city_recording:
                    expect(page.locator(".legend")).to_contain_text("Baseline ghost")
                page.screenshot(path=str(args.output / "recording.png"), full_page=True)
                passed("real_catalogued_recording_shared_seek_and_world_labels")
                # Return to asset inspection for the renderer context-loss check.
                page.get_by_role('button', name='Leave recording & explore', exact=True).click()
            else:
                expect(page.get_by_role("button", name="Play selected journey", exact=True)).to_be_enabled()
                expect(page.locator('#timeline')).to_be_disabled()
                expect(page.locator(".legend")).to_have_count(0)
                switch_section(page, 'Results')
                expect(page.get_by_role("heading", name="Results follow a run.", exact=True)).to_be_visible()
                switch_section(page, 'Run')
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
            # Inject a renderer exception in this ephemeral page, never in a simulator.
            page.evaluate("""() => {
                const prototype=WebGL2RenderingContext.prototype;
                window.__qaOriginalDraws={};
                for(const name of ['drawElements','drawArrays','drawElementsInstanced','drawArraysInstanced']){
                    window.__qaOriginalDraws[name]=prototype[name];
                    prototype[name]=function(){throw new Error('Injected UI QA rendering failure; no simulation failure implied');};
                }
            }""")
            page.get_by_role("button", name="Reset camera to city overview").click()
            expect(page.locator(".canvas-status")).to_contain_text("rendering error")
            expect(page.locator(".city-fallback")).to_be_visible()
            page.evaluate("""() => {for(const [name,method] of Object.entries(window.__qaOriginalDraws))WebGL2RenderingContext.prototype[name]=method;delete window.__qaOriginalDraws;}""")
            page.get_by_role("button", name="Retry 3D city").click()
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            passed("animation_frame_exception_preserves_evidence_and_retries")


            if args.include_mobile:
                page.set_viewport_size({"width": 390, "height": 844})
            page.emulate_media(reduced_motion="reduce")
            switch_section(page, 'Settings')
            expect(page.get_by_label("Reduced motion", exact=True)).to_be_checked()
            expect(page.locator('.follow-ambulance')).to_be_disabled()
            page.evaluate("scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Horizontal overflow"
            if args.include_mobile:
                assert page.locator(".stage").bounding_box()["y"] < 240, "Mobile city is buried below settings"
                passed("optional_mobile_original_city_fits", assert_overview_fits(page))
                page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
                passed("optional_mobile_city_first_no_overflow_reduced_motion")
            else:
                passed("desktop_reduced_motion_no_overflow")
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.tagName")
            # The map is intentionally focusable for non-pointer camera access.
            # Reset → Tab may enter it; the next Tab must leave, not trap focus.
            if focused == "CANVAS":
                assert page.evaluate("document.activeElement.matches('.three-host canvas[tabindex=\"0\"]')")
                page.keyboard.press("Tab")
                focused = page.evaluate("document.activeElement.tagName")
            assert focused in {"A", "BUTTON", "INPUT", "SELECT", "SUMMARY"}, focused
            passed("keyboard_focus_leaves_camera_for_interactive_html", focused)
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
