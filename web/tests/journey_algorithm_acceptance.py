"""Headed desktop journey-lock and source-backed Algorithm acceptance.

Uses the actual public catalog and two original recording downloads. Frame arrays
are skipped only in this harness's metadata reader, after exact decoded SHA/size
checks; no replacement replay is served. The loading case holds a genuine GET
without inventing a response, and checks product worker termination before QA
cleanup. This is interaction/geometry evidence, not a new scientific benchmark.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright

from desktop_product_acceptance import (
    ROOT, UNSAFE_DEFAULTS, check_map_controls, decoded_recording, digest, foreground_gate, geometry,
    open_recording, ready, returning_visit, seek, settled, source_identity,
    stable_box, switch_section, verify_served_build,
)
from study_negative_acceptance import FETCH_OBSERVER, preserved, state


LIMIT = 128 * 1024 * 1024
ROUTING_HASHES = {
    "sim/network.py": "9fc5578664b00ef4e5a307998133c605786378a2f794fbee4b5421a15e33b779",
    "sim/demand.py": "b9cb1c63db28b2ab4df243d4a07563147cd412d072a911be4f0921b5783bd925",
    "sim/run.py": "eccde802007afabd76106d8fc6b0466f8b697fbff233282af99601fd59ce6b45",
}
VIEWER_REFERENCE = "9fafa929e377203d3a4d33ca23065f608a736a52"
FRAME_KEY = re.compile(r'(?<=[{,])\s*"frames"\s*:\s*\[')
ARRAY_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[\[\]]')

WORKER_OBSERVER = """(() => {
  const Native=window.Worker;window.__journeyWorkers=[];
  window.Worker=class extends Native {
    constructor(...args) {
      super(...args);const url=String(args[0]);if(!url.includes('recording.worker'))return;
      const row={url,terminated:false,messages:0};window.__journeyWorkers.push(row);
      this.addEventListener('message',()=>row.messages++);
      const terminate=this.terminate.bind(this);
      this.terminate=()=>{row.terminated=true;return terminate();};
    }
  };
})()"""


def recording_metadata(context, base_url: str, entry: dict) -> dict:
    """Read exact public bytes once, excluding large pose arrays from JSON objects.

    This keeps at most the bounded decoded bytes/text plus small metadata alive,
    rather than materializing hundreds of thousands of Python vehicle objects.
    The scanner treats strings atomically, so brackets inside strings cannot end
    an array. Only the two world.frames arrays are omitted from the local reader.
    Original bytes, checksums, responses and browser inputs remain unchanged.
    """
    address = urljoin(urljoin(base_url, "replays/"), entry["url"])
    assert urlsplit(address).netloc == urlsplit(base_url).netloc, "Recording escaped product origin"
    response = context.request.get(address, timeout=90000)
    assert response.ok, (address, response.status)
    transfer = response.body()
    assert len(transfer) <= LIMIT, "Recording transport exceeds bounded QA reader"
    transfer_size = len(transfer)
    raw = decoded_recording(transfer)
    del transfer
    assert digest(raw) == entry["sha256"] and len(raw) == entry["bytes"], "Original recording identity mismatch"
    decoded_size = len(raw)
    text = raw.decode("utf-8", errors="strict")
    del raw
    parts, cursor, skipped = [], 0, 0
    while match := FRAME_KEY.search(text, cursor):
        start = match.end() - 1
        depth, end = 1, None
        for token in ARRAY_TOKEN.finditer(text, start + 1):
            value = token.group()
            if value == "[":
                depth += 1
            elif value == "]":
                depth -= 1
                if depth == 0:
                    end = token.end()
                    break
        assert end is not None, "Unterminated genuine recording frame array"
        parts.extend((text[cursor:start], "[]"))
        cursor = end
        skipped += 1
    parts.append(text[cursor:])
    assert skipped == 2, ("Expected exactly two world frame arrays", skipped)
    metadata = json.loads("".join(parts))
    assert set(metadata["worlds"]) == {"afterlight", "baseline"}
    assert all(world["frames"] == [] for world in metadata["worlds"].values())
    assert metadata["scenario"]["pickup_id"] == entry["pickup_id"]
    assert metadata["scenario"]["hospital_id"] == entry["hospital_id"]
    assert metadata["step_s"] == .5, "Acceptance requires genuine dense public recordings"
    del text, parts
    gc.collect()
    return {"recording": metadata, "identity": {
        "id": entry["id"], "url": entry["url"], "sha256": entry["sha256"],
        "decoded_bytes": decoded_size, "response_body_bytes": transfer_size,
        "frame_arrays_skipped_by_metadata_reader": skipped,
    }}


def open_journey(page, force_user_open=False):
    switch_section(page, "Run")
    before = geometry(page)
    details = page.locator("details.route-control")
    summary = details.locator(":scope > summary")
    expect(summary).to_be_visible()
    if force_user_open and details.get_attribute("open") is not None:
        summary.focus()
        page.keyboard.press("Enter")
        expect(details).not_to_have_attribute("open", "")
    if details.get_attribute("open") is None:
        summary.focus()
        page.keyboard.press("Enter")
    expect(details).to_have_attribute("open", "")
    # The product must reveal its CTA/fields after the user's native open.
    # Do not scroll here: that would hide a product visibility regression.
    settled(page)
    after = geometry(page)
    for key in ("stage", "canvas", "transport", "dock"):
        stable_box(before, after, key)
    assert after["scroll"] == before["scroll"] == [0, 0], (before, after)
    return details


def layout(page) -> dict:
    settled(page)
    before = geometry(page)
    width, height = before["viewport"]
    assert before["document"][0] <= width + 1 and before["document"][1] <= height + 1, before
    assert before["scroll"] == [0, 0], before
    for key in ("stage", "canvas", "transport", "dock"):
        box = before[key]
        assert box and box["x"] >= -1 and box["y"] >= -1 and box["right"] <= width + 1 and box["bottom"] <= height + 1, (key, before)
    assert before["stage"]["scrollHeight"] <= before["stage"]["clientHeight"] + 1, before
    page.locator(".settings-scroll").evaluate("e=>{e.scrollTop=e.scrollHeight}")
    settled(page)
    after = geometry(page)
    for key in ("stage", "canvas", "transport", "dock"):
        stable_box(before, after, key)
    assert after["scroll"] == [0, 0], after
    page.locator(".settings-scroll").evaluate("e=>{e.scrollTop=0}")
    settled(page)
    return {"geometry": before, "right_pane_stationary_on_left_scroll": True}


def locked_journey(page, label: str) -> dict:
    details = open_journey(page, force_user_open=True)
    fields = details.locator("fieldset.journey-fields")
    # Playwright's disabled assertion is defined for interactive controls and
    # does not classify FIELDSET itself. Check its native state explicitly,
    # then check every descendant's effective :disabled state below.
    assert fields.evaluate("e=>e.disabled&&e.matches(':disabled')"), "Journey fieldset must be natively disabled"
    expect(fields).to_have_class(re.compile(r"\bis-locked\b"))
    expect(fields).to_have_attribute("aria-describedby", "journey-lock-note")
    expect(page.locator("#journey-lock-note")).to_contain_text("fixed journey")
    expect(page.locator("#pickup-search")).to_have_count(0)
    expect(page.get_by_role("button", name="Randomize", exact=True)).to_be_disabled()
    controls = fields.locator("input,select,button,textarea")
    assert controls.count() >= 5, "Not all expected journey controls were found"
    statuses = controls.evaluate_all("es=>es.map(e=>({tag:e.tagName,id:e.id,label:e.getAttribute('aria-label')||e.textContent,disabled:e.matches(':disabled')}))")
    assert all(control["disabled"] for control in statuses), statuses
    blur = fields.evaluate("e=>getComputedStyle(e).filter")
    match = re.search(r"blur\(([\d.]+)px\)", blur)
    assert match and float(match[1]) >= 3, ("Journey must visibly blur while locked", blur)
    cta = page.get_by_role("button", name="Leave recording & explore", exact=True)
    expect(cta).to_be_enabled()
    placement = cta.evaluate("e=>{const f=document.querySelector('fieldset.journey-fields'),r=document.querySelector('.settings-scroll').getBoundingClientRect(),c=e.getBoundingClientRect(),b=f.getBoundingClientRect();const top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);return {outside:!f.contains(e),ctaTop:c.top,ctaBottom:c.bottom,fieldsTop:b.top,filter:getComputedStyle(e).filter,leftScrollerVisibleTop:top,leftScrollerVisibleBottom:bottom,visibleBlurredFieldsPx:Math.max(0,Math.min(bottom,b.bottom)-Math.max(top,b.top))}}")
    assert placement["outside"] and placement["ctaBottom"] <= placement["fieldsTop"] + 1 and placement["filter"] == "none", placement
    assert placement["ctaTop"] >= placement["leftScrollerVisibleTop"] - 1 and placement["ctaBottom"] <= placement["leftScrollerVisibleBottom"] + 1, ("User-open must reveal the entire Leave button", placement)
    assert placement["visibleBlurredFieldsPx"] >= 32, ("User-open must reveal the blurred journey fields", placement)
    summary = details.locator(":scope > summary")
    prominence = summary.evaluate("e=>{const s=getComputedStyle(e),t=getComputedStyle(e.querySelector('h2'));return {native:e.tagName==='SUMMARY',label:e.textContent.trim(),padding:parseFloat(s.paddingTop),font:parseFloat(t.fontSize),width:e.getBoundingClientRect().width,disclosureWidth:e.parentElement.getBoundingClientRect().width}}")
    assert prominence["native"] and prominence["padding"] >= 12 and prominence["font"] >= 14 and prominence["width"] >= 200 and prominence["width"] >= prominence["disclosureWidth"] * .95, prominence
    # Disabled fieldsets must be skipped by native sequential keyboard focus.
    cta.focus()
    tabs = []
    for _ in range(6):
        page.keyboard.press("Tab")
        active = page.evaluate("()=>({tag:document.activeElement.tagName,id:document.activeElement.id,label:document.activeElement.getAttribute('aria-label')||document.activeElement.textContent?.slice(0,70),insideLocked:Boolean(document.activeElement.closest('fieldset.journey-fields'))})")
        assert not active["insideLocked"], active
        tabs.append(active)
    return {"case": label, "controls": statuses, "computed_filter": blur,
            "leave_cta": placement, "native_summary": prominence, "tab_sequence_skips_locked_fields": tabs}


def leave_keyboard(page) -> dict:
    open_journey(page)
    cta = page.get_by_role("button", name="Leave recording & explore", exact=True)
    cta.focus()
    page.keyboard.press("Enter")
    expect(page.locator("#pickup-search")).to_have_count(0)
    pickup = page.locator("#pickup")
    expect(pickup).to_be_enabled()
    expect(pickup).to_be_focused()
    fields = page.locator("fieldset.journey-fields")
    expect(fields).not_to_have_class(re.compile(r"\bis-locked\b"))
    assert fields.evaluate("e=>getComputedStyle(e).filter") == "none"
    assert fields.locator("input,select,button,textarea").evaluate_all("es=>es.every(e=>!e.matches(':disabled'))")
    expect(page.locator("#timeline")).to_be_disabled()
    expect(page.get_by_role("button", name="Randomize", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="Play selected journey", exact=True)).to_be_enabled()
    return {"keyboard_activation": "Enter", "focus_restored_to_pickup_dropdown": True,
            "controls_enabled_and_unblurred": True, "recording_timeline_disabled": True,
            "custom_play_enabled_but_not_started": True, "no_pickup_search": True}


def algorithm(page, metadata: dict) -> dict:
    replay = metadata["recording"]
    expected_edges = replay["scenario"]["route_edges"]
    provenance = replay["provenance"]
    assert provenance["source_dirty"] is False
    assert all(provenance["source_files"].get(name) == sha for name, sha in ROUTING_HASHES.items()), "Actual public source no longer matches the reviewed routing implementation"
    commit = provenance["source_commit"]
    assert re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit)
    switch_section(page, "Results")
    page.get_by_role("button", name="Algorithm", exact=True).click()
    root = page.locator("section.algorithm-results")
    expect(root).to_have_attribute("data-algorithm", "dijkstra-distance")
    expect(root.get_by_role("heading", name="How this journey works", exact=True)).to_be_visible()
    expect(root.locator("ol.algorithm-steps > li")).to_have_count(4)
    expect(root.locator(".algorithm-summary")).to_contain_text("shortest legal road distance")
    expect(root.locator(".algorithm-route-sharing")).to_have_attribute("data-route-relation", "shared")
    expect(root.locator('.algorithm-worlds [data-world="baseline"] dt')).to_contain_text("Ordinary ambulance")
    expect(root.locator('.algorithm-worlds [data-world="baseline"] dt')).to_contain_text("ghost when enabled")
    route = root.locator("details.algorithm-route")
    if route.get_attribute("open") is None:
        route.locator(":scope > summary").click()
    edges = route.locator(".algorithm-route-edges > li").evaluate_all("es=>es.map(e=>({edge:e.dataset.edgeId,index:Number(e.dataset.routeIndex),text:e.textContent}))")
    assert edges == [{"edge": edge, "index": i, "text": edge} for i, edge in enumerate(expected_edges)], (expected_edges, edges)
    cost = route.locator(".algorithm-cost")
    expect(cost).to_have_attribute("data-cost-unit", "m")
    expect(cost).to_contain_text("Σ canonical edge length_m")
    expect(cost).to_contain_text("no numeric search total")
    expect(root.locator(".algorithm-steps")).to_contain_text("not estimated arrival time")
    lane_references = {}
    for world in ("afterlight", "baseline"):
        expected = replay["worlds"][world]["decision"]["observation"]["values"]["route_distance_m"]
        actual = route.locator(f'.algorithm-lane-distance dd[data-world="{world}"]')
        assert float(actual.get_attribute("data-lane-distance-m")) == expected
        lane_references[world] = expected
    expect(route).to_contain_text("not the Dijkstra search total")
    sources = root.locator("details.algorithm-sources")
    if sources.get_attribute("open") is None:
        sources.locator(":scope > summary").click()
    source_links = sources.locator("a[data-source-file]").evaluate_all("es=>es.map(e=>({file:e.dataset.sourceFile,href:e.href,target:e.target,rel:e.rel}))")
    assert len(source_links) == 7, source_links
    for link in source_links:
        revision = commit if link["file"] in ROUTING_HASHES else VIEWER_REFERENCE
        assert link["href"].startswith(f"https://github.com/JunaidAhamed-7777/afterlight/blob/{revision}/{link['file']}#L"), link
        assert link["target"] == "_blank" and "noreferrer" in link["rel"], link
    fingerprints = sources.locator(".algorithm-fingerprints > div").evaluate_all("es=>Object.fromEntries(es.map(e=>[e.querySelector('dt').textContent,e.querySelector('dd').textContent]))")
    assert fingerprints == ROUTING_HASHES
    expect(sources).to_contain_text("front bumper")
    expect(sources).to_contain_text("same clock")
    expect(sources).to_contain_text("does not fetch or independently audit")
    return {"recording": metadata["identity"], "edge_order": edges,
            "distance_objective": cost.inner_text(), "separate_saved_lane_references_m": lane_references,
            "shared_saved_route": True, "ordinary_ghost_explained": True,
            "capture_commit": commit, "source_links": source_links, "fingerprints": fingerprints}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5182/")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-manifest", type=Path)
    parser.add_argument("--build-manifest-sha256")
    args = parser.parse_args()
    address = urlsplit(args.base_url)
    if address.username or address.password or address.query or address.fragment or not (
        address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1"}
        or address.scheme == "https" and address.hostname and address.hostname.endswith(".vercel.app")
    ):
        parser.error("Use the local product or its HTTPS Vercel deployment, without credentials/query")
    if args.build_manifest_sha256 and not args.build_manifest:
        parser.error("Manifest SHA requires --build-manifest")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "local-runtime").resolve()):
        parser.error("Use fresh local-runtime output")
    manifest = None
    manifest_sha = None
    if args.build_manifest:
        manifest_raw = args.build_manifest.read_bytes()
        manifest_sha = digest(manifest_raw)
        if args.build_manifest_sha256 and manifest_sha != args.build_manifest_sha256:
            parser.error("Externally pinned build manifest SHA does not match")
        manifest = json.loads(manifest_raw)
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "pending", "scope": __doc__, "started_utc": datetime.now(timezone.utc).isoformat(),
              "base_url": args.base_url, "source_before": source_identity(), "build_manifest_sha256": manifest_sha,
              "checks": {}, "page_errors": [], "screenshots": []}
    playwright = browser = context = page = None
    held = []
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome", headless=False,
            chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        report["browser_version"] = browser.version
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        returning_visit(context)
        context.add_init_script(FETCH_OBSERVER)
        context.add_init_script(WORKER_OBSERVER)
        if manifest:
            report["served_build_before"] = verify_served_build(context, args.base_url, manifest)
        response = context.request.get(urljoin(args.base_url, "replays/catalog.json"))
        assert response.ok
        catalog_bytes = response.body()
        assert len(catalog_bytes) <= 1024 * 1024
        entries = json.loads(catalog_bytes)["runs"]
        first = next(row for row in entries if row["seed"] == 7)
        second = next(row for row in entries if row["seed"] == 8)
        assert first["hospital_id"] != second["hospital_id"], "Expected two actual destination hospitals"
        metadata = {row["id"]: recording_metadata(context, args.base_url, row) for row in (first, second)}
        print(json.dumps({"milestone": "both-genuine-recordings-hash-checked-metadata-read"}), flush=True)
        report["catalog_sha256"] = digest(catalog_bytes)
        report["recordings"] = [metadata[row["id"]]["identity"] for row in (first, second)]
        page = context.new_page()
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.goto(args.base_url + "?" + urlencode({"inspect": "1", "run": first["id"]}), wait_until="domcontentloaded")
        ready(page)
        page.evaluate("document.title='AFTERLIGHT journey and Algorithm check — automated browser'")
        report["foreground_window"] = foreground_gate(page, output, "journey-algorithm", False)
        expect(page.locator("#timeline")).to_be_enabled(timeout=90000)

        for width, height in ((1920, 1080), (1280, 720)):
            page.set_viewport_size({"width": width, "height": height})
            check = locked_journey(page, f"loaded-recording-{width}x{height}")
            check["layout"] = layout(page)
            open_journey(page, force_user_open=True)
            page.screenshot(path=str(output / f"journey-locked-{width}x{height}.png"), full_page=True)
            report["checks"][f"locked-{width}x{height}"] = check
            print(json.dumps({"milestone": "locked-layout-passed", "viewport": [width, height]}), flush=True)
        page.set_viewport_size({"width": 1920, "height": 1080})
        report["checks"]["keyboard-leave"] = leave_keyboard(page)
        page.screenshot(path=str(output / "journey-explore-enabled.png"), full_page=True)
        # Genuine select options, not generated route IDs.
        choices = {}
        for selector in ("#pickup", "#hospital"):
            select = page.locator(selector)
            before = select.input_value()
            other = next(value for value in select.locator("option").evaluate_all("es=>es.map(e=>e.value)") if value != before)
            select.select_option(other)
            expect(select).to_have_value(other)
            choices[selector] = {"before": before, "selected": other}
        report["checks"]["native-journey-selects"] = choices
        report["checks"]["actual-map-dropdown-randomize-and-picks"] = check_map_controls(page)
        print(json.dumps({"milestone": "keyboard-unlock-real-pickup-hospital-and-map-controls-passed"}), flush=True)

        switch_section(page, "Results")
        page.get_by_role("button", name="Algorithm", exact=True).click()
        expect(page.locator(".algorithm-empty")).to_contain_text("Open a recording")
        expect(page.locator(".algorithm-route-edges,.algorithm-cost,.algorithm-worlds")).to_have_count(0)
        assert not page.evaluate("window.__studyFetch"), "Empty Algorithm fetched Study"
        report["checks"]["no-recording-algorithm"] = {"helpful_prompt": True, "no_invented_route_or_world_metrics": True}

        open_recording(page, first)
        locked_journey(page, "reselected-recording")
        seek(page, 180.5)
        page.locator(".follow-ambulance").click()
        expect(page.locator(".follow-ambulance")).to_have_attribute("aria-pressed", "true")
        settled(page)
        baseline = state(page)
        camera_before = page.locator(".three-host canvas").get_attribute("data-camera-state")
        assert not page.evaluate("window.__studyFetch"), "Study loaded before its subview was selected"
        report["checks"]["first-recording-algorithm"] = algorithm(page, metadata[first["id"]])
        preserved(page, baseline)
        assert page.locator(".three-host canvas").get_attribute("data-camera-state") == camera_before
        report["checks"]["algorithm-layout"] = layout(page)
        page.screenshot(path=str(output / "algorithm-overview.png"), full_page=True)
        page.locator("details.algorithm-route").evaluate("e=>e.scrollIntoView({block:'start'})")
        page.screenshot(path=str(output / "algorithm-saved-route.png"), full_page=True)
        page.locator("details.algorithm-sources").evaluate("e=>e.scrollIntoView({block:'start'})")
        page.screenshot(path=str(output / "algorithm-source-details.png"), full_page=True)
        page.get_by_role("button", name="This run", exact=True).click()
        expect(page.locator(".algorithm-results,.study-results")).to_have_count(0)
        preserved(page, baseline)
        page.get_by_role("button", name="Algorithm", exact=True).click()
        preserved(page, baseline)
        assert not page.evaluate("window.__studyFetch"), "This run/Algorithm eagerly fetched Study"
        page.get_by_role("button", name="Study", exact=True).click()
        expect(page.locator(".study-counts")).to_be_visible(timeout=30000)
        assert page.evaluate("window.__studyFetch"), "Actual Study selection did not fetch its public publication"
        preserved(page, baseline)
        page.get_by_role("button", name="Algorithm", exact=True).click()
        preserved(page, baseline)
        assert page.locator(".three-host canvas").get_attribute("data-camera-state") == camera_before
        report["checks"]["result-subviews-preserve-recording"] = {"paused_state": baseline,
            "full_camera_state_unchanged": True, "follow_preserved": True,
            "study_requested_only_after_explicit_selection": True,
            "study_fetches": page.evaluate("window.__studyFetch")}
        print(json.dumps({"milestone": "actual-algorithm-and-study-subviews-preserve-paused-follow-camera"}), flush=True)
        page.set_viewport_size({"width": 1280, "height": 720})
        report["checks"]["algorithm-layout-1280x720"] = layout(page)
        page.screenshot(path=str(output / "algorithm-1280x720.png"), full_page=True)
        page.set_viewport_size({"width": 1920, "height": 1080})

        # Hold the genuine other-hospital fetch. Worker termination must be
        # observable before QA releases this held interception for cleanup.
        leave_keyboard(page)
        expect(page.locator("#pickup-search")).to_have_count(0)
        expect(page.get_by_role("button", name="Randomize", exact=True)).to_be_enabled()
        workers_before = page.evaluate("window.__journeyWorkers.length")
        pattern = "**/replays/" + second["url"]
        def hold_actual_get(route):
            assert route.request.method == "GET"
            held.append(route)
        context.route(pattern, hold_actual_get)
        button = page.locator(".recording-list button").filter(has_text=second["title"]).first
        button.click()
        page.wait_for_function("n=>window.__journeyWorkers.length>n", arg=workers_before)
        deadline = 30000
        # Playwright dispatches route handlers while these browser waits yield.
        for _ in range(deadline // 50):
            if held:
                break
            page.wait_for_timeout(50)
        assert len(held) == 1, "Actual other-hospital GET was not held"
        report["checks"]["loading-recording-lock"] = locked_journey(page, "genuine-recording-GET-pending")
        expect(page.locator("#timeline")).to_be_disabled()
        page.screenshot(path=str(output / "journey-loading-lock.png"), full_page=True)
        leave_keyboard(page)
        page.wait_for_function("n=>window.__journeyWorkers.length===n+1&&window.__journeyWorkers[n].terminated", arg=workers_before)
        worker = page.evaluate("n=>window.__journeyWorkers[n]", workers_before)
        assert worker["messages"] == 0, worker
        report["checks"]["leave-cancels-pending-real-load"] = {
            "held_url": held[0].request.url, "method": held[0].request.method,
            "worker": worker, "terminated_before_QA_request_cleanup": True,
            "no_response_substituted": True}
        print(json.dumps({"milestone": "held-real-GET-canceled-by-product-worker-termination"}), flush=True)
        context.unroute_all(behavior="ignoreErrors")
        for route in held:
            # The worker has already terminated, so its target is gone. Public
            # fallback resolves Playwright's pending handler locally; no new
            # request or invented response is supplied. abort() can throw after
            # that target disappeared and leave the Python handler pending.
            route.fallback()
        held.clear()
        open_recording(page, second)
        report["checks"]["other-hospital-reselection-lock"] = locked_journey(page, "other-hospital-recording-loaded")
        report["checks"]["second-recording-algorithm"] = algorithm(page, metadata[second["id"]])
        page.screenshot(path=str(output / "algorithm-other-hospital.png"), full_page=True)
        page.reload(wait_until="domcontentloaded")
        ready(page)
        expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
        report["checks"]["reload-lock"] = locked_journey(page, "recording-after-reload")
        camera_options = page.locator(".camera-console details")
        if camera_options.get_attribute("open") is None:
            camera_options.locator("summary").click()
        expect(page.get_by_role("checkbox", name="Reveal streets behind foreground buildings", exact=True)).to_be_checked()
        camera_options.locator("summary").click()
        report["checks"]["default-reveal"] = {"checked_after_reload": True,
            "scope": "Default control state only; the dedicated camera suite owns reveal pixel/angle coverage."}
        report["checks"]["final-layout"] = layout(page)
        assert not report["page_errors"], report["page_errors"]
        if manifest:
            report["served_build_after"] = verify_served_build(context, args.base_url, manifest)
            assert report["served_build_before"] == report["served_build_after"]
        report["source_after"] = source_identity()
        assert report["source_before"] == report["source_after"], "Source changed during this acceptance cohort"
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        if page:
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True, timeout=15000)
            except Exception as capture_error:
                report["failure_capture_error"] = str(capture_error)
        raise
    finally:
        if held and context:
            try:
                context.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
        for route in held:
            try:
                route.abort()
            except Exception:
                try:
                    route.fallback()
                except Exception:
                    pass  # A failed test may already have closed its target.
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["screenshots"] = [{"file": path.name, "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
                                 for path in sorted(output.glob("*.png"))]
        (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


if __name__ == "__main__":
    main()
