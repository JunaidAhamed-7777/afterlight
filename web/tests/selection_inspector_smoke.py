"""Desktop Omen-only selection-inspector contract test with structural fixtures.

All fixture responses exist only in a fresh Playwright context. No simulator,
model training, evaluation, real traffic trace or benchmark outcome is used.
The fixture is deliberately invalid/censored and must never be published.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

HASH = 'a' * 64
WARNING = 'SYNTHETIC UI CONTRACT TEST: no traffic, training or evaluation ran.'


def fixture(kind):
    identifier = f'structural-ui-{kind}'
    frames = [{'t': t, 'vehicles': [], 'signals': [], 'queue_count': 0} for t in (0, 1)]
    replay = {
        'schema': 'afterlight.replay.v1', 'mode': 'recorded',
        'scenario': {'id': identifier, 'seed': 1, 'pickup_id': 'fixture_start', 'hospital_id': 'fixture_end',
            'network_kind': 'fixture', 'dispatch_s': 0, 'episode_id': 'structural-episode', 'split': 'test'},
        'coordinates': {'source': 'canonical XY meters', 'position_reference': 'front_bumper', 'render': '[x,z,-y]'},
        'provenance': {'source_commit': 'synthetic-ui-only-no-simulator', 'network_sha256': HASH,
            'demand_sha256': HASH, 'sumo_version': 'NO SIMULATOR EXECUTED',
            'model_sha256': HASH if kind in ('residual_tree', 'malformed') else None},
        'duration_s': 1, 'step_s': 1, 'network_geometry': {'signals': []},
        'worlds': {
            'afterlight': {'world_id': 'afterlight', 'policy': 'fixed', 'lead_s': 10, 'status': 'invalid',
                'decision': {'kind': 'dispatch', 't': 0, 'policy': 'fixed', 'selected_lead_s': 10,
                             'request_plan': {}, 'observation': {}, 'candidate_prediction': {}},
                'metrics': {}, 'events': [], 'frames': deepcopy(frames)},
            'baseline': {'world_id': 'baseline', 'policy': 'ordinary', 'lead_s': None, 'status': 'censored',
                'metrics': {}, 'events': [], 'frames': deepcopy(frames)},
        },
    }
    if kind == 'legacy': return replay
    evidence = {key: HASH for key in ('selector_sha256', 'study_sha256', 'protocol_sha256', 'release_sha256',
        'report_sha256', 'selection_sha256', 'trace_manifest_sha256', 'collection_manifest_sha256', 'comparison_artifact_sha256')}
    evidence.update(schema='afterlight.selection-evidence.v1', selector_kind='analytical' if kind == 'analytical' else 'residual_tree',
        model_sha256=None if kind == 'analytical' else HASH, model_file_sha256=None if kind == 'analytical' else HASH,
        case_id='structural-case', episode_id='structural-episode', selected_lead_s=10,
        source_world_aliases={
            'afterlight': {'original_world_id': 'fixed-10', 'trace_sha256': HASH, 'trace_file': 'worlds/structural-case/fixed-10/rich-world.json'},
            'baseline': {'original_world_id': 'ordinary', 'trace_sha256': HASH, 'trace_file': 'worlds/structural-case/ordinary/rich-world.json'},
        }, interpretation=WARNING)
    if kind == 'malformed': evidence['selected_lead_s'] = 20
    replay['selection_evidence'] = evidence
    return replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173')
    parser.add_argument('--output', type=Path, default=Path('local-runtime/selection-inspector-ui-fixture'))
    parser.add_argument('--channel', choices=('chrome', 'msedge'), default='chrome')
    parser.add_argument('--headless', action='store_true', help='Supplementary only; desktop headed mode is default')
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('Only a loopback AFTERLIGHT viewer is permitted')
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f'Output directory already exists: {args.output}. Choose a fresh --output directory to preserve earlier evidence.')
    except OSError as error:
        parser.error(f'Cannot create output directory {args.output}: {error}')
    payloads, rows = {}, []
    for kind in ('residual_tree', 'analytical', 'legacy', 'malformed'):
        replay = fixture(kind)
        body = json.dumps(replay, separators=(',', ':'), sort_keys=True).encode('utf-8')
        path = f'/__selection_ui_fixture__/{kind}.json'
        payloads[path] = body
        rows.append({'id': replay['scenario']['id'], 'title': f'SYNTHETIC UI ONLY · {kind}', 'url': path,
            'seed': 1, 'pickup_id': 'fixture_start', 'hospital_id': 'fixture_end', 'policy': 'fixed',
            'lead_s': 10, 'duration_s': 1, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)})
    catalog = {'schema': 'afterlight.catalog.v1', 'runs': rows}
    report = {'scope': WARNING, 'checks': [], 'page_errors': [], 'status': 'pending', 'headless': args.headless}
    trace_requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=args.headless, chromium_sandbox=True,
            ignore_default_args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                '--enable-unsafe-swiftshader', '--unsafely-disable-devtools-self-xss-warnings',
                '--disable-ipc-flooding-protection', '--disable-client-side-phishing-detection'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        def respond(route, status, body):
            route.fulfill(status=status, content_type='application/json', body=body,
                headers={'Access-Control-Allow-Origin': f'{parsed.scheme}://{parsed.netloc}',
                    'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Allow-Methods': 'GET,OPTIONS'})
        def intercept(route):
            path = urlsplit(route.request.url).path
            if path in payloads: return respond(route, 200, payloads[path])
            if path.endswith('/replays/catalog.json') or path == '/api/catalog':
                return respond(route, 200, json.dumps(catalog))
            if path == '/api/health': return respond(route, 200, json.dumps({'generation_available': False}))
            if '/worlds/' in path:
                trace_requests.append(route.request.url)
                return respond(route, 404, '{}')
            if path.startswith('/api/'):
                return respond(route, 405, json.dumps({'error': 'Synthetic inspector test never invokes the runner'}))
            route.continue_()
        page.route('**/*', intercept)
        try:
            page.goto(args.base_url, wait_until='networkidle')
            # Visible watermark prevents these screenshots being mistaken for traffic evidence.
            page.evaluate("""text => {
                const label = document.createElement('div'); label.textContent = text;
                label.setAttribute('data-synthetic-test-only','true');
                label.style.cssText='position:sticky;top:0;z-index:9999;padding:14px;background:#382d11;color:#fff;font:700 16px system-ui';
                document.body.prepend(label);
            }""", WARNING)
            page.get_by_role('button', name='Open available recording', exact=True).click()
            inspector = page.get_by_role('region', name='Offline selector provenance', exact=True)
            expect(inspector).to_be_visible(timeout=30000)
            expect(inspector.get_by_role('heading')).to_have_text('Learned selector · recorded fixed 10 s candidate')
            expect(inspector).to_contain_text('not a live learned controller')
            expect(inspector).to_contain_text('this one recording does not establish a benefit')
            expect(inspector).to_contain_text('A held-out study conclusion is not bundled')
            expect(page.locator('.fixture-view')).to_be_visible()
            expect(page.locator('.legend')).to_have_count(0)
            expect(page.locator('.stage-subtitle')).to_contain_text('recorded fixed 10 s candidate')
            statuses = page.locator('.evidence-table-wrap tr').filter(has=page.get_by_role('rowheader', name='Run status', exact=True))
            expect(statuses).to_contain_text('invalid'); expect(statuses).to_contain_text('censored')
            page.get_by_text('Dispatch decision & legal priority sequence', exact=True).click()
            expect(page.locator('.decision-inspector')).to_contain_text('The fixed decision was frozen at 0.0 s.')
            expect(page.locator('.decision-inspector')).to_contain_text('Selected clearance lead: 10 s.')
            report['checks'].append('offline_label_fixed_physics_and_invalid_status_preserved')
            artifacts = inspector.get_by_text('Selection artifacts and original-world references', exact=True)
            artifacts.focus(); artifacts.press('Enter')
            expect(inspector).to_contain_text('does not fetch or independently rehash')
            expect(inspector).to_contain_text('worlds/structural-case/fixed-10/rich-world.json')
            expect(inspector).to_contain_text('worlds/structural-case/ordinary/rich-world.json')
            expect(inspector.locator('a')).to_have_count(0)
            assert not trace_requests, trace_requests
            page.screenshot(path=str(args.output/'SYNTHETIC-inspector-only.png'), full_page=True)
            report['checks'].append('keyboard_artifact_disclosure_plain_paths_no_fetch')
            select = page.get_by_label('Recorded experiment', exact=True)
            select.select_option('structural-ui-analytical')
            expect(inspector.get_by_role('heading')).to_have_text('Analytical selector · recorded fixed 10 s candidate', timeout=30000)
            if inspector.locator('details').get_attribute('open') is None: artifacts.click()
            expect(inspector).to_contain_text('No model (analytical selector)')
            report['checks'].append('analytical_selector_not_mislabeled_as_learned')
            select.select_option('structural-ui-legacy')
            expect(inspector).to_have_count(0)
            expect(page.locator('.stage-subtitle')).to_contain_text('Seed 1 · fixed', timeout=30000)
            report['checks'].append('absent_optional_evidence_keeps_original_ui')
            select.select_option('structural-ui-malformed')
            expect(page.get_by_text('Recording unavailable', exact=True)).to_be_visible(timeout=30000)
            expect(inspector).to_have_count(0)
            expect(page.get_by_role('heading', name='No outcome claims yet', exact=True)).to_be_visible()
            report['checks'].append('mismatched_lead_fails_without_stale_inspector_or_outcomes')
            assert not report['page_errors'], report['page_errors']
            assert not trace_requests, trace_requests
            report['status'] = 'passed'
        except Exception as error:
            report['status'] = 'failed'; report['failure'] = str(error)
            page.screenshot(path=str(args.output/'SYNTHETIC-failure-only.png'), full_page=True)
            raise
        finally:
            report['completed_at_unix'] = time.time()
            (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            context.close(); browser.close()
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
