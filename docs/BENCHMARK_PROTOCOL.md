# Benchmark protocol

## Frozen expanded-city study

The current study has 56 independent demand groups: 24 training, 12 validation
and 20 held-out test cases, each with seven complete-from-zero policy worlds.
The map has 81 primary nodes and 77 signal controllers. The saved input and
protocol identities are retained in [the frozen study proof](validation/study-v4/).
The earlier 180-episode workload below is a historical planning proposal, not the
size of this experiment.

Each case runs ordinary signals, immediate priority and fixed leads of 0, 5, 10,
20 and 30 seconds against identical saved demand and route inputs. All variants
share the same 3-second yellow, 3-second all-red, minimum-green, release and
maximum-hold rules. Integration uses 0.5 seconds; scalar scientific evidence uses
5-second pose samples and the exact recorded control events. The common window
ends at 3,000 seconds: demand ends at 180, the primary horizon is 360 and the
drain is 2,640. Sparse, moderate and asymmetric demand appear in development;
heavy demand and one ordered origin/hospital route family are held out.

The matched expanded-city pilot completed all 84 declared worlds with valid
accounting and audits before this study was frozen. Development then completed
168 training and 84 validation worlds. One prespecified residual tree was fitted
to 120 finite training candidate labels from 24 groups, with maximum depth 3,
minimum leaf size 8 and random seed 0. Validation selected the shared fixed-lead
comparator at 5 seconds. These are development facts, not held-out performance.

The initial selection command stopped in raw verification before model fitting:
a legacy pilot helper reconstructed an integer objective weight instead of using
the complete frozen estimator configuration. The retained failure and explicit
[pre-test analysis amendment](ANALYSIS_AMENDMENT.md) preserve all original source,
input and evidence identities. The corrected separate analysis consumes the
exact frozen estimator hash; the simulation and held-out collector stay pinned
to their original source. Independent checks of the
[descriptor](validation/study-v4/analysis-amendment-review.json) and
[actual frozen model](validation/study-v4/model-pre-test-review.json) preceded
the single learned-mode test release.

The complete 20-case/140-world test collection took 8,951.34 seconds: 134 traffic
worlds completed and six were invalid. All 140 remain in the audited inventory.
The learned selector failed on 1/20 cases versus 0/20 for validation-best fixed
lead 5. Among 19 paired-valid cases its mean objective difference was **+0.68 s**
(95% grouped interval **−4.99 to +5.98 s**); positive values favor the comparator.
It chose exactly the same actions as the analytical selector on all 20 cases.
This study establishes **no learned policy benefit**, and the model is not
promoted. The [actual report checkpoint](validation/study-v4/report-checkpoint.json)
retains the full denominators and original report identities.

The separate declared validation-only timing measurement used all 12 retained
snapshots and 2,400 repeated calls per method. Complete five-candidate learned
inference had a 0.2241 ms median and 0.2512 ms nearest-rank p95 on the owner's
Ryzen 9 5900HX. This is warm in-process Python computation, excluding file I/O,
imports, simulator, UI and network; it is not hosted or live-controller latency.
The [original timing samples](validation/study-v4/selector-timing.json) bind
hardware, source, model and input bytes. Before/after observations found no
active SUMO process; they do not establish continuous system isolation.

Model fitting and test collection do not modify either public illustrative
recording. Scientific 5-second traces stay private; public traffic playback
requires actual 0.5-second captures. The public Study pack is published only
after deterministic report and original-byte verification.

## Desktop rendering evidence

The current journey/Algorithm production build was measured in two separate
30-second foreground windows in headed Chrome 156 with the observed ANGLE AMD
Radeon(TM) Graphics renderer. All 63 served files (46,973,555 bytes) matched the
isolated inventory before and after acceptance. The exact product source is
`4126b4fed79a9eaeb7a5302fa7f071296e23ab5b`; the strict manifest is
`d14c3ea31de1a8a12a9dc0eb08be0a4cdfb1edf520af6189b8e11da02bad2d81`.

