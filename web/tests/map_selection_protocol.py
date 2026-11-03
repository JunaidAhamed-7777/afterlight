"""Omen-only synthetic API protocol test for map-selection locks.

Requires the viewer built with VITE_API_BASE for loopback local generation.
Every API request is intercepted. No simulator, traffic trace or outcome is used.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173')
    parser.add_argument('--output', type=Path, default=Path('local-runtime/map-selection-protocol'))
    parser.add_argument('--channel', choices=('chrome', 'msedge'), default='chrome')
    parser.add_argument('--headless', action='store_true', help='Supplementary only; headed desktop is default')
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('Only the local AFTERLIGHT viewer is supported')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'Synthetic API lock fixture; no simulator, traces or results', 'status': 'pending'}
    requests, held = [], []
    recovering = {'hold': False}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=args.headless, chromium_sandbox=True,
            ignore_default_args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                '--enable-unsafe-swiftshader', '--unsafely-disable-devtools-self-xss-warnings',
                '--disable-ipc-flooding-protection', '--disable-client-side-phishing-detection'])
        context = browser.new_context(viewport={'width':1440, 'height':1000})
        page = context.new_page()
        def respond(route, status, value):
            route.fulfill(status=status, content_type='application/json',
                headers={'Access-Control-Allow-Origin': f'{url.scheme}://{url.netloc}',
                         'Access-Control-Allow-Headers': 'Content-Type',
                         'Access-Control-Allow-Methods':'GET,POST,OPTIONS'}, body=json.dumps(value))
        def intercept(route):
            request = route.request
            path = urlsplit(request.url).path
            if request.method == 'OPTIONS': return respond(route, 200, {})
            if path == '/api/health': return respond(route, 200, {'generation_available':True})
            if path == '/api/catalog': return respond(route, 200, {'schema':'afterlight.catalog.v1', 'runs':[]})
            if path == '/api/runs' and request.method == 'POST':
                value = request.post_data_json; requests.append(value)
                return respond(route, 202, {'id':value['request_id'], 'status':'queued',
                    'parameters':{key:item for key,item in value.items() if key != 'request_id'},
                    'message':'Synthetic queued request. No simulator ran.'})
            if path.startswith('/api/jobs/'):
                if recovering['hold']:
                    held.append(route); return
                if requests:
                    value=requests[0]
                    return respond(route, 200, {'id':value['request_id'], 'status':'queued',
                        'parameters':{key:item for key,item in value.items() if key != 'request_id'},
                        'message':'Synthetic queued request. No simulator ran.'})
            return respond(route, 404, {'error':'Synthetic protocol fixture has no such endpoint'})
        page.route('**/api/**', intercept)
        try:
            page.goto(args.base_url, wait_until='networkidle')
            page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
            generate=page.get_by_role('button', name='Generate paired run', exact=True)
            expect(generate).to_be_enabled(timeout=15000)
            pickup=page.get_by_role('button', name='Choose pickup on map', exact=True)
            hospital=page.get_by_role('button', name='Choose hospital on map', exact=True)
            expect(pickup).to_be_enabled(); pickup.click()
            expect(page.locator('.map-pick-instructions')).to_be_visible()
            generate.click()
            expect(page.locator('.generation-status')).to_contain_text('Queued for SUMO')
            expect(pickup).to_be_disabled(); expect(hospital).to_be_disabled()
            expect(page.locator('.map-pick-instructions')).to_have_count(0)
            assert len(requests)==1
            report['queued_request_blocks_and_exits_map_mode']=True
            # Dropdowns remain next-journey controls; they cannot rewrite the submitted job.
            original=requests[0]['pickup']
            replacement='P002' if original!='P002' else 'P003'
            page.get_by_label('Pickup point', exact=True).select_option(replacement)
            expect(page.locator('.experiment-summary')).to_contain_text(original)
            expect(page.locator('.experiment-summary')).to_contain_text('Saved request')
            recovering['hold']=True
            page.reload(wait_until='domcontentloaded')
            page.wait_for_function("document.querySelector('.three-host canvas') && !document.querySelector('.canvas-status')", timeout=30000)
            deadline=time.monotonic()+10
            while not held and time.monotonic()<deadline: page.wait_for_timeout(50)
            assert held, 'Saved-job recovery request was not observed'
            expect(pickup).to_be_disabled(); expect(hospital).to_be_disabled()
            report['recovery_blocks_map_after_renderer_ready']=True
            # A failed read leaves the original request uncertain, still locked, without another POST.
            for route in held: respond(route, 404, {'error':'Synthetic missing status; no simulator ran'})
            held.clear()
            expect(page.get_by_role('button', name='Retry exact saved request', exact=True)).to_be_visible()
            expect(pickup).to_be_disabled(); expect(hospital).to_be_disabled()
            assert len(requests)==1, 'Uncertain read must not create another job'
            report['uncertain_request_keeps_map_locked']=True
            expect(page.get_by_role('button', name='Open completed recording', exact=True)).to_have_count(0)
            page.screenshot(path=str(args.output/'synthetic-map-lock-only.png'), full_page=True)
            report['status']='passed'
        except Exception as error:
            report['status']='failed'; report['failure']=str(error)
            page.screenshot(path=str(args.output/'failure-synthetic-map-lock-only.png'), full_page=True)
            raise
        finally:
            report['completed_at_unix']=time.time()
            (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            context.close(); browser.close()
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
