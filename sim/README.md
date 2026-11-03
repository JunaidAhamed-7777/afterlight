# SUMO backend — implementation checkpoint

The expanded city has genuine source-bound recordings and an ordinary/ordinary
negative control accepted on the owner's Omen. The matched 84-world pilot and
252 development worlds are complete; the released held-out study still needs
its final report. See [recording evidence](../docs/validation/expanded-city-recordings.json),
[negative control](../docs/validation/expanded-city-negative-control.json) and
[the current study protocol](../docs/BENCHMARK_PROTOCOL.md). Commands below create
new evidence; running a command is not a claim of policy improvement.

From repository root in the pinned Python 3.12 virtual environment:

```powershell
python -m unittest discover -s tests/sim -v
python -m sim.run --network fixture --output local-runtime/fixture-7 --seed 7 --policy fixed --lead 10 --sample 0.5
python -m sim.audit --run local-runtime/fixture-7
# Only after fixture correctness passes:
python -m sim.run --network city --output local-runtime/city-7 --seed 7 --regime sparse --policy fixed --lead 10 --pickup P001 --hospital HOSP_EAST --sample 0.5
python -m sim.audit --run local-runtime/city-7
```

Choose a fresh output directory for each invocation; existing evidence is never overwritten. `sim.audit` checks schedule/frame alignment and accounting, not visual or performance superiority.

