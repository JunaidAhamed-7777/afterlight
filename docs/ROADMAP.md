# AFTERLIGHT roadmap — implementation checkpoint

All times **IST (UTC+05:30)**. Planning begins November 3, 2026 around 01:00. Target submission-ready November 4 at 16:00; organizer deadline November 4 at 20:00. These are bounded work allocations, not guarantees that unmeasured training/rendering will finish in a stated time. Actual pilot results determine scope cuts.

## Current checkpoint — November 3, 02:30 IST

The original asset pack is published and verified: 25 primary junctions plus 32 access/bend/terminal nodes, two hospitals, 100 curb anchors, nine GLBs (1,268,584 bytes). Graph reachability passes for all 200 pickup/hospital pairs; this is not SUMO or traffic validation. Preserve city glTF root transforms and the vehicle center/front-bumper convention. No simulation, viewer, model or benchmark result exists at this checkpoint.

Implementation is on the cloud development PC. **All test suites, browser QA, simulation experiments/training and performance measurements run on the owner's Omen checkout at `C:\Github\afterlight`.** Cloud compilation/development is permitted; it is not acceptance evidence. Publish focused checkpoints, relay exact commits and commands to the Omen tester, fix failures, then recheck the affected behavior there. Never label a pending local check as passed.

## Critical path

Documentation checkpoint → three-junction legal scheduler and accounting → canonical full-city importer → genuine paired traces → truthful polished viewer → pilot → frozen evaluation. Frontend and simulation can proceed in parallel after this checkpoint; shared schemas and geometry remain authoritative. A small valid study is mandatory; photorealism is not.

| Window (IST) | Focus | Exit evidence / decision |
|---|---|---|
| Nov 3 02:30–03:00 | Publish this final document pass; pin replay, coordinate and simulation interfaces; begin implementation. | Remote documentation commit precedes application code. Preserve original assets; do not repeat completed art work. |
| 03:00–04:30 | Python three-junction fixture, legal scheduler and demand accounting; React/Three.js original-asset city and accessible controls in parallel. | Omen executes fixture/unit checks; city root transform preserved; no invented moving traffic or benchmark values. |
| 04:30–06:00 | Full-city conversion, paired-run exporter and local API; synchronized recorded viewer and fallback/error states. | Real independent-world traces, matching demand hashes and absolute time; canonical roads and route selection; Omen integration checks. |
| 06:00–08:00 | Iterate on Omen failures, pilot runtime/action diversity, responsive/keyboard/ghost review and documentation. | Working tested vertical slice and honest readiness report at 08:00. Continue useful passes to this checkpoint; completion is not assumed. |
| 08:00–12:00 | If pilot supports it: freeze practical train/validation budget and residual model; otherwise strengthen valid baseline/evidence. | Group-disjoint manifests, measured runtime, candidate diversity, frozen objective and feature schema. No dataset-size promise before pilot. |
| 12:00–16:00 | Freeze evaluation and run untouched held-out study when feasible; publish genuine replay subset. | Failure/censoring accounting and strong fixed-lead/analytical comparison. ML may be inconclusive. |
| 16:00–21:00 | Targeted product polish, evidence inspector, measured frame-time/accessibility checks. | Exact metrics/trace agreement and Omen visual evidence; no unsupported route claims. |
| 21:00–Nov 4 01:00 | Static release preparation, independent reproduction, provenance/license audit. | Local-only fallback if free hosting is unavailable; deployment only when authorized. |
| Nov 4 01:00–09:00 | Contingency and correction of known failures; no new scope. | Stable demo cases, complete evidence, no critical accounting/replay defects. |
| 09:00–13:00 | Capture actual browser demo, captions, screenshots and results table. | Actual app, explicit mode, civilian tradeoff, limitations and real sample count. |
| 13:00–16:00 | Submission-readiness checklist and owner review. | Repository/demo links, exact team/rules/license details; submission requires authorization. |
| 16:00–20:00 | Four-hour contingency before organizer deadline. | Authorized corrections and verified receipt if submission is requested. |

## Parallel work boundaries

**Simulation/evaluation owner:** network/configuration, scheduler, features, model and all metric truth. **Visual/frontend owner:** original assets, one canonical coordinate transform, replay/live presentation and UX. **Release owner:** reproducibility, provenance, README and submission verification. One person/agent may fill multiple roles, but do not let separate implementations redefine metrics or time independently.

## Must-have gates

