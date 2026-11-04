"""Opt-in headed acceptance of NEW genuine exploratory SUMO requests.

This starts one partial run, cancels it through the actual product, then starts
one fresh request and waits for its actual recording. It never substitutes a
response, cached replay or simulator result. No model fit or held-out retry.
The original NDJSON/gzip response is retained under fresh ignored local-runtime.
Browser cancellation proves UI/network behavior; owned-server-child cleanup is
covered separately by backend lifecycle tests, not inferred from this browser.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_map_selection_checks import assert_randomized_journey
from desktop_product_acceptance import (
    ROOT, UNSAFE_DEFAULTS, check_map_controls, digest, ready, returning_visit,
    settled, source_identity, switch_section, verify_served_build,
)
from journey_algorithm_acceptance import leave_keyboard, open_journey


def assert_personal_visual_edits(page) -> dict:
    """Check the owner's edits in the rendered browser, not source strings."""
    switch_section(page, 'Run')
    expect(page.locator('.mode-label')).to_have_count(0)
    for removed_intro in (r'^Same city\.?\s*(?:Different signals\.?)?$', r'^Different signals\.?$'):
        expect(page.get_by_text(re.compile(removed_intro, re.I))).to_have_count(0)
    recordings = page.get_by_role('heading', name='Recordings', level=1, exact=True)
    recordings.scroll_into_view_if_needed()
    expect(recordings).to_be_visible()
    expect(recordings).to_be_in_viewport()
    journey = page.locator('.route-control > summary h2')
    expect(journey).to_have_count(1)
    journey.scroll_into_view_if_needed()
    expect(journey).to_be_visible()
    expect(journey).to_be_in_viewport()
    expect(journey).to_contain_text(re.compile(r'^(Choose a journey|Explore another journey)$'))
    expect(page.locator('footer').filter(has_text=re.compile(r'Built with SUMO', re.I))).to_have_count(0)
    return {'mode_label_absent': True, 'marketing_intro_absent': True,
            'recordings': recordings.evaluate("e=>({tag:e.tagName,text:e.textContent.trim()})"),
            'journey_title': journey.evaluate("e=>({tag:e.tagName,text:e.textContent.trim()})"),
            'built_with_sumo_footer_absent': True,
            'scope': 'Actual rendered browser DOM and visible native headings; no App.tsx edits'}


def point(city: dict, kind: str, identifier: str) -> list[float]:
    key, coordinates = ('pickups', 'position') if kind == 'pickup' else ('hospitals', 'driveway_anchor')
    row = next(row for row in city[key] if row['id'] == identifier)
    value = row[coordinates]
    return [value[0], value[2] if len(value) > 2 else 0, -value[1]]


def anchor_observation(page, city: dict, focused_kind: str) -> dict:
    ids = {'pickup': page.locator('#pickup').input_value(), 'hospital': page.locator('#hospital').input_value()}
    expected = point(city, focused_kind, ids[focused_kind])
    page.wait_for_function("expected=>{const c=document.querySelector('.three-host canvas');if(!c?.dataset.cameraState)return false;const s=JSON.parse(c.dataset.cameraState);return s.zoom>=8&&s.target.every((n,i)=>Math.abs(n-expected[i])<1e-7)}", arg=expected)
    settled(page)
    observation = page.locator('.three-host canvas').evaluate("c=>({camera:JSON.parse(c.dataset.cameraState),markers:JSON.parse(c.dataset.journeyMarkers),revision:Number(c.dataset.journeyFocusRevision)})")
    assert len(observation['markers']) == 2, observation
    for marker in observation['markers']:
        assert marker['id'] == ids[marker['kind']], marker
        target = point(city, marker['kind'], marker['id'])
        target[1] += .28
        assert all(abs(a-b) < 1e-7 for a, b in zip(marker['position'], target)), (marker, target)
    return {'selected': ids, 'focused_kind': focused_kind, 'expected_target': expected, **observation}


def live_queue_observation(page, selector: str) -> dict:
    page.wait_for_function("selector=>{const root=document.querySelector(selector);return root&&[...root.querySelectorAll('.queue-series')].some(e=>Number(e.dataset.samples)>1&&Number(e.dataset.lastTime)>0)}", arg=selector, timeout=30000)
    chart = page.locator(selector)
    expect(chart).to_be_visible()
    state = chart.evaluate("e=>({world:e.dataset.queueWorld,time:Number(e.dataset.queueTime),series:[...e.querySelectorAll('.queue-series')].map(s=>({world:s.dataset.world,samples:Number(s.dataset.samples),lastTime:Number(s.dataset.lastTime),lastQueue:Number(s.dataset.lastQueue)})),caption:e.querySelector('.queue-caption')?.textContent})")
    for series in state['series']:
        if not series['samples']:
            continue
        assert series['world'] in {'baseline', 'afterlight'}
        assert 0 < series['samples'] <= 1801 and series['lastTime'] == (series['samples'] - 1) * .5, series
        assert series['lastQueue'] >= 0 and int(series['lastQueue']) == series['lastQueue'], series
    return state


