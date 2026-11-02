# Pass 2 — architecture and contracts

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

The browser consumes evidence; it does not generate experimental truth. Blender authors appearance, not traffic behavior. A local development adapter may invoke Python, but the public static site never implies a backend exists.

## Decision model

At dispatch `t_d`, capture queue lengths, recent arrival estimates, signal phases and elapsed phase time, downstream occupancy, and ambulance position/estimated travel times. Freeze arrival estimates for this decision. Do not expose future route-file departures, latent demand settings or future simulator observations to either learned or analytical inference.

Candidate lead `L` is one of `{0, 5, 10, 20, 30}` seconds. For intersection `i`, request start is `max(t_d, ETA_i_at_dispatch - L)`, where ETA is an absolute simulated timestamp. This is a request, not an unsafe instantaneous switch: the shared scheduler enforces minimum green, yellow and all-red transitions.

A single depth-limited tree regressor is the initial model family: predict a scalar residual in the predeclared objective J (seconds-equivalent), not independent component residuals. ExtraTrees is a possible validation-stage alternative only if the simple tree is insufficient; not a prevalidated winner. Use validation to choose model/hyperparameters and fixed objective weights; freeze before test. Prefer interpretable features and a small model over adding neural depth for appearance.

All priority variants within each evaluated network use the same transition, release and recovery scheduler; ordinary fixed-time control has no special recovery. Otherwise a comparison could mistakenly credit learning for a different post-priority controller. Recovery initially follows a documented debt/queue-aware legal phase schedule with capped service starvation; no claim of guaranteed bounded waits under infeasible demand.

## Planned modules and ownership

| Planned module | Responsibility | Explicit non-responsibility |
|---|---|---|
| `sim/` | Network, routes, policy-neutral runner and observations | UI state or fabricated counters |
| `policies/` | Fixed/actuated, immediate, fixed lead, analytical, learned selectors | Breaking legal phase transitions |
| `models/` | Feature schema, fit, prediction, persisted metadata | Reading future arrivals |
| `evaluation/` | Splits, paired metrics, uncertainty, manifests | Choosing test seeds after seeing winners |
| `export/` | Canonical replay and provenance | Correcting bad experiment results cosmetically |
| `web/` | Replay, accessible charts, controls, provenance | Claiming recorded traces are live |
| `assets/source/` | Original procedural Blender source | Unlicensed downloaded models |

These are proposed paths, not existing implementation.

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

The map target is 20–25 intersections, with a working 25-node authoritative graph, two hospitals and about 100 pickup anchors. A graph manifest owns node/edge geometry, lanes, junction IDs, hospital access and pickup IDs. SUMO and Blender both derive from it; no independently drawn frontend road network. Validate every offered pickup-to-hospital route for connectivity, drivable direction and endpoint placement before enabling it. A pickup anchor is a route point, not an additional junction.

Maintain two scale tiers: (1) three-junction fixed-route correctness fixture and (2) the expanded city. Validate scheduling, route length, action diversity, transition timing and complete runtime on tier 2 before claiming the model works there. The original five-lead action and frozen ETA are corridor experiments; adapting them to variable-length routes requires a documented feature/action contract and newly appropriate held-out evaluation. Do not silently treat every city route as already covered by a three-junction model.

## Ghost-ambulance world isolation

Maintain separate `world_id=afterlight` and `world_id=baseline` simulations. Pre-generate the same exogenous traffic schedule, vehicle types/routes, dispatch and ambulance route for a paired run. AFTERLIGHT contains the solid ambulance and its own civilians/signals responding to AFTERLIGHT policy. Baseline has ordinary signals, its own civilians/queues and its own ambulance without AFTERLIGHT preemption. Policy effects can change insertion and queues; identical scheduled demand does not mean identical realized traffic.

Primary rendering uses AFTERLIGHT traffic/signals plus its solid ambulance. The baseline ambulance pose becomes a translucent light-blue, gently emissive **render-only ghost**. Never add it as a vehicle, collider, detector input, TraCI object, priority request or signal trigger in the AFTERLIGHT simulator. Baseline traffic/signals remain separately available for inspection rather than blended into active truth.

Both worlds use the same absolute simulated timestamp, origin and route scale. Do not normalize journey duration, speed up a losing trace or interpolate invented progress to make a race. A local live pair may advance with a synchronization barrier; if one world stalls, pause shared playback and label the state rather than presenting stale pose as live. Static replays use the same adapter/time contract.

Ghost position may overlap active-world vehicles or appear to pass an active-world red light because its own world has different queues/signals. Show a permanent “Baseline ghost — separate world” label, ghost toggle and separate baseline inspection view. Never adjust its trajectory to avoid this visual discrepancy. Show actual elapsed/arrival times and censoring; distance gaps alone are not claimed seconds saved.

### Graph integration details

The topology worker's current draft proposes an approximately 1 km² irregular 5×5 primary-junction district with service roads; this is a draft, not a validated SUMO export. Distinguish primary signal junctions from driveway/service geometry nodes. Final graph counts and hashes come from validation, not this plan.

Use deterministic pickup/hospital IDs and valid network curb anchors rather than arbitrary building centroids. With 100 pickups and two hospitals, validate reachability for the 200 potential origin/destination pairs, including permitted vehicle access and endpoint placement. This is a graph-connectivity target, **not 200 benchmarked traffic cases**. Persist route availability and manifest revision for UI selection; do not expose a visually plausible but disconnected route.
