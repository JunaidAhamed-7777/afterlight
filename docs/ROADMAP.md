# AFTERLIGHT roadmap — implementation checkpoint

All times **IST (UTC+05:30)**. Target submission-ready November 4 at 16:00;
recorded organizer deadline November 4 at 20:00, subject to the final rules check.
The morning checkpoint is not completion. The owner authorized continued work
while Omen is off; cloud development continues, but tests and experiments stay on
Omen. Scope depends on actual acceptance and measured pilot runtime.

## Original documentation checkpoint — November 3, 02:30 IST

The original asset pack is published and verified: 25 primary junctions plus 32 access/bend/terminal nodes, two hospitals, 100 curb anchors, nine GLBs (1,268,584 bytes). Graph reachability passes for all 200 pickup/hospital pairs; this is not SUMO or traffic validation. Preserve city glTF root transforms and the vehicle center/front-bumper convention. No simulation, viewer, model or benchmark result exists at this checkpoint.

Implementation is on the cloud development PC. **All test suites, browser QA, simulation experiments/training and performance measurements run on the owner's Omen checkout at `C:\Github\afterlight`.** Cloud compilation/development is permitted; it is not acceptance evidence. Publish focused checkpoints, relay exact commits and commands to the Omen tester, fix failures, then recheck the affected behavior there. Never label a pending local check as passed.

## Updated progress — November 3, 10:45 IST

The overnight allocations are superseded by the evidence gates below. The
owner explicitly continued the whole-day build and then switched off Omen.
Cloud implementation continues; all acceptance and experiments wait for Omen.
Desktop-only is now the target (`AGENTS.md`); real 3D geometry and low-poly
instanced civilian traffic remain mandatory.

Actual `7ef8ffe` evidence: desktop browser 14/14, preview 9/9, asset 8/8, frontend
Node 57/57 and production build passed; fixture/city network conversion had no
warnings. A previous real fixture pair was invalid due to a collision. Its
insertion fix has not yet passed a new real run. Last Python batch outcome is
unknown after transport loss; inspect saved records/processes before retrying.

Next critical gates, in order: resolve that unknown execution; validate newer
source and geometry; run fresh fixture plus ordinary/ordinary control; inspect
city lane/stopline geometry and sparse city traffic; only then measure pilot
runtime/action diversity, freeze a feasible study, and evaluate untouched data.
No public traffic recording or learned-performance claim until genuine evidence
passes these gates. Retain the November 4 submission buffer; reduce experimental
breadth before correctness or the actual browser demo.

## Critical path

Documentation checkpoint → three-junction legal scheduler and accounting → canonical full-city importer → genuine paired traces → truthful polished viewer → pilot → frozen evaluation. Frontend and simulation can proceed in parallel after this checkpoint; shared schemas and geometry remain authoritative. A small valid study is mandatory; photorealism is not.

| Next gate | Work and required evidence |
|---|---|
| While Omen is off | Finish scoped source fixes, preserve failed/unknown evidence, reconcile docs and prepare pinned acceptance commands. No cloud testing, training or invented replay. Latest V3/map-picking preview is source `a6b2c12`, aggregate `2710cd6`; later backend changes do not inherit its build. |
| First reconnect | Resolve the interrupted Python batch from saved records/process state before retry. Run the selected source cohort's unit/build/desktop checks, V3 geometry and canonical map-picking regressions. |
| Traffic correctness | Fresh three-junction pair and ordinary/ordinary negative control; retain failures. Audit city lane/stop-line placement, then sparse city traffic. Clean conversion alone does not pass this gate. |
| Experiment feasibility | Measure runtime and useful lead diversity. Freeze feasible whole-realization splits, objective, model-selection rules and capture case IDs before collection. The source-implemented offline selected-replay bridge must pass acceptance using actual captured traces, preserving original fixed-candidate physics and separate selector provenance; it is not a live learned controller. |
| Evaluation and replay | Only after valid collection: fit on training, choose on validation, freeze, evaluate untouched test. Retain invalid/censored cases and publish only audited real captures. No held-out gain means an honest inconclusive/non-learned result. |
| Nov 4, by 13:00 | Capture the actual desktop product/demo and truthful results or limitations; reconcile reproduction, attribution, licensing and evidence links. Reduce experiment breadth before correctness. |
| Nov 4, 13:00–16:00 | Owner review and submission-ready package. A missing validity/model gate remains visible; do not call an unfinished experiment complete. |
| Nov 4, 16:00–20:00 | Protected contingency for authorized corrections/submission and receipt verification. |

The desktop viewer keeps true 3D geometry, X/Y/Z camera controls and localized
building transparency. The 25 MB map budget is a ceiling, not a target. Keep
civilian cars/trucks/bikes simple and instanced. Existing responsive behavior is
preserved, but mobile optimization/testing is not part of the current work.

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

**No useful action diversity:** simplify the action design using training evidence only, or demonstrate why the validation-best fixed lead is sufficient. **No held-out ML gain:** ship the stronger non-learned policy and retain the evaluated ML experiment transparently; no AI-performance claim. **No hosting:** local executable system and recorded demo, with source/setup intact. **No verified MCP:** document capability blocker; do not install or expose services without required authorization. **No stable 3D performance:** reduce geometry detail, render resolution and optional effects while retaining actual 3D buildings, roads, vehicles and ambulance. Parallax/billboard substitution is not allowed.

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

The expanded 20–25-intersection city, two hospitals/~100 pickups and baseline ghost were added after the original review. The documentation-first revision and original Blender asset work are complete. The documentation-before-code checkpoint was completed; do not repeat that gate. Keep the existing deadline; new scope does not extend time. Map and asset work can resume against one accepted graph after that gate.

1. **Authoritative topology first:** graph IDs, roads, hospital access and pickup anchors; validate direction/connectivity. Existing three-junction fixture remains the first simulation test, not the final whole map.
2. **Thin end-to-end spike:** graph → SUMO geometry → Blender GLB → renderer; cardinal/bumper fixtures; ordinary and AFTERLIGHT traces; render-only ghost with world-isolation tests.
3. **Expanded runtime gate:** pilot actual city rollouts and route lengths before committing the old dataset budget. If full-city ML is not feasible, expose the city honestly with validated corridors and mark unsupported runs; do not fake arbitrary-route intelligence.
4. **Low-poly production:** cuboid color-varied buildings, simple cars/trucks/bikes, two hospital landmarks, detailed ambulance shared with the ghost. Instancing/LOD/material sharing before extra decorative detail.
5. **Product gate:** searchable valid pickup/hospital selection, clear local-generation/public-recorded modes, loading/error/retry, disconnect handling, desktop controls, keyboard/reduced motion, results fallback and no stale metrics.
6. **Performance gate:** measure worst demand and camera, per-file transfer, visible triangles/draw calls, frame-time p95 and memory stability. Optimize ghost overlay first; optional paired city is secondary.
7. **Evidence gate:** group-held-out randomized scenarios, route coverage statement, actual baseline trajectory and unchanged timings. Randomness is not an anti-overfitting proof.

Preserve a polished browser-recorded demo and truthful results. Cut city ornament, then unsupported route breadth and simultaneous duplicate rendering before cutting accounting or validity. “100 pickups available to select” must never be used as a substitute for 100 evaluated routes. New stages replace discretionary polish time in the existing schedule; they are not additional time after the deadline.
