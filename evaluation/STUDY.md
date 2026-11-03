# Saved-input studies

This workflow prepares a finite, declared study from an **actually completed,
audited pilot**. It does not turn pilot data into training data, run an experiment
implicitly, or manufacture a model. Execute commands and tests only on the
assigned Omen machine. The current expanded-city pilot and development
collections have been executed and audited locally; the single released held-out
collection completed all 140 worlds, retaining six invalid traffic outcomes.
The exact frozen design, negative learned result and current evidence are in
[the benchmark protocol](../docs/BENCHMARK_PROTOCOL.md).

The current source-pinned study uses an explicit
[pre-test analysis amendment](../docs/ANALYSIS_AMENDMENT.md) because its original
study verifier reconstructed the legacy pilot estimator configuration. The
separate frozen entry point consumes the complete original frozen configuration
and binds the correction into selection/report hashes; the simulation and
original one-shot test collector remain unchanged. For this study, use the
amended entry point for selection/report verification and the amended publication
helpers described below, rather than relabeling or rewriting the original data.
Canonical main now supplies the complete frozen estimator for **future** study
audits, preserving the legacy pilot path. That correction has a new source
identity and does not change this study's original source or frozen amendment.

## Lock source before generating data

Use a clean implementation commit **C** and a pinned Python environment. Keep all
specifications, generated inputs and results under the ignored `local-runtime/`
directory. Do not pull or edit source during a study. A study pins C and its source
byte inventory; freezing generated metadata does not require a new source commit.
Publishing results later must preserve their original C provenance.

First finish the matching pilot: 12–20 whole episodes spanning sparse, moderate,
asymmetric and heavy traffic, seven worlds each (ordinary, immediate, five fixed
leads). Preserve the entire directory, including raw lifecycle/tripinfo, outcomes,
compact signal traces and execution metadata. Preparation rereads those artifacts,
checks identities, reruns lifecycle/signal audits, recomputes analytical predictions
and pilot summary, and extrapolates the **full** measured pilot wall time. A failed
or incomplete pilot cannot justify a study budget. Censored policy outcomes remain
in the pilot; they do not become finite learning targets.

## Explicit specification

Save JSON containing these required fields; there is no automatic large budget:

- `schema`: `afterlight.study-spec.v2`; safe `study_id`; `network_kind`: fixture or city.
- `declared_exploration_seeds`: required sorted, unique integer seeds in
  `0..2147483647` previously inspected through local generation, demos or other
  exploratory runs. Use explicit `[]` only when there are no additional known
  explored seeds. Booleans are not integers here. This exclusion is additive to
  reserved qualification seed 7 and all pilot seeds, across every regime/split.
- `cases`: explicit objects with `case_id`, `split` (train/validation/test), `seed`,
  `regime`, `dispatch_s`, `pickup_id`, `hospital_id`, `route_family`.
- `timing`: `demand_end_s`, `horizon_s`, `drain_s`, `step_s`, `sample_s`,
  `sensor_lag_s` (at least 1), and absolute `recovery_window_s: [start, end]`.
  Network, integration/sampling resolution and workload horizons must match the
  measured pilot. Endpoints/dispatch are declared before outcomes exist.
- `budget`: integer `max_episodes`, integer `max_rollouts`, positive
  `max_wall_time_s`, and a nonempty measured-pilot `rationale`. Seven worlds are
  required per episode. Budget selection is a human review step after the pilot;
  action diversity does not establish learned decision gain.
- `civilian_weight`: **1**. Initial study implementation supports only the actual
  simulator defaults: `analytical_config` is `{"queue_headway_s":2,
  "transition_loss_s":4,"ordinary_cycle_s":58,"civilian_weight":1,
  "civilian_cost_scale":1}`. No custom configuration is silently substituted.
- `model_specification`: one declared `max_depth` (1–8) and `min_samples_leaf`.
- `illustrative_capture`: explicit `{case_ids: [], max_world_bytes: 0, max_total_bytes: 0}`
  for no presentation capture, or the bounded predeclared test-case contract below.
- `heldout_regimes` and `heldout_route_families`: explicit lists (possibly empty).
  Every declared holdout must be represented in test only. For held-out route
  families, the actual ordered edge route cannot also appear outside test.
  Other family labels remain user-defined strata, not geometric novelty claims.

Study-spec v1 is rejected rather than silently assigning an empty exploration
history. To prepare a new v2 study, the operator must review known exploration
and declare it before generating inputs. Existing generated studies cannot be
silently upgraded or rebranded as untouched. The declaration is frozen into the
protocol and rechecked when loading; no runtime folders are scanned. It is a
manual disclosure safeguard, **not proof that every inspected run was disclosed**.
After freeze, do not preview or locally generate any study seed outside its
scheduled collection/selection/released-test workflow. If accidental exploration
occurs, disclose it and do not claim that affected evidence remained untouched;
a frozen declaration cannot retroactively repair exposure.

