# AFTERLIGHT desktop viewer

React/Three.js viewer for the expanded original city and genuine paired SUMO
recordings. Simulation, Results and Settings scroll on the left; city, camera
and playback remain visible on the right. Desktop is the optimization and default
acceptance target. Existing responsive behavior is preserved.

## Run locally

Use Node >=22.12.0 and the pinned lockfile. The static viewer needs no Python,
SUMO, API key or environment variable.

```powershell
# Repository root; choose an unused port.
npm --prefix web ci
npm --prefix web test
npm --prefix web run dev -- --port 5182 --strictPort
```

Open `http://127.0.0.1:5182/`. A published recording opens automatically. The
first-visit walkthrough introduces the controls and can be skipped or reopened
from Settings. Play advances the actual journey; the speed selector includes
10× and 20×. Follow Ambulance tracks the solid ambulance in the inspected world.
Follow Ghost opens Afterlight, shows the baseline ghost and tracks it. Changing
Afterlight/Ordinary releases follow. Results contains whole-run outcomes. Leave
the recording to choose another pickup/hospital or explore the city.

For a production build:

```powershell
npm --prefix web run build
npm --prefix web run preview -- --port 5185 --strictPort
```

`prepare:assets` copies authoritative exports, the canonical map and fallback
previews into ignored `public/assets/`. Edit source assets, then rerun preparation
or build; do not edit generated copies. Preserve existing user services and raw
experiment directories. A source-bound preview has a separate workflow in
[preview/README.md](../preview/README.md).

## Product and recording contract

The city covers 2,040 × 2,010 m: 81 primary junctions, 77 signal controllers,
826 buildings, two diagonal hospitals and 100 pickup anchors. All 200 routes pass
static connectivity qualification; that is separate from traffic-study coverage.
The city GLB is 14.38 MB. The owner permits 50 MB of shipped assets including
compressed recordings. See the [asset inventory](../assets/README.md).

`public/replays/catalog.json` publishes two exploratory city pairs. Their `.json.gz`
containers are lossless; each decoded recording retains every 0.5 s simulator
step through 900 s, using a 3 s all-red clearance. The two gzip files total
13,304,439 bytes. Catalog `bytes`/`sha256` bind decoded original JSON;
`encoding`, `transfer_bytes` and `transfer_sha256` describe transport. The loader
accepts an HTTP-decoded response or gzip magic bytes, enforces a 128 MiB bound on
both wire and decoded reads, checks valid UTF-8, finite numbers and at most 64
nested containers, validates the replay, then binds selected metadata.

A module worker fetches, decompresses, hashes and validates dense recordings.
It terminates on success, failure or cancellation. GLB downloads have a 60 s
deadline and abort on renderer teardown; recording fetches have a 30 s deadline.
Errors offer retry, and HTML evidence remains usable if rendering fails. Only
the latest locally returned replay is cached. Empty libraries remain valid and
show city exploration without invented traffic.

Both physical worlds share absolute timestamps and coordinate scale, with their
own vehicles, queues and lamps. Only the baseline ambulance becomes a render-only
ghost in the Afterlight view. Fixture or mismatched-city recordings open HTML
results and never appear on unrelated city geometry. SUMO front-bumper poses
convert to centered vehicle meshes, then `[x,z,-y]`; the city root stays intact.
Every vehicle's lowest geometry rests at recorded elevation plus road top 0.18 m.

Movement arrows represent individual controlled links. Exact event-derived lamp
boundaries are accepted only if they reproduce every saved state; incomplete
legacy evidence keeps its sampled presentation. Pose interpolation uses adjacent
real frames; metrics remain measured whole-run values. Fresh 0.5 s captures replaced
coarse presentation that incorrectly moved three stopped cars before green.
Original failed evidence is preserved. See the [replay contract](../docs/REPLAY_SCHEMA.md).

## Study results

Results has separate **This run** and **Study** views. Individual recordings are
exploratory examples. Study displays only an actually audited, released test
report; before its publication it shows **Study not published**, without pending
or invented metrics. It fetches only while that view is open, verifies the exact
summary bytes against `study/manifest.json`, and cancels requests when you leave.
The manifest is capped at 16 KiB and the summary at 1 MiB.

Study shows failures and sample counts before conditional paired deltas. Negative
means selected choice minus comparator is lower; missing intervals retain their
reason. The method/source disclosure explains offline cached-candidate selection
and links published proof files. Checking the summary's checksum does not
independently re-audit every linked artifact. The dependency-free compiled preview
serves the same published `web/public/study/` files without copying or regenerating
scientific outcomes.

## Camera and accessibility

Explore uses genuine perspective; Full city fits an orthographic overview.
Drag orbits, right-drag/arrow keys pan, scroll/+/- zoom, and focused-canvas X/Y/Z
adjust tilt/heading/roll. Shift reverses rotation; 0 resets; Tab leaves the map.
Starting Follow Ambulance or Follow Ghost frames that trajectory at a minimum
12× target-plane zoom. Subsequent camera adjustments are retained. Changing
the inspected world, deliberate panning, Explore or Full city releases follow.
Actual-model thumbnails and text identify both responses in the legend.
Reduced motion disables continuous following.

