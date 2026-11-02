# Loopback local adapter

This is a development/local research service, not a public hosting backend. Bind
is fixed to `127.0.0.1`; do not expose it through a tunnel or change firewall rules.
No account, credentials or paid service are required.

```powershell
# Recordings only, generation disabled by default:
.\.venv\Scripts\python.exe -m api.server
# Explicit real local generation, after SUMO correctness gates pass:
.\.venv\Scripts\python.exe -m api.server --enable-generation
```

Set the viewer's `VITE_API_BASE=http://127.0.0.1:8765` for this local adapter.
Only loopback viewer origins are allowed; Host validation prevents DNS rebinding.
The static public viewer does not start simulations.

- `GET /api/health`: capabilities, never a fake progress value.
- `GET /api/catalog`, `GET /api/runs/{id}`: allow-listed verified recording files.
- `POST /api/runs`: enabled only by the explicit flag; JSON parameters `network`,
  `seed`, `regime`, `policy`, `lead`, `pickup`, `hospital`, and optional `request_id`.
  A 32-hex client request ID is an idempotency key: the same ID/parameters returns
  the existing job, never starts a second one; changed parameters are rejected.
- `GET /api/jobs/{id}`: queued/running/completed/failed actual process lifecycle.
- `GET /api/jobs/{id}/replay`: only a completed validated real paired recording.

One job runs at a time. Repeated submissions are rejected, not silently queued.
Outputs go to server-generated directories under `local-runtime/jobs`; clients
cannot choose paths or shell commands. Each job uses the same bounded fixture
protocol (dispatch60, demand end180, horizon240 plus drain360 seconds), pilot
split only. This is local *generation followed by recorded playback*, not live
streaming or an evaluated learned controller. All completed/invalid/censored
outcomes are retained. Errors are not replaced by sample data.

Stopping the server waits for an active job to finish so it does not abandon a
SUMO child process. There is no active-job cancel UI in this checkpoint. Terminal job records can be recovered by their exact ID after restart; outputs
survive restart. In-progress work cannot be silently resumed after a process crash. Do not change checkout
while a run is active. Use the exporter to register a completed run into the
recording catalog after validation.

Tests under `tests/api` use explicit synthetic unit fixtures and mock runners;
they never establish traffic benefit. Execute all tests on Omen, not the cloud.

The server captures the simulation source identity at startup. If the checkout
changes, new generation is refused until the server is restarted; a long-lived
Python process must not attribute cached old modules to a newer commit. Existing
verified recordings remain readable. Do not pull while a simulation is running.