- Three junctions, fixed route, no emergency privilege confound, legal phase scheduler and finite hold/release.
- Complete scheduled-vehicle accounting and a common horizon/drain protocol.
- Group-disjoint train/validation/test and no future information in features.
- Immediate, validation-best fixed lead, analytical and learned comparison; ordinary baseline.
- Real evidence for any claimed model benefit; honest fallback if absent.
- Shared scene/time contract, original Blender-authored assets, truthful recorded/live labels.
- Public complete source, tested local instructions, screenshots/GIF, actual metrics, AI-assistance disclosure.
- Polished **browser-recorded demo video** remains core even if deployment fails.

## Scope cuts in order

1. Expensive offline Cycles cinematic rendering; never cut the demo video itself.
2. Volumetrics, reflections, bloom, detailed façades, wheel animation, extra prop variants.
3. Browser model inference and optional max-pressure baseline if its correctness cannot be established; retain required strong fixed-lead/analytical baselines.
4. Simultaneous dual viewport if performance fails: use synchronized toggled comparison with the same clock/camera.
5. Rich traces for every benchmark episode: retain scalar outcomes for all and rich traces for a declared representative subset.
6. Dataset size based on measured runtime, with smaller-sample uncertainty clearly reported.

Never cut honest accounting, untouched test, input provenance, legal transitions, evidence labels or reproducibility to preserve visual spectacle.

## Go / no-go decisions

**No useful action diversity:** simplify the action design using training evidence only, or demonstrate why the validation-best fixed lead is sufficient. **No held-out ML gain:** ship the stronger non-learned policy and retain the evaluated ML experiment transparently; no AI-performance claim. **No hosting:** local executable system and recorded demo, with source/setup intact. **No verified MCP:** document capability blocker; do not install or expose services without required authorization. **No stable 3D performance:** reduce to an attractive 2.5D miniature retaining original assets and accurate traces.

## Submission acceptance record to fill with facts

- Repository commit and visibility check:
- Tested setup/environment and reproduction result:
- Dataset/model/result manifest hashes:
- Public viewer URL and exact mode, or local-only statement:
- Demo URL, screenshots/GIF and license attribution:
- Team information and AI-assistance disclosure checked:
- Final rules/eligibility check:
- Submission timestamp and verified receipt:

Blank fields are intentional pending work, not successful delivery claims.

## Post-three-pass scope revision — city, ghost and proper-product gate

The expanded 20–25-intersection city, two hospitals/~100 pickups and baseline ghost were added after the original review. The documentation-first revision and original Blender asset work are complete. **Publish the implementation checkpoint before application code.** Keep the existing deadline; new scope does not extend time. Map and asset work can resume against one accepted graph after that gate.

1. **Authoritative topology first:** graph IDs, roads, hospital access and pickup anchors; validate direction/connectivity. Existing three-junction fixture remains the first simulation test, not the final whole map.
2. **Thin end-to-end spike:** graph → SUMO geometry → Blender GLB → renderer; cardinal/bumper fixtures; ordinary and AFTERLIGHT traces; render-only ghost with world-isolation tests.
3. **Expanded runtime gate:** pilot actual city rollouts and route lengths before committing the old dataset budget. If full-city ML is not feasible, expose the city honestly with validated corridors and mark unsupported runs; do not fake arbitrary-route intelligence.
4. **Low-poly production:** cuboid color-varied buildings, simple cars/trucks/bikes, two hospital landmarks, detailed ambulance shared with the ghost. Instancing/LOD/material sharing before extra decorative detail.
5. **Product gate:** searchable valid pickup/hospital selection, clear local-live/public-replay modes, loading/error/retry, disconnect handling, responsive controls, keyboard/reduced motion, results fallback and no stale metrics.
6. **Performance gate:** measure worst demand and camera, per-file transfer, visible triangles/draw calls, frame-time p95 and memory stability. Optimize ghost overlay first; optional paired city is secondary.
7. **Evidence gate:** group-held-out randomized scenarios, route coverage statement, actual baseline trajectory and unchanged timings. Randomness is not an anti-overfitting proof.

Preserve a polished browser-recorded demo and truthful results. Cut city ornament, then unsupported route breadth and simultaneous duplicate rendering before cutting accounting or validity. “100 pickups available to select” must never be used as a substitute for 100 evaluated routes. New stages replace discretionary polish time in the existing schedule; they are not additional time after the deadline.
