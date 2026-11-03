# Evaluation tools

The matched expanded-city pilot completed 84 audited worlds; development then
completed 168 training and 84 validation worlds. One frozen residual model has
passed [pre-test review](../docs/validation/study-v4/model-pre-test-review.json).
The single released 140-world test collection is in progress, with no held-out
performance claim yet. [Current protocol and provenance](../docs/BENCHMARK_PROTOCOL.md)
distinguish these measured artifacts from the explicitly synthetic unit fixtures.
All experiments, fitting and acceptance run on the owner's Omen.

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

`paired_decision_report` compares explicit episode→lead maps against all five real cached outcomes without fitting or oracle action selection. It retains every episode and headlines selected/comparator failures before conditional finite deltas, changed-action rate, empirical p95 across paired-feasible episode-level civilian mean-delay differences (not an individual-vehicle tail percentile) and hindsight regret (diagnostic only). `grouped_bootstrap_interval` resamples whole demand-realization groups, keeping dispatch variants together; fewer than ten supported groups defaults to no confidence interval. Neither conditional statistics nor a narrow interval alone establish ML promotion.

## Deliberate pilot execution (Omen only)

First pass the three-junction correctness tests and inspect one real paired run. Then prepare a pilot plan without starting SUMO:

```powershell
.\.venv\Scripts\python.exe -m evaluation.pilot local-runtime/pilot-plan.json --network fixture
```

The default predeclares 12 whole episodes (three seeds each across sparse, moderate, asymmetric and heavy regimes), seven worlds per episode (ordinary, immediate, five leads), one shared network and one saved demand realization per episode. A later city pilot must use `--network city`; fixture runtime is not a city-runtime estimate. These are exploratory pilot groups only, never train/validation/test data.

Execute only after checking the plan and local correctness gates:

```powershell
.\.venv\Scripts\python.exe -m evaluation.pilot local-runtime/pilot-plan.json --execute --output local-runtime/pilot-fixture-001
```

For a smaller **runtime scout**, prepare a separate city plan with
`--network city --seed-start 1001 --seeds-per-regime 1`: four episodes (one per
regime), 28 worlds, seeds 1001–1004. Inspect the saved plan before execution.
This scout is too small to authorize a study: study preparation requires 12–20
completed audited pilot episodes spanning all four regimes. If later using a
separate 12-case city pilot starting at 1101, keep scout seeds 1001–1004 in the
study's explicit `declared_exploration_seeds`; the selected pilot's own seeds
1101–1112 are excluded automatically. These example blocks must first be checked
against known prior exploration. Seed 7 remains reserved. Never relabel scout or
pilot outcomes as train/validation/test, or infer city throughput from the sparse
qualification pair's wall time.

There is no pilot wall-time timeout or resume feature. Supervise the finite
plan. A caught Ctrl+C (`KeyboardInterrupt`) records `status: interrupted`, the
current world (if any), full attempted/remaining inventory and wall time, then
re-raises. Prior rows and raw files stay intact; an interrupted world gets no
invented outcome or finite target. Inspect process state and retained evidence
before any new attempt. Hard termination, a second interrupt or storage failure
can prevent final journaling; this is not a crash-proof checkpoint guarantee.

The output directory must not already exist. Source commit, dependencies, hardware/runtime, expected/recorded/unattempted worlds, demand hashes, scalar rows and raw per-world SUMO/lifecycle files are retained. No automatic retry: the first infrastructure failure is retained and stops the pilot; after diagnosis, repeat the unchanged plan in a **new** directory and preserve the failed attempt. Traffic invalidity/censoring is an outcome, not infrastructure, so those worlds remain in the full pilot.

The summary reports actual feasible oracle lead winners and runner-up objective margins (default exploratory threshold 1 second-equivalent), in addition to request-schedule signatures. Multiple useful observed winners are a pilot diagnostic, not evidence of learned selector performance or test-set improvement. A failed/incomplete candidate grid cannot establish diversity. Inspect raw outcomes, failure rates and full output wall time before freezing the main dataset budget.

