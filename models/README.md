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

`models.analytical.choose_lead(observation)` is the runner adapter. Its `queue-lost-service-v1` surrogate starts from frozen ETA, subtracts possible queue discharge during lead minus yellow/all-red time, discounts service by observed downstream occupancy, and adds a triangular lost-service waiting-area surrogate per ordinary cycle. Defaults match the initial controller: 2 seconds/queued vehicle, 4 seconds yellow+all-red, 58-second ordinary cycle. This approximation ignores individual phase stage/min-green residual, actual clipped request schedules and future arrivals. It is a deliberately limited **prediction**, never measured ambulance travel or all-demand civilian delay. No claim that it is calibrated is made.

Phase elapsed is retained as an observed model feature but not interpreted as green age: the actual stage may be yellow or all-red. Downstream occupancy is a fraction, not SUMO's raw percentage. Every candidate shares the same lagged observation. Changes to these formulas/configuration require a new pre-test freeze. Fitting checks the candidate `analytical_config_sha256` against `protocol.analytical_estimator` (`{version, config}`), and learned inference requires the same hash plus objective weight and frozen protocol hash. A model trained against another analytical baseline cannot silently be reused.

## Optional Omen training entry point

Only after actual pilot results support a study, a disjoint dataset exists, and the model/feature/objective/estimator protocol is frozen:

```powershell
.\.venv\Scripts\python.exe -m models --train-outcomes training-candidates.json --frozen-protocol frozen-protocol.json --output residual-tree.json
```

The input must contain all five fixed-lead rows for every training episode, including invalid/censored candidates. Fitting uses only finite targets but records excluded-label counts. `model_specification` requires `max_depth` and `min_samples_leaf`; feature entries require `name`, `unit`, `source`, and `sensor_lag_s`. The model is output to a new file only. This command does **not** access validation/test rows or prove ML benefit. Keep test execution under a separate explicit release gate.
