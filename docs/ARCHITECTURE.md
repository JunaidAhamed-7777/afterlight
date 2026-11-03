# Architecture and contracts

## System boundary

```text
Versioned network + explicit arrivals + seed manifest
                    |
          Python experiment runner
                    |
   Observation at dispatch (past/present only)
                    |
 Analytical predictor + learned residual (optional by policy)
                    |
   Candidate scorer -> constrained signal scheduler
                    |
                  SUMO
                    |
   metrics + lifecycle events + canonical trajectory traces
                    |
       static React / Three.js replay viewer
```

The browser consumes evidence; it does not generate experimental truth. Blender authors appearance, not traffic behavior. The explicitly enabled loopback adapter invokes Python and later opens a recorded result; the public static site has no simulator backend. The diagram describes the research architecture. The product has genuine exported city pairs; training and held-out conclusions require their own frozen study artifacts and are not established by a playable recording.

## Decision model

At dispatch `t_d`, capture queue lengths, recent arrival estimates, signal phases and elapsed phase time, downstream occupancy, and ambulance position/estimated travel times. Freeze arrival estimates for this decision. Do not expose future route-file departures, latent demand settings or future simulator observations to either learned or analytical inference.

Candidate lead `L` is one of `{0, 5, 10, 20, 30}` seconds. For intersection `i`, request start is `max(t_d, ETA_i_at_dispatch - L)`, where ETA is an absolute simulated timestamp. This is a request, not an unsafe instantaneous switch: the shared scheduler enforces minimum green, yellow and all-red transitions.

A single depth-limited tree regressor is the initial model family: predict a scalar residual in the predeclared objective J (seconds-equivalent), not independent component residuals. ExtraTrees is a possible validation-stage alternative only if the simple tree is insufficient; not a prevalidated winner. Use validation to choose model/hyperparameters and fixed objective weights; freeze before test. Prefer interpretable features and a small model over adding neural depth for appearance.

All priority variants within each evaluated network use the same transition, release and recovery scheduler; ordinary fixed-time control has no special recovery. Otherwise a comparison could mistakenly credit learning for a different post-priority controller. Recovery initially follows a documented debt/queue-aware legal phase schedule with capped service starvation; no claim of guaranteed bounded waits under infeasible demand.

## Modules and ownership

| Module | Responsibility | Explicit non-responsibility |
|---|---|---|
| `sim/` | Network, routes, policy-neutral runner and observations | UI state or fabricated counters |
| `policies/` | Fixed/actuated, immediate, fixed lead, analytical, learned selectors | Breaking legal phase transitions |
| `models/` | Feature schema, fit, prediction, persisted metadata | Reading future arrivals |
| `evaluation/` | Splits, paired metrics, uncertainty, manifests | Choosing test seeds after seeing winners |
| `export/` | Canonical replay and provenance | Correcting bad experiment results cosmetically |
| `web/` | Replay, accessible charts, controls, provenance | Claiming recorded traces are live |
| `api/` | Explicit loopback local generation and recordings | Public hosted backend or fake live progress |
| `assets/src/` and original `.blend` scenes | Original procedural Blender source | Unlicensed downloaded models |

These paths now contain source implementation. Their presence is not a claim that SUMO, model fitting or product acceptance has passed; see the [actual validation log](validation/OMEN_LOG.md). A tree-training entry point is not a trained artifact.

## Reproducibility manifest

Each run must record schema version, commit, dependency versions, SUMO command/config hash, network hash, arrival-file hash, random seed, scenario family, split, policy/version, dispatch timestamp, model hash, candidate selection, objective weights, horizon and export hash. Keep raw outputs. A failed run is explicit, not silently omitted.

## Replay contract

- Time: simulated seconds from `t=0`, monotonic; dispatch and ambulance exit are events.
- Space: SUMO meters; export a single documented transform to Three.js axes and origin. Apply the same transform to roads, lights and vehicles.
- Vehicle IDs persist through every frame; vehicle types distinguish ambulance from civilian appearance without changing privileges implicitly.
- State fields: time, vehicle ID, position, heading, speed, active/arrived state; signal phase and queue observations; selected action and decision inputs at dispatch.
- Derived display metrics reference their exact evaluation definitions; interpolation changes only visual position, never metrics.
- Chunk traces by time or scenario. Manifest lists duration, sample rate, hashes, byte sizes and replay label.
- Validate missing timestamps, duplicate IDs, impossible jumps and endpoint mismatch before publication.

## Failure boundaries

If model training exceeds budget, reduce scenarios only using a predeclared pilot decision and state the resulting uncertainty. If Blender MCP is unavailable, author procedural Blender Python without claiming MCP was used. If WebGL fails, show static comparison images and a readable results table. If deployment fails, deliver local reproducibility and a clearly recorded demo. No fallback may manufacture a favorable benchmark.

## Pass 3 locked learning contract