Foreground building reveal is **on by default on every page access**; Camera
options can turn it off for the current visit. Full city stays opaque. Logarithmic depth keeps thin
road/facade layers stable across kilometre-scale perspective views. Shared opaque
materials and instanced vehicle colors retain geometry and draw-call efficiency.
Map picking uses real anchors and click/drag separation, with search/dropdown
alternatives. [The camera contract](../docs/CAMERA_AND_3D_MAP.md) covers details.

## Headed desktop acceptance

Use the existing project Python environment, an installed Chrome and pinned
optional QA dependencies. These commands do not download a browser.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
# Serve the production build on 5185 as above. Use a fresh output for each attempt.
.\.venv\Scripts\python.exe -B web/tests/desktop_product_acceptance.py --base-url http://127.0.0.1:5185/ --output local-runtime/desktop-product-NEW --require-recording --measure-seconds 30
.\.venv\Scripts\python.exe -B web/tests/real_signal_stoplines.py --base-url http://127.0.0.1:5185/ --output local-runtime/stoplines-NEW
```

The product harness covers desktop
window sizes, independent scroll regions, keyboard controls, reduced motion,
map/search controls, world/ghost isolation, catalog/graphics recovery and actual
rendered instance matrices. `--build-manifest` additionally binds served bytes to
an isolated production inventory. Inspection pages are separate from performance
pages; never benchmark with `?inspect=1`.

Rendering observations report browser presentation cadence and JavaScript/draw
submission time, not completed GPU execution. Retain device, renderer, resolution,
asset/recording hashes and screenshots. Check several camera tilts/yaws and
paused repeats; one frame is insufficient. `--headless` is supplementary capture.
Tests never substitute synthetic traffic into the public catalog or start SUMO.

Run the read-only, source-bound public presentation audit separately:

```powershell
node --experimental-strip-types web/scripts/audit-presentation.mjs --catalog web/public/replays/catalog.json --output local-runtime/presentation-NEW.json
```

The output path must be new. It verifies lossless transport, every 0.5 s sample
and exact lamp timelines, then classifies eligible front-bumper stop-line
crossings. Red or unresolved classifications produce a nonzero exit status.
This does not replace raw SUMO/lifecycle audits or establish policy superiority.

## Optional local generation

Prepare Python/SUMO using [the local adapter instructions](../api/README.md).
Use unused loopback ports; keep any existing read-only demo service intact.

```powershell
# Repository root, configured Python/SUMO environment:
.\.venv\Scripts\python.exe -m api.server --enable-generation --port 8782
# Separate terminal, for this local viewer only:
$env:VITE_API_BASE = 'http://127.0.0.1:8782'
npm --prefix web run dev -- --port 5183 --strictPort
```

The local server
advertises real capability, accepts one paired exploratory job at a time and
returns actual queued/running/completed/failed states. Playback begins from a
completed recorded result; it is not live streaming. The saved immutable request
ID/settings survive an interrupted response. Recovery reads the known ID before
an explicit same-ID retry. Closing the page does not cancel a running simulator.
Leave `VITE_API_BASE` unset for public builds.

`current_job_recovery.py` checks an existing genuine completed job through GETs
and same-tab reload, preserving original identity and artifacts. It does not
prove that the UI originally submitted that job. Local exploration seeds and all
inspected outcomes must be declared/excluded according to
[the study workflow](../evaluation/STUDY.md); they are not untouched test data.

## Historical harnesses and evidence

Older `browser_smoke.py`, `desktop_layout_checks.py`, `real_replay_smoke.py` and
`real_job_recovery_smoke.py` retain selectors and strict source-bound preview
requirements for their original checkpoints. Use the current harness for the
current UI. Do not weaken historical manifest guards or inherit their acceptance.
The original committed preview can be stale relative to later source; rebuild it
only from a verified committed cohort using its documented helper.

`selection_inspector_smoke.py`, `map_selection_protocol.py` and the interrupted
request fixture use isolated, labeled synthetic UI responses. Their screenshots
are contract tests, not traffic/model evidence. The genuine replay harness reuses
retained qualified raw recordings without rerunning SUMO. `?inspect=1` exposes
actual instance buffers only on explicit QA pages; ordinary use collects no such
snapshots. Numerical pose/contact checks are distinct from pixel review.

Historical `3060716` results accepted the smaller city's scoped real replay,
ghost isolation and tyre contact. The later desktop redesign was frozen untested
at the owner halt. Those facts remain attached to their old sources. Current
public captures, source-bound product acceptance and any learned-study release
have separate artifacts and must not be inferred from those earlier checks.

Root `DESIGN.md` owns visual direction and `docs/VIEWER_AND_DEMO.md` owns behavior.
No trained or held-out improvement follows from a working viewer or one demo.