Use `eclipse-sumo==1.28.0`, its required `sumo-data==1.28.0` companion, `traci==1.28.0` and `sumolib==1.28.0`. The official [PyPI release](https://pypi.org/project/eclipse-sumo/1.28.0/) supplies a Python 3 Windows x86-64 wheel; installation and execution remain local acceptance gates. No paid service or API key is needed.

## What is actually implemented

- Three-crossroad fixture and full canonical graph → netconvert XML, explicit permitted connections, no coordinate normalization. Netconvert's generated signal greens are reused; the controller does not invent conflicting phase combinations.
- Deterministic, pre-generated explicit civilian demand and exactly one ambulance in each independent world. Same full route-file hash in both worlds. All vehicles use normal passenger permissions, including the ambulance; no bluelight device, red-light privilege or emergency speed mode override.
- Ordinary fixed cycle and immediate/fixed-lead/analytical preemption share minimum green (8 s), yellow (3 s), and network-specific all-red clearance (city 3 s; fixture 1 s). Ordinary greens 25 s; priority hold capped at 35 s; request timeout 90 s; one debt/queue-selected recovery service of 25 s then ordinary cycling. Recovery is not learned and does not claim bounded waits under infeasible demand.
- Frozen absolute ETA at dispatch: external-lane free-flow time plus 2 s per observed route queue vehicle, using a snapshot at least 1 s old. Zero lead requests at ETA, immediate requests at dispatch. Actual passage cancels stale future requests. Request timing is quantized to the declared simulation step and logged.
- Ambulance dispatch is projected onto the actual clipped outer lane polyline adjacent to the curb marker; it is not placed at the pedestrian marker. Front-bumper poses and actual vehicle length are exported. Source XY maps to render `[x,z,-y]`; SUMO heading is clockwise from north.
- Full scheduled/inserted/completed/running/not-inserted civilian accounting, per-vehicle lifecycle, raw SUMO tripinfo and retained collision/teleport records. CLI defaults are a 240 s horizon plus 360 s drain for the fixture, and 360 s plus 540 s for city demos. The frozen scientific study uses its own common 3,000 s endpoint. No completion-only mean on censored or invalid runs. Ambulance journey includes insertion delay from scheduled dispatch. Final trip timestamps are reconciled from flushed SUMO tripinfo; TraCI list notifications retain their separate discovery timestamps rather than introducing a one-step measurement bias.
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

## Identity and revision safeguards

The runner records source commit, dirty-code status and SHA-256 for each first-party Python source module. A changed source snapshot during a pair refuses replay publication while retaining raw world files. Keep the Omen checkout on one SHA until a process ends. City replay provenance includes the exact `canonical_map_sha256` of the published manifest so the viewer can reject stale geometry. Net conversion must preserve all canonical edge IDs, endpoints and the exact permitted external edge-transition set; generated geometry is still subject to Omen visual inspection.

## Prepare a genuine city recording for the viewer

After a clean-source Omen city run and successful artifact audit:

```powershell
python -m export.catalog --run local-runtime/city-7 --destination web/public/replays
```

Registration re-audits raw SUMO evidence, checks the canonical map fingerprint, and copies exact bytes. It creates a compact evidence companion and atomically appends the catalog under an exclusive lock. Invalid/censored traffic outcomes retain explicit statuses; infrastructure failures are not registered as complete recordings. Existing different evidence is never overwritten, and an interrupted copy cannot leave a truncated final filename. This is local artifact preparation, not automatic deployment or Git publication. Public recording IDs include source-code revision; scientific episode/action IDs remain separate.

### Official portable Windows alternative

If the large `eclipse-sumo` wheel cannot be retrieved, use the verified official SUMO 1.28.0 portable archive and install matching `traci`/`sumolib` wheels in the selected interpreter. Set `SUMO_HOME` only in the running PowerShell session to the extracted distribution directory containing `bin`, then run `python -m sim.environment`. The runner supports that standard location without global PATH changes or installation. Missing `eclipse-sumo` and `sumo-data` Python metadata is explicitly recorded as null for this mode; the actual running SUMO version remains mandatory provenance. Verify the archive against the official published SHA-256 before extraction/use.

### Independent-world negative control

Before interpreting a priority benefit, run a fresh fixture pair with `--policy ordinary`, then `python -m sim.audit --run <that-run-directory>`. Both independent worlds must have exactly matching frames, control events, observations and metrics except wall-clock runtime. The audit asserts this automatically for ordinary/ordinary pairs. Passing this checks repeatability/world initialization; it is not evidence of policy improvement or real-world safety.

### Frozen dispatch causality

Every paired artifact audit also checks identical frames/events strictly before
dispatch, identical lagged observations and absolute junction ETAs, and one
matching frozen dispatch decision per world. Dispatch-boundary and later states
may diverge because the controllers are independent. Ordinary control has no
request plan; immediate requests start at dispatch; fixed/analytical requests
use `max(dispatch, absolute_eta - selected_lead)` (zero lead is not immediate).
Zero sensor lag remains supported only for the pre-action observation. Unknown
future policy labels report timing coverage as not checked rather than silently
passing it. This is an artifact-consistency gate, not proof of traffic benefit.

### Passage observability

Every world records `junction_passage_observed` once per controlled route junction,
independently of whether priority was requested or already expired. It records the
first simulation boundary where route-index advancement is observed (or arrival
notification for an unsampled final advancement), not an exact continuous-time
crossing or rear-bumper clearance. These events improve release/expiry inspection
without changing controller decisions, physics or the shared simulation clock.


## Individual-civilian descriptive tail

New runs retain `civilian_excess_p95_s`, the **within-world individual vehicle**
95th percentile of `max(0, arrival − scheduled departure − reference_s)` across
**every scheduled civilian**. It excludes the ambulance and includes insertion
waiting. The estimator is nearest rank `ceil(0.95 × n)` (one-based), without
interpolation. `civilian_excess_p95_population` records the scheduled/completed/
included counts, eligibility, method, units and reference convention.

The value is null for invalid or censored worlds, incomplete civilian demand,
or an empty civilian population; no completed-only subset is substituted. The
existing mean's empty-population convention remains unchanged. The underlying
reference is the saved external-lane free-flow lower bound, excluding internal
junctions and acceleration—not a calibrated no-traffic journey.

This is descriptive, not a paired individual harm metric, not the percentile
of episode-level mean differences in evaluation reports, and not a real-world
safety claim. It does not alter the objective J, selector, recovery metric or
any comparison inference. Raw lifecycle/tripinfo audit recomputes the value
and population whenever these optional new fields occur; legacy recordings
without either field remain compatible.


## Expanded city — November 3, 2026

The canonical map now covers **2,040 × 2,010 m**, exactly four times the old
1,020 × 1,005 m footprint. A 9 × 9 main grid keeps the original street/block
scale: 81 primary junctions, 233 streets including local loops and hospital
driveways, 826 buildings, and 100 distributed curb pickups. Westhaven Medical
is in the southwest; Eastbank General is in the northeast.

City demand uses an explicitly recorded fourfold arrival-rate multiplier,
with 68% cars, 12% trucks and 20% compact motorbikes. The three-junction
fixture retains its original rates and type mix. Every vehicle still uses
normal passenger-class permissions and SUMO car-following/right-of-way
behavior; motorbikes are compact motor-traffic proxies, not validated bicycle
dynamics. The demand manifest records the actual arrival rate and mix.

The expanded graph's independent static checks pass all 200 pickup/hospital
routes. Its first SUMO 1.28 conversion produced no warnings on the owner's
Windows/Python 3.12 environment. Traffic and benchmark evidence must bind this
new map SHA; old-city recordings cannot certify this topology.


### End-of-horizon censoring

SUMO 1.28 may write `vaporized="end"` together with `arrival="-1"` when
flushing unfinished and not-yet-inserted vehicles at the common endpoint. These
remain running/not-inserted in the complete ledger and make the world
**censored**. They are not silently removed or assigned finite delay targets.
Actual collision/TraCI/vaporizer/teleport removal reasons remain invalid, as does
an `end` marker on a claimed completed trip. This distinction was found during
the expanded-city pilot and corrected with regression tests. The subsequent
matched 84-world pilot passed; older raw attempts remain unchanged.

The exact behavior is visible in the official
[SUMO 1.28 tripinfo implementation](https://github.com/eclipse-sumo/sumo/blob/v1_28_0/src/microsim/devices/MSDevice_Tripinfo.cpp#L356)
and its unfinished-output path. The general
[tripinfo documentation](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html#output-for-vehicles-that-have-not-arrived-at-simulation-end)
describes the `--tripinfo-output.write-unfinished` option.


### City clearance profile

Heavy exploratory traffic exposed bike/truck overlap at permissive left turns
with the original one-second all-red clearance. Disabling minor-link dawdling
and increasing driver gap/advance conservatism did not remove the known case;
those failed diagnostics are retained and are not the shipped model. Extending
city all-red clearance to **three seconds**, with default drivers unchanged,
removed the demonstrated collisions on all three inspected heavy ordinary
worlds. This is an engineering qualification result, not a road-safety claim.

`timing_for_network` applies the same city profile to ordinary, immediate,
fixed, and analytical worlds. Native SUMO programs and the external scheduler
share it. Each new world's metrics record the complete timing dictionary;
signal audits use those recorded durations, and pilot/study verification binds
them to the declared network profile. Historical one-second recordings remain
auditable with their original source. The current matched pilot, dense demos and
development collections use this profile; old results are never relabeled.