Define `J = T_ambulance + lambda * D_civilian`, where `T_ambulance` is dispatch-to-exit seconds and `D_civilian` is mean excess journey time per scheduled civilian, including departure/insertion delay, only for runs completing the common drain protocol. Lambda is a dimensionless tradeoff weight fixed on training/validation before test. Failed drain is reported as censored with common-horizon burden and backlog, not assigned a fabricated complete-trip cost. Policy-caused invalid or censored runs rank infeasible behind feasible completed outcomes under identical predefined rules; report failure counts. They retain manifest rows but no invented finite residual target. Full evaluation retains hard episodes and reports selected-action failures before conditional finite-cost results; see the benchmark protocol.

Training label: `r(e,L) = J_SUMO(e,L) - J_analytical(x_e,L)`. Prediction: `J_hat(e,L) = J_analytical(x_e,L) + f(x_e,L)`. Enumerate candidates and select minimum predicted cost with a fixed tie-break. Actual component metrics are always reported separately. Residual labels must come from real simulations, never the same analytical formula being corrected.

Feature rows need source, unit, observation timestamp, sensor lag and inference availability. Arrival windows end no later than dispatch minus the declared lag. Forbid actual future passage, rollout queues/outcomes, seed IDs, demand-regime labels, future route departures and oracle action. Candidate rows share identical observed state; only candidate-specific analytical inputs differ.

ETA uses current ambulance position, route geometry and observed queue estimates; freeze its exact formula during validation. Log request plan, actual request, legal priority-green onset, passage and release for each junction. Configure minimum green, yellow, all-red, maximum priority hold and release timeout explicitly before experiment generation.

## Expanded-city contract (post-three-pass revision)

The canonical map has 81 primary intersections in a 9×9 grid, two hospitals in diagonal quadrants and 100 pickup anchors. Its 2,040 × 2,010 m footprint is exactly four times the original area. A graph manifest owns node/edge geometry, lanes, junction IDs, hospital access and pickup IDs. SUMO and Blender both derive from it; no independently drawn frontend road network. Validate every offered pickup-to-hospital route for connectivity, drivable direction and endpoint placement before enabling it. A pickup anchor is a route point, not an additional junction.

Maintain two scale tiers: (1) three-junction fixed-route correctness fixture and (2) the expanded city. Validate scheduling, route length, action diversity, transition timing and complete runtime on tier 2 before claiming the model works there. The original five-lead action and frozen ETA are corridor experiments; adapting them to variable-length routes requires a documented feature/action contract and newly appropriate held-out evaluation. Do not silently treat every city route as already covered by a three-junction model.

## Ghost-ambulance world isolation

Maintain separate `world_id=afterlight` and `world_id=baseline` simulations. Pre-generate the same exogenous traffic schedule, vehicle types/routes, dispatch and ambulance route for a paired run. AFTERLIGHT contains the solid ambulance and its own civilians/signals responding to AFTERLIGHT policy. Baseline has ordinary signals, its own civilians/queues and its own ambulance without AFTERLIGHT preemption. Policy effects can change insertion and queues; identical scheduled demand does not mean identical realized traffic.

Primary rendering uses AFTERLIGHT traffic/signals plus its solid ambulance. The baseline ambulance pose becomes a translucent light-blue, gently emissive **render-only ghost**. Never add it as a vehicle, collider, detector input, TraCI object, priority request or signal trigger in the AFTERLIGHT simulator. Baseline traffic/signals remain separately available for inspection rather than blended into active truth.

Both worlds use the same absolute simulated timestamp, origin and route scale. Do not normalize journey duration, speed up a losing trace or interpolate invented progress to make a race. Current local generation completes before playback; it is not live streaming. Any future streamed adapter would require a synchronization barrier and an explicit stalled state, not stale poses presented as live.

Ghost position may overlap active-world vehicles or appear to pass an active-world red light because its own world has different queues/signals. Show a permanent “Baseline ghost — separate world” label, ghost toggle and separate baseline inspection view. Never adjust its trajectory to avoid this visual discrepancy. Show actual elapsed/arrival times and censoring; distance gaps alone are not claimed seconds saved.

### Graph integration details

The canonical manifest defines 81 primary nodes, 120 additional access/service nodes, 233 roads and 77 signal controllers. All 200 pickup/hospital routes pass static network qualification; that is connectivity evidence, not 200 evaluated traffic cases. Two audited exploratory pairs are published at 0.5 s cadence. Their exact source, geometry, lifecycle and control checks are retained in [network qualification](validation/expanded-network-qualification.json) and [recording evidence](validation/expanded-city-recordings.json).

Historical checkpoint: `7ef8ffe` converted the earlier approximately 1 km², 5×5 primary-junction map without warnings. Its acceptance does not transfer to the fourfold expansion.

Use deterministic pickup/hospital IDs and valid network curb anchors rather than arbitrary building centroids. With 100 pickups and two hospitals, validate reachability for the 200 potential origin/destination pairs, including permitted vehicle access and endpoint placement. This is a graph-connectivity target, **not 200 benchmarked traffic cases**. Persist route availability and manifest revision for UI selection; do not expose a visually plausible but disconnected route.

### Imported stop lines and simulation time grid

