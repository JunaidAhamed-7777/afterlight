"""Omen-only desktop split-scroll assertions; no fixtures or traffic synthesis.

Import assert_persistent_workspace(page) after opening a real recording to cover
transport, or use main against an empty/static viewer for shell coverage only.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
from real_replay_smoke import UNSAFE_DEFAULTS, safe_path, verify_served_preview


def assert_persistent_workspace(page):
    results = []
    for width, height in [(1440, 900), (1280, 720)]:
        page.set_viewport_size({'width': width, 'height': height})
        pane = page.get_by_role('region', name='Experiment settings and evidence', exact=True)
        expect(pane).to_be_visible()
        page.wait_for_function("document.querySelector('.three-host canvas')?.width > 0")
        expect(page.locator('.camera-console')).to_be_visible(timeout=60000)
        pane.evaluate('element => { element.scrollTop = 0; }')
        # Reading on animation frames allows the real ResizeObserver to settle.
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        def geometry():
            return page.evaluate('''() => {
                const rect = selector => {
                    const element = document.querySelector(selector);
                    if (!element) return null;
                    const b = element.getBoundingClientRect();
                    return {x:b.x,y:b.y,width:b.width,height:b.height,bottom:b.bottom,right:b.right};
                };
                return {stage:rect('.stage-column'),canvas:rect('.three-host canvas'),
                    dock:rect('.camera-console'),transport:rect('.transport'),
                    scrollY:scrollY,documentHeight:document.documentElement.scrollHeight,
                    viewportHeight:innerHeight,viewportWidth:innerWidth};
            }''')
        before = geometry()
        assert before['documentHeight'] <= height + 1, before
        assert before['stage']['bottom'] <= height + 1, before
        assert before['canvas']['height'] >= 200, before
        assert before['canvas']['right'] <= width + 1, before
        if before['dock']:
            assert before['canvas']['bottom'] <= before['dock']['y'] + 1, before
        if before['transport']:
            assert before['transport']['bottom'] <= height + 1, before
        assert pane.evaluate('element => element.scrollHeight > element.clientHeight')
        pane.focus()
        page.keyboard.press('End')
        page.wait_for_function("document.querySelector('.settings-scroll').scrollTop > 100")
        expect(page.locator('.settings-scroll footer')).to_be_in_viewport()
        after = geometry()
        assert after['scrollY'] == 0, after
        for key in ('stage', 'canvas', 'transport'):
            assert before[key] == after[key], (key, before, after)
        # Focus navigation must move only the left scroller, not the right view.
        expect(page.locator('#pickup-search')).to_have_count(0)
        disclosure = page.locator('.route-control')
        if disclosure.get_attribute('open') is None:
            disclosure.locator('summary').click()
        # Preserve the selected recording: focus its Leave button while its
        # canonical dropdown is locked, rather than unlocking or starting a run.
        target = page.locator('#pickup')
        if target.is_disabled():
            target = page.get_by_role('button', name='Leave recording & explore', exact=True)
        target.focus()
        expect(target).to_be_focused()
        expect(target).to_be_in_viewport()
        assert geometry()['stage'] == before['stage']
        results.append({'viewport': [width, height], 'right_pane_stationary': True,
                        'transport_present': before['transport'] is not None,
                        'canvas_height': before['canvas']['height']})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--open-recording', action='store_true', help='Open an already available genuine catalog recording; never generate one')
    args = parser.parse_args()
    base = urlsplit(args.base_url)
    if base.scheme != 'http' or base.hostname not in {'127.0.0.1', 'localhost'} or base.username or base.password:
        parser.error('Use the loopback committed viewer.')
    output = safe_path(args.output)
    try: output.mkdir(parents=True, exist_ok=False)
    except OSError as error: parser.error(f'Fresh output required: {error}')
    report = {'status': 'pending', 'scope': 'Desktop layout only, not traffic or performance evidence', 'page_errors': []}
    playwright = browser = page = None
    try:
        report['viewer'] = verify_served_preview(base)
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome', headless=False,
            chromium_sandbox=True, ignore_default_args=UNSAFE_DEFAULTS)
        page = browser.new_page(viewport={'width':1440,'height':900})
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(args.base_url, wait_until='domcontentloaded')
        if args.open_recording:
            page.get_by_role('button', name='Open available recording', exact=True).click()
            expect(page.locator('#timeline')).to_be_visible(timeout=60000)
        report['checks'] = assert_persistent_workspace(page)
        page.screenshot(path=str(output/'desktop-split-workspace.png'), full_page=True)
        if report['page_errors']: raise AssertionError('Uncaught browser errors')
        report['status'] = 'passed_desktop_layout_checks'
    except Exception as error:
        report.update(status='failed', error=str(error))
        if page is not None:
            try: page.screenshot(path=str(output/'failure.png'), full_page=True)
            except Exception: pass
        raise
    finally:
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
