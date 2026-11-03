# AFTERLIGHT viewer

React / Three.js instrument for the original city and paired recorded SUMO worlds. No fake moving traffic or benchmark numbers are included. Until real replays are published, the viewer is explicitly **City exploration**.

## Local commands

```powershell
cd C:\Github\afterlight\web
npm ci
npm run build
npm test
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173`. All acceptance tests and browser QA belong on Omen. Cloud compilation has succeeded; this is not browser, test-suite or performance evidence.

`prepare:assets` copies the canonical repository assets into ignored `public/assets/` for dev/build. Do not edit those generated copies. Original city glTF transforms are preserved. A SUMO front-bumper pose is converted to model center using recorded length and clockwise-from-north heading, then mapped `[x,z,-y]`.

## Recording contract

`public/replays/catalog.json` contains `schema: afterlight.catalog.v1` and `runs`. Each run has `id,title,url,seed,pickup_id,hospital_id,policy,duration_s`. Relative `url` resolves against `/replays/`. Replay schema is `afterlight.replay.v1` with `scenario.network_kind` explicitly `fixture` or `city`. Fixture data is shown as text/evidence, never atop the city. Both worlds must carry identical absolute frame timestamps. They remain separate objects; the ghost is a render clone of the baseline ambulance only.

For an explicit local API library, set `VITE_API_BASE=http://127.0.0.1:8765` before starting Vite. The viewer fetches `/api/catalog`; this does not claim live simulation. Generation controls appear only when the explicitly enabled local server reports that capability.

### Exploration seeds and scientific studies

Local generation is exploration, not untouched benchmark evidence. Keep an
operator record of every seed whose outcomes you inspect, and include those
seeds in a future study spec's required `declared_exploration_seeds` list. Changing
regime, route or dispatch does not make that seed untouched. Seed 7 and all pilot
seeds are excluded separately. After freezing a study, do not preview its seeds
through local generation. This manual declaration is not an automated audit or
proof of complete exploration history; see `evaluation/STUDY.md`.

## Omen browser acceptance matrix

- Desktop 1440×900 and desktop window resizing: no horizontal overflow, legible controls, city asset visible and road/marker alignment.
- Inspect city glTF original root transform; select P001 and both hospitals; verify markers at canonical anchors.
- Keyboard: visible focus, native select/search, reset camera, timeline, play/pause when a real recording exists.
- Reduced motion: no auto-follow or autoplay; system preference respected.
- Empty catalog: no traffic or metrics; static exploration label, recording selector unavailable.
- Failed catalog/replay: useful retry, old replay/metrics cleared; cancel loading and rapid selection changes cannot restore stale data.
- Real city run: equal world clock on seek, baseline inspection, ghost toggle/opacity; no invented interpolation or duration normalization.
- Fixture run: text-only fixture view, no vehicles on unrelated city geometry.
- WebGL context failure: original static preview plus readable evidence and retry.
- Inspect browser console/network and actual GPU frame times. No performance threshold is claimed before measurements.

## Design ownership

Root `DESIGN.md` is normative. `src/styles/tokens.css` maps its semantic colors, sans/mono roles, spacing unit and radius once; `app.css` and scene rendering consume this miniature-at-twilight direction. Native HTML selects/search/ranges/checks own keyboard behavior. `docs/VIEWER_AND_DEMO.md` owns interaction truth. No toast/modal/CRUD system is needed for this single read-only instrument. No remote fonts or stock assets.

Impeccable launcher was unavailable in this checkout; context and references were read directly. Visual acceptance remains pending Omen captures, not self-certified from compilation.

### Resilience and rendering checkpoint

Catalog entries are validated before selection; recording URLs are confined to the configured library origin. Aborted requests cannot replace current errors or results. City-map errors have a separate retry. Baseline inspection labels its solid vehicle as baseline, never AFTERLIGHT. The 3D module loads separately from the accessible UI (about 208 KB raw UI / 601 KB raw renderer at this checkpoint). Paused, unchanged views do not redraw the GPU; vehicle pools update on changed recorded frames. These are implementation/build facts, not measured browser-performance claims. Mobile places the city before the full settings panel.

