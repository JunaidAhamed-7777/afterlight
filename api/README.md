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

## Artifact and source integrity

HTTP replay reads, generation completion checks, and restarted-job recovery use
one shared **64 MiB** byte cap. The cap applies to the actual read, not just a
prior file-size check. Oversized or changed artifacts remain on disk but cannot
be advertised/served as verified completions. Both replay endpoints return the exact original bytes that passed their
recorded hash, schema and request/catalog checks. Pretty-printing is preserved,
so catalog SHA256 and byte counts remain valid in the viewer. They do not
reserialize hash-bound replays or reopen a separately validated path. JSON
nonfinite tokens, exponent overflow (such as `1e309`) and excessive parser depth
are rejected as controlled errors, including nested metadata values. JSON is
UTF-8 (an optional UTF-8 BOM is accepted), with at most **64 nested object/array
containers including the root**. A quote/escape-aware linear scan enforces this
bound before structure decoding, independently of interpreter recursion limits.
The same depth bound covers requests, catalogs, replay bytes, recovered job
records and generated HTTP metadata. Byte limits remain context-specific: replay
and catalog reads default to 64 MiB, persisted job metadata to 1 MiB, and POST
bodies to 16 KiB. An explicit context cap is honored by both the reader and
parser rather than being replaced by the replay cap. Exact-byte replay responses remain unchanged.

Generation rechecks the server's startup source identity after the runner and
again before recording completion. A mismatch is an explicit infrastructure
failure, not a measured policy outcome; raw simulation evidence is retained.
The fixed 600-second simulation horizon is **not a wall-clock timeout**. There
is no unsafe thread cancellation or global process-kill fallback: shutdown
waits for the owned runner, and this checkpoint does not promise bounded wall
runtime or automatic crash recovery.
