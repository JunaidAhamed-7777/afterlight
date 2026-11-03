"""Shared Omen-only assertions against actual original-city render telemetry."""

def assert_overview_fits(page):
    page.wait_for_function("!document.querySelector('.canvas-status')", timeout=30000)
    page.get_by_role("button", name="Reset camera to city overview").click()
    page.wait_for_function("""() => {
        const canvas = document.querySelector('.three-host canvas');
        if (!canvas?.dataset.cityFit) return false;
        const fit = JSON.parse(canvas.dataset.cityFit);
        const box = canvas.getBoundingClientRect();
        return fit.overview && Math.abs(box.width-fit.viewportWidth)<1 &&
            Math.abs(box.height-fit.viewportHeight)<1 &&
            fit.maxX <= 0.85 && fit.maxY <= 0.85;
    }""", timeout=15000)
    result = page.locator('.three-host canvas').get_attribute('data-city-fit')
    import json
    fit = json.loads(result)
    assert fit['source'] == 'world-transformed original glTF bounds'
    return fit


def assert_favicon_served(page):
    icon = page.locator('link[rel="icon"]')
    assert icon.count() == 1
    url = icon.evaluate('(element) => element.href')
    response = page.request.get(url)
    assert response.status == 200, f'Favicon returned {response.status}'
    assert '<svg' in response.text(), 'Original SVG favicon was not served'
    return url


def assert_camera_exploration(page):
    """Exercise real camera controls; never a traffic or performance benchmark."""
    import json
    import math
    canvas = page.locator('.three-host canvas')
    page.get_by_role('button', name='Explore 2.5×', exact=True).click()
    page.wait_for_function("document.querySelector('.three-host canvas').dataset.cameraPresentation === 'perspective'")
    assert abs(float(canvas.get_attribute('data-camera-zoom')) - 2.5) < 1e-9
    details = page.locator('.camera-console details')
    if details.get_attribute('open') is None:
        details.locator('summary').click()
    changed = {}
    for label, attribute in [('Tilt', 'data-camera-elevation'), ('Turn', 'data-camera-azimuth'), ('Roll', 'data-camera-roll')]:
        before = float(canvas.get_attribute(attribute))
        assert math.isfinite(before)
        page.get_by_role('button', name=f'{label} camera positive', exact=True).click()
        page.wait_for_function("args => Number(document.querySelector('.three-host canvas').getAttribute(args.attribute)) !== args.before", arg={'attribute': attribute, 'before': before})
        after = float(canvas.get_attribute(attribute))
        assert math.isfinite(after)
        page.get_by_role('button', name=f'{label} camera negative', exact=True).click()
        page.wait_for_function("args => Math.abs(Number(document.querySelector('.three-host canvas').getAttribute(args.attribute)) - args.before) < 1e-8", arg={'attribute': attribute, 'before': before})
        changed[label] = {'before': before, 'after': after}
    canvas.focus()
    for key, attribute in [('x', 'data-camera-elevation'), ('y', 'data-camera-azimuth'), ('z', 'data-camera-roll')]:
        before = float(canvas.get_attribute(attribute))
        canvas.press(key)
        page.wait_for_function("args => Number(document.querySelector('.three-host canvas').getAttribute(args.attribute)) !== args.before", arg={'attribute': attribute, 'before': before})
        canvas.press('Shift+' + key.upper())
        page.wait_for_function("args => Math.abs(Number(document.querySelector('.three-host canvas').getAttribute(args.attribute)) - args.before) < 1e-8", arg={'attribute': attribute, 'before': before})
    pan = page.get_by_label('Drag to pan instead of orbit', exact=True)
    pan.check()
    assert pan.is_checked()
    pan.uncheck()
    info = json.loads(canvas.get_attribute('data-render-info'))
    assert info['calls'] > 0 and info['triangles'] > 0, info
    assert 0 <= info['fadedBuildings'] <= info['occluderBuildings'], info
    # These are actual renderer counters, not a benchmark or a proof of smoothness.
    # Occlusion correctness also needs its geometry unit cases and a local visual witness.
    page.get_by_role('button', name='Full city', exact=True).click()
    page.wait_for_function("document.querySelector('.three-host canvas').dataset.cameraPresentation === 'orthographic'")
    assert abs(float(canvas.get_attribute('data-camera-roll'))) < 1e-9
    assert_overview_fits(page)
    if details.get_attribute('open') is not None:
        details.locator('summary').click()
    return {'axes': changed, 'explore_render_counters': info}
