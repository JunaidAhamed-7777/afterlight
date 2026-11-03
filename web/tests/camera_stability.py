"""Headed desktop camera sweep for real city depth/material stability.

Repeated paused captures detect temporal changes; retained angle captures still
need visual review for stripes, clipping and depth fighting. This does not prove
every possible orbit or GPU configuration is artifact-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, ready, returning_visit, seek, settled, source_identity


def capture(page, output: Path, label: str, *, opaque=False):
    settled(page)
    canvas = page.locator(".three-host canvas")
    state = canvas.evaluate("c => ({camera:JSON.parse(c.dataset.cameraState),render:JSON.parse(c.dataset.renderInfo),faded:Number(c.dataset.fadedBuildings)})")
    assert 0 <= state["faded"] <= state["render"]["occluderBuildings"], state
    if opaque:
        assert state["faded"] == 0, "Explicitly opaque depth baseline faded buildings"
    first = canvas.screenshot(path=str(output / f"{label}.png"))
    page.wait_for_timeout(150)
    second = canvas.screenshot(path=str(output / f"{label}-repeat.png"))
    after = canvas.evaluate("c => ({camera:JSON.parse(c.dataset.cameraState),faded:Number(c.dataset.fadedBuildings)})")
    assert state["camera"] == after["camera"], "Paused camera changed between repeated screenshots"
    assert state["faded"] == after["faded"], "Paused reveal membership changed without camera motion"
    identical = first == second
    if not identical:
        raise AssertionError(f"Paused same-camera canvas pixels changed in {label}")
    return {"label": label, **state, "same_camera_png_identical": identical,
            "png_sha256": hashlib.sha256(first).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5182/")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--viewport", choices=("both", "1920", "2560"), default="both")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"}: parser.error("Use the loopback viewer")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "local-runtime").resolve()): parser.error("Use local-runtime output")
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": __doc__, "status": "pending", "source_before": source_identity(), "samples": [], "reveal_defaults": [], "page_errors": [], "events": [], "loads": [], "stage": "launch"}
    playwright = browser = page = None
    try:
        playwright = sync_playwright().start()
        for width, height, dpr in [(1920, 1080, 1), (2560, 1440, 1.5)]:
            if args.viewport != "both" and str(width) != args.viewport: continue
            # Release the entire test-owned browser between viewport cohorts.
            browser = playwright.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
            browser.on("disconnected", lambda: report["events"].append({"event": "browser_disconnected", "stage": report["stage"]}))
            prefix = f"{width}x{height}-dpr{dpr:g}"
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=dpr)
            returning_visit(context)
            page = context.new_page(); page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
            page.on("crash", lambda: report["events"].append({"event": "page_crashed", "stage": report["stage"]}))
            page.add_init_script("window.__loadLongTasks=[];new PerformanceObserver(l=>window.__loadLongTasks.push(...l.getEntries().map(e=>({start:e.startTime,duration:e.duration})))).observe({type:'longtask',buffered:true});")
            report["stage"] = prefix + "-loading"
            started = time.perf_counter()
            page.goto(args.base_url, wait_until="domcontentloaded"); ready(page)
            expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
            cdp = context.new_cdp_session(page); cdp.send("Performance.enable")
            metrics = {v["name"]: v["value"] for v in cdp.send("Performance.getMetrics")["metrics"]}
            gpu = browser.new_browser_cdp_session().send("SystemInfo.getInfo")["gpu"]
            report["loads"].append({"viewport": [width, height], "dpr": dpr, "ready_seconds": time.perf_counter()-started,
                "js_heap_used_bytes": metrics.get("JSHeapUsedSize"), "js_heap_total_bytes": metrics.get("JSHeapTotalSize"),
                "long_tasks": page.evaluate("window.__loadLongTasks"), "gpu_devices": gpu.get("devices"),
                "gl_renderer": gpu.get("auxAttributes", {}).get("glRenderer")})
            report["stage"] = prefix + "-capture"
            seek(page, 182)
            reveal = page.get_by_label("Reveal streets behind foreground buildings", exact=True)
            expect(reveal).to_be_checked()
            expect(reveal).to_be_enabled()
            default = capture(page, output, prefix + "-default-reveal")
            assert default["camera"]["mode"] == "perspective", default
            report["samples"].append(default)
            page.get_by_role("button", name="Full city", exact=True).click()
            page.wait_for_function("document.querySelector('.three-host canvas').dataset.cameraPresentation === 'orthographic' && Number(document.querySelector('.three-host canvas').dataset.fadedBuildings)===0")
            # Keep the seven-angle depth regression explicitly opaque. The
            # separate default/reload samples above and below accept intentional
            # foreground fading and require identical paused repeat pixels.
            options = page.locator(".camera-console details")
            if options.get_attribute("open") is None: options.locator("summary").click()
            reveal.uncheck()
            expect(reveal).not_to_be_checked()
            options.locator("summary").click()
            report["samples"].append(capture(page, output, prefix + "-overview", opaque=True))
            page.get_by_role("button", name=re.compile(r"^Explore(?: 2\.5×)?$")).click()
            report["samples"].append(capture(page, output, prefix + "-explore", opaque=True))
            follow = page.locator(".follow-ambulance")
            if follow.get_attribute("aria-pressed") != "true": follow.click()
            expect(follow).to_have_attribute("aria-pressed", "true")
            page.wait_for_function("Number(document.querySelector('.three-host canvas').dataset.cameraZoom)>=11.9")
            # Paused camera is already translated exactly by Follow. Disable the
            # optional following blend before testing physical orbit stability.
            if follow.get_attribute("aria-pressed") == "true": follow.click()
            report["samples"].append(capture(page, output, prefix + "-near", opaque=True))
            canvas = page.locator(".three-host canvas"); canvas.focus()
            for name, key, repetitions in [("yaw", "y", 6), ("tilt-up", "x", 3), ("tilt-down", "Shift+X", 5), ("reverse-yaw", "Shift+Y", 10)]:
                for _ in range(repetitions): canvas.press(key)
                report["samples"].append(capture(page, output, prefix + "-" + name, opaque=True))
            page.screenshot(path=str(output / f"{prefix}-workspace.png"), full_page=True)
            page.reload(wait_until="domcontentloaded"); ready(page)
            expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
            seek(page, 182)
            expect(reveal).to_be_checked()
            report["samples"].append(capture(page, output, prefix + "-reload-default-reveal"))
            report["reveal_defaults"].append({"viewport": [width, height], "initial_checked": True,
                "opt_out_not_persisted_after_reload": True, "overview_stays_opaque_with_reveal_enabled": True})
            report["stage"] = prefix + "-closing"
            context.close(); browser.close(); browser = None
        assert not report["page_errors"], report["page_errors"]
        report["status"] = "passed_paused_camera_stability_pending_pixel_review"
    except Exception as error:
        report.update(status="failed", error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report["source_after"] = source_identity()
        report["source_stable"] = report["source_before"] == report["source_after"]
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: report.get(k) for k in ("status", "error", "source_stable")}, indent=2))


if __name__ == "__main__": main()