Overview recorded 4,579 draw-bearing frames over 30.0122 s: **152.5 FPS**.
Close ambulance follow recorded 3,893 frames over 30.0121 s: **129.7 FPS**.
Both windows were visible and focused at start/end, with no intervening
lifecycle events or long-task entries. The actual recording had 373 vehicles
at the chosen 180.5 s start frame. Full product checks also passed fixed desktop
layout, keyboard/map controls, actual instance matrices, world playback,
contrast checks and graphics/catalog recovery.

Street reveal remained enabled. The initial perspective view reported three
faded buildings; both timed windows reported zero at their start and end.
This is a view-dependent cutaway, so enabled does not imply geometry is faded
in every view. The separate [camera record](validation/journey-algorithm-camera.json)
checks actual default/reload reveal and eighteen identical paused repeat pairs
at two desktop profiles, plus explicitly opaque seven-angle sweeps.

The configured viewport was **1920 x 1080 emulated CSS pixels at DPR 1**; the
native window was **1724 x 978** and measured canvas buffer **1552 x 737**.
FPS is `(frames - 1) / elapsed` over first/last draw-bearing RAF timestamps.
Callback duration includes JavaScript and draw submission, not completed GPU
execution. This is one hardware/browser/recording observation, not simulator
throughput or a cross-hardware guarantee. Raw frame sample arrays are not
retained; the report provides count/span and percentile summaries.

[The current reviewed record](validation/journey-algorithm-desktop-performance.json)
retains exact conditions and scope. The [earlier identity-build record](validation/final-desktop-performance.json)
measured 161.8/127.7 FPS with reveal default OFF and retains its original failed,
no-sample and unqualified attempts. Those numbers remain historical. No new
scientific rollout, fitting or held-out-policy outcome belongs to this UI check.

## Experiment

Use a three-intersection fixed-route correctness fixture first; scale to the expanded city only after validity and runtime gates. Vary civilian arrival patterns, queue states, dispatch times and reproducible seeds. Keep full demand files and route permissions identical across policies. Replay each policy from `t=0`; do not assume save/load restores all RNG and route state.

Primary experiment disables SUMO bluelight behavior. Its documented privileges can ignore red lights, alter surrounding traffic or introduce emergency teleport behavior, confounding the controller. Ambulance visuals do not confer simulator privileges. Record all collision, teleport and signal-constraint events. Safety assertions are simulator checks, not real-world certification.

## Comparators

1. Ordinary fixed-time signals.
2. Actuated or max-pressure baseline, only if correctly implemented and described.
3. Immediate priority: request all controlled route intersections at dispatch (three in the correctness fixture), respecting legal transitions.
4. Best fixed lead chosen on validation from the same action set.
5. Analytical candidate selector without learned residuals, sharing all other components.
6. Learned residual selector.

`L=0` requests priority at predicted arrival; it is **not** the immediate baseline. Deduplicate identical clipped schedules and report the effective candidate count. A dataset with five action labels but one actual schedule cannot demonstrate timing learning.

## Splits and workload

Split whole demand-realization groups before fitting; dispatch-time variants of one realization and every candidate row stay together. Assert disjoint group sets. Report episodes separately from action labels. Never place neighboring samples from one rollout in both training and test. Hold out demand patterns/regimes as well as seeds where feasible. Run a 12–20 whole-episode CPU pilot spanning sparse, moderate, asymmetric and heavy demand. Proposed main budget: 180 episodes (108 training, 36 validation, 36 test), seven rollouts each (five leads, immediate, ordinary) = 1,260 rollouts. These are planning numbers, not a commitment. If the pilot measures 5 seconds/run this would be 1.75 raw sequential hours; at 30 seconds/run, 10.5 hours, before I/O/failures. Pilot complete output/parsing cost before freezing a feasible budget. Cache scalar candidate outcomes; frozen analytical/learned selectors can reuse those only if they select exactly the same candidate policies. Keep rich traces for a declared small illustrative subset.

Generate paired outcomes with identical exogenous intended departures/routes per scenario (realized insertion and downstream arrivals can differ). Keep validation distinct from final test. Lock feature schema, candidate set, objective weights, model choices and evaluation script before test. Preserve failed and unfavorable cases with reason codes.

## Outcomes