The evidence panel formats scalar outcomes and each civilian lifecycle count separately, rather than dumping queue arrays into a cell. Nested provenance remains safely text-rendered. Recorded queue histories are charted with a shared absolute axis, distinguishing them from the predeclared recovery metric. Invalid/censored pairs retain an explicit warning. Playback UI updates are bounded to 10 Hz; React state updater functions are pure. Source is formatted for review. Smooth render-only pose interpolation now follows adjacent recorded samples on the shared animation clock; signals and metrics remain sampled observations. New/removed vehicles and discontinuities are not fabricated. This implementation still requires the Omen visual and runtime checks.

### Geometry and decision integrity

City overlays now require `provenance.canonical_map_sha256` to match a SHA-256 digest computed from the actual fetched canonical map bytes. Mismatches preserve evidence but disable the traffic scene. Exported per-controlled-link lane geometry drives symbolic movement arrows; a junction is never represented as universally green. The selected route is a canonical road-center reference line, not an invented lane trajectory. Dispatch inputs, frozen requests and actual priority/release events can be inspected independently of playback. The renderer module has an error boundary, keeping HTML evidence available if 3D code fails.

### Explicit local generation

Start the loopback API with generation enabled, then opt the viewer into that API:

```powershell
# Repository root, in the configured Python environment:
python -m api.server --enable-generation --port 8765
# Separate terminal:
cd web
$env:VITE_API_BASE = 'http://127.0.0.1:8765'
npm run dev -- --port 5173
```

The panel is health-gated. It submits one real paired job, shows actual queued/running/completed/failed state, and opens a completed result only on request. It is **local generation**, not a live traffic stream. No progress percentage, model-training claim or automatic POST retry is invented. A client-chosen request ID and original settings are saved before POST and retained in session storage. An interrupted response first triggers read-only recovery; an explicit retry reuses that exact ID and settings, so the server can return the same job rather than create a duplicate. Closing the viewer does not cancel a running simulator.

Optional Omen-only reproducible browser smoke (using already installed Playwright and Chrome, with the viewer running):

```powershell
python web/tests/browser_smoke.py --base-url http://127.0.0.1:5173 --output local-runtime/browser-smoke
# For a viewer configured with VITE_API_BASE, add --catalog-path /api/catalog.
```

The script defaults to desktop screenshots, browser errors, empty/actual recording behavior, catalog error/retry and WebGL context recovery. Legacy mobile checks are optional and outside the current acceptance target. It does not download a browser or disable sandbox protection. It is not a complete accessibility, traffic-validity or performance benchmark.

Vehicle templates alone are normalized around their longitudinal/lateral footprint center, then scaled per instance to actual SUMO `length_m` and optional `width_m`. Their ground/up geometry is preserved. The city root is never normalized. This makes the authored model's nose agree with the recorded front bumper rather than assuming all authored mesh dimensions equal simulator type dimensions.

The browser smoke launcher defaults to headed Chrome with `chromium_sandbox=True`, excluding unsafe sandbox/shared-memory disabling defaults; `--headless` is an explicitly supplementary capture mode, not actual headed-GPU performance evidence. No GPU override is supplied.

For the optional interrupted-request/idempotency UI fixture, configure `VITE_API_BASE` before starting the viewer, then run `python web/tests/local_generation_smoke.py`. This separate script intercepts every API request in an isolated browser context; it uses **no simulator, no traffic traces and no outcome metrics**. Its labeled synthetic screenshot/report must not be presented as traffic evidence. It checks a lost POST response, known-ID read recovery, and explicit same-ID/same-settings retry after route controls change.

### Implemented contract hardening — acceptance is source-specific

Replay acceptance now binds the exact requested catalog metadata, verifies published byte counts/checksums when present, and mirrors the exporter's ordinary-baseline/world-identity/cadence/no-physical-ghost constraints. Nested city geometry and event timestamps fail closed before rendering. Saved-job recovery disables new submissions while in flight and stale responses cannot replace a newer request. Runtime rendering exceptions halt the scene into its retryable preview instead of leaving an apparently live stale canvas. Scoped keyboard controls pan/zoom/reset only while the canvas has focus; follow mode uses the AFTERLIGHT trajectory in both inspection views to preserve a shared comparison camera.

Compilation is not runtime acceptance. Run all new unit/browser regressions on the pinned commit on Omen before treating this checkpoint as validated.

