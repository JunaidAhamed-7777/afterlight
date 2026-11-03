"""Desktop first-visit tour acceptance using the actual served public recordings.

The first genuine recording GET is briefly held to test readiness gating; its
bytes are unchanged. Other cases use normal requests. This test never starts
simulation work and does not synthesize traffic, metrics, or tour targets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, source_identity, verify_served_build

KEY = "afterlight.onboarding.v1"
TITLES = [
    "Start with a recorded run", "Press play", "Jump to any moment",
    "Stay with the ambulance", "Compare the results",
]
TARGETS = [".recording-list", ".play-button", "#timeline", ".follow-controls", '.panel-nav [data-tour="results"]']


def loaded(page):
    page.wait_for_function("document.querySelector('.three-host canvas')?.dataset.renderInfo && !document.querySelector('.canvas-status') && !document.querySelector('.boot-screen')", timeout=90000)
    expect(page.locator("#timeline")).to_be_enabled(timeout=90000)


def tour_step(page, index, output, label):
    dialog = page.get_by_role("dialog", name=TITLES[index], exact=True)
    expect(dialog).to_be_visible(timeout=30000)
    expect(dialog).to_have_attribute("data-step", str(index + 1))
    expect(dialog).to_have_attribute("data-target", TARGETS[index])
    expect(dialog.locator(".onboarding-spotlight")).to_be_visible()
    expect(dialog.locator(".onboarding-card")).to_be_visible()
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    geometry = page.evaluate("""() => {
      const layer = document.querySelector('.onboarding-layer');
      const box = e => {const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
      return {viewport:[innerWidth,innerHeight],card:box(layer.querySelector('.onboarding-card')),
        target:box(document.querySelector(layer.dataset.target)),spotlight:box(layer.querySelector('.onboarding-spotlight')),
        modal:layer.matches(':modal'),focusInside:layer.contains(document.activeElement),
        document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight]};
    }""")
    card, target = geometry["card"], geometry["target"]
    assert geometry["modal"] and geometry["focusInside"], geometry
    assert card["x"] >= 8 and card["y"] >= 8 and card["right"] <= geometry["viewport"][0] - 8 and card["bottom"] <= geometry["viewport"][1] - 8, geometry
    overlap = max(0, min(card["right"], target["right"]) - max(card["x"], target["x"])) * max(0, min(card["bottom"], target["bottom"]) - max(card["y"], target["y"]))
    assert overlap == 0, ("Coachmark covers its highlighted control", geometry)
    assert geometry["document"][0] <= geometry["viewport"][0] + 1 and geometry["document"][1] <= geometry["viewport"][1] + 1, geometry
    expect(page.locator(".play-button")).to_have_attribute("aria-label", "Play recording")
    page.screenshot(path=str(output / f"{label}-step-{index + 1}.png"), full_page=True)
    return geometry


def assert_focus_contained(page):
    for key in ["Tab"] * 9 + ["Shift+Tab"] * 9:
        page.keyboard.press(key)
        assert page.evaluate("document.querySelector('.onboarding-layer').contains(document.activeElement)"), "Keyboard focus escaped the modal tour"


def persisted(page, status):
    assert page.evaluate("key => JSON.parse(localStorage.getItem(key))", KEY) == {"version": 1, "status": status}


def no_tour_after_reload(page):
    page.reload(wait_until="domcontentloaded")
    loaded(page)
    page.wait_for_timeout(500)
    expect(page.locator(".onboarding-layer")).to_have_count(0)


def reopen(page):
    page.get_by_role("button", name="Settings", exact=True).click()
    button = page.locator("[data-tour-reopen]")
    expect(button).to_be_visible()
    button.click()
    expect(page.get_by_role("dialog", name=TITLES[0], exact=True)).to_be_visible()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5182/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.username or url.password or not ((url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}) or (url.scheme == "https" and url.hostname and url.hostname.endswith(".vercel.app"))):
        parser.error("Use the local product or its HTTPS Vercel deployment")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "local-runtime").resolve()): parser.error("Use fresh local-runtime output")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status":"pending", "started_utc":datetime.now(timezone.utc).isoformat(),
              "base_url":args.base_url, "scope":"Headed desktop tour behavior using actual public recording requests; no new simulation or substituted traffic.",
              "source_before":source_identity(), "cases":[], "page_errors":[]}
    current_page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
            report["browser_version"] = browser.version
            context = browser.new_context(viewport={"width":1440,"height":810}, device_scale_factor=1)
            if args.build_manifest:
                manifest = json.loads(args.build_manifest.read_bytes())
                report["served_build_before"] = verify_served_build(context, args.base_url, manifest)
            catalog_response = context.request.get(urljoin(args.base_url, "replays/catalog.json"))
            assert catalog_response.ok
            catalog = catalog_response.json()
            entry = catalog["runs"][0]
            assert entry["id"].endswith("dt0p5"), "Expected the actual dense 0.5 s public recording"
            held = []
            pattern = "**/replays/" + entry["url"]
            context.route(pattern, lambda route: held.append(route))
            current_page = context.new_page()
            current_page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
            current_page.goto(args.base_url, wait_until="domcontentloaded")
            current_page.evaluate("document.title='AFTERLIGHT tour check — automated browser'")
            started = time.monotonic()
            while not held and time.monotonic() - started < 30: current_page.wait_for_timeout(100)
            assert held, "The genuine recording request was not held"
            expect(current_page.locator("#timeline")).to_be_disabled()
            current_page.wait_for_timeout(1000)
            expect(current_page.locator(".onboarding-layer")).to_have_count(0)
            for route in held: route.continue_()
            context.unroute(pattern)
            loaded(current_page)
            before_time = current_page.locator("#timeline").input_value()
            bounds = [tour_step(current_page, 0, output, "1440-first-visit")]
            expect(current_page.get_by_role("button", name="Back", exact=True)).to_be_disabled()
            assert_focus_contained(current_page)
            current_page.get_by_role("button", name="Next", exact=True).click()
            tour_step(current_page, 1, output, "1440-back-check")
            # A real pointer click on the visible spotlight must not start a
            # recording while the tour dialog owns interaction.
            play = current_page.locator(".play-button").bounding_box()
            current_page.mouse.click(play["x"] + play["width"] / 2, play["y"] + play["height"] / 2)
            expect(current_page.locator(".play-button")).to_have_attribute("aria-label", "Play recording")
            current_page.get_by_role("button", name="Back", exact=True).click()
            tour_step(current_page, 0, output, "1440-returned")
            for index in range(1, 5):
                current_page.get_by_role("button", name="Next", exact=True).click()
                bounds.append(tour_step(current_page, index, output, "1440-first-visit"))
            current_page.get_by_role("button", name="Done", exact=True).click()
            expect(current_page.locator(".onboarding-layer")).to_have_count(0)
            persisted(current_page, "completed")
            assert current_page.locator("#timeline").input_value() == before_time, "Tour changed recorded time"
            no_tour_after_reload(current_page)
            reopen(current_page)
            current_page.set_viewport_size({"width":1280,"height":720})
            smaller = []
            for index in range(5):
                smaller.append(tour_step(current_page, index, output, "1280-reopened"))
                if index < 4: current_page.get_by_role("button", name="Next", exact=True).click()
            current_page.keyboard.press("Escape")
            expect(current_page.locator(".onboarding-layer")).to_have_count(0)
            persisted(current_page, "skipped")
            assert current_page.evaluate("document.activeElement?.getClientRects().length > 0 && !document.activeElement.closest('.onboarding-layer')"), "Focus was not restored to a visible product control"
            no_tour_after_reload(current_page)
            report["cases"].append({"case":"first-visit-complete-and-reopen", "genuine_recording_id":entry["id"],
                                    "readiness_held_GET_only":True, "back_next_done":True, "keyboard_contained":True,
                                    "background_click_did_not_start_playback":True, "time_unchanged":True,
                                    "completion_and_escape_persisted":True, "reopen_from_settings":True,
                                    "focus_restored":True, "desktop_1440_bounds":bounds, "desktop_1280_bounds":smaller})
            if args.build_manifest: report["served_build_after"] = verify_served_build(context, args.base_url, manifest)
            context.close()

            for case in ("malformed-storage", "storage-blocked"):
                context = browser.new_context(viewport={"width":1600,"height":900}, device_scale_factor=1)
                if case == "malformed-storage":
                    context.add_init_script(f"localStorage.setItem({json.dumps(KEY)},'not-json')")
                else:
                    context.add_init_script("Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new DOMException('Storage disabled for acceptance','SecurityError')}})")
                current_page = context.new_page()
                current_page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
                current_page.goto(args.base_url, wait_until="domcontentloaded")
                loaded(current_page)
                tour_step(current_page, 0, output, case)
                current_page.get_by_role("button", name="Skip tour", exact=True).click()
                expect(current_page.locator(".onboarding-layer")).to_have_count(0)
                if case == "malformed-storage": persisted(current_page, "skipped")
                else:
                    current_page.wait_for_timeout(500)
                    expect(current_page.locator(".onboarding-layer")).to_have_count(0)
                    reopen(current_page)
                    current_page.keyboard.press("Escape")
                    expect(current_page.locator(".onboarding-layer")).to_have_count(0)
                report["cases"].append({"case":case,"opens_safely":True,"skip_exits":True,"storage_failure_does_not_block_reopen":case == "storage-blocked"})
                context.close()
            assert not report["page_errors"], report["page_errors"]
            browser.close()
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed",error=str(error))
        if current_page is not None:
            try: current_page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception: pass
        raise
    finally:
        report["source_after"] = source_identity()
        report["source_stable"] = report["source_before"] == report["source_after"]
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({k:report.get(k) for k in ("status","error","browser_version","source_stable")},indent=2))


if __name__ == "__main__": main()
