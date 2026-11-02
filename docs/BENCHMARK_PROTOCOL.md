# Benchmark protocol — planned, not achieved

## Experiment

Use one three-intersection network and fixed ambulance route. Vary civilian arrival patterns, queue states, dispatch times and reproducible seeds. Keep full demand files and route permissions identical across policies. Replay each policy from `t=0`; do not assume save/load restores all RNG and route state.

Primary experiment disables SUMO bluelight behavior. Its documented privileges can ignore red lights, alter surrounding traffic or introduce emergency teleport behavior, confounding the controller. Ambulance visuals do not confer simulator privileges. Record all collision, teleport and signal-constraint events. Safety assertions are simulator checks, not real-world certification.

## Comparators

1. Ordinary fixed-time signals.
2. Actuated or max-pressure baseline, only if correctly implemented and described.
3. Immediate priority: request all three intersections at dispatch, respecting legal transitions.
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