Canonical `stop_line.distance_before_node_m` is the node-centered design target,
not a value that can be copied directly into SUMO `endOffset` (which is an extra
setback from the generated junction boundary). The current importer preserves
canonical road identity and origin, but lets netconvert construct lane endpoints.
Those generated endpoints are the runtime stop-line truth exported to the viewer.
Before full-city alignment or benchmark readiness is claimed, audit every
signalized incoming lane against its canonical target: signed longitudinal
setback, lateral offset, difference, and exact network hash. A difference larger
than 0.5 m is an explicit geometry-review flag, not an outcome-dependent excuse to
move vehicles or silently widen tolerance. Resolve the source/importer discrepancy
or document an intentional map revision before accepting the city fixture.
Numerical coordinate comparisons use 0.05 m tolerance; this is not a relaxation of
the target-alignment gate. Current automated geometry/control audits are retained with the qualified recordings. They do not establish universal visual or sub-centimetre certification across every route and camera.

Controller stage durations and maximum hold must be representable on the chosen
simulation step, which must also use whole positive SUMO milliseconds;
incompatible grids are rejected rather than rounding hard caps
upward. Frozen absolute requests can fall between ticks: activation occurs at the
first tick at or after the planned timestamp. The absolute request-timeout check
may likewise occur less than one step after its nominal deadline. Preserve both
planned and actual event timestamps; do not retime the replay or label them equal.
All priority variants use the same grid, controller, release and recovery logic.

Numerical deadline comparisons use a fixed absolute 1 ns tie tolerance, smaller
than the artifact audit tolerance and far below one simulation tick. This avoids
a floating-point boundary postponing a cap by a whole tick; actual event
timestamps are retained and meaningful early transitions remain prohibited.
The supported grid follows [SUMO's documented time-step contract](https://sumo.dlr.de/docs/Simulation/Basic_Definition.html),
with additional exact-controller-duration divisibility required by AFTERLIGHT.

## Desktop rendering and selection boundary

The enhanced city preserves the original glTF root and canonical map. Per-building
identity permits material batching with foreground reveal enabled on every page
access; a current-visit opt-out is not persisted. Full city stays opaque. Ground
and shared-color trees must never enter the building fade mask. True-perspective
Explore and orthographic Full city are views of the same physical world. X tilt,
Y heading and Z view-roll affect rendering only. Low-poly traffic stays instanced.

Opt-in map picking uses canonical curb/driveway anchors and the actual rendered
camera, including roll. It cannot select a ghost or traffic vehicle. A route click
must not be confused with a camera drag. The map-only lock covers loaded/loading
recordings and active/recovering/uncertain local requests; existing dropdowns may
still prepare a next journey without changing the immutable submitted request.
Desktop controls retain keyboard alternatives and explicit failure/readiness states.

The separate offline selected-replay bridge preserves the selected real fixed-lead world's policy, decision and
trace, maps source world IDs explicitly, and adds model/protocol/report/trace
provenance outside physical policy fields. It is not a new live learned controller;
a selected replay alone does not establish a trained model’s held-out benefit. Model/report release status belongs to scientific study artifacts.

## Dense recording transport and presentation

Public city recordings use a 3 s all-red clearance and retain every 0.5 s
simulation integration boundary. Both
worlds cover the same absolute window and keep original physical poses, events
and metrics. Coarse 2 s presentation previously moved three stopped cars across
stop lines before their exact green. Failed captures were retained and replaced
by fresh dense recordings; no guessed movement-specific trajectory gate was added.

Catalog `bytes`/`sha256` bind original decoded JSON. Optional `encoding: gzip` and
`transfer_bytes`/`transfer_sha256` describe its lossless wire container. The loader
accepts HTTP-decoded bodies or decodes gzip magic bytes, bounds both reads to
128 MiB, checks UTF-8/depth/finite numbers, validates the replay and binds selected
metadata before exposing outcomes. A module worker performs this work and
terminates on completion, failure or cancellation. Only the latest locally
returned recording is cached by the UI.

Signals use recorded states and exact audited control-event boundaries. A
reconstructed timeline must reproduce every saved lamp state; incomplete legacy
evidence falls back to sampled states. Movement arrows use imported lane/link
geometry and the inspected world. The ghost never supplies active-world lamps.
Pose interpolation remains presentational between adjacent real samples;
metrics are not interpolated. The read-only `web/scripts/audit-presentation.mjs`
checks exact public transport bytes, dense cadence and geometry-eligible
front-bumper stop-line crossings against those production lamp timelines. Its
red/unresolved result is separate from raw simulator correctness and scientific
policy comparison.

The renderer uses logarithmic depth for kilometre-scale perspective and thin
road/facade layers. Canonical road top is 0.18 m; visual hospital plazas top out
at 0.14 m to avoid equal-depth overlap. Vehicle colors are stable by ID and use
existing instance batches. The 50 MB shipped-asset budget is separate from
decoded replay memory. Measure desktop frame time and memory on the release
build. Vercel serves static output only; SUMO and fitting stay local.