Pilot plans also predeclare the objective weight (default 1), useful-action margin (default 1 second-equivalent), queue scope and the common absolute recovery window (default dispatch 60 s through common drain endpoint 600 s). Each policy's primary excess-queue area is computed against that episode's ordinary world over exactly this window, in vehicle-seconds. Active civilian queue counts exclude insertion backlog, which remains separately reported; do not interpret this queue metric as complete all-demand delay.

Held-out decision reports require the hash-verified frozen protocol, not merely rows labeled `test`. Group assignment, source commit, common horizon/drain and objective weight must match it. Non-test reports are labeled `exploratory`. These checks prevent obvious relabeling/configuration drift; they are **not independent proof** that a human or another process never inspected or tuned on the test data. Preserve the actual freeze and access/run history.

## Freeze the actual selectors before test

A second-stage selector freeze follows training/validation and precedes any test run. `evaluation.selectors` creates analytical, validation-selected fixed-lead, and trained residual-model artifacts, then `freeze_selectors(...)` exclusively saves a hash-bound pair. This separate file avoids a circular hash between a training protocol and the model fitted against it.

A test-mode report now requires this selector freeze and recomputes every selected/comparator action from the frozen lagged observations and analytical formula. Supplied action maps must match those decisions exactly; an arbitrary hindsight/oracle map is rejected. The report includes selector artifact hashes, verifies analytical costs/configuration, feature order/lag, and model training-group provenance. Fixed-lead artifacts record the validation-data hash and selection summary. Exploratory comparisons may still accept explicit action maps, but are labeled accordingly. Metadata and hashes are audit guards, not independent proof against fabricated inputs or earlier human test inspection.

Pilot execution also requires clean committed source, records the source-file hash snapshot, and checks that snapshot before/after worlds. A mid-pilot edit/pull stops and retains the failed/unfinished attempt rather than stamping changed code with the initial commit. Official portable SUMO is supported: the eclipse-sumo wheel metadata is optional, but actual binary version is recorded per successful world.

The initial study protocol must also freeze a complete `episode_inventory`: each entry includes `episode_id`, `demand_group_id`, `split`, full `demand_sha256`, `network_sha256`, `regime`, and `dispatch_s`. This inventory is prepared from saved exogenous demand before outcome generation, not inferred from whichever runs finished. It covers every declared group and dispatch variant. Training fit, validation fixed-lead selection and held-out reporting reject missing/extra episodes or changed input identities—even when another episode from the same group is present. Failed/censored candidate rows remain required; infrastructure failures need explicit resolution, not omission.

## Saved-input study workflow

[Study preparation and collection](STUDY.md) now provides explicit, bounded input
preparation, a frozen episode inventory, and audited train/validation collection.
It requires a genuine matching pilot and refuses pilot-group reuse. Test collection requires an explicit immutable release digest and a one-attempt
claim after selector freezing; ordinary train/validation commands cannot open
test outcomes. The report revalidates the full claimed test inventory and both
strong comparators without fitting. The current study's separately frozen
[exact-estimator analysis correction](../docs/ANALYSIS_AMENDMENT.md) retains the
original simulation and collector source. Source compilation alone is not a
study result.

The study `select` command now verifies complete audited train/validation evidence,
selects the validation-best fixed lead, and optionally fits one declared residual
tree with explicit ML-version guards. It freezes comparisons against both the
fixed and analytical selectors before any test release. Baseline-only and
inconclusive outputs remain explicit; fitting is not evidence of held-out gain.


The operational study selection schema is now `afterlight.study-selection.v2`:
release and report verification regenerate the validation-best fixed comparator
from retained exact validated candidate bytes, not only its claimed lead/hash.
Legacy selection artifacts without that evidence are rejected. Comparison schema
v2 names the episode-mean percentile explicitly and records its eligibility and
population metadata; the former ambiguous civilian-harm p95 key is not reused.
