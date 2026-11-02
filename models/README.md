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
