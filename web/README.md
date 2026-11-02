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

For an explicit local API library, set `VITE_API_BASE=http://127.0.0.1:8000` before starting Vite. The viewer fetches `/api/catalog`; this does not claim live simulation. Job generation UI is not implemented in this checkpoint.

## Omen browser acceptance matrix

- Desktop 1440×900 and mobile 390×844: no horizontal overflow, legible controls, city asset visible and road/marker alignment.
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
