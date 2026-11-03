# Recorded Omen acceptance

Run these commands from the checkout root **on Omen only**. This tool does not
install dependencies, build the app, fit models, or read held-out results. The
default `units-network` profile runs Python/Node units and fixture/city network
conversion; traffic requires the explicit profile described below.

First resolve any existing remote/manual process: a disconnected session does
not prove its tests or SUMO process stopped. This runner has **no concurrency
lock** and does not detect unrelated processes. The confirmation below is an
operator assertion, not evidence of process liveness.

```powershell
# Inspect fixed commands without executing anything:
.\.venv\Scripts\python.exe -B scripts/omen_acceptance.py --plan --output local-runtime/acceptance/checkpoint-01
# Only after process preflight; replace SHA with the exact approved commit:
.\.venv\Scripts\python.exe -B scripts/omen_acceptance.py --execute --expected-commit <FULL_SHA> --confirm-no-active-runs --output local-runtime/acceptance/checkpoint-01
# Safe after reconnect: read records, never resume or rerun:
.\.venv\Scripts\python.exe -B scripts/omen_acceptance.py --status --output local-runtime/acceptance/checkpoint-01
```

Use an installed Node runtime and already-installed repository dependencies.
`run.json` and `steps/<name>/step.json` are atomically replaced and contain exact
commands, working directories, environment overrides, PID, timestamps and exit
codes. Separate stdout/stderr logs are retained. Source bytes and index/HEAD
identities are checked before/after steps, without trusting cached Git status.
Every preview manifest source/output/runtime-asset entry is included, along with
API, tests, generators, frontend configuration and compiled preview inputs.
Installed direct Node dependency versions must match the lock; their package
metadata and installed lock hashes are retained. This does **not** verify the
installed dependency code tree.
The first failure stops subsequent steps. A zero exit with changed source is not
accepted as pinned-source evidence.

Output must be a **new** `local-runtime/acceptance/<safe-id>` directory. Existing
attempts are never overwritten, resumed, retried, or cleaned automatically.
Unknown/started prior acceptance records block a new attempt, including a
partially created directory after a crash. Inspect the actual local processes
and preserve the old evidence before any manually reviewed resolution. No
process is cancelled or killed. An interrupted wait or missing terminal record
is reported as **unresolved**, not success or confirmed process termination.

Only the new output directory receives logs, converted networks and redirected
child temp/cache files. Build/browser/traffic acceptance remains a separate,
explicit workflow; these checks cannot establish visual quality or policy gain.


## Explicit traffic qualification (Omen only)

Only after the unit/network checkpoint and process preflight, select a **new**
attempt directory. This profile runs no study collection, model training or
held-out evaluation. Seed 7 is qualification/exploration, never unseen evidence.

```powershell
.\.venv\Scripts\python.exe -B scripts/omen_acceptance.py --plan --profile traffic-qualification --output local-runtime/acceptance/traffic-01
.\.venv\Scripts\python.exe -B scripts/omen_acceptance.py --execute --profile traffic-qualification --expected-commit <FULL_SHA> --confirm-no-active-runs --output local-runtime/acceptance/traffic-01
```

The fixed ordered stages are fixture moderate fixed lead 10; independent fixture
ordinary/ordinary with identical saved demand/network identities; then sparse
city fixed lead 10 from P001 to HOSP_EAST. Each pair is followed by the full
artifact audit and a separate completion gate. The latter binds audit/replay
hashes, source, route, seed, regime, policy and timing, and rejects **either**
world being invalid, censored, incomplete or carrying validity reasons. Audit
consistency by itself is not enough. The ordinary pair also requires the exact
negative-control audit to pass; later stages never start after a failed gate.

All commands explicitly freeze dispatch 60 s, demand end 180 s, common horizon
240 s, drain 360 s, integration step 0.5 s and recording sample 1 s. Total planned
allocation is six worlds × 600 simulated seconds = 3,600 simulated seconds.
This is **not a wall-time estimate or limit**: an active child has no automatic
timeout or kill. Logs and every failed/raw outcome stay in the new attempt.
`traffic/<case>/qualification.json` is fresh-only and says `qualified`, not
benchmark superiority, visual acceptance or real-world traffic safety.
