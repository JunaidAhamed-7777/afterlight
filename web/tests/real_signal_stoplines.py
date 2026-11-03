"""Inspect actual civilian instance buffers and signal colors at real stop lines.

Uses only genuine catalog recordings. Known regressions are declared before
reading the new dense capture. Additional red-held car/bike/truck examples are
selected descriptively from each world; this is not a city-wide traffic audit.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
from urllib.parse import urljoin, urlencode
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, decoded_recording, digest, ready, returning_visit, seek, source_identity, verify_served_build
from real_replay_smoke import inspect, sampled_vehicles

KNOWN = [
    {"id": "civilian_00022", "type": "bike", "junction": "J04", "from_lane": "H04_0_R_0", "stop": [7.25, -868.38], "unit": [-1, 0], "links": [2, 3], "green": 62.0},
    {"id": "civilian_00076", "type": "car", "junction": "J18", "from_lane": "V81_0_R_0", "stop": [918.38, -649.5], "unit": [0, -1], "links": [0, 1], "green": 62.0},
    {"id": "civilian_00065", "type": "truck", "junction": "J33", "from_lane": "H33_0_R_1", "stop": [-222.75, -223.38], "unit": [-1, 0], "links": [5, 6], "green": 62.0},
]
KNOWN_RECORDING_SHA256 = "47b13feab0a0f9b022673f942b8a8d585402b5b06e3a05da65fa29faf0ee0441"


def fetch(url: str) -> bytes:
    with urlopen(url, timeout=30) as response: return response.read(128 * 1024 * 1024 + 1)


def held_examples(replay):
    grid = {}
    for signal in replay["network_geometry"]["signals"]:
        lanes = {}
        for link in signal["links"]: lanes.setdefault(link["from_lane"], []).append(link)
        for links in lanes.values():
            a, b = links[0]["incoming_shape"][-2:]
            dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy)
            row = {"junction": signal["id"], "stop": links[0]["stop_line"], "unit": [dx/length, dy/length], "links": [link["index"] for link in links]}
            cell = tuple(math.floor(value/8) for value in row["stop"][:2])
            grid.setdefault(cell, []).append(row)
    result = []
    for world in ("afterlight", "baseline"):
        found = set()
        for frame in replay["worlds"][world]["frames"]:
            if frame["t"] < 60 or frame["t"]+.2 > replay["duration_s"]: continue
            signals = {s["id"]: s["state"] for s in frame["signals"]}
            for vehicle in frame["vehicles"]:
                kind = vehicle["type"]
                if kind not in {"car", "truck", "bike"} or kind in found or vehicle["speed_mps"] > .01: continue
                cell = [math.floor(vehicle[key]/8) for key in ("x", "y")]
                angle = math.radians(vehicle["angle_deg"])
                direction = [math.sin(angle), math.cos(angle)]
                for x in range(cell[0]-1, cell[0]+2):
                    for y in range(cell[1]-1, cell[1]+2):
                        for line in grid.get((x, y), []):
                            u = line["unit"]; delta = [vehicle["x"]-line["stop"][0], vehicle["y"]-line["stop"][1]]
                            progress = sum(a*b for a, b in zip(delta, u))
                            side = abs(delta[0]*u[1]-delta[1]*u[0])
                            states = signals.get(line["junction"], "")
                            if sum(a*b for a, b in zip(direction, u)) < .99 or not -2 < progress < -.01 or side > .4: continue
                            if not all(i < len(states) and states[i].lower() == "r" for i in line["links"]): continue
                            result.append({**line, "id": vehicle["id"], "type": kind, "world": world, "time": round(frame["t"]+.2, 1), "observed_progress_m": progress})
                            found.add(kind); break
                        if kind in found: break
                    if kind in found: break
                if len(found) == 3: break
            if len(found) == 3: break
    return result


def check_pose(page, replay, case, time_s, world, require_red=False, require_green=False):
    label = "Afterlight" if world == "afterlight" else "Ordinary"
    page.get_by_role("button", name=label, exact=True).click()
    seek(page, time_s)
    snapshot = inspect(page, time_s, world, True)
    selected = next((v for v in snapshot["active"]["selectedVehicles"] if v["id"] == case["id"]), None)
    assert selected and selected["consistentMatrices"], (case, time_s, "Missing or inconsistent actual civilian matrices")
    expected = next(v for v in sampled_vehicles(replay["worlds"][world]["frames"], time_s) if v["id"] == case["id"])
    front = [selected["nose"][0], -selected["nose"][2]]
    assert abs(front[0]-expected["x"]) < 1e-4 and abs(front[1]-expected["y"]) < 1e-4, (front, expected)
    assert abs(selected["bounds"]["min"][1]-expected["z"]-.18) < 1e-4
    progress = sum((front[i]-case["stop"][i])*case["unit"][i] for i in (0, 1))
    colors = {row["linkIndex"]: row["color"] for row in snapshot["signalLinks"] if row["signalId"] == case["junction"]}
    assert all(i in colors for i in case["links"]), (case, colors)
    if require_red:
        assert all(colors[i] == "#ed8b82" for i in case["links"]), (case, time_s, colors)
        assert progress <= 1e-4, (case, time_s, "Rendered civilian crossed displayed red", progress)
    if require_green: assert any(colors[i] == "#78d9cb" for i in case["links"]), (case, time_s, colors)
    return {"id": case["id"], "type": expected["type"], "world": world, "time_s": time_s,
            "front_xy_from_actual_matrices": front, "signed_stop_line_progress_m": progress,
            "actual_controlled_link_colors": colors, "require_red": require_red, "require_green": require_green}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5186/")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-manifest", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/"local-runtime").resolve()): parser.error("Use fresh local-runtime output")
    output.mkdir(parents=True, exist_ok=False)
    catalog = json.loads(fetch(urljoin(args.base_url, "replays/catalog.json")))
    entry = next(row for row in catalog["runs"] if row["seed"] == 7)
    raw = decoded_recording(fetch(urljoin(urljoin(args.base_url, "replays/"), entry["url"])))
    assert digest(raw) == entry["sha256"] and len(raw) == entry["bytes"]
    assert entry["sha256"] == KNOWN_RECORDING_SHA256, "Update declared regression cases if the final 3 s recording changes"
    replay = json.loads(raw); del raw; gc.collect()
    assert replay["step_s"] == .5, "This regression requires the dense genuine recapture"
    extra = held_examples(replay)
    ids = list(dict.fromkeys([case["id"] for case in KNOWN+extra]))
    signals = list(dict.fromkeys([case["junction"] for case in KNOWN+extra]))
    query = urlencode({"inspect": "1", "run": entry["id"], "inspect_ids": ",".join(ids), "inspect_signals": ",".join(signals)})
    report = {"scope": __doc__, "status": "pending", "source_before": source_identity(), "recording": entry,
              "known_regressions": KNOWN, "selected_held_examples": extra, "samples": [], "page_errors": []}
    playwright = browser = page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        returning_visit(context)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:
            report["served_production_build"] = manifest
            report["served_build_before"] = verify_served_build(context, args.base_url, manifest)
        page = context.new_page()
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
        page.goto(args.base_url+"?"+query, wait_until="domcontentloaded"); ready(page)
        expect(page.locator("#timeline")).to_be_enabled(timeout=90000)
        page.get_by_role("button", name="Full city", exact=True).click()
        for case in KNOWN:
            for world in ("afterlight", "baseline"):
                rows = [check_pose(page, replay, case, case["green"]+offset, world, require_red=offset<0, require_green=offset>=0) for offset in (-.2, 0, .5, 1)]
                report["samples"].extend(rows)
                assert rows[-1]["signed_stop_line_progress_m"] > rows[0]["signed_stop_line_progress_m"] + .05, (case, world, "No recorded release on displayed green")
                page.screenshot(path=str(output/f"known-{case['id']}-{case['junction']}-{world}.png"), full_page=True)
        for case in extra:
            report["samples"].append(check_pose(page, replay, case, case["time"], case["world"], require_red=True))
        assert {(c["world"], c["type"]) for c in extra} == {(w, kind) for w in ("afterlight", "baseline") for kind in ("car", "truck", "bike")}, "Missing held car/truck/bike coverage in one world"
        assert not report["page_errors"], report["page_errors"]
        if manifest: report["served_build_after"] = verify_served_build(context, args.base_url, manifest)
        report["status"] = "passed_actual_civilian_buffers_and_signal_stop_lines"
    except Exception as error:
        report.update(status="failed", error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output/"failure.png"), full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report["source_after"] = source_identity(); report["source_stable"] = report["source_before"] == report["source_after"]
        (output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: report.get(k) for k in ("status", "error", "source_stable")}, indent=2))


if __name__ == "__main__": main()
