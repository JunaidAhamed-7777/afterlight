"""Exercise the real bounded city-fetch deadline and its desktop recovery UI."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, ready, returning_visit, source_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5182/")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--site", type=Path, help="Serve a real production directory with a native stalled HTTP body")
    parser.add_argument("--port", type=int, default=5190)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/"local-runtime").resolve()): parser.error("Use fresh local-runtime output")
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": "One real 60-second asset-fetch timeout; only an isolated browser GET is held. No simulation, metrics or traffic data are changed.",
              "status": "pending", "source_before": source_identity(), "page_errors": []}
    playwright = browser = page = server = None
    release = threading.Event()
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        context = browser.new_context(viewport={"width":1440,"height":810})
        returning_visit(context)
        held = []; started = []
        def hold(route):
            held.append(route); started.append(time.monotonic())
        base_url = args.base_url
        if args.site:
            site = args.site.resolve()
            class Handler(SimpleHTTPRequestHandler):
                def __init__(self,*a,**kw):super().__init__(*a,directory=str(site),**kw)
                def log_message(self,*a):pass
                def do_GET(self):
                    if urlsplit(self.path).path == "/assets/exports/city_enhanced.glb" and not started:
                        started.append(time.monotonic());held.append("native-http-body")
                        model = site/"assets/exports/city_enhanced.glb"
                        self.send_response(200);self.send_header("Content-Type","model/gltf-binary")
                        self.send_header("Content-Length",str(model.stat().st_size));self.end_headers()
                        release.wait(90);return
                    super().do_GET()
            server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base_url=f"http://127.0.0.1:{args.port}/"
            report["stall_method"]="Native HTTP response headers sent; actual model body deliberately stalled"
        else:
            context.route("**/assets/exports/city_enhanced.glb",hold)
            report["stall_method"]="DevTools request interception (supplementary)"
        page = context.new_page(); page.on("pageerror",lambda e:report["page_errors"].append(str(e)))
        page.goto(base_url,wait_until="domcontentloaded")
        open_workspace = page.get_by_role("button",name="Open workspace",exact=True)
        expect(open_workspace).to_be_visible(timeout=75000)
        assert started and len(held)==1, "Real model fetch was not held exactly once"
        elapsed = time.monotonic()-started[0]
        assert 59 <= elapsed <= 74, f"Unexpected real fetch deadline: {elapsed} seconds"
        expect(page.get_by_role("button",name="Try again",exact=True)).to_be_visible()
        page.screenshot(path=str(output/"asset-timeout-boot.png"),full_page=True)
        open_workspace.click()
        retry = page.get_by_role("button",name="Retry 3D city",exact=True)
        expect(retry).to_be_visible(); expect(page.locator(".city-fallback")).to_be_visible()
        context.unroute_all(behavior="ignoreErrors")
        release.set()
        for route in held:
            try:
                if hasattr(route,"abort"):route.abort()
            except Exception:pass
        page.wait_for_timeout(50)
        retry.click(); ready(page)
        expect(page.locator(".city-fallback")).to_have_count(0)
        expect(page.locator(".boot-screen")).to_have_count(0)
        page.screenshot(path=str(output/"asset-timeout-recovered.png"),full_page=True)
        assert not report["page_errors"],report["page_errors"]
        report.update(status="passed_real_asset_deadline_and_retry",deadline_seconds=elapsed,boot_recovery_actions_visible=True,workspace_fallback_accessible=True,retry_loaded_real_city=True)
    except Exception as error:
        report.update(status="failed",error=str(error))
        if page is not None:
            try:page.screenshot(path=str(output/"failure.png"),full_page=True)
            except Exception:pass
        raise
    finally:
        if browser is not None:browser.close()
        if playwright is not None:playwright.stop()
        release.set()
        if server is not None:server.shutdown();server.server_close()
        report["source_after"]=source_identity();report["source_stable"]=report["source_before"]==report["source_after"]
        (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps({k:report.get(k) for k in ("status","error","deadline_seconds","source_stable")},indent=2))


if __name__=="__main__":main()