All three splits must exist. Every civilian realization and all its dispatch/route
variants stay in one split; pilot groups cannot be reused. In addition, each RNG
seed belongs to exactly one `(split, regime)` pair. Dispatch/route variants may
share that pair, but changing the regime does not make the underlying random
stream independent. This prevents same-seed correlated regime variants from
crossing splits or being counted as independent test groups. The frozen protocol
records exact seed assignments and every candidate must retain its episode seed.

Seed **7** is additionally reserved for software qualification: its fixture stream
has already been inspected, and qualification profiles reuse it. It is rejected
for train, validation and test regardless of which seeds a later pilot uses.
The protocol freezes `reserved_qualification_seeds: [7]`; this is separate from
the scientific pilot exclusion and cannot be removed to make explored data
"untouched." This reservation is not a claim that all qualification gates passed.

Pilot evidence v2 carries an explicit sorted seed inventory. Every pilot seed is
excluded from all study regimes, even when a changed regime produces different
actual demand bytes. Legacy evidence lacking seeds is rejected, never guessed or
relabeled. These stream guards supplement—not replace—civilian-content hashes. Preparation saves demand
and network inputs for all splits, **not outcomes**. Test traffic is not run or read
by preparation or training selection.

```powershell
python -m evaluation.study prepare --spec local-runtime/study-spec.json --pilot-dir local-runtime/pilot --output local-runtime/study
python -m evaluation.study freeze --study local-runtime/study
```

Output must be a new directory. Preparation saves exact input byte hashes and
semantic network identity, complete episode inventory, route-family membership,
and the protocol. Freeze verifies the saved inputs and their link to execution
configuration before exclusively writing `frozen-protocol.json`. Failure records
are preserved; do not overwrite directories to retry.

## Collection handoff and budget semantics

`evaluation.collector.collect_split(study_directory, split, output_directory)`
consumes only the saved, frozen inputs. Train and validation collection need no release. Test requires the explicit
selector-release and single-attempt gate described below. The collector retains ordinary, immediate and all five fixed worlds,
raw evidence and all failed/unattempted inventory entries. `outcomes.json` holds
all worlds; `candidate-outcomes.json` holds the fixed candidates for later fitting.
No collection command implicitly trains a model, selects a policy or releases test.

The wall-time budget is a **whole-study planned start allowance**, allocated to
splits in proportion to episode count. Each collection attempt checks its split
allowance before starting another world. An ongoing world may overrun: this is not
a hard timeout or a guarantee. An explicit retry consumes additional wall time;
separate attempts are not silently pooled into a claim of total-budget compliance.
Pilot estimates are estimates, not performance promises.

Later stages must fit only train, select fixed/tree configuration only validation,
freeze selector artifacts separately (avoiding a protocol/model hash cycle), then
explicitly release test once. Cached demo traces must come from the exact declared
study episode/policy/source—not an unrelated earlier replay with a model label.
Bounded predeclared rich trace retention and the explicit test-release workflow are described below.

Hashes and metadata guards detect drift and inconsistent artifacts. They cannot
prove a human never inspected test information or that reported files are truthful
without independent execution. No held-out gain is claimed before actual results.

## Train/validation selection checkpoint

After a frozen study has one completed audited attempt for each development split:

```powershell
python -m evaluation.collector --study local-runtime/study --split train --output local-runtime/train-attempt
python -m evaluation.collector --study local-runtime/study --split validation --output local-runtime/validation-attempt
python -m evaluation.study select --study local-runtime/study --train local-runtime/train-attempt --validation local-runtime/validation-attempt --output local-runtime/selection
```

The default freezes analytical versus the best validation fixed lead, without
importing optional ML. To fit the **single declared** tree, explicitly add
`--fit-model` after installing the reviewed optional requirements in the study
venv. The selection manifest records actual Python, scikit-learn (must be 1.7.2),
NumPy, SciPy, joblib and threadpoolctl versions and the optional requirements byte
hash. There is no hidden parameter search or install/upgrade in this command.

Each collection must supply all seven audited worlds per frozen episode. The
verifier checks its split before opening outcomes, original raw-byte hashes,
scalar/raw consistency, lifecycle and signal audits, recomputed common-window
recovery, source/runtime, candidate inventory and observation-only predictions.
Failed/censored policy outcomes remain rows; invalid infrastructure/audit attempts
cannot be pooled into a cosmetically complete dataset. It does not accept a test
path or scan directories looking for outcomes.

Too few finite training labels produce `baseline_only`, with a reason and no model.
No common feasible validation cohort produces `inconclusive`, with no invented
best fixed comparator. A fitted tree yields `learned_ready`, **not** a performance
claim, and separately freezes comparisons against both analytical and best fixed
lead. Selection never releases test; that requires the separate explicit gate below.


## Explicit held-out release, one attempt, descriptive reporting

These commands are **not** part of preparation or routine tests. Run them only
when development-data review is complete and the selection artifact is ready.
The mode is mandatory: `learned` requires the learned model plus both strong
comparators. `baseline_only` is a deliberate alternative, never a silent fallback
from an inconclusive learned selection. An inconclusive fixed comparator blocks
both modes.

