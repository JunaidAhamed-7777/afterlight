# Evaluation tools

These modules are implementation, **not measured experiment results**. Test fixtures use explicitly synthetic inputs. All execution/acceptance is on Omen, not the cloud development PC.

From repository root, Python 3.12+:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/evaluation -p "test_*.py" -v
.\.venv\Scripts\python.exe -m evaluation audit outcomes.json --civilian-weight 1
.\.venv\Scripts\python.exe -m evaluation pilot pilot-outcomes.json
.\.venv\Scripts\python.exe -m evaluation freeze proposed-protocol.json frozen-protocol.json
```

`audit` expects an array of scalar outcome objects; it never starts simulations. Each row includes `episode_id`, `demand_group_id`, `split`, `status`, `validity_reasons`, `ambulance_journey_s`, `civilian_mean_excess_s`, and integer civilian `accounting` fields: `scheduled`, `inserted`, `completed`, `running`, `not_inserted`. Candidate rows/dispatch variants share their original demand group. Pair validation additionally requires matching `demand_sha256`, `network_sha256`, `horizon_s`, and `drain_end_s`.

Only valid fully drained completed outcomes receive finite `J = ambulance_journey_s + civilian_weight * civilian_mean_excess_s`. Null targets are retained, not imputed or silently dropped. Infrastructure failures are distinct from policy invalidity. Corrupt accounting is an error. Queue excess integrates left-held observations over a prespecified **absolute** window with full coverage; no extrapolation or exit-time realignment.

Freeze creates a new content-addressed protocol file exclusively; it cannot overwrite an existing file. The protocol records source, whole-group assignments, held-out regimes, features, five leads, weight, horizon/drain, recovery window, tie-break, invalid rules and model specification. Freeze is not evidence that the experiment was executed or that the held-out data stayed untouched. Preserve the frozen artifact and raw outcomes in a reproducible run record.

`paired_decision_report` compares explicit episode→lead maps against all five real cached outcomes without fitting or oracle action selection. It retains every episode and headlines selected/comparator failures before conditional finite deltas, changed-action rate, empirical civilian-harm p95 and hindsight regret (diagnostic only). `grouped_bootstrap_interval` resamples whole demand-realization groups, keeping dispatch variants together; fewer than ten supported groups defaults to no confidence interval. Neither conditional statistics nor a narrow interval alone establish ML promotion.

## Deliberate pilot execution (Omen only)

First pass the three-junction correctness tests and inspect one real paired run. Then prepare a pilot plan without starting SUMO:

```powershell
.\.venv\Scripts\python.exe -m evaluation.pilot pilot-plan.json --network fixture
```

The default predeclares 12 whole episodes (three seeds each across sparse, moderate, asymmetric and heavy regimes), seven worlds per episode (ordinary, immediate, five leads), one shared network and one saved demand realization per episode. A later city pilot must use `--network city`; fixture runtime is not a city-runtime estimate. These are exploratory pilot groups only, never train/validation/test data.

Execute only after checking the plan and local correctness gates:

```powershell
.\.venv\Scripts\python.exe -m evaluation.pilot pilot-plan.json --execute --output local-runtime/pilot-fixture-001
```

The output directory must not already exist. Source commit, dependencies, hardware/runtime, expected/recorded/unattempted worlds, demand hashes, scalar rows and raw per-world SUMO/lifecycle files are retained. No automatic retry: the first infrastructure failure is retained and stops the pilot; after diagnosis, repeat the unchanged plan in a **new** directory and preserve the failed attempt. Traffic invalidity/censoring is an outcome, not infrastructure, so those worlds remain in the full pilot.

The summary reports actual feasible oracle lead winners and runner-up objective margins (default exploratory threshold 1 second-equivalent), in addition to request-schedule signatures. Multiple useful observed winners are a pilot diagnostic, not evidence of learned selector performance or test-set improvement. A failed/incomplete candidate grid cannot establish diversity. Inspect raw outcomes, failure rates and full output wall time before freezing the main dataset budget.

Pilot plans also predeclare the objective weight (default 1), useful-action margin (default 1 second-equivalent), queue scope and the common absolute recovery window (default dispatch 60 s through common drain endpoint 600 s). Each policy's primary excess-queue area is computed against that episode's ordinary world over exactly this window, in vehicle-seconds. Active civilian queue counts exclude insertion backlog, which remains separately reported; do not interpret this queue metric as complete all-demand delay.

Held-out decision reports require the hash-verified frozen protocol, not merely rows labeled `test`. Group assignment, source commit, common horizon/drain and objective weight must match it. Non-test reports are labeled `exploratory`. These checks prevent obvious relabeling/configuration drift; they are **not independent proof** that a human or another process never inspected or tuned on the test data. Preserve the actual freeze and access/run history.

## Freeze the actual selectors before test

A second-stage selector freeze follows training/validation and precedes any test run. `evaluation.selectors` creates analytical, validation-selected fixed-lead, and trained residual-model artifacts, then `freeze_selectors(...)` exclusively saves a hash-bound pair. This separate file avoids a circular hash between a training protocol and the model fitted against it.

A test-mode report now requires this selector freeze and recomputes every selected/comparator action from the frozen lagged observations and analytical formula. Supplied action maps must match those decisions exactly; an arbitrary hindsight/oracle map is rejected. The report includes selector artifact hashes, verifies analytical costs/configuration, feature order/lag, and model training-group provenance. Fixed-lead artifacts record the validation-data hash and selection summary. Exploratory comparisons may still accept explicit action maps, but are labeled accordingly. Metadata and hashes are audit guards, not independent proof against fabricated inputs or earlier human test inspection.

Pilot execution also requires clean committed source, records the source-file hash snapshot, and checks that snapshot before/after worlds. A mid-pilot edit/pull stops and retains the failed/unfinished attempt rather than stamping changed code with the initial commit. Official portable SUMO is supported: the eclipse-sumo wheel metadata is optional, but actual binary version is recorded per successful world.

The initial study protocol must also freeze a complete `episode_inventory`: each entry includes `episode_id`, `demand_group_id`, `split`, full `demand_sha256`, `network_sha256`, and `dispatch_s`. This inventory is prepared from saved exogenous demand before outcome generation, not inferred from whichever runs finished. It covers every declared group and dispatch variant. Training fit, validation fixed-lead selection and held-out reporting reject missing/extra episodes or changed input identities—even when another episode from the same group is present. Failed/censored candidate rows remain required; infrastructure failures need explicit resolution, not omission.
