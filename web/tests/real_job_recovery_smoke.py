"""Omen-only seeded recovery of one already qualified real API job.

No request interception, POST, SUMO launch, held-out access or publication.
This proves saved-job UI recovery, not that the UI originally submitted the job.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from api.artifacts import parse_json_object, read_bytes
from scripts.api_real_acceptance import load, http, verified_terminal
from real_replay_smoke import safe_path, verify_served_preview, UNSAFE_DEFAULTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173/local.html')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    acceptance, journal = load(args.acceptance)
    if journal['state'] not in {'terminal_verified', 'recovery_verified'}:
        parser.error('An already terminal_verified or recovery_verified API acceptance journal is required.')
    output = safe_path(args.output)
    if output == ROOT/'local-runtime' or output.is_relative_to(acceptance) or acceptance.is_relative_to(output):
        parser.error('Output must be a fresh local-runtime folder outside the original acceptance tree.')
    base = urlsplit(args.base_url)
    if (base.scheme != 'http' or base.hostname not in {'127.0.0.1', 'localhost'} or
        base.username or base.password or base.path != '/local.html' or base.query or base.fragment or
        base.port is None or not 1024 <= base.port <= 65535):
        parser.error('Use an explicit loopback port and /local.html without query or fragment.')
    manifest = parse_json_object(read_bytes(ROOT/'preview/manifest.json'))
    if manifest['entries']['local.html']['VITE_API_BASE'] != journal['base_url']:
        parser.error('The committed local viewer API origin must exactly match the acceptance journal.')
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f'Cannot create fresh output directory: {error}')
    report = {'scope': __doc__, 'status': 'pending', 'requests': [], 'page_errors': [], 'console_errors': [], 'checks': []}
    browser = context = page = playwright = None
    journal_bytes = read_bytes(acceptance/'journal.json')
    identifier = journal['request']['request_id']
    job_path = '/api/jobs/' + identifier
    api_origin = journal['base_url']
    viewer_origin = f'{base.scheme}://{base.netloc}'
    responses = []

    def get(path):
        return http(api_origin, 'GET', path)

    def exact_job():
        code, payload = get(job_path)
        if code != 200:
            raise ValueError('Existing job is unavailable; no submission or retry is permitted.')
        return payload, parse_json_object(payload)

    try:
        viewer = verify_served_preview(base)
        raw_job, job = exact_job()
        evidence = verified_terminal(acceptance, journal, job, lambda method, path: get(path))
        if evidence != journal['terminal_evidence']:
            raise ValueError('Existing raw job/replay differs from accepted terminal evidence.')
        code, health_bytes = get('/api/health')
        if code != 200 or parse_json_object(health_bytes).get('generation_available') is not True:
            raise ValueError('Keep the original generation-enabled server available for saved-job recovery.')
        expected_replay = read_bytes(acceptance/'jobs'/identifier/'replay.json')
        replay = parse_json_object(expected_replay)
        if job.get('replay_url') != job_path + '/replay':
            raise ValueError('Unexpected completed-job replay route.')
        (output/'job-before.json').write_bytes(raw_job)
        report.update(viewer=viewer, job_id=identifier, replay_sha256=evidence['replay_sha256'],
                      journal_sha256=hashlib.sha256(journal_bytes).hexdigest(), terminal_evidence=evidence)
        from playwright.sync_api import sync_playwright, expect
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome', headless=False,
            chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, service_workers='block')
        saved = {'id': job['id'], 'parameters': job['parameters']}
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('request', lambda request: report['requests'].append({'method': request.method, 'url': request.url}))
        page.on('response', lambda response: responses.append(response))
        page.on('console', lambda message: report['console_errors'].append(message.text) if message.type == 'error' else None)
        # Seed once on an inert, hash-verified same-origin asset. Reload never
        # reseeds storage, so the second recovery depends on actual retention.
        page.goto(viewer_origin + '/favicon.svg', wait_until='load')
        page.evaluate("data => sessionStorage.setItem(data.key, JSON.stringify(data.saved))",
                      {'key': 'afterlight.local-job:' + api_origin, 'saved': saved})
        replay_responses = 0
        job_responses = 0
        for attempt in range(2):
            prior_replay_gets, prior_job_gets = replay_responses, job_responses
            if attempt == 0:
                page.goto(args.base_url, wait_until='domcontentloaded')
            else:
                page.reload(wait_until='domcontentloaded')
            button = page.get_by_role('button', name='Open completed recording', exact=True)
            expect(button).to_be_visible(timeout=60000)
            expect(page.locator('.generation-status')).to_contain_text('Execution finished')
            expect(page.locator('.generation-status')).to_contain_text('seed 7')
            expect(page.locator('.generation-status')).to_contain_text(job['parameters']['pickup'])
            expect(page.locator('.generation-status')).to_contain_text(job['parameters']['hospital'])
            expect(page.locator('.generation-status')).to_contain_text(job['parameters']['policy'])
            button.click()
            expect(page.locator('.evidence caption')).to_have_text('Paired run outcomes · ' + replay['scenario']['id'])
            if float(page.locator('#timeline').get_attribute('max')) != replay['duration_s']:
                raise AssertionError('Opened recording duration differs from the actual replay.')
            status = page.locator('.evidence tbody tr').first
            expect(status.locator('td')).to_have_text(['completed', 'completed'])
            page.screenshot(path=str(output/f'real-recovered-job-{attempt+1}.png'), full_page=True)
            report['checks'].append({'pass': 'initial recovery' if attempt == 0 else 'same-tab reload recovery',
                                     'scenario_id': replay['scenario']['id']})
            for response in responses:
                if response.url == api_origin + job_path + '/replay':
                    if response.status != 200 or response.body() != expected_replay:
                        raise AssertionError('Browser replay response differs from exact audited raw bytes.')
                    replay_responses += 1
                elif response.url == api_origin + job_path:
                    if response.status != 200 or parse_json_object(response.body()) != job:
                        raise AssertionError('Browser recovered a changed job record.')
                    job_responses += 1
            pass_replay_gets = replay_responses - prior_replay_gets
            pass_job_gets = job_responses - prior_job_gets
            if pass_replay_gets < 1 or pass_job_gets < 1:
                raise AssertionError('Each navigation must fetch the genuine saved job and replay.')
            report['checks'][-1].update(job_gets=pass_job_gets, replay_gets=pass_replay_gets)
            responses.clear()
            retained = page.evaluate("key => sessionStorage.getItem(key)", 'afterlight.local-job:' + api_origin)
            if retained is None or json.loads(retained) != saved:
                raise AssertionError('The app did not retain the actual saved request for same-tab reload.')
        if replay_responses < 2 or job_responses < 2:
            raise AssertionError('Both initial and reload recovery must fetch the genuine job and replay.')
        for request in report['requests']:
            address = urlsplit(request['url'])
            request_origin = f'{address.scheme}://{address.netloc}'
            if request['method'] not in {'GET', 'HEAD'} or request_origin not in {viewer_origin, api_origin}:
                raise AssertionError('Unexpected modifying or external browser request; no POST is permitted.')
            if request_origin == api_origin and address.path.startswith('/api/jobs/') and address.path not in {job_path, job_path+'/replay'}:
                raise AssertionError('Browser requested a different job identity.')
        if report['page_errors'] or report['console_errors']:
            raise AssertionError('Uncaught browser errors occurred.')
        raw_after, after = exact_job()
        (output/'job-after.json').write_bytes(raw_after)
        if after != job or verified_terminal(acceptance, journal, after, lambda method, path: get(path)) != evidence:
            raise AssertionError('Job identity or original raw evidence changed during UI recovery.')
        if read_bytes(acceptance/'journal.json') != journal_bytes or verify_served_preview(base) != viewer:
            raise AssertionError('Acceptance journal or served viewer changed during recovery.')
        report.update(status='passed_seeded_real_job_recovery', browser_job_gets=job_responses,
                      browser_replay_gets=replay_responses, browser_post_count=0)
        context.close(); context = None
        browser.close(); browser = None
    except Exception as error:
        report.update(status='failed', error=str(error), error_type=type(error).__name__)
        if page is not None:
            try:
                page.screenshot(path=str(output/'failure.png'), full_page=True)
            except Exception:
                pass
        raise
    finally:
        if context is not None:
            try: context.close()
            except Exception: pass
        if browser is not None:
            try: browser.close()
            except Exception: pass
        if playwright is not None:
            try: playwright.stop()
            except Exception: pass
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
