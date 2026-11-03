"""Headed desktop product checks and measured browser rendering observations.

Uses the served product and its genuine public recording catalog. It never
generates traffic, changes recordings, substitutes a trace, or downloads a
browser. Error-path requests are intercepted only in a separate UI test page.
RAF intervals describe browser presentation cadence, not GPU execution time.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import gzip
import io
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import time
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright
from real_replay_smoke import check_layer, inspect, sample_times, sampled_vehicles
from browser_map_selection_checks import marker_on_canvas

ROOT = Path(__file__).resolve().parents[2]
CANVAS = ".three-host canvas"
UNSAFE_DEFAULTS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
    "--enable-unsafe-swiftshader", "--unsafely-disable-devtools-self-xss-warnings",
    "--disable-ipc-flooding-protection", "--disable-client-side-phishing-detection",
]

# Installed in an isolated QA page, never in the product source. The callback
# timer includes JavaScript work and draw submission, not completed GPU work.
INSTRUMENT = """(() => {
  const qa = window.__desktopQA = {samples: [], longTasks: [], readyMs: null,
    enabled: false, active: null, drawCount: 0, lifecycle: []};
  const state = kind => ({kind,timestamp:performance.now(),visibility:document.visibilityState,focused:document.hasFocus()});
  qa.state = state;
  for (const kind of ['focus','blur']) window.addEventListener(kind,()=>{if(qa.enabled)qa.lifecycle.push(state(kind));});
  document.addEventListener('visibilitychange',()=>{if(qa.enabled)qa.lifecycle.push(state('visibilitychange'));});
  const originalRaf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = callback => originalRaf(timestamp => {
    const start = performance.now(), before = qa.drawCount;
    try { callback(timestamp); }
    finally {
      const calls = qa.drawCount - before;
      if (qa.enabled && calls > 0)
        qa.samples.push({timestamp, callbackMs: performance.now() - start, calls});
    }
  });
  for (const Constructor of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!Constructor) continue;
    for (const name of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
      const original = Constructor.prototype[name];
      if (!original) continue;
      Constructor.prototype[name] = function(...args) { qa.drawCount++; return original.apply(this, args); };
    }
  }
  try { new PerformanceObserver(list => {
    if (qa.enabled) qa.longTasks.push(...list.getEntries().map(e => ({startMs:e.startTime,durationMs:e.duration})));
  }).observe({type:'longtask',buffered:false}); } catch {}
  const observer = new MutationObserver(() => {
    if (qa.readyMs === null && document.querySelector('.three-host canvas')?.dataset.renderInfo &&
        !document.querySelector('.canvas-status') && !document.querySelector('.boot-screen')) {
      qa.readyMs = performance.now();
    }
  });
  observer.observe(document,{subtree:true,childList:true,attributes:true});
})()"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decoded_recording(data: bytes) -> bytes:
    # Catalog checksums and byte counts always bind original JSON bytes. A .gz
    # file is a lossless transport container; HTTP may already have decoded it.
    limit = 128 * 1024 * 1024
    if data[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            decoded = stream.read(limit + 1)
    else:
        decoded = data
    if len(decoded) > limit: raise ValueError("Decoded recording exceeds 128 MiB")
    return decoded


def source_identity() -> dict:
    files = sorted((ROOT / "web/src").rglob("*"))
    files += [ROOT / "web/package.json", ROOT / "web/package-lock.json", ROOT / "assets/map/city_manifest.json"]
    files += [ROOT / "web/index.html", ROOT / "web/scripts/prepare-assets.mjs", ROOT / "web/public/favicon.svg"]
    files += sorted((ROOT / "assets/exports").glob("*"))
    hashes = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in files if p.is_file()}
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    return {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": digest(encoded), "files": hashes}


def percentile(values: list[float], fraction: float) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(samples: list[dict], long_tasks: list[dict]) -> dict:
    intervals = [b["timestamp"] - a["timestamp"] for a, b in zip(samples, samples[1:])]
    callbacks = [s["callbackMs"] for s in samples]
    seconds = (samples[-1]["timestamp"] - samples[0]["timestamp"]) / 1000 if len(samples) > 1 else 0
    return {"rendered_frames": len(samples), "observed_seconds": seconds,
            "rendered_fps": (len(samples) - 1) / seconds if seconds > 0 else None,
            "render_interval_ms": {"median": percentile(intervals, .5), "p95": percentile(intervals, .95), "maximum": max(intervals, default=None)},
            "drawing_callback_cpu_ms": {"median": percentile(callbacks, .5), "p95": percentile(callbacks, .95), "maximum": max(callbacks, default=None)},
            "long_tasks": long_tasks,
            "interpretation": "Headed Chrome render cadence and JavaScript/draw-submission callback duration. These are not completed GPU times, simulator throughput, or a cross-hardware guarantee."}


def settled(page):
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def ready(page):
    page.wait_for_function("document.querySelector('.three-host canvas')?.dataset.renderInfo && !document.querySelector('.canvas-status') && !document.querySelector('.boot-screen')", timeout=90000)


def returning_visit(context):
    """Regular acceptance targets returning users; onboarding has its own suite."""
    context.add_init_script("localStorage.setItem('afterlight.onboarding.v1',JSON.stringify({version:1,status:'completed'}))")


def verify_served_build(context, base_url: str, manifest: dict):
    checked = []
    for name, expected in manifest["files"].items():
        response = context.request.get(urljoin(base_url, name))
        assert response.ok, f"Snapshot file unavailable: {name} ({response.status})"
        data = response.body()
        assert digest(data) == expected["sha256"] and len(data) == expected["bytes"], f"Served snapshot mismatch: {name}"
        checked.append(name)
    return {"files": len(checked), "bytes": sum(v["bytes"] for v in manifest["files"].values()),
            "manifest_sha256": digest(json.dumps(manifest, sort_keys=True).encode())}


def geometry(page):
    return page.evaluate("""() => {
      const rect = selector => {
        const e = document.querySelector(selector); if (!e) return null;
        const b = e.getBoundingClientRect();
        return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom,right:b.right,
          scrollHeight:e.scrollHeight,clientHeight:e.clientHeight};
      };
      return {viewport:[innerWidth,innerHeight],document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],
        scroll:[scrollX,scrollY],stage:rect('.stage-column'),canvas:rect('.three-host canvas'),
        settings:rect('.settings-scroll'),transport:rect('.transport'),dock:rect('.camera-console')};
    }""")


def stable_box(before, after, key):
    for axis in ("x", "y", "width", "height"):
        assert abs(before[key][axis] - after[key][axis]) < 1, (key, axis, before, after)


def check_layout(page, output: Path):
    results = []
    for width, height in [(1920, 1080), (1440, 810), (1280, 720), (2560, 1440)]:
        page.set_viewport_size({"width": width, "height": height})
        ready(page); settled(page)
        before = geometry(page)
        assert before["document"][0] <= width + 1 and before["document"][1] <= height + 1, before
        assert before["canvas"]["height"] >= 240, before
        assert before["stage"]["bottom"] <= height + 1 and before["stage"]["right"] <= width + 1, before
        assert before["stage"]["scrollHeight"] <= before["stage"]["clientHeight"] + 1, before
        if before["transport"]:
            assert before["transport"]["bottom"] <= height + 1, before
        pane = page.locator(".settings-scroll")
        pane.evaluate("e => e.scrollTo({top:e.scrollHeight,behavior:'instant'})")
        settled(page)
        after = geometry(page)
        assert after["scroll"] == [0, 0], after
        stable_box(before, after, "stage"); stable_box(before, after, "canvas")
        if before["transport"]:
            stable_box(before, after, "transport")
        pane.evaluate("e => e.scrollTo({top:0,behavior:'instant'})")
        # Switching long/short left panels must preserve the right workspace.
        for section in ("Results", "Settings", "Run"):
            switch_section(page, section)
            changed = geometry(page)
            stable_box(before, changed, "stage"); stable_box(before, changed, "canvas")
            assert changed["document"][1] <= height + 1, changed
            if pane.evaluate("e => e.scrollHeight > e.clientHeight + 1"):
                pane.focus(); page.keyboard.press("End"); settled(page)
                # Wait for the native End-key smooth-scroll to finish before
                # switching panels; resetting midway can cancel the next key.
                page.wait_for_function("() => {const e=document.querySelector('.settings-scroll');return Math.abs(e.scrollHeight-e.clientHeight-e.scrollTop)<1;}", timeout=5000)
                stable_box(before, geometry(page), "canvas")
            pane.evaluate("e => e.scrollTo({top:0,behavior:'instant'})")
        page.screenshot(path=str(output / f"desktop-{width}x{height}.png"), full_page=True)
        results.append({"viewport": [width, height], "geometry": before, "right_pane_stationary_on_left_scroll": True})
    page.set_viewport_size({"width": 1920, "height": 1080}); settled(page)
    return results


def switch_section(page, name: str):
    # Native buttons are deliberate here; the product does not present these as
    # ARIA tabs unless it also implements the corresponding keyboard model.
    for label in (["Simulation", "Run"] if name == "Run" else [name]):
        for role in ("tab", "button"):
            element = page.get_by_role(role, name=label, exact=True)
            if element.count():
                element.click(); settled(page)
                if role == "button" and element.get_attribute("aria-pressed") is not None:
                    expect(element).to_have_attribute("aria-pressed", "true")
                return


def open_recording(page, entry):
    switch_section(page, "Run")
    button = page.locator(".recording-list button").filter(has_text=entry["title"])
    if button.count():
        details = page.locator("details").filter(has=button)
        if details.count() and details.first.get_attribute("open") is None:
            details.first.locator("summary").click()
        button.first.click()
    else:
        selector = page.locator("#recording")
        # Route-filtered selects must first receive the catalog's real route.
        if page.locator("#pickup").count(): page.locator("#pickup").select_option(entry["pickup_id"])
        if page.locator("#hospital").count(): page.locator("#hospital").select_option(entry["hospital_id"])
        selector.select_option(entry["id"])
    expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
    ready(page)


def seek(page, value: float):
    page.locator("#timeline").evaluate("(e,value) => {const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(e,String(value));e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}", value)
    settled(page)


def check_camera(page):
    canvas = page.locator(CANVAS)
    page.get_by_role("button", name="Full city", exact=True).click()
    page.wait_for_function("JSON.parse(document.querySelector('.three-host canvas').dataset.cityFit).overview")
    fit = json.loads(canvas.get_attribute("data-city-fit"))
    assert fit["maxX"] <= .86 and fit["maxY"] <= .86, fit
    before = float(canvas.get_attribute("data-camera-zoom"))
    canvas.focus(); canvas.press("Shift+Equal")
    page.wait_for_function("v => Number(document.querySelector('.three-host canvas').dataset.cameraZoom)>v", arg=before)
    target = canvas.get_attribute("data-camera-target")
    canvas.press("ArrowRight")
    page.wait_for_function("v => document.querySelector('.three-host canvas').dataset.cameraTarget!==v", arg=target)
    canvas.press("0")
    page.wait_for_function("JSON.parse(document.querySelector('.three-host canvas').dataset.cityFit).overview")
    page.get_by_role("button", name=re.compile(r"^Explore(?: 2\.5×)?$")).click()
    details = page.locator(".camera-console details")
    before_options = geometry(page)
    details.locator("summary").click()
    options = page.locator(".camera-options").bounding_box()
    assert options and options["y"] >= 0 and options["y"] + options["height"] <= page.viewport_size["height"] + 1, options
    stable_box(before_options, geometry(page), "canvas")
    axes = {}
    for label, attribute in [("Tilt", "data-camera-elevation"), ("Turn", "data-camera-azimuth"), ("Roll", "data-camera-roll")]:
        original = float(canvas.get_attribute(attribute))
        page.get_by_role("button", name=f"{label} camera positive", exact=True).click()
        page.wait_for_function("a => Number(document.querySelector('.three-host canvas').getAttribute(a.attr)) !== a.value", arg={"attr": attribute, "value": original})
        changed = float(canvas.get_attribute(attribute))
        page.get_by_role("button", name=f"{label} camera negative", exact=True).click()
        page.wait_for_function("a => Math.abs(Number(document.querySelector('.three-host canvas').getAttribute(a.attr))-a.value)<1e-8", arg={"attr": attribute, "value": original})
        axes[label] = {"before": original, "after": changed}
    page.get_by_label("Drag to pan instead of orbit", exact=True).check()
    page.get_by_label("Drag to pan instead of orbit", exact=True).uncheck()
    details.locator("summary").click()
    page.get_by_role("button", name="Full city", exact=True).click(); settled(page)
    return {"full_city_fit": fit, "keyboard_zoom_pan_reset": True, "camera_options_overlay": options, "axis_controls": axes}


def check_map_controls(page):
    switch_section(page, "Run")
    disclosure = page.locator(".route-control")
    if disclosure.count() and disclosure.get_attribute("open") is None: disclosure.locator("summary").click()
    leave = page.get_by_role("button", name="Leave recording & explore", exact=True)
    if leave.count(): leave.click()
    ready(page)
    search = page.get_by_role("searchbox", name="Find a pickup", exact=True)
    search.fill("no-such-pickup")
    expect(page.locator(".route-control")).to_contain_text("No matches")
    page.get_by_role("button", name="Clear pickup search", exact=True).click()
    expect(search).to_have_value(""); expect(search).to_be_focused()
    page.get_by_role("button", name="Full city", exact=True).click(); settled(page)
    result = {}
    for kind, label, selector in [("pickup", "Pick on map", "#pickup"), ("hospital", "Hospital on map", "#hospital")]:
        before = page.locator(selector).input_value()
        trigger = page.get_by_role("button", name=label, exact=True)
        expect(trigger).to_be_enabled(); trigger.click()
        page.wait_for_function("m => document.querySelector('.three-host canvas').dataset.mapPickMode===m", arg=kind)
        marker = marker_on_canvas(page, before)
        page.mouse.click(marker["clientX"], marker["clientY"])
        expect(page.locator(selector)).to_have_value(marker["id"])
        expect(trigger).to_be_focused()
        trigger.click(); page.keyboard.press("Escape")
        expect(page.locator(selector)).to_have_value(marker["id"])
        expect(trigger).to_have_attribute("aria-pressed", "false")
        result[kind] = marker["id"]
    return {"selected_canonical_ids": result, "no_results_clear_focus": True, "escape_does_not_change_route": True}


def check_text_contrast(page):
    """Measure visible UI text against its actual solid composited background.

    Scene pixels, native OS popup colors, disabled controls, and gradient-backed
    elements are excluded rather than assigned an invented contrast result.
    """
    result = page.evaluate("""() => {
      const scratch=document.createElement('canvas');scratch.width=scratch.height=1;
      const ctx=scratch.getContext('2d',{willReadFrequently:true});
      const rgba=value=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=value;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].map((v,i)=>i===3?v/255:v/255)};
      const luminance=c=>c.slice(0,3).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
      const checked=[],skipped=[];
      for(const e of document.querySelectorAll('.topbar *, .sidebar *, .stage-toolbar *, .map-location *, .camera-console *, .transport *, .legend *')) {
        const text=[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();
        if(!text||!e.getClientRects().length||e.closest('[hidden],[aria-hidden=true],button:disabled,select:disabled,input:disabled'))continue;
        const box=e.getBoundingClientRect();if(box.bottom<0||box.top>innerHeight)continue;
        const s=getComputedStyle(e);let bg=[0,0,0,0],gradient=false;
        for(let p=e;p;p=p.parentElement){const ps=getComputedStyle(p);if(ps.backgroundImage!=='none')gradient=true;const c=rgba(ps.backgroundColor);const alpha=bg[3]+c[3]*(1-bg[3]);if(alpha)bg=[0,1,2].map(i=>(bg[i]*bg[3]+c[i]*c[3]*(1-bg[3]))/alpha).concat(alpha);if(bg[3]>=.999)break;}
        if(gradient||bg[3]<.999){skipped.push(text.slice(0,60));continue;}
        const fg=rgba(s.color);const color=fg.slice(0,3).map((v,i)=>v*fg[3]+bg[i]*(1-fg[3]));
        const l=[luminance(color),luminance(bg)].sort((a,b)=>b-a),ratio=(l[0]+.05)/(l[1]+.05);
        const size=parseFloat(s.fontSize),large=size>=24||(size>=18.66&&parseInt(s.fontWeight)>=700),threshold=large?3:4.5;
        checked.push({text:text.slice(0,80),ratio,font_px:size,threshold,pass:ratio>=threshold});
      }
      return {checked,skipped};
    }""")
    failures = [item for item in result["checked"] if not item["pass"]]
    assert not failures, failures
    return {"checked_text_nodes": len(result["checked"]), "minimum_ratio": min((i["ratio"] for i in result["checked"]), default=None), "skipped": result["skipped"], "failures": failures}


def foreground_gate(page, output: Path, phase: str, manual: bool):
    # Restore only this dedicated test browser's own native window. Never disable
    # Chromium's background throttling or change the product's renderer settings.
    session = page.context.new_cdp_session(page)
    try:
        window = session.send('Browser.getWindowForTarget')
        before = window['bounds']
        if before['windowState'] == 'minimized':
            session.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
        after = session.send('Browser.getWindowBounds',{'windowId':window['windowId']})['bounds']
    finally:
        session.detach()
    page.bring_to_front()
    if manual:
        marker = output / ('foreground-ready-' + phase)
        request = {'phase':phase,'title':page.title(),'ready_marker':marker.name,
                   'scope':'Operator must visibly activate this dedicated test window before creating the marker; no performance samples are collected while waiting.'}
        (output / 'foreground-request.json').write_text(json.dumps(request,indent=2),encoding='utf-8')
        print(json.dumps({'waiting_for_visible_test_window':request}),flush=True)
        deadline = time.monotonic() + 120
        while not marker.is_file():
            if time.monotonic() > deadline: raise AssertionError('Foreground operator gate timed out; no performance sample accepted')
            page.wait_for_timeout(100)
    page.wait_for_function("document.visibilityState==='visible' && document.hasFocus()",polling=100,timeout=15000)
    return {'native_window_before':before,'native_window_after':after,'operator_marker_required':manual}


def measure(page, seconds: float):
    start = page.locator(CANVAS).evaluate("c => ({counters:JSON.parse(c.dataset.renderInfo),camera:JSON.parse(c.dataset.cameraState),buffer:[c.width,c.height]})")
    page.evaluate("() => {const q=window.__desktopQA;q.samples=[];q.longTasks=[];q.lifecycle=[q.state('start')];q.enabled=true;}")
    page.wait_for_timeout(seconds * 1000)
    data = page.evaluate("() => {const q=window.__desktopQA;q.lifecycle.push(q.state('end'));q.enabled=false;return {samples:q.samples,longTasks:q.longTasks,lifecycle:q.lifecycle};}")
    result = summarize(data["samples"], data["longTasks"])
    result['lifecycle'] = data['lifecycle']
    result['foreground_qualified'] = all(state['visibility']=='visible' and state['focused'] for state in data['lifecycle'])
    result["start"] = start
    result["end"] = page.locator(CANVAS).evaluate("c => ({counters:JSON.parse(c.dataset.renderInfo),camera:JSON.parse(c.dataset.cameraState),buffer:[c.width,c.height]})")
    end = result["end"]["camera"]
    result["camera_orientation_and_zoom_stable"] = (
        start["camera"]["mode"] == end["mode"] and abs(start["camera"]["zoom"]-end["zoom"]) < 1e-7
        and all(abs(a-b) < 1e-7 for a,b in zip(start["camera"]["quaternion"],end["quaternion"]))
    )
    return result


def check_genuine_matrices(context, base_url: str, entry: dict, replay: dict, output: Path):
    """Separate inspection page: matrices are never collected in performance runs."""
    inspection_url = base_url + ("&" if "?" in base_url else "?") + "inspect=1&run=" + entry["id"]
    page = context.new_page()
    page.goto(inspection_url, wait_until="domcontentloaded"); ready(page)
    open_recording(page, entry)
    times, fractional = sample_times(replay)
    result = {"times_s": times, "fractional_sample": fractional, "samples": []}
    switch_section(page, "Settings")
    checkbox = page.get_by_role("checkbox", name=re.compile(r"^Show baseline ghost"))
    checkbox.check()
    for time_s in times:
        seek(page, time_s)
        for world, label in [("afterlight", "Afterlight"), ("baseline", "Ordinary")]:
            page.get_by_role("button", name=re.compile("^(Baseline|Ordinary)$") if world == "baseline" else label, exact=world != "baseline").click()
            snapshot = inspect(page, time_s, world, True)
            active = check_layer(snapshot["active"], sampled_vehicles(replay["worlds"][world]["frames"], time_s), world)
            ordinary = sampled_vehicles(replay["worlds"]["baseline"]["frames"], time_s)
            ghosts = [v for v in ordinary if v["id"] == "ambulance"] if world == "afterlight" else []
            ghost = check_layer(snapshot["ghost"], ghosts, "render-only-ghost")
            result["samples"].append({"time_s": time_s, "world": world, "active": active, "ghost": ghost})
        page.screenshot(path=str(output / f"genuine-matrices-{time_s:g}s.png"), full_page=True)
    page.get_by_role("button", name="Afterlight", exact=True).click()
    checkbox.uncheck()
    snapshot = inspect(page, times[-1], "afterlight", False)
    check_layer(snapshot["ghost"], [], "ghost-disabled")
    result["ghost_disabled_empty"] = True
    page.close()
    return result


def check_recovery(context, base_url: str, output: Path):
    page = context.new_page()
    errors = []; page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/replays/catalog.json", lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"Deliberate isolated UI test outage"}'))
    page.goto(base_url, wait_until="domcontentloaded")
    open_workspace = page.get_by_role("button", name="Open workspace", exact=True)
    expect(open_workspace).to_be_visible(timeout=90000)
    open_workspace.click()
    retry = page.get_by_role("button", name=re.compile(r"^Retry (library|catalog)$"))
    expect(retry).to_be_visible(timeout=90000)
    page.screenshot(path=str(output / "catalog-error.png"), full_page=True)
    page.unroute("**/replays/catalog.json")
    retry.click(); expect(retry).to_have_count(0)
    ready(page)
    supported = page.evaluate("""() => {const gl=document.querySelector('.three-host canvas').getContext('webgl2');
      const e=gl?.getExtension('WEBGL_lose_context');if(!e)return false;e.loseContext();return true;}""")
    assert supported, "WEBGL_lose_context unavailable; recovery not exercised"
    retry_3d = page.get_by_role("button", name="Retry 3D city", exact=True)
    expect(retry_3d).to_be_visible(timeout=30000)
    expect(page.locator(".city-fallback")).to_be_visible()
    page.screenshot(path=str(output / "graphics-error.png"), full_page=True)
    retry_3d.click(); ready(page)
    expect(page.locator(".city-fallback")).to_have_count(0)
    page.emulate_media(reduced_motion="reduce")
    switch_section(page, "Settings")
    reduced = page.get_by_role("checkbox", name=re.compile(r"^Reduced motion"))
    expect(reduced).to_be_checked()
    assert not errors, errors
    page.close()
    return {"catalog_error_retry": True, "webgl_context_loss_retry": True, "system_reduced_motion": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5182/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recording-id")
    parser.add_argument("--require-recording", action="store_true")
    parser.add_argument("--build-manifest", type=Path, help="Exact isolated production build inventory to verify over HTTP")
    parser.add_argument("--measure-seconds", type=float, default=15)
    parser.add_argument("--skip-recovery", action="store_true")
    parser.add_argument("--foreground-gate", action="store_true", help="Pause before each measurement for an operator to activate the dedicated test window and create its output marker")
    parser.add_argument("--headless", action="store_true", help="Supplementary capture only; not headed-GPU evidence")
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.username or url.password or not ((url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}) or (url.scheme == "https" and url.hostname and url.hostname.endswith(".vercel.app"))):
        parser.error("Use the local product or its HTTPS Vercel deployment")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "local-runtime").resolve()): parser.error("Output must stay inside local-runtime")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "pending", "started_utc": datetime.now(timezone.utc).isoformat(),
              "base_url": args.base_url, "platform": platform.platform(), "headless": args.headless,
              "scope": "Desktop product browser acceptance and renderer observations using actual served assets/recordings. No new SUMO traffic or benchmark policy outcomes are generated.",
              "source_before": source_identity(), "page_errors": [], "checks": {}}
    browser = page = playwright = None
    try:
        playwright = sync_playwright().start()
        # Retain Playwright until the outer failure handler can save a screenshot.
        with nullcontext(playwright) as p:
            browser = p.chromium.launch(channel="chrome", headless=args.headless, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
            report["browser_version"] = browser.version
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            returning_visit(context)
            build_manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
            if build_manifest:
                report["served_production_build"] = build_manifest
                report["served_build_before"] = verify_served_build(context, args.base_url, build_manifest)
            context.add_init_script(INSTRUMENT)
            page = context.new_page(); page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
            page.goto(args.base_url, wait_until="domcontentloaded"); ready(page)
            if build_manifest and "fonts/InterVariable.woff2" in build_manifest["files"]:
                report["identity"] = page.evaluate("""async () => {
                  await document.fonts.ready;
                  const mark=document.querySelector('.wordmark .brand-mark');
                  return {title:document.title, canonical:document.querySelector('link[rel=canonical]')?.href,
                    body_font:getComputedStyle(document.body).fontFamily,
                    fonts:[...document.fonts].map(f=>({family:f.family,status:f.status,weight:f.weight})),
                    mark:mark?{src:new URL(mark.src).pathname,complete:mark.complete,width:mark.naturalWidth,height:mark.naturalHeight,alt:mark.alt,
                      rendered_width:mark.getBoundingClientRect().width,rendered_height:mark.getBoundingClientRect().height}:null};
                }""")
                identity = report["identity"]
                assert any(face["family"].strip('"') == "Inter" and face["status"] == "loaded" for face in identity["fonts"]), "Actual self-hosted Inter font did not load"
                assert identity["body_font"].startswith('Inter'), "Identity font is not applied to the interface"
                mark = identity["mark"]
                assert mark and mark["src"] == "/brand/mark.svg" and mark["complete"] and mark["alt"] == "", "Shared decorative brand mark did not load"
                # A viewBox-only SVG has browser-default natural dimensions.
                # Its positive square image and actual on-screen size matter.
                assert mark["width"] == mark["height"] > 0, "Brand mark has invalid source proportions"
                assert 16 <= mark["rendered_width"] <= 64 and abs(mark["rendered_width"] - mark["rendered_height"]) < .01, "Brand mark is distorted or below the guide's readable minimum"
                assert identity["title"] == "AFTERLIGHT — Traffic signal lab"
                assert identity["canonical"] == "https://afterlight-gamma.vercel.app/"
            page.evaluate("document.title='AFTERLIGHT performance check — leave this window untouched'")
            report["load"] = page.evaluate("""() => ({map_ready_ms:window.__desktopQA.readyMs,
              navigation:performance.getEntriesByType('navigation')[0]?.toJSON(),
              resources:performance.getEntriesByType('resource').map(e=>({name:e.name,transfer_bytes:e.transferSize,decoded_bytes:e.decodedBodySize,duration_ms:e.duration}))})""")
            report["renderer"] = page.locator(CANVAS).evaluate("""c => {const gl=c.getContext('webgl2'),e=gl?.getExtension('WEBGL_debug_renderer_info');
              return {vendor:e?gl.getParameter(e.UNMASKED_VENDOR_WEBGL):null,renderer:e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):null,
                counters:JSON.parse(c.dataset.renderInfo),device_pixel_ratio:devicePixelRatio,buffer:[c.width,c.height]};}""")
            page.screenshot(path=str(output / "initial-1920x1080.png"), full_page=True)
            report["checks"]["camera"] = check_camera(page)
            catalog_response = page.request.get(urljoin(args.base_url, "replays/catalog.json"))
            assert catalog_response.ok, f"Catalog HTTP {catalog_response.status}"
            raw_catalog = catalog_response.body(); catalog = json.loads(raw_catalog)
            report["catalog_sha256"] = digest(raw_catalog)
            entries = catalog["runs"]
            if args.recording_id: entries = [e for e in entries if e["id"] == args.recording_id]
            if args.require_recording: assert entries, "No genuine public recording available"
            if entries:
                entry = entries[0]
                response = page.request.get(urljoin(urljoin(args.base_url, "replays/"), entry["url"]))
                assert response.ok, f"Recording HTTP {response.status}"
                transported = response.body()
                raw_replay = decoded_recording(transported); replay = json.loads(raw_replay)
                assert replay["scenario"]["id"] == entry["id"]
                if "sha256" in entry: assert digest(raw_replay) == entry["sha256"], "Catalog/recording checksum mismatch"
                if "bytes" in entry: assert len(raw_replay) == entry["bytes"], "Catalog/recording byte count mismatch"
                canonical = page.request.get(urljoin(args.base_url, "assets/map/city_manifest.json")).body()
                assert replay["provenance"]["canonical_map_sha256"] == digest(canonical), "Recording/map byte identity mismatch"
                report["recording"] = {"catalog_entry": entry, "sha256": digest(raw_replay), "bytes": len(raw_replay), "response_body_bytes": len(transported), "canonical_map_sha256": digest(canonical)}
                open_recording(page, entry)
                page.evaluate("document.title='AFTERLIGHT performance check — leave this window untouched'")
                frames = replay["worlds"]["afterlight"]["frames"]
                candidates = [f for f in frames if any(v["id"] == "ambulance" for v in f["vehicles"]) and f["t"] + args.measure_seconds < replay["duration_s"]]
                busiest = max(candidates or frames, key=lambda f: len(f["vehicles"]))
                seek(page, busiest["t"])
                report["recording"]["measurement_start_s"] = busiest["t"]
                report["recording"]["vehicles_at_start"] = len(busiest["vehicles"])
                report['foreground_overview'] = foreground_gate(page,output,'overview',args.foreground_gate)
                page.get_by_role("button", name="Play recording", exact=True).click()
                report["performance"] = measure(page, args.measure_seconds)
                assert report["performance"]["foreground_qualified"], "Overview lost visible foreground focus; retain measurements without a foreground benchmark claim"
                assert report["performance"]["camera_orientation_and_zoom_stable"], "Camera changed during untouched overview performance measurement"
                page.get_by_role("button", name="Pause recording", exact=True).click()
                ordinary = page.get_by_role("button", name=re.compile(r"^(Baseline|Ordinary)$"))
                ordinary.click()
                expect(ordinary).to_have_attribute("aria-pressed", "true")
                page.get_by_role("button", name="Afterlight", exact=True).click()
                expect(page.get_by_role("button", name="Afterlight", exact=True)).to_have_attribute("aria-pressed", "true")
                report["checks"]["play_pause_world_switch"] = True
                follow = page.locator(".follow-ambulance")
                seek(page, busiest["t"])
                expect(follow).to_be_enabled()
                if follow.get_attribute("aria-pressed") != "true": follow.click()
                expect(follow).to_have_attribute("aria-pressed", "true")
                page.wait_for_function("Number(document.querySelector('.three-host canvas').dataset.cameraZoom)>=11.9")
                pose = next(v for v in sampled_vehicles(frames, busiest["t"]) if v["id"] == "ambulance")
                angle = math.radians(pose["angle_deg"])
                expected_target = [pose["x"]-math.sin(angle)*pose["length_m"]/2,pose["z"]+1.5,-(pose["y"]-math.cos(angle)*pose["length_m"]/2)]
                page.wait_for_function("expected=>{const target=JSON.parse(document.querySelector('.three-host canvas').dataset.cameraState).target;return Math.hypot(...target.map((n,i)=>n-expected[i]))<.02}",arg=expected_target)
                report["performance_close_follow_setup"] = {
                    "control": ".follow-ambulance", "pressed": True, "world": "afterlight",
                    "time_s": busiest["t"], "expected_target_from_genuine_pose": expected_target,
                    "actual_camera": page.locator(CANVAS).evaluate("c=>JSON.parse(c.dataset.cameraState)"),
                }
                report['foreground_follow'] = foreground_gate(page,output,'follow',args.foreground_gate)
                page.get_by_role("button", name="Play recording", exact=True).click()
                report["performance_close_follow"] = measure(page, args.measure_seconds)
                assert report["performance_close_follow"]["foreground_qualified"], "Follow lost visible foreground focus; retain measurements without a foreground benchmark claim"
                expect(follow).to_have_attribute("aria-pressed", "true")
                assert report["performance_close_follow"]["camera_orientation_and_zoom_stable"], "Camera orientation/zoom changed during untouched follow performance measurement"
                page.get_by_role("button", name="Pause recording", exact=True).click()
                page.screenshot(path=str(output / "traffic-close-follow.png"), full_page=True)
                follow.click()
                check_camera(page)
            else:
                report["recording"] = None
                report["performance"] = {"scope": "Static idle city; no traffic performance result"}
            report["checks"]["desktop_layout"] = check_layout(page, output)
            for section in ("Run", "Results", "Settings"):
                switch_section(page, section)
                ready(page); settled(page)
                page.screenshot(path=str(output / f"section-{section.lower()}.png"), full_page=True)
                report["checks"][f"text_contrast_{section.lower()}"] = check_text_contrast(page)
            if entries:
                report["checks"]["genuine_instance_matrices"] = check_genuine_matrices(context, args.base_url, entry, replay, output)
            report["checks"]["canonical_map_controls"] = check_map_controls(page)
            if not args.skip_recovery: report["checks"]["recovery"] = check_recovery(context, args.base_url, output)
            if build_manifest: report["served_build_after"] = verify_served_build(context, args.base_url, build_manifest)
            assert not report["page_errors"], report["page_errors"]
            report["source_after"] = source_identity()
            report["source_stable"] = report["source_before"] == report["source_after"]
            report["status"] = "passed" if report["source_stable"] or build_manifest else "passed_runtime_source_changed_during_development"
            if build_manifest:
                report["validation_binding"] = "Every served file matched the isolated production-build inventory before and after acceptance; current workspace changes are reported separately."
            browser.close(); browser = None
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
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: report.get(key) for key in ("status", "error", "performance", "renderer")}, indent=2))


if __name__ == "__main__": main()