Catalog `policy` is a machine identifier; optional `policy_label` is presentation only and `lead_s` binds the recorded lead. The matching exporter catalog contract is implemented; both sides still require acceptance on the same source cohort. All network JSON readers (catalog, canonical map, recordings and local-job responses) enforce the 64 MiB decoded-byte limit while streaming, including missing/compressed Content-Length. They require valid UTF-8, reject nesting beyond 64 containers including the root, and reject nonfinite numbers even in unused metadata. Quoted brackets do not count as nesting; exact original recording/map bytes remain the checksum input. These newer browser guards still need Omen acceptance. Local job status and replay completion are guarded against a newer operation before any state update.

## Offline selection evidence acceptance

The optional inspector distinguishes a frozen offline selector from the original
fixed-lead controller that produced the recording. Artifact hashes are declared
references, not browser-verified model contents. One displayed recording does not
establish held-out gain. A present metric status must match its world status.

For the separate **synthetic UI-only** contract harness on Omen, serve the pinned
preview and use a fresh output directory:

```powershell
python web/tests/selection_inspector_smoke.py --base-url http://127.0.0.1:5173 --output local-runtime/selection-inspector-new-attempt
```

This headed desktop harness intercepts its own fixture responses and watermarks
its screenshots. It covers learned/analytical labels, original fixed physics,
keyboard disclosure, legacy absence and malformed-evidence rejection. It does
not run SUMO, train a model, produce real traffic, or establish a scientific
result. It is authored but not yet accepted on Omen. Never register its fixtures
in the public recording catalog.

## Genuine city replay inspection (Omen only)

After the complete traffic qualification chain succeeds, serve the committed
preview and inspect its existing seed-7 city recording without rerunning SUMO:

```powershell
python -B web/tests/real_replay_smoke.py --run local-runtime/acceptance/ATTEMPT/traffic/city-sparse --base-url http://127.0.0.1:5173 --output local-runtime/real-city-visual-NEW
```

Replace `ATTEMPT` with the retained qualified attempt and use a fresh output
folder outside its traffic evidence tree. The harness re-audits the original
fixed/ordinary/city chain, verifies exact replay bytes before decoding, and binds
served viewer hashes separately from the simulator source commit. It intercepts
only the catalog/recording responses in its isolated browser context using those
**genuine recorded bytes**; it neither publishes a recording nor generates one.

The opt-in `?inspect=1` mode exposes actual instance-buffer matrices after render.
Checks compare active traffic and the render-only baseline ambulance at the same
absolute times, including interpolation when available, then verify ghost-off
and baseline-view isolation. Ordinary browsing does not collect these snapshots.
Do not benchmark performance in inspection mode. Matrix agreement is not visual
certification of roads, lane positions, stop lines, vertical placement or
occlusion: review the retained screenshots separately. The new harness and
telemetry require Omen acceptance; cloud compilation alone is not a pass.

## Recover the same genuine API job (Omen only)

After `scripts/api_real_acceptance.py` records `terminal_verified` or
`recovery_verified`, keep its generation-enabled API server and job directory
available. Serve the matching committed preview, then use a fresh output folder:

```powershell
python -B web/tests/real_job_recovery_smoke.py --acceptance local-runtime/api-real-ATTEMPT --base-url http://127.0.0.1:5173/local.html --output local-runtime/api-ui-recovery-NEW
```

This headed desktop check seeds a fresh browser session with the **actual saved
job ID and parameters**, observes genuine GET responses without interception,
opens the completed recording, and repeats recovery after a same-tab reload.
It binds the served viewer/assets, raw replay bytes and unchanged before/after
job identity to the original accepted seed-7 pilot. It submits no POST, launches
no SUMO process, and does not consume held-out data. This is seeded saved-job
recovery coverage, **not proof the UI originally submitted the job**. It requires
Omen execution; authoring or cloud compilation is not a pass.

Vehicle ground contact uses the authored road surface at render Y = 0.18 m:
`assets/src/generate_city.py` places a 0.12 m thick road box at Blender Z =
0.12 m. Each vehicle template caches the actual lowest baked geometry point;
its instance is placed at SUMO elevation + road surface minus that point.
This applies equally to the ordinary render-only ghost and solid vehicles,
without editing GLBs, canonical XY, recorded trajectories, or vehicle height.
The contact correction and its authored CPU regressions require Omen acceptance.
The genuine replay harness also checks the rendered ambulance's lowest world
bound against its recorded SUMO elevation + 0.18 m. This numerical contact check
is separate from screenshot review of road alignment, stop lines and occlusion;
the correction is not considered passed until it is measured on Omen.
