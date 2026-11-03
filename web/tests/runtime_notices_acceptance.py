"""Check the actual Settings/About notice popup and unmodified served bytes.

Runs one native headed desktop browser. No response/header overrides are used.
The expected BOM belongs to the new combined container, not its notice bodies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, digest, ready, returning_visit, source_identity, verify_served_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-manifest', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'local-runtime').resolve()): parser.error('Use a fresh local-runtime output')
    output.mkdir(parents=True, exist_ok=False)
    raw = (ROOT / 'web/public/THIRD_PARTY_NOTICES.txt').read_bytes()
    assert 3 < len(raw) <= 256 * 1024 and raw.startswith(b'\xef\xbb\xbf'), 'Combined notice container requires its UTF-8 BOM'
    expected = raw.decode('utf-8-sig').replace('\r\n', '\n').strip()
    assert not expected.startswith('\ufeff')
    lock = json.loads((ROOT / 'web/package-lock.json').read_bytes())
    versions = {}
    for package, label in (('react', 'react'), ('react-dom', 'react-dom'), ('scheduler', 'scheduler'), ('three', 'three'), ('vite', 'vite-runtime')):
        versions[label] = lock['packages']['node_modules/' + package]['version']
        assert f'===== {label} ({versions[label]}) =====' in expected
    report = {'schema': 'afterlight.native-notices-check.v1', 'status': 'pending', 'scope': __doc__,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'base_url': args.base_url,
              'source_before': source_identity(), 'page_errors': [], 'requests': []}
    page = context = browser = playwright = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome', headless=False, chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        report['browser_version'] = browser.version
        context = browser.new_context(viewport={'width': 1440, 'height': 810}, device_scale_factor=1)
        returning_visit(context)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest: report['served_build_before'] = verify_served_build(context, args.base_url, manifest)
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        context.on('request', lambda request: report['requests'].append({'method': request.method, 'url': request.url}))
        page.goto(args.base_url, wait_until='domcontentloaded'); ready(page)
        page.evaluate("document.title='AFTERLIGHT native notices check — automated browser'")
        page.get_by_role('button', name='Settings', exact=True).click()
        page.get_by_text('About this experiment', exact=True).click()
        link = page.get_by_role('link', name='Third-party notices', exact=False)
        expect(link).to_be_visible()
        assert link.get_attribute('target') == '_blank'
        expected_url = urljoin(args.base_url, 'THIRD_PARTY_NOTICES.txt')
        with page.expect_popup() as info: link.click()
        popup = info.value; popup.wait_for_load_state('domcontentloaded')
        assert popup.url == expected_url
        response = context.request.get(popup.url)
        assert response.status == 200 and response.body() == raw, 'Native notice URL changed exact source bytes'
        native = popup.evaluate("()=>({charset:document.characterSet,contentType:document.contentType,text:document.body.innerText})")
        assert native['charset'].upper() == 'UTF-8', native['charset']
        assert native['contentType'] == 'text/plain'
        assert native.pop('text').replace('\r\n', '\n').strip() == expected, 'Native notice text differs from full original bodies'
        popup.screenshot(path=str(output / 'native-notices.png'), full_page=True)
        report['notice'] = {'url': popup.url, 'HTTP_status': response.status, 'content_type_header': response.headers.get('content-type'),
                            'bytes': len(raw), 'sha256': digest(raw), 'container_UTF8_BOM': True,
                            'source_bytes_exact': True, 'full_native_text_exact': True, 'native': native, 'pinned_versions': versions}
        assert not report['page_errors'] and all(request['method'] in {'GET', 'HEAD'} for request in report['requests'])
        if manifest: report['served_build_after'] = verify_served_build(context, args.base_url, manifest)
        report['status'] = 'passed_native_UTF8_notices_without_header_overrides'
    except Exception as error:
        report.update(status='failed', error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output / 'failure.png'), full_page=True)
            except Exception: pass
        raise
    finally:
        if context is not None: context.close()
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        report['source_after'] = source_identity(); report['source_stable'] = report['source_before'] == report['source_after']
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({key: report.get(key) for key in ('status', 'notice', 'error')}, indent=2))


if __name__ == '__main__': main()
