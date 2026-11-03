# Recorded Omen acceptance

Run these commands from the checkout root **on Omen only**. This tool does not
install dependencies, build the app, run traffic, fit models, or read held-out
results. It runs Python/Node units and fixture/city network conversion.

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