```powershell
python -m evaluation.study_release --study local-runtime/study --selection local-runtime/selection --mode learned
# Copy the printed release_sha256 exactly; do not substitute a guessed hash.
python -m evaluation.collector --study local-runtime/study --split test --release-sha256 RELEASE_SHA256 --output local-runtime/test-attempt
python -m evaluation.study report --study local-runtime/study --collection local-runtime/test-attempt --output local-runtime/test-report
```

Use `--mode baseline_only` only for the explicit analytical-versus-best-fixed
study. Release writes immutable `test-release.json`; collection reserves immutable
`test-attempt.json` before its first world. A crash or failed attempt leaves the
claim in place and does **not** authorize automatic retries, deleting markers,
changing seeds or silently replacing the protocol. Preserve evidence and review
any future revised protocol explicitly. The report cannot create a release,
claim, simulation run or model.

The held-out verifier checks the release, selector artifacts, exclusive claim,
exact claimed output directory and full declared inventory before reading
outcomes. It then repeats the raw evidence audits used for development data.
Incomplete or infrastructure-failed attempts are retained but cannot be promoted
to a complete decision report. Audited policy failures and censored outcomes
remain in the completed inventory and failure counts; no finite cost is invented.

`report.json` binds original raw bytes, source/runtime, release, claim and selector
hashes. Choices are recomputed from frozen observations—not picked from test
outcomes. Learned studies report both learned-versus-best-validation-fixed and
learned-versus-analytical comparisons. Ordinary/immediate results are descriptive
context, not replacements for those stronger comparators.

The report exposes all policy status counts, paired failures, finite-cohort
objective/ambulance/civilian differences and common-absolute-window excess queue
area differences. Grouped 95% percentile bootstrap intervals use a fixed seed 0,
2,000 resamples and a minimum of 10 independent demand groups. Below that support,
the interval is null with an explicit reason. Finite comparisons remain
conditional on both policies completing validly; no multiplicity-adjusted
significance, automatic performance badge, deployed safety or lives-saved claim
is produced. Read failures and cohort sizes alongside any interval.


## Predeclared representative traces (optional presentation evidence)

Before freezing the study, set `illustrative_capture` to zero–three unique **test**
case IDs already in the declared case inventory. An empty list requires both byte
limits to be zero. Otherwise explicitly choose positive `max_world_bytes` (at most
8 MiB) and `max_total_bytes` (at most 256 MiB, at least the per-world limit).
No examples are selected by favorable outcomes. The collector uses the existing
case and policy order, not a ranking by results.

Only ordinary and all five fixed-lead worlds of those cases retain compact
`rich-world.json`: exact recorded vehicles, signals, times, metrics and original
world policy/decision, before in-memory poses are released. Immediate remains
scalar/context evidence. `traces.json` binds the full six-world inventory, source,
study/protocol/input hashes, original identities and exact per-file SHA-256.
Collection metadata binds the exact trace-manifest file hash; outcome rows retain
their corresponding capture entries. No virtual poses are reconstructed later.

Limits are checked against the complete compact JSON byte length before writing.
Intended bytes are charged before each attempted write, so a failed partial write
cannot silently recycle its budget. Budget, serialization, file-write or optional
manifest failure is explicit, with partial evidence retained where safe. Such
presentation failures **do not** turn a valid scalar outcome into an infrastructure
failure, discard it, stop the planned scientific collection, select another case
or authorize a rerun. Scalar evidence may still support an honest report; an
exporter must refuse an incomplete six-world representative capture.

The local capture allowance is not a public-file allowance. Public paired replay
JSON remains below the existing **20 MiB** limit; the separate 25 MB map allowance
does not apply to traces. A model-selected presentation must independently verify
all six retained worlds and choose solely from the frozen lagged observation,
retaining physical policy `fixed` and an explicit cached-selector provenance
record. It must not relabel an unrelated recording as a learned simulation.


## Selection and percentile schema revision

New selections use `afterlight.study-selection.v2`. They retain
`validation-candidates.json` as the **exact bytes** of the already-audited
validation collection's `candidate-outcomes.json`. The file is bound both to that
original file SHA-256 and the canonical candidate-row digest. Release/report
verification reads this validation-only snapshot and recomputes the failure-first,
common-feasible best-fixed argmin and full selector artifact. Merely repeating a
weaker lead in consistently rehashed metadata cannot certify it as best-fixed.
There is no held-out access or model refit in this check.

Version 1 selections or missing snapshots are rejected explicitly; do not guess,
relabel, silently upgrade or reconstruct evidence from test outcomes. No study
may be relabeled or rewritten to upgrade its schema. Changing
source/protocol requires preserving the prior evidence and reviewing a fresh
study, not recycling an exposed test set.

Decision comparisons now use `afterlight.decision-comparison.v2`. The ambiguous
`conditional_civilian_harm_p95_s` key is removed, not redefined. Its explicitly
named replacement is `conditional_episode_mean_civilian_delta_p95_s`, with a
population descriptor: nearest-rank p95 across **episode-level differences in
all-demand civilian mean excess time**, conditional on both policies completing
validly through the common drain. It is **not** a percentile of individual
civilian journeys or individual harms. No per-vehicle tail statistic is inferred
from means. Older comparison outputs remain historical artifacts, not silently
converted claims.
