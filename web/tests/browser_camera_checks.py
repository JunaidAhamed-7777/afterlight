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
