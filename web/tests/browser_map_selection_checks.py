"""Desktop Omen-only real-map picking checks. No synthetic traffic or outcomes."""
import json
from playwright.sync_api import expect


def marker_on_canvas(page, excluded_id=None):
    """Select an actually projected, uncovered marker, never an invented click point."""
    result = page.evaluate("""excluded => {
        const canvas = document.querySelector('.three-host canvas');
        const rect = canvas.getBoundingClientRect();
        const anchors = JSON.parse(canvas.dataset.mapAnchors || '[]');
        for (const anchor of anchors) {
            const [x,y,z] = anchor.ndc;
            if (anchor.id === excluded || Math.abs(x) > .88 || Math.abs(y) > .88 || z < -1 || z > 1) continue;
            const clientX = rect.left + (x+1)*rect.width/2;
            const clientY = rect.top + (1-y)*rect.height/2;
            const overlaps = anchors.some(other => other.id !== anchor.id &&
                Math.hypot((other.ndc[0]-x)*rect.width/2, (other.ndc[1]-y)*rect.height/2) < 18);
            if (!overlaps && document.elementFromPoint(clientX,clientY) === canvas)
                return {...anchor, clientX, clientY};
        }
        return null;
    }""", excluded_id)
    assert result, 'No projected canonical marker is uncovered at this camera pose'
    return result


def start_mode(page, mode):
    button = page.get_by_role('button', name='Pick on map' if mode == 'pickup' else 'Hospital on map', exact=True)
    expect(button).to_be_enabled(timeout=30000)
    button.click()
    page.wait_for_function("mode => document.querySelector('.three-host canvas')?.dataset.mapPickMode === mode", arg=mode)


def assert_randomized_journey(page):
    """Exercise canonical selection only; never press Play or start a run."""
    expect(page.locator('#pickup-search')).to_have_count(0)
    pickup, hospital = page.locator('#pickup'), page.locator('#hospital')
    pickup_ids = pickup.locator('option').evaluate_all('es=>es.map(e=>e.value)')
    hospital_ids = hospital.locator('option').evaluate_all('es=>es.map(e=>e.value)')
    assert len(pickup_ids) == 100 and len(hospital_ids) == 2
    before = {'pickup': pickup.input_value(), 'hospital': hospital.input_value()}
    randomize = page.get_by_role('button', name='Randomize', exact=True)
    expect(randomize).to_be_enabled()
    randomize.click()
    page.wait_for_function("before=>document.querySelector('#pickup').value!==before.pickup||document.querySelector('#hospital').value!==before.hospital", arg=before)
    after = {'pickup': pickup.input_value(), 'hospital': hospital.input_value()}
    assert after['pickup'] in pickup_ids and after['hospital'] in hospital_ids, after
    expect(page.get_by_role('button', name='Play selected journey', exact=True)).to_be_enabled()
    expect(page.locator('#timeline')).to_be_disabled()
    return {'before': before, 'after': after, 'all_canonical_options': [len(pickup_ids), len(hospital_ids)],
            'no_pickup_search': True, 'play_enabled_without_starting_simulation': True}


def assert_map_selection(page):
    canvas = page.locator('.three-host canvas')
    randomized = assert_randomized_journey(page)
    page.get_by_role('button', name='Explore 2.5×', exact=True).click()
    canvas.focus(); canvas.press('z')
    page.wait_for_function("Number(document.querySelector('.three-host canvas').dataset.cameraRoll) !== 0")
    before = page.get_by_label('Pickup point', exact=True).input_value()
    start_mode(page, 'pickup')
    marker = marker_on_canvas(page, before)
    page.mouse.move(marker['clientX'], marker['clientY'])
    expect(page.locator('.map-pick-hover')).to_contain_text(marker['id'])
    page.mouse.click(marker['clientX'], marker['clientY'])
    expect(page.get_by_label('Pickup point', exact=True)).to_have_value(marker['id'])
    expect(page.get_by_role('button', name='Pick on map', exact=True)).to_be_focused()
    page.wait_for_function("document.querySelector('.three-host canvas').dataset.mapPickMode === 'none'")
    selected = marker['id']

    # Moving the camera across a marker must never commit a journey change.
    start_mode(page, 'pickup')
    marker = marker_on_canvas(page)
    page.mouse.move(marker['clientX'], marker['clientY']); page.mouse.down()
    page.mouse.move(marker['clientX'] + 65, marker['clientY'] + 12, steps=8); page.mouse.up()
    expect(page.get_by_label('Pickup point', exact=True)).to_have_value(selected)
    expect(page.get_by_role('button', name='Pick on map', exact=True)).to_have_attribute('aria-pressed', 'true')
    page.keyboard.press('Escape')
    expect(page.get_by_role('button', name='Pick on map', exact=True)).to_have_attribute('aria-pressed', 'false')
    expect(page.get_by_role('button', name='Pick on map', exact=True)).to_be_focused()

    # Grounded Full city makes both actual hospital driveway anchors available.
    page.get_by_role('button', name='Full city', exact=True).click()
    page.wait_for_function("document.querySelector('.three-host canvas').dataset.cameraPresentation === 'orthographic'")
    previous_hospital = page.get_by_label('Destination hospital', exact=True).input_value()
    start_mode(page, 'hospital')
    marker = marker_on_canvas(page, previous_hospital)
    page.mouse.click(marker['clientX'], marker['clientY'])
    expect(page.get_by_label('Destination hospital', exact=True)).to_have_value(marker['id'])
    selected_hospital = marker['id']
    start_mode(page, 'hospital')
    page.get_by_role('button', name='Cancel map selection', exact=True).click()
    expect(page.get_by_label('Destination hospital', exact=True)).to_have_value(selected_hospital)
    expect(page.get_by_role('button', name='Hospital on map', exact=True)).to_be_focused()
    return {'pickup': selected, 'hospital': selected_hospital, 'rolled_perspective': True,
            'drag_and_cancel_unchanged': True, 'randomized_journey': randomized}


def assert_replay_map_lock(page):
    details = page.locator('.route-control')
    if details.get_attribute('open') is None:
        details.locator('summary').click()
    expect(page.get_by_role('button', name='Pick on map', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Hospital on map', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Randomize', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Leave recording & explore', exact=True)).to_be_visible()
    expect(page.locator('.map-pick-instructions')).to_have_count(0)
