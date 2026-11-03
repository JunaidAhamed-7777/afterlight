"""Genuine-positive Study acceptance, runnable only after the public release exists.

An explicit released manifest SHA is mandatory. The pack verifier GETs only
published companions; no local/private outcomes or valid positive fixtures are
accepted. The one injected response is invalid, then Retry uses the real server.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, open_recording, ready, returning_visit, seek, source_identity, verify_served_build
from released_study_pack import load_released_public_pack, local_url, sha
from study_negative_acceptance import FETCH_OBSERVER, preserved, state


def normalized(text):
    return ' '.join(text.split())


def shown_metric(text, value):
    """Check signs and independent numeric rounding, not a copied UI formatter."""
    text = normalized(text)
    if value is None:
        assert text == 'Unavailable', (text, value)
        return
    assert text.endswith(' s'), (text, value)
    if value > 0: assert text.startswith('+'), (text, value)
    if value < 0: assert text.startswith(('−', '-')), (text, value)
    actual = float(text[:-2].replace('−', '-').replace(',', ''))
    tolerance = abs(value) * .051 if value != 0 and (abs(value) < .1 or abs(value) >= 1e6) else .050000001
    assert math.isfinite(actual) and abs(actual - value) <= tolerance, (text, value)
    if value != 0 and abs(value) < .1: assert actual != 0, (text, value)


def dl_values(locator):
    return locator.evaluate("e=>Object.fromEntries([...e.children].map(row=>[row.querySelector('dt').textContent.trim(),row.querySelector('dd').textContent.trim()]))")


def check_actual_study(page, pack, output):
    summary = pack['summary']
    title = 'Offline selector results' if summary['mode'] == 'learned' else 'Analytical baseline results'
    expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible(timeout=30000)
    expect(page.locator('.study-empty')).to_have_count(0)
    expect(page.locator('.study-counts dd')).to_have_text([f"{summary['counts'][key]:,}" for key in ('test', 'test_demand_groups', 'test_worlds')])
    expect(page.locator('.study-sign-rule')).to_contain_text('selected choice minus comparator')
    expect(page.locator('.study-sign-rule')).to_contain_text('Negative is lower; positive is higher')
    expect(page.locator('.study-mode-note')).to_have_count(1 if summary['mode'] == 'baseline_only' else 0)
    amended = pack['verification']['analysis_amendment']['present']
    expect(page.locator('.study-analysis-note')).to_have_count(1 if amended else 0)
    comparisons = page.locator('.study-comparison')
    expect(comparisons).to_have_count(len(summary['comparisons']))
    checked = []
    for index, expected in enumerate(summary['comparisons']):
        section = comparisons.nth(index)
        assert normalized(section.locator('h3').inner_text()) == f"{expected['selected_label']} vs {expected['comparator_label']}"
        assert normalized(section.locator('.study-population').inner_text()) == f"All {expected['episodes']:,} test episodes · {expected['demand_groups']:,} demand groups"
        expect(section.locator('.study-failures dd')).to_have_text([f"{expected[side + '_failures']:,} / {expected['episodes']:,}" for side in ('selected', 'comparator')])
        expect(section.locator('.study-condition')).to_contain_text(f"use {expected['paired_feasible_episodes']:,} of {expected['episodes']:,} pairs")
        displayed = section.locator('.study-deltas dd').all_text_contents()
        assert len(displayed) == 3
        for text, field in zip(displayed, ('mean_delta_j_s', 'mean_delta_ambulance_s', 'mean_delta_civilian_s')):
            shown_metric(text, expected[field])
        interval = normalized(section.locator('.study-interval').evaluate("e=>[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('')"))
        if expected['interval_95_j_s'] is None:
            assert interval == 'Unavailable — ' + expected['interval_reason'], interval
        else:
            low, high = interval.split(' to ')
            shown_metric(low, expected['interval_95_j_s'][0]); shown_metric(high, expected['interval_95_j_s'][1])
        expect(section.locator('.study-interval > span')).to_have_text(f"Independent demand groups for the interval: {expected['interval_groups']:,}.")
        rate = re.search(r'choice:\s*([\d.,]+)%', section.locator('.study-action-rate').inner_text())
        assert rate and abs(float(rate.group(1).replace(',', '')) - expected['changed_action_rate'] * 100) <= .050000001
        section.locator('.study-statuses > summary').click()
        rows = section.locator('.study-accounting tbody tr')
        for row_index, status in enumerate(('completed', 'censored', 'invalid', 'infrastructure_error')):
            expect(rows.nth(row_index).locator('td')).to_have_text([f"{expected[side + '_status_counts'][status]:,}" for side in ('selected', 'comparator')])
        checked.append({'id': expected['id'], 'all_episode_failures_and_statuses_match': True, 'paired_means_and_signs_match': True,
                        'interval_or_actual_missing_reason_matches': True, 'changed_action_rate_matches': True})
    page.locator('.study-method > summary').click()
    method = dl_values(page.locator('.study-method dl'))
    assert method['Train / validation / test episodes'] == ' / '.join(f"{summary['counts'][split]:,}" for split in ('train', 'validation', 'test'))
    assert method['Held-out demand regimes'] == (', '.join(summary['holdouts']['regimes']) or 'No additional regime holdout')
    assert method['Held-out route families'] == (', '.join(summary['holdouts']['route_families']) or 'No additional route-family holdout')
    assert float(method['Tuned fixed lead'].removesuffix(' s')) == summary['fixed_lead_s']
    assert method['Objective, civilian weight 1'] == summary['objective']['definition']
    page.locator('.study-provenance > summary').click()
    if amended:
        expect(page.locator('.study-analysis-note')).to_be_visible()
        expect(page.locator('.study-analysis-note')).to_contain_text('documented pre-test correction')
    provenance = dl_values(page.locator('.study-provenance dl'))
    assert provenance['Summary SHA-256'] == pack['manifest']['sha256']
    for key, value in summary['provenance'].items():
        assert provenance[key.replace('_', ' ')] == (value if value is not None else 'No learned model in this release')
    links = page.locator('.study-downloads a').evaluate_all("items=>items.map(a=>({label:a.textContent,href:a.href,download:a.hasAttribute('download')}))")
    assert links[:3] == [
        {'label': 'Simulation source commit', 'href': 'https://github.com/JunaidAhamed-7777/afterlight/tree/' + summary['provenance']['source_commit'], 'download': False},
        {'label': 'Publication manifest', 'href': pack['manifest_url'], 'download': True},
        {'label': 'Verified study summary', 'href': pack['summary_url'], 'download': True},
    ]
    assert links[3:] == [{'label': artifact['kind'].replace('_', ' '), 'href': local_url(artifact['url'], pack['summary_url']), 'download': True} for artifact in summary['artifacts']]
    page.screenshot(path=str(output / 'actual-study-provenance.png'), full_page=True)
    page.locator('.settings-scroll').evaluate("e=>e.scrollTo({top:0,behavior:'instant'})")
    page.screenshot(path=str(output / 'actual-study-overview.png'), full_page=True)
    return {'comparisons': checked, 'holdouts_objective_and_provenance_match': True, 'all_download_labels_and_targets_match': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--released-manifest-sha256', required=True, help='Exact SHA supplied only after audited public publication')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-manifest', type=Path)
    args = parser.parse_args()
    address = urlsplit(args.base_url)
    if address.username or address.password or not ((address.scheme == 'http' and address.hostname in {'localhost', '127.0.0.1'}) or (address.scheme == 'https' and address.hostname and address.hostname.endswith('.vercel.app'))):
        parser.error('Use the local product or its HTTPS Vercel deployment')
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'local-runtime').resolve()): parser.error('Use fresh local-runtime output')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'pending', 'scope': __doc__, 'started_utc': datetime.now(timezone.utc).isoformat(), 'base_url': args.base_url,
              'source_before': source_identity(), 'requests': [], 'study_responses': [], 'page_errors': []}
    playwright = browser = context = page = None
    try:
        pack = load_released_public_pack(args.base_url, args.released_manifest_sha256)
        report['verified_real_publication'] = pack
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome', headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        report['browser_version'] = browser.version
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
        returning_visit(context); context.add_init_script(FETCH_OBSERVER)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest: report['served_build_before'] = verify_served_build(context, args.base_url, manifest)
        catalog_response = context.request.get(urljoin(args.base_url, 'replays/catalog.json'))
        assert catalog_response.ok
        entry = catalog_response.json()['runs'][0]
        report['genuine_recording'] = entry
        page = context.new_page(); page.on('pageerror', lambda e: report['page_errors'].append(str(e)))
        page.on('request', lambda r: report['requests'].append({'method': r.method, 'url': r.url}))
        def response_seen(response):
            if response.url not in (pack['manifest_url'], pack['summary_url']): return
            observation = {'url': response.url, 'status': response.status}
            try:
                data = response.body(); observation.update(bytes=len(data), sha256=sha(data))
            except Exception as error: observation['body_unavailable'] = str(error)
            report['study_responses'].append(observation)
        page.on('response', response_seen)
        page.goto(args.base_url, wait_until='domcontentloaded'); ready(page)
        open_recording(page, entry)
        page.evaluate("document.title='AFTERLIGHT released Study check — automated browser'")
        expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
        seek(page, 180.5); page.locator('.follow-ambulance').click()
        expect(page.locator('.follow-ambulance')).to_have_attribute('aria-pressed', 'true')
        page.wait_for_timeout(600)
        baseline = state(page); report['preserved_recording_baseline'] = baseline
        assert not page.evaluate('window.__studyFetch'), 'Publication fetched before Study was opened'
        page.get_by_role('button', name='Results', exact=True).click()
        expect(page.get_by_role('button', name='This run', exact=True)).to_have_attribute('aria-pressed', 'true')
        assert not page.evaluate('window.__studyFetch'), 'This run eagerly fetched Study'
        page.get_by_role('button', name='Study', exact=True).click()
        expect(page.locator('.study-counts')).to_be_visible(timeout=30000)
        expect(page.get_by_role('button', name='Study', exact=True)).to_be_focused()
        report['actual_UI'] = check_actual_study(page, pack, output)
        preserved(page, baseline)
        for url, expected_sha in ((pack['manifest_url'], pack['manifest_sha256']), (pack['summary_url'], pack['manifest']['sha256'])):
            assert any(r['url'] == url and r['status'] == 200 and r.get('sha256') == expected_sha for r in report['study_responses']), ('Browser did not receive exact actual released bytes', url)
        for destination in ('This run', 'Simulation'):
            page.get_by_role('button', name=destination, exact=True).click()
            expect(page.locator('.study-results')).to_have_count(0); preserved(page, baseline)
            page.get_by_role('button', name='Results', exact=True).click()
            if page.get_by_role('button', name='Study', exact=True).get_attribute('aria-pressed') != 'true': page.get_by_role('button', name='Study', exact=True).click()
            expect(page.locator('.study-counts')).to_be_visible(timeout=30000); preserved(page, baseline)
        report['mount_unmount_preserves_real_recording'] = True

        page.get_by_role('button', name='This run', exact=True).click()
        def invalid_manifest(route): route.fulfill(status=200, content_type='application/json', body=b'{')
        pattern = '**/study/manifest.json'
        page.route(pattern, invalid_manifest)
        page.get_by_role('button', name='Study', exact=True).click()
        expect(page.get_by_role('heading', name='Study evidence unavailable', exact=True)).to_be_visible(timeout=30000)
        expect(page.locator('.study-counts,.study-comparison')).to_have_count(0)
        page.unroute(pattern, invalid_manifest)
        response_start = len(report['study_responses'])
        # Retry now uses the real HTTP publication, never a fulfilled valid body.
        page.get_by_role('button', name='Retry study', exact=True).focus(); page.keyboard.press('Enter')
        heading = page.get_by_role('heading', name='Offline selector results' if pack['summary']['mode'] == 'learned' else 'Analytical baseline results', exact=True)
        expect(heading).to_be_visible(timeout=30000); expect(heading).to_be_focused()
        for url, expected_sha in ((pack['manifest_url'], pack['manifest_sha256']), (pack['summary_url'], pack['manifest']['sha256'])):
            assert any(r['url'] == url and r['status'] == 200 and r.get('sha256') == expected_sha for r in report['study_responses'][response_start:]), ('Retry did not fetch exact real publication bytes', url)
        preserved(page, baseline)
        report['invalid_then_retry_REAL_publication_ready_heading_focus'] = True

        for exit_action in ('Skip tour', 'Done'):
            page.get_by_role('button', name='Settings', exact=True).click()
            guide = page.locator('[data-tour-reopen]'); expect(guide).to_be_enabled(); guide.click()
            expect(page.locator('.onboarding-layer')).to_be_visible()
            if exit_action == 'Done':
                for _ in range(4): page.get_by_role('button', name='Next', exact=True).click()
            page.get_by_role('button', name=exit_action, exact=True).click()
            expect(page.locator('.onboarding-layer')).to_have_count(0)
            page.get_by_role('button', name='Results', exact=True).click()
            expect(page.get_by_role('button', name='This run', exact=True)).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('.study-results')).to_have_count(0); preserved(page, baseline)
            page.get_by_role('button', name='Study', exact=True).click()
            expect(page.locator('.study-counts')).to_be_visible(timeout=30000)
        report['Study_Settings_guide_exit_Results_restores_This_run'] = ['Skip tour', 'Done']
        assert not report['page_errors'] and all(r['method'] in {'GET', 'HEAD'} for r in report['requests'])
        # Re-fetch actual public bytes to reject a mid-run publication change.
        again = load_released_public_pack(args.base_url, args.released_manifest_sha256)
        assert again == pack, 'Released public pack changed during acceptance'
        if manifest: report['served_build_after'] = verify_served_build(context, args.base_url, manifest)
        report['status'] = 'passed_actual_released_Study_positive_acceptance'
    except Exception as error:
        report.update(status='failed', error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output / 'failure.png'), full_page=True)
            except Exception: pass
        raise
    finally:
        if context is not None: context.unroute_all(behavior='ignoreErrors'); context.close()
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report['source_after'] = source_identity(); report['source_stable'] = report['source_before'] == report['source_after']
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({key: report.get(key) for key in ('status', 'error', 'browser_version')}, indent=2))


if __name__ == '__main__': main()