def verify_actual_stream(raw: bytes, request: dict, output: Path) -> dict:
    assert len(raw) <= 32 * 1024 * 1024
    accepted, complete, route = None, None, None
    queues = {'baseline': [], 'afterlight': []}
    compressed = bytearray()
    chunks = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        assert len(line) <= 128 * 1024
        event = json.loads(line)
        assert complete is None, 'The server sent data after completion'
        kind = event['type']
        if kind == 'accepted':
            assert accepted is None and event['request_id'] == request['request_id']
            accepted = event
        elif kind == 'queue':
            assert accepted is not None
            world, t, count = event['world_id'], event['t'], event['queue_count']
            assert world in queues and isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)
            assert isinstance(count, int) and not isinstance(count, bool) and count >= 0
            assert not queues[world] or t > queues[world][-1]['t']
            queues[world].append({'t': t, 'queue_count': count})
        elif kind == 'route':
            assert event['pickup'] == request['pickup'] and event['hospital'] == request['hospital']
            assert isinstance(event['route_edges'], list) and event['route_edges']
            route = event
        elif kind == 'replay_chunk':
            assert accepted is not None and event['index'] == chunks
            block = base64.b64decode(event['data'], validate=True)
            assert block and len(block) <= 64 * 1024
            compressed.extend(block)
            assert len(compressed) <= 20 * 1024 * 1024
            chunks += 1
        elif kind == 'complete':
            complete = event
        else:
            assert kind in {'heartbeat', 'progress'}, event
    assert accepted is not None and route is not None and complete is not None
    assert complete['request_id'] == request['request_id'] and complete['chunks'] == chunks
    assert complete['compressed_bytes'] == len(compressed) and complete['compressed_sha256'] == digest(compressed)
    decoded_hash, decoded_bytes = hashlib.sha256(), 0
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        while block := stream.read(64 * 1024):
            decoded_bytes += len(block)
            assert decoded_bytes <= 128 * 1024 * 1024
            decoded_hash.update(block)
    assert decoded_bytes == complete['decoded_bytes'] and decoded_hash.hexdigest() == complete['replay_sha256']
    for samples in queues.values():
        assert len(samples) == 1801
        assert [sample['t'] for sample in samples] == [index * .5 for index in range(1801)]
    (output/'completed-stream.ndjson').write_bytes(raw)
    (output/'completed-replay.json.gz').write_bytes(compressed)
    return {'complete': complete, 'route': route, 'stream_bytes': len(raw), 'stream_sha256': digest(raw),
            'compressed_bytes': len(compressed), 'compressed_sha256': digest(compressed),
            'decoded_bytes': decoded_bytes, 'decoded_sha256': decoded_hash.hexdigest(),
            'live_queue_samples': {world: {'count': len(samples), 'first': samples[0], 'last': samples[-1]}
                                   for world, samples in queues.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--build-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-real-simulation', action='store_true', help='Required: starts one partial and one full NEW exploratory run')
    parser.add_argument('--queue-selector', default='.live-queues', help='Actual live civilian-queue component root')
    args = parser.parse_args()
    if not args.allow_real_simulation:
        parser.error('Explicit --allow-real-simulation is required; this is not a mocked browser test')
    base = urlsplit(args.base_url)
    if (base.username or base.password or base.query or base.fragment or
        not ((base.scheme == 'http' and base.hostname in {'127.0.0.1', 'localhost'}) or
             (base.scheme == 'https' and base.hostname and base.hostname.endswith('.vercel.app')))):
        parser.error('Use the loopback product or its public HTTPS Vercel deployment')
    manifest_bytes = args.build_manifest.read_bytes()
    if digest(manifest_bytes) != args.build_manifest_sha256:
        parser.error('Build manifest differs from its explicit external pin')
    manifest = json.loads(manifest_bytes)
    output = args.output.resolve()
    runtime = (ROOT/'local-runtime').resolve()
    if output == runtime or not output.is_relative_to(runtime):
        parser.error('Use a fresh child directory under local-runtime')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'pending', 'scope': __doc__, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'base_url': args.base_url, 'build_manifest_sha256': digest(manifest_bytes),
              'source_before': source_identity(), 'checks': {}, 'post_requests': [], 'page_errors': []}
    browser = context = page = playwright = None
    responses = []
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome', headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
        returning_visit(context)
        report['served_build_before'] = verify_served_build(context, args.base_url, manifest)
        map_bytes = context.request.get(urljoin(args.base_url, 'assets/map/city_manifest.json')).body()
        assert digest(map_bytes) == manifest['files']['assets/map/city_manifest.json']['sha256']
        city = json.loads(map_bytes)
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('request', lambda request: report['post_requests'].append(request.post_data_json)
                if request.method == 'POST' and urlsplit(request.url).path.endswith('/api/simulate') else None)
        page.on('response', lambda response: responses.append(response)
                if response.request.method == 'POST' and urlsplit(response.url).path.endswith('/api/simulate') else None)
        session = context.new_cdp_session(page)
        window = session.send('Browser.getWindowForTarget')
        session.send('Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'windowState': 'normal'}})
        session.detach()
        page.bring_to_front()
        page.goto(args.base_url, wait_until='domcontentloaded')
        ready(page)
        report['checks']['personal_visual_edits_before'] = assert_personal_visual_edits(page)
        page.screenshot(path=str(output/'personal-ui-before.png'), full_page=True)
        switch_section(page, 'Run')
        open_journey(page)
        if page.get_by_role('button', name='Leave recording & explore', exact=True).count():
            report['checks']['leave'] = leave_keyboard(page)
        page.get_by_role('button', name='Explore 2.5×', exact=True).click()
        page.locator('#pickup').select_option('P050')
        report['checks']['pickup_focus'] = anchor_observation(page, city, 'pickup')
        page.locator('#hospital').select_option('HOSP_WEST')
        report['checks']['hospital_focus'] = anchor_observation(page, city, 'hospital')
        report['checks']['randomize'] = assert_randomized_journey(page)
        report['checks']['randomized_focus'] = anchor_observation(page, city, 'pickup')
        report['checks']['real_map_selection'] = check_map_controls(page)
        report['checks']['map_focus_and_ground_markers'] = anchor_observation(page, city, 'hospital')

        # Start a real request, observe actual progress, then abort through UI.
        page.locator('#pickup').select_option('P050')
        page.locator('#hospital').select_option('HOSP_WEST')
        page.get_by_role('button', name='Play selected journey', exact=True).click()
        expect(page.locator('.simulation-notice')).to_be_visible(timeout=30000)
        page.wait_for_function("()=>{const p=document.querySelector('progress[aria-label=\"Simulation progress\"]');return p&&p.hasAttribute('value')&&p.value>0}", timeout=120000)
        expect(page.locator('.simulation-notice strong')).to_contain_text('Calculating ordinary traffic')
        switch_section(page, 'Results')
        report['checks']['first_live_graph'] = live_queue_observation(page, args.queue_selector)
        assert report['checks']['first_live_graph']['world'] == 'baseline'
        assert report['checks']['first_live_graph']['time'] < 900, 'Cancellation must occur during the first actual traffic world'
        page.screenshot(path=str(output/'real-progress-before-cancel.png'), full_page=True)
        page.get_by_role('button', name='Cancel simulation', exact=True).click()
        expect(page.locator('.simulation-notice')).to_have_count(0, timeout=15000)
        expect(page.locator('.timeline-label label')).to_have_text('Simulation canceled')
        expect(page.locator('#timeline')).to_be_disabled()
        expect(page.get_by_role('button', name='Play selected journey', exact=True)).to_be_enabled()
        assert len(report['post_requests']) == 1
        report['checks']['cancel'] = {'request': report['post_requests'][0], 'no_replay_installed': True,
            'play_enabled_after_cancel': True, 'server_child_cleanup_not_inferred_from_browser': True}

        # A fresh explicit Play request, not an automatic retry of held-out data.
        switch_section(page, 'Run')
        report['checks']['randomize_after_cancel'] = assert_randomized_journey(page)
        page.locator('#pickup').select_option('P050')
        page.locator('#hospital').select_option('HOSP_EAST')
        page.get_by_role('button', name='Play selected journey', exact=True).click()
        expect(page.locator('.simulation-notice')).to_be_visible(timeout=30000)
        expect(page.locator('#pickup')).to_be_disabled()
        expect(page.get_by_role('button', name='Randomize', exact=True)).to_be_disabled()
        switch_section(page, 'Results')
        expect(page.locator(args.queue_selector)).to_be_visible(timeout=120000)
        report['checks']['second_live_graph'] = live_queue_observation(page, args.queue_selector)
        expect(page.locator('#timeline')).to_be_enabled(timeout=305000)
        expect(page.get_by_role('button', name='Pause recording', exact=True)).to_be_visible()
        page.get_by_role('button', name='Pause recording', exact=True).click()
        expect(page.locator('.simulation-notice')).to_have_count(0)
        assert len(report['post_requests']) == 2
        first, completed = report['post_requests']
        assert first['request_id'] != completed['request_id']
        assert completed['pickup'] == 'P050' and completed['hospital'] == 'HOSP_EAST'
        actual = next(response for response in responses if response.request.post_data_json['request_id'] == completed['request_id'])
        assert actual.ok and 'application/x-ndjson' in actual.headers.get('content-type', '')
        report['checks']['actual_completed_stream'] = verify_actual_stream(actual.body(), completed, output)
        report['checks']['personal_visual_edits_after'] = assert_personal_visual_edits(page)
        page.screenshot(path=str(output/'real-completed-journey.png'), full_page=True)
        assert not report['page_errors'], report['page_errors']
        report['served_build_after'] = verify_served_build(context, args.base_url, manifest)
        report['source_after'] = source_identity()
        assert report['source_after'] == report['source_before'], 'Source changed during genuine acceptance'
        report['status'] = 'passed_genuine_new_exploratory_cancel_then_complete'
    except Exception as error:
        report.update(status='failed', error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output/'failure.png'), full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
