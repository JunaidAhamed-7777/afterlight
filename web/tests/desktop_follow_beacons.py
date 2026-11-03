"""Headed dual-follow, playback speed, and actual roof-material/pixel observations.

Loads genuine published 0.5 s recordings. Only camera, playback and visibility
controls are operated. Beacon snapshots read assigned render materials; saved
browser PNGs still require human pixel review. No physics or metrics are edited.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from desktop_product_acceptance import ROOT, UNSAFE_DEFAULTS, decoded_recording, digest, ready, returning_visit, seek, source_identity, verify_served_build
from real_replay_smoke import sampled_vehicles


def fetched(url):
    with urlopen(url,timeout=30) as response: return response.read(128*1024*1024+1)


def observed(page):
    return page.locator('.three-host canvas').evaluate("c=>({vehicles:JSON.parse(c.dataset.vehicleInspection),camera:JSON.parse(c.dataset.cameraState),render:JSON.parse(c.dataset.renderInfo)})")


def lamp_color(page):
    materials = observed(page)['vehicles']['active']['beaconMaterials']
    assert len(materials)==1,materials
    material = materials[0]
    assert material['color']==material['emissive'] and material['emissiveIntensity']==3 and material['toneMapped'] is False,material
    return material['color']


def wait_lamp(page,color):
    page.wait_for_function("color=>JSON.parse(document.querySelector('.three-host canvas').dataset.vehicleInspection).active.beaconMaterials[0]?.color===color",arg=color,timeout=10000)


def capture_phase(page,output,color,label):
    for _ in range(12):
        wait_lamp(page,color)
        before = observed(page)
        png = page.screenshot(full_page=True)
        after = observed(page)
        if before['vehicles']['active']['beaconMaterials'][0]['color']==after['vehicles']['active']['beaconMaterials'][0]['color']==color:
            (output/(label+'.png')).write_bytes(png)
            return {'label':label,'material_before':before['vehicles']['active']['beaconMaterials'],
                    'material_after':after['vehicles']['active']['beaconMaterials'],'png_sha256':digest(png),
                    'observed_time_s':after['vehicles']['absoluteTime'],'camera':after['camera'],'render':after['render']}
    raise AssertionError('Could not capture a natural stable beacon phase: '+label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:5182/')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--build-manifest',type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'local-runtime').resolve()):parser.error('Use fresh local-runtime output')
    output.mkdir(parents=True,exist_ok=False)
    catalog = json.loads(fetched(urljoin(args.base_url,'replays/catalog.json')))
    entry = next(row for row in catalog['runs'] if row['seed']==7)
    raw = decoded_recording(fetched(urljoin(urljoin(args.base_url,'replays/'),entry['url'])))
    assert digest(raw)==entry['sha256'] and len(raw)==entry['bytes']
    replay = json.loads(raw); del raw
    assert replay['step_s']==.5
    tracks = {world:[{'t':frame['t'],'vehicles':[v for v in frame['vehicles'] if v['id']=='ambulance']} for frame in replay['worlds'][world]['frames']] for world in ('afterlight','baseline')}
    common = [frame['t'] for frame in tracks['afterlight'] if frame['t']>replay['scenario']['dispatch_s']+20 and frame['vehicles'] and sampled_vehicles(tracks['baseline'],frame['t'])]
    assert common
    time_s = round(common[len(common)//3]+.2,1)
    del replay;gc.collect()
    report = {'scope':__doc__,'status':'pending','source_before':source_identity(),'recording':entry,'time_s':time_s,'checks':{},'beacon_phases':[],'page_errors':[]}
    browser = playwright = page = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(channel='chrome',headless=False,chromium_sandbox=True,ignore_default_args=UNSAFE_DEFAULTS)
        report['browser_version'] = browser.version
        context = browser.new_context(viewport={'width':1920,'height':1080},device_scale_factor=1)
        returning_visit(context)
        manifest = json.loads(args.build_manifest.read_bytes()) if args.build_manifest else None
        if manifest:report['served_build_before']=verify_served_build(context,args.base_url,manifest)
        page = context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        query = urlencode({'inspect':'1','run':entry['id']})
        page.goto(args.base_url+'?'+query,wait_until='domcontentloaded');ready(page)
        page.evaluate("document.title='AFTERLIGHT follow and roof-light check — automated browser'")
        expect(page.locator('#timeline')).to_be_enabled(timeout=90000)
        seek(page,time_s)
        a = page.locator('.follow-ambulance');g = page.locator('.follow-ghost')
        def check_target(world,label):
            pose = next(v for v in sampled_vehicles(tracks[world],time_s) if v['id']=='ambulance')
            radians = math.radians(pose['angle_deg'])
            expected = [pose['x']-math.sin(radians)*pose['length_m']/2,pose['z']+1.5,-(pose['y']-math.cos(radians)*pose['length_m']/2)]
            page.wait_for_function("expected=>{const p=JSON.parse(document.querySelector('.three-host canvas').dataset.cameraState).target;return Math.hypot(...p.map((n,i)=>n-expected[i]))<.02}",arg=expected,timeout=10000)
            state = observed(page)
            report['checks'][label] = {'expected_from_genuine_pose':expected,'actual_camera_target':state['camera']['target'],'world':state['vehicles']['world']}
            return state
        a.click();expect(a).to_have_attribute('aria-pressed','true');expect(g).to_have_attribute('aria-pressed','false')
        check_target('afterlight','follow-visible-afterlight')
        page.get_by_role('button',name='Ordinary',exact=True).click()
        expect(a).to_have_attribute('aria-pressed','false');expect(g).to_have_attribute('aria-pressed','false')
        a.click();check_target('baseline','follow-visible-ordinary')
        g.click();expect(g).to_have_attribute('aria-pressed','true');expect(a).to_have_attribute('aria-pressed','false')
        expect(page.get_by_role('button',name='Afterlight',exact=True)).to_have_attribute('aria-pressed','true')
        check_target('baseline','ghost-follow-activates-afterlight-scene')
        page.get_by_role('button',name='Settings',exact=True).click()
        ghost = page.get_by_role('checkbox',name='Show baseline ghost',exact=False)
        expect(ghost).to_be_checked();ghost.uncheck()
        expect(g).to_have_attribute('aria-pressed','false')
        page.wait_for_function("JSON.parse(document.querySelector('.three-host canvas').dataset.vehicleInspection).ghost.ambulances.length===0")
        g.click();expect(ghost).to_be_checked();check_target('baseline','ghost-follow-restores-hidden-ghost')
        page.get_by_role('button',name='Simulation',exact=True).click()
        a.click();check_target('afterlight','ambulance-follow-replaces-ghost-follow')
        for rate in (10,20):
            seek(page,time_s)
            page.get_by_role('combobox',name='Playback speed',exact=True).select_option(str(rate))
            before = page.locator('.three-host canvas').evaluate('c=>({wall:performance.now(),time:JSON.parse(c.dataset.vehicleInspection).absoluteTime})')
            page.get_by_role('button',name='Play recording',exact=True).click();page.wait_for_timeout(1800)
            page.get_by_role('button',name='Pause recording',exact=True).click()
            after = page.locator('.three-host canvas').evaluate('c=>({wall:performance.now(),time:JSON.parse(c.dataset.vehicleInspection).absoluteTime})')
            elapsed = (after['wall']-before['wall'])/1000;delta=after['time']-before['time']
            assert elapsed*rate*.65<delta<elapsed*rate*1.15,(rate,elapsed,delta)
            report['checks'][str(rate)+'x-playback']={'wall_seconds_including_clicks':elapsed,'recorded_seconds_advanced':delta,'observed_ratio':delta/elapsed}
        seek(page,time_s);page.get_by_role('combobox',name='Playback speed',exact=True).select_option('1')
        # Keep the genuine ambulance in view and inspect its original roof bar.
        # Zoom and tilt are normal product controls; no geometry is substituted.
        page.locator('.three-host canvas').focus()
        while float(page.locator('.three-host canvas').get_attribute('data-camera-zoom'))<47.9:
            page.get_by_role('button',name='Zoom in',exact=True).click()
        canvas=page.locator('.three-host canvas');canvas.focus();canvas.press('x');canvas.press('x')
        page.get_by_role('button',name='Play recording',exact=True).click()
        report['beacon_phases'].append(capture_phase(page,output,'#ff304d','roof-playing-red'))
        report['beacon_phases'].append(capture_phase(page,output,'#2288ff','roof-playing-blue'))
        page.get_by_role('button',name='Pause recording',exact=True).click();page.wait_for_timeout(1000)
        wait_lamp(page,'#2288ff')
        paused1 = page.screenshot(path=str(output/'roof-paused-steady-blue.png'),full_page=True)
        page.wait_for_timeout(900);paused2=page.screenshot(path=str(output/'roof-paused-steady-blue-repeat.png'),full_page=True)
        assert paused1==paused2,'Paused pixels changed after camera settled'
        assert lamp_color(page)=='#2288ff'
        report['checks']['paused-steady-blue']={'actual_material':observed(page)['vehicles']['active']['beaconMaterials'],'same_pixels_over_900ms':True}
        page.get_by_role('button',name='Settings',exact=True).click()
        reduced=page.get_by_role('checkbox',name='Reduced motion',exact=False);reduced.check()
        expect(a).to_be_disabled();expect(g).to_be_disabled();expect(a).to_have_attribute('aria-pressed','false')
        page.get_by_role('button',name='Play recording',exact=True).click()
        colors=[]
        for _ in range(8):page.wait_for_timeout(160);colors.append(lamp_color(page))
        assert set(colors)=={'#2288ff'},colors
        page.screenshot(path=str(output/'roof-reduced-motion-steady-blue.png'),full_page=True)
        page.get_by_role('button',name='Pause recording',exact=True).click()
        report['checks']['reduced-motion']={'both_follow_controls_disabled':True,'actual_material_samples':colors,'playback_remains_available':True}
        reduced.uncheck();expect(a).to_be_enabled();expect(g).to_be_enabled()
        thumbnails=page.locator('.legend-model').evaluate_all('imgs=>imgs.map(i=>({src:new URL(i.src).pathname,width:i.naturalWidth,height:i.naturalHeight}))')
        assert len(thumbnails)==2 and all(row['width']>20 and row['height']>20 for row in thumbnails) and thumbnails[0]['src']!=thumbnails[1]['src'],thumbnails
        report['checks']['authored-model-thumbnails']=thumbnails
        assert not report['page_errors'],report['page_errors']
        if manifest:report['served_build_after']=verify_served_build(context,args.base_url,manifest)
        report['status']='passed_headed_dual_follow_playback_and_beacon_materials_pending_pixel_review'
    except Exception as error:
        report.update(status='failed',error=str(error))
        if page is not None:
            try:page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception:pass
        raise
    finally:
        if browser is not None:browser.close()
        if playwright is not None:playwright.stop()
        report['source_after']=source_identity();report['source_stable']=report['source_before']==report['source_after']
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ('status','error','checks')},indent=2))


if __name__=='__main__':main()
