# Saved-input studies

This workflow prepares a finite, declared study from an **actually completed,
audited pilot**. It does not turn pilot data into training data, run an experiment
implicitly, or manufacture a model. Execute commands and tests only on the
assigned Omen machine. New study tooling still needs its first local verification.

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

- `schema`: `afterlight.study-spec.v1`; safe `study_id`; `network_kind`: fixture or city.
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
- `heldout_regimes` and `heldout_route_families`: explicit lists (possibly empty).
  Every declared holdout must be represented in test only. For held-out route
  families, the actual ordered edge route cannot also appear outside test.
  Other family labels remain user-defined strata, not geometric novelty claims.

All three splits must exist. Every civilian realization and all its dispatch/route
variants stay in one split; pilot groups cannot be reused. Preparation saves demand
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
consumes only the saved, frozen inputs. Initially only train and validation are
accepted; **test is explicitly rejected** until a reviewed selector-release gate
exists. The collector retains ordinary, immediate and all five fixed worlds,
raw evidence and all failed/unattempted inventory entries. `outcomes.json` holds
all worlds; `candidate-outcomes.json` holds the fixed candidates for later fitting.
No default training, selector freeze, test release or report CLI is implied here.

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
Rich trace retention and test-release orchestration are subsequent checkpoints.

Hashes and metadata guards detect drift and inconsistent artifacts. They cannot
prove a human never inspected test information or that reported files are truthful
without independent execution. No held-out gain is claimed before actual results.
