# Residual selector implementation

No trained model, predictive accuracy or policy gain is claimed. The baseline remains the deployable choice until Omen runs real training/validation and a frozen untouched test comparison.

`models.residual` implements:

- a strict inference feature allowlist and `observed_at_s <= dispatch_s - sensor_lag_s` guard;
- identical observed state/provenance across all five candidate rows;
- validation-only fixed-lead selection, minimizing infeasible count then mean objective over the **common fully feasible episode subset**, then smallest lead; absent a common subset is explicitly inconclusive;
- optional shallow scikit-learn `DecisionTreeRegressor` fitting on **training-only** finite real SUMO residual targets, retaining the excluded infeasible-label count;
- hash-checked JSON tree persistence and safe inference, not pickle loading;
- analytical and residual candidate selection with smallest-lead tie-break, explicitly labeled predictions.

Initial actual observation subset is `DEFAULT_FEATURES`: route queue sum/max, downstream occupancy, route distance/junction count, frozen ETA remaining time and elapsed phase time. Arrival-rate features are not enabled in that default because the runner does not yet have a validated lagged detector window. No seed, demand regime, future arrivals or rollout outcomes enter prediction. Feature allowlisting/timestamps do not independently establish sensor correctness: inspect runner provenance and local tests.

The analytical cost is supplied by the shared policy estimator; it is not a training label. Training targets are `J_SUMO - J_analytical`. A residual regressor does not learn feasibility. Evaluation must retain and headline selected-action failures, including all-infeasible episodes, before any conditional finite objective comparison. Hyperparameters and objective weights belong in the frozen protocol before test.

Reference: [scikit-learn DecisionTreeRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeRegressor.html). Dependency installation and all training/testing occur on Omen. Stdlib model contract tests are included under `tests/evaluation`; they intentionally do not fit a model.

## Explicit analytical baseline

`models.analytical.choose_lead(observation)` is the runner adapter. The versioned
`queue-concentration-v2` surrogate corrects an algebraic limitation of v1: the
old aggregate subtraction credited every route junction with service even when
all observed queuing was concentrated at one junction. This is a modeling
correction, **not evidence of empirical policy improvement**.

The existing seven features are unchanged. The runner sums incoming-edge lane
queues once per controlled route junction; `queue_sum_veh = Q`, `queue_max_veh = M`
and `route_junction_count = n` describe that same grouping. They must satisfy
`0 <= M <= Q <= n*M`. Frozen ETA must include at least its runner-defined `2*Q` queue
component. This fixed ETA convention is separate from configurable service headway `h`. Inconsistent observations are rejected rather than silently repaired.

For lead `L`, transition loss `tau`, occupancy fraction `o` and headway `h`:

- Equal assumed service at each junction is `S = max(0, L - tau) * (1 - o)` seconds.
- The residual delay for an unknown allocation is `sum(max(h*q_i - S, 0))`.
- The optimistic bound is `max(h*M-S, 0) + max(h*(Q-M)-(n-1)*S, 0)`.
- Write `Q = k*M + r`, with `k=floor(Q/M)`. The conservative bound is
  `k*max(h*M-S, 0) + max(h*r-S, 0)`; when `Q=0`, both bounds are zero.

The conservative expression concentrates queues into as few junctions as the
observed maximum allows. Convexity of `max(h*q-S,0)` gives the worst residual
allocation within this equal-service model. For one occupied junction, empty
junctions cannot discharge its queue. Scores use the conservative bound plus
free-flow time reconstructed as `ETA - 2*Q` (never `ETA - h*Q` for a custom headway); both bounds are exposed as
prediction diagnostics, not additional learned features.

The civilian penalty is `scale*n*L^2/(2*cycle)*(1+o)` **seconds**, multiplied by the
unchanged frozen objective weight. It is a coarse uncalibrated mean-delay
surrogate, not measured all-demand delay or queue area. Its frozen default
parameters remain 2 seconds per queued vehicle, a 4-second transition-loss proxy,
and a 58-second ordinary-cycle proxy. Those are analytical assumptions, not
measurements of the imported city's signal programs. The expanded city's actual
controller uses 3 seconds yellow plus 3 seconds all-red; different junctions can
also have different numbers of green phases. The scalar study compares this
unchanged analytical predictor and the learned residual against the same real
candidate outcomes, without claiming that the predictor reproduces those cycles.
Incoming-edge queues may include other turns; occupancy is route-averaged.
The bounds apply only to the surrogate, not actual traffic guarantees. Individual
phase/min-green constraints, actual clipped request schedules and future arrivals
remain unmodeled. Arithmetic is checked for finite intermediate/output values.

Phase elapsed is retained as an observed model feature but not interpreted as green age: the actual stage may be yellow or all-red. Downstream occupancy is a fraction, not SUMO's raw percentage. Every candidate shares the same lagged observation. Changes to these formulas/configuration require a new pre-test freeze. Fitting checks the candidate `analytical_config_sha256` against `protocol.analytical_estimator` (`{version, config}`), and learned inference requires the same hash plus objective weight and frozen protocol hash. A model trained against another analytical baseline cannot silently be reused.

## Optional Omen training entry point

Only after actual pilot results support a study, a disjoint dataset exists, and the model/feature/objective/estimator protocol is frozen:

```powershell
.\.venv\Scripts\python.exe -m models --train-outcomes training-candidates.json --frozen-protocol frozen-protocol.json --output residual-tree.json
```

The input must contain all five fixed-lead rows for every training episode, including invalid/censored candidates. Fitting uses only finite targets but records excluded-label counts. `model_specification` requires `max_depth` and `min_samples_leaf`; feature entries require `name`, `unit`, `source`, and `sensor_lag_s`. The model is output to a new file only. This command does **not** access validation/test rows or prove ML benefit. Keep test execution under a separate explicit release gate.