| Outcome | Required treatment |
|---|---|
| Ambulance journey | Dispatch-to-exit seconds, with explicit noncompletion/censoring; no excluding failures. |
| Civilian delay | Define reference travel time per route, report mean and p95 with population and horizon. |
| Unfinished and uninserted traffic | Enable unfinished trip output; also account for demand waiting to enter. Never call completed-only averages overall delay. |
| Backlog and approach waits | Per-approach queues/waits, max and p95 where defensible; disclose overload. |
| Throughput | Arrivals completed plus pending/insertion backlog at common horizon. |
| Recovery | Primary: excess-queue area over one prespecified absolute-time window, using E(t)=max(0,Q_priority(t)−Q_ordinary(t)). Supplementary: event-aligned time after ambulance exit until excess stays below a predeclared tolerance for a fixed interval. Censor never-recovered runs; do not record zero. Freeze window, queue scope, tolerance and persistence before test. |
| Policy validity | Collision/teleport events, illegal phase transitions, min-green/yellow/all-red violations. |
| ML contribution | Prediction error, candidate regret and downstream policy improvement vs identical analytical selector. |
| Runtime | Training/generation wall time, inference latency and hardware. |

For delay, maintain an all-demand accounting table: scheduled, inserted, completed, unfinished, not inserted. If a single aggregate cannot fairly cover censored journeys, report separate cohorts and backlog rather than invent a favorable combined number. Report exact horizon and follow-up drain period uniformly.

## Analysis and publication

Report per-scenario paired differences, medians/means and episode-level bootstrap intervals where sample size supports them. Do not treat per-second observations as independent episodes. Publish seed manifest, full outcome table and aggregation script. Choose the hero demo seed transparently (e.g. representative validation case); never claim that selection is an unbiased test result.

The key acceptance gate is a valid comparison, not a predetermined percentage gain. If learning offers no robust benefit over the fixed-lead and analytical alternatives, say so, diagnose feature/action insufficiency and preserve the negative result. No “lives saved,” real-city performance, or universal dominance claims.

## Pass 3 acceptance gates and claim ladder

1. **Action diversity:** at least two genuinely distinct schedules are useful under different training conditions. If one lead dominates everywhere, prefer the simpler fixed lead; do not redesign test conditions to create a win.
2. **Simulator validity:** reject collisions, unexplained teleports, conflicting greens, permanent priority holds or missing ambulance arrival; keep rejection counts/reasons. A policy-caused failure is an outcome, not an excuse to omit that scenario.
3. **Accounting:** reconcile every scheduled civilian. Mean complete-trip delay is valid only when the common drain completes; otherwise publish censored status, common-horizon system burden and backlog.
4. **Reproducibility:** repeat a representative run with pinned versions/config/input hashes and declare tolerances. Full replay is the default; snapshot branching requires demonstrated equivalence including RNG, future demand and controller state.
5. **Isolation:** all priority variants share transition/release/recovery logic. Best fixed lead is selected on validation. Hindsight best is only an oracle lower bound.
6. **ML promotion:** require practically meaningful held-out decision improvement over both analytical and validation-best fixed lead, with civilian tradeoffs disclosed. Report changed-action rate, improved/worsened fraction, regret and high-percentile civilian harm, not just regression MAE. Uncertain small change is inconclusive.
7. **No test recycling:** if test exposes a flaw, label that evaluation exploratory. A revised claim needs new untouched test data; never relabel the same tuned-on test as held out.

The objective is defined once in [Architecture](ARCHITECTURE.md). Its horizon includes the aftermath; lead selection changes the disruption left for a shared recovery controller. Do not claim a learned recovery policy. Ordinary-policy queue references are evaluation data, never predictor inputs. Publish final objective weight, metric formulas and rejection rules before unlocking the test set.

## Predeclared infeasibility and censored outcomes

Use identical predefined validity and completion rules for every policy. A policy-caused invalid run or failure to complete the common drain is ranked **infeasible**, behind feasible completed outcomes, with explicit failure count and reason; never assign an invented finite completion cost. Among infeasible outcomes report failure categories, common-horizon burden and backlog rather than claiming a comparable completed-trip objective. Infrastructure/tool failures are separately identified and retried under the same documented policy; they are not silently counted as traffic failures or erased.

