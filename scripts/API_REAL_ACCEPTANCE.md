# Genuine local API acceptance (Omen only)

This is a separate gate after units, real traffic qualification and real-replay
visual checks. `web/tests/local_generation_smoke.py` is still a **synthetic UI
protocol test**, not this genuine API test. No cloud execution is authorized.

Resolve all earlier/manual process uncertainty first and hold one clean source
SHA throughout. The client does not start, stop, restart or kill servers/SUMO.
It reuses the acceptance source/dependency identity, including installed direct
Node package metadata; it does not install anything or certify the full
third-party installation tree.

From the repository root, use a **new** output path:

```powershell
.\.venv\Scripts\python.exe -B scripts/api_real_acceptance.py prepare --expected-commit <FULL_SHA> --output local-runtime/api-real-01
# In a separate terminal; keep this server running until the client is terminal:
.\.venv\Scripts\python.exe -B -m api.server --enable-generation --job-dir local-runtime/api-real-01/jobs --port 8765
# In the client terminal after process preflight:
.\.venv\Scripts\python.exe -B scripts/api_real_acceptance.py run --output local-runtime/api-real-01 --confirm-no-active-runs --monitor-seconds 900
```

Preparation persists a fresh 32-hex request ID before network traffic. An
exclusive `run-started.json` claim blocks concurrent execution and crash retry
even if the mutable journal still says prepared. The only
request is city, seed 7, sparse demand, fixed lead 10, P001 → HOSP_EAST. The API
uses its fixed pilot/exploration protocol: two independent worlds, dispatch 60 s,
demand end 180 s, horizon 240 s + drain 360 s. No train/validation/test selection,
model fitting or dataset collection occurs.

After a valid acknowledged first POST, the client deliberately submits the
**identical saved body and ID** once to test idempotency. A lost, malformed or
unacknowledged first response never triggers this probe or an automatic retry.
The client records every request intent before sending, response bytes/hashes,
terminal audit and full raw-file inventory. A successful API job alone is not
enough: both traffic worlds must be valid completed, and HTTP replay bytes must
exactly equal the retained audited recording.

A 900-second **client observation window is not a simulator timeout**. If it
expires or the connection drops, the server/SUMO may still run. Do not start a
new attempt, change source or restart the server. Use GET-only status:

```powershell
.\.venv\Scripts\python.exe -B scripts/api_real_acceptance.py status --output local-runtime/api-real-01
```

Status does not alter the journal or submit work. A 404 is unresolved, not proof
that the original POST never executed. There is no automatic resume/retry path.
Preserve all files and resolve process state with the test coordinator.

Only after the journal says `terminal_verified`, gracefully stop the now-idle
server in its own terminal and restart the exact command with the same job path
and source. Then:

```powershell
.\.venv\Scripts\python.exe -B scripts/api_real_acceptance.py verify-recovery --output local-runtime/api-real-01 --confirm-server-restarted-after-terminal
```

Recovery first GETs and re-audits the exact terminal job. Only then it probes the
same POST, requiring unchanged job identity, replay hash and raw-file inventory.
An exclusive recovery marker blocks automatic repetition after interruption.
The restart flag is explicitly an **operator assertion**: the current API does
not expose an independent server-process identity. No traffic-benefit, visual
quality or deployed-safety claim follows from this software acceptance gate.
