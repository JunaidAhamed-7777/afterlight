# SUMO backend — implementation checkpoint

These commands are **pending Omen validation**, not claimed test results. All experiments and tests run on the owner's Omen; cloud work authors code only.

From repository root in the pinned Python 3.12 virtual environment:

```powershell
python -m unittest discover -s tests/sim -v
python -m sim.run --network fixture --output local-runtime/fixture-7 --seed 7 --policy fixed --lead 10
python -m sim.audit --run local-runtime/fixture-7
# Only after fixture correctness passes:
python -m sim.run --network city --output local-runtime/city-7 --seed 7 --regime sparse --policy fixed --lead 10 --pickup P001 --hospital HOSP_EAST
python -m sim.audit --run local-runtime/city-7
```

Choose a fresh output directory for each invocation; existing evidence is never overwritten. `sim.audit` checks schedule/frame alignment and accounting, not visual or performance superiority.

Use `eclipse-sumo==1.28.0`, `traci==1.28.0`, `sumolib==1.28.0`. The official [PyPI release](https://pypi.org/project/eclipse-sumo/1.28.0/) supplies a Python 3 Windows x86-64 wheel; installation and execution remain local acceptance gates. No paid service or API key is needed.

## What is actually implemented

- Three-crossroad fixture and full canonical graph → netconvert XML, explicit permitted connections, no coordinate normalization. Netconvert's generated signal greens are reused; the controller does not invent conflicting phase combinations.
- Deterministic, pre-generated explicit civilian demand and exactly one ambulance in each independent world. Same full route-file hash in both worlds. All vehicles use normal passenger permissions, including the ambulance; no bluelight device, red-light privilege or emergency speed mode override.
- Ordinary fixed cycle and immediate/fixed-lead/analytical preemption share minimum green (8 s), yellow (3 s), all-red (1 s). Ordinary greens 25 s; priority hold capped at 35 s; request timeout 90 s; one debt/queue-selected recovery service of 25 s then ordinary cycling. Recovery is not learned and does not claim bounded waits under infeasible demand.
- Frozen absolute ETA at dispatch: external-lane free-flow time plus 2 s per observed route queue vehicle, using a snapshot at least 1 s old. Zero lead requests at ETA, immediate requests at dispatch. Actual passage cancels stale future requests. Request timing is quantized to the declared simulation step and logged.
- Ambulance dispatch is projected onto the actual clipped outer lane polyline adjacent to the curb marker; it is not placed at the pedestrian marker. Front-bumper poses and actual vehicle length are exported. Source XY maps to render `[x,z,-y]`; SUMO heading is clockwise from north.
- Full scheduled/inserted/completed/running/not-inserted civilian accounting, per-vehicle lifecycle, raw SUMO tripinfo, collisions/teleports retained, common 240 s horizon plus 360 s drain. No completion-only mean on censored or invalid runs. Ambulance journey includes insertion delay from scheduled dispatch.
- Paired replay is genuine SUMO data; every frame uses one absolute clock. Baseline ambulance becomes a render-only ghost in the viewer, never a second active simulator vehicle. Fixture traces must not be overlaid on the city asset.

## Metric limits and experiments

Civilian excess time currently uses a declared external-lane free-flow lower-bound reference (lane length divided by min(edge,type speed)); this excludes internal junction lengths and acceleration. It is a reproducible convention, **not** a calibrated no-traffic reference. Raw lifecycle times are retained. Freeze any revised reference and objective before held-out data. The analytical selector is an explicitly coarse prediction, not measured delay; its fixed 58-second cycle proxy does not claim every generated signal has two phases. All five candidate scores are logged. The compact `bike` type is a low-speed passenger-class proxy, not a validated SUMO bicycle model.

Whole-demand grouping hashes civilians only, so dispatch and ambulance-route variants remain in the same group. Exact paired input hash additionally includes the ambulance. `episode_id` excludes policy/lead; `run_id` includes them. No learned model, action diversity, performance gain, frame rate or city-validity result is claimed merely because this code exists.

`local-runtime/` is ignored. Failures retain `pair-failure.json`/world `failure.json`; do not omit them from a pilot. Exported replay has `network_geometry.signals` containing actual generated incoming lane shapes, stopline endpoints and full controlled-link mappings. A single green dot cannot represent a junction's mixed signal states.

## Primary implementation references

- [SUMO traffic light control](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html): direct state control and generated programs.
- [TraCI signal state API](https://eclipse.dev/sumo/docs/TraCI/Change_Traffic_Lights_State.html): persistent online states require explicit subsequent updates.
- [Netconvert options](https://sumo.dlr.de/docs/netconvert.html): origin preservation and network conversion.
- [TripInfo](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html): depart delay and unfinished traffic semantics.

Network identity uses canonical XML excluding generated timestamp/path comments and insignificant whitespace; the exact raw network file SHA is also retained. This prevents different output directories from accidentally making identical candidate episodes appear unrelated. Episode IDs hash network, complete demand and common timing settings; run IDs add policy/action. Repeated ordinary baselines across candidate pairs share a run ID and must be deduplicated when building a scalar dataset, not treated as independent episodes.