Finite residual regression labels exist only for completed, valid candidate outcomes. Keep infeasible candidate rows in the dataset manifest with validity status and no fabricated numeric target. Report how many labels lack a finite target and which episodes are affected. This means a regression-only selector may not predict feasibility: do not conceal that limitation or remove difficult episodes from test. If selected actions are infeasible, count those policy failures in the headline comparison before any conditional finite-cost analysis. Any additional feasibility model or constraint must be trained/calibrated without test access and applied consistently. Full-episode evaluation retains every held-out episode, including all-infeasible cases.

## Expanded-city and ghost revision gates

Seeded randomness creates reproducible variation, not proof against overfitting. Keep demand-realization groups disjoint; for city-level claims include declared held-out origin/destination or route families and demand regimes, not only new random numbers on an identical easy corridor. Do not claim generalization across every pickup/hospital combination unless sampled coverage supports it. Publish tested route count, route-length/junction distribution and failure counts alongside episode counts.

The ghost must replay the ordinary baseline's actual trajectory from its independent simulation, not a synthetic speed curve. Unit/integration checks assert no ghost ID in AFTERLIGHT simulation vehicles/detectors/priority events, equal absolute timestamps, matching input hashes, and identical exported pose to the baseline trace. Traffic responds to the solid ambulance only in AFTERLIGHT; baseline has its own ordinary signal/traffic evolution. Apparent ghost/visible-traffic overlap is a rendering explanation issue, never a reason to alter benchmark trajectories.

Re-run the complete runtime pilot on the expanded graph before carrying over dataset or latency estimates. More intersections, longer routes and randomized traffic can change both simulation cost and feature distribution. The three-junction result is a fixture result until expanded evaluation passes. Freeze any new route-conditioned features or variable-length action semantics before that test; prior review does not validate new model scope.

## Executable pre-study gates

Every newly frozen episode inventory records its demand regime as well as demand
group, split, network/demand hashes and dispatch time. A declared held-out regime
must be represented in test and absent from train/validation; dispatch variants
within one demand group cannot relabel their regime. Candidate outcome rows must
match that frozen inventory. Older synthetic unit envelopes with no regime
metadata and no regime-holdout claim remain readable, but cannot be newly frozen
under the stronger contract without the metadata.

Pilot action diversity compares distinct frozen request schedules, not merely
lead labels: clipping can make 20 s and 30 s the same action. Such duplicates must
have identical measured outcomes; conflicting outcomes stop interpretation and
retain raw evidence. A common best lead across all useful-margin episodes means
there is still a single fixed action explaining those episodes, even if lowest-
label tie representatives differ. This is exploratory diversity evidence, never
held-out learned-selector gain.

Before any pilot outcome receives a finite objective, its actual lifecycle and
signal-event/frame evidence must pass the same pure checks used for paired
artifacts. Freeze and recheck source and dependency metadata around every world;
require one actual SUMO version across the pilot. A drift or evidence failure is
retained, stops the pilot, and leaves remaining worlds explicitly unattempted.
Report scheduled worlds, invoked simulations, preflight rejections, retained
outcomes and failures separately. New world metrics record `simulation_step_s`;
replay `step_s` is only the sampling cadence and must not be used as the simulator
integration step when auditing request/hold deadlines.

## Implemented percentile scope

Decision-comparison v2 reports the nearest-rank p95 of **episode-level mean
civilian excess-delay differences**, conditional on both selected and comparator
policies completing validly through the common drain. It records the eligible
episode count and population explicitly. This is not the p95 of individual
vehicle delays and must not be interpreted as an individual-vehicle tail.
The source now separately records `civilian_excess_p95_s`: nearest-rank
`ceil(0.95*n)` of individual excess delays over every scheduled civilian in
one valid completed, fully drained world. Its population metadata binds
scheduled/completed/included counts, units, method and saved free-flow reference.
Invalid/censored/incomplete worlds and empty civilian populations yield null,
not a completed-only percentile. Insertion wait is included through scheduled
departure time; the ambulance is excluded. This descriptive implementation is
pending Omen acceptance, changes no objective or selector, and adds no paired
individual-harm inference. Failed/censored episodes remain in
the full failure accounting rather than entering a finite percentile.

The validation-best fixed comparator is re-derived from retained exact
validation-only candidate bytes during selection verification (selection schema
v2). Neither that check nor hash binding independently proves untouched test
history. Preserve the actual freeze, release and execution records.
