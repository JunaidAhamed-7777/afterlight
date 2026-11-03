# Implementation checkpoints

This document distinguishes source implementation from execution evidence. All
acceptance testing and simulation experiments are performed on the owner's Omen
Windows PC; cloud code review/build is not an acceptance result.

## Initial source checkpoint

- Shared frozen-lead scheduling and conservative legal transition state machine.
- Local-only recordings API with catalog allow-list and path confinement.
- Unit checks written for timing, finite hold, ordinary-world isolation and API boundaries.
- Official SUMO 1.28.0 dependencies pinned for the Python 3.12 acceptance environment.
- **Initial checkpoint only:** unit tests, SUMO conversion/runs and product browser acceptance were unexecuted then. Later scoped unit results are in the [acceptance log](validation/OMEN_LOG.md).
- **Not yet available:** measured benchmark, trained model, real replay catalog.

The initial API served recordings only. The optional local-generation adapter now
connects to the real runner when explicitly enabled, with one active job, bounded
inputs, real status and validated completed recordings. This source capability is
pending Omen acceptance; it is not live streaming and does not invent progress.

## Reproduction commands — use the existing pinned environment

From `C:\Github\afterlight` in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sim.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests/sim -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/api -v
```

If the Windows Python launcher is unavailable, invoke the already-installed
Python 3.12 interpreter by its local path instead; no global Python change is
required. Do not infer success from these instructions. Record command, source commit,
environment, output, pass/fail and untested scope after real execution.

Official package source: https://pypi.org/project/eclipse-sumo/1.28.0/

## Local acceptance evidence

See [Omen validation log](validation/OMEN_LOG.md) for scoped actual results and
known failures. A newer source commit does not inherit a prior test pass. The
complete pinned SUMO and npm dependencies were installed on Omen. A real fixture
pair executed but was invalid due to a civilian collision; the insertion fix
still needs a fresh paired run. At `7ef8ffe`, both fixture and city conversion
completed with empty warning logs, and desktop browser acceptance passed.
Conversion is not traffic acceptance. Later source revisions remain untested
until the device returns; its last Python batch outcome is unknown and must be
resolved from process state and saved logs before any retry.
The [compiled preview](../preview/README.md) permits separate browser acceptance
without npm installation, but does not waive the source-build or simulator gates.

## First imported-city geometry audit

After a genuine city network conversion on Omen, inspect its actual stop lines
without rerunning or modifying SUMO:

```powershell
python -m sim.geometry_audit --graph assets/map/city_manifest.json --network local-runtime/city-7/network/network.net.xml --output local-runtime/city-7/stop-line-audit.json
```

Use the actual generated network path. The command refuses an existing report
and records graph/network hashes, every signalized incoming lane, signed setback
and lateral offset. Reconcile discrepancies before claiming city visual alignment;
a graph-connectivity pass is not a stop-line-position pass. The audit does not
alter simulation validity, move vehicles, or certify a real traffic system.

## Current cloud work after the laptop shutdown

- Exact replay bytes are now validated, hashed and returned unchanged by the API;
  source changes during generation fail as infrastructure, retaining raw evidence.
- Paired audits check identical pre-dispatch histories and causal observations,
  then policy-specific frozen ETA/lead request timing in independent worlds.
- The analytical selector now accounts for concentrated queues rather than
  assuming every junction can clear part of the same queue. Its conservative
  bound is a surrogate calculation, not a real-traffic guarantee.
- Study preparation isolates each RNG seed to one split/regime and excludes
  pilot seeds even when different demand rates produce different content hashes.
- Desktop map selection uses actual canonical curb/driveway anchors, with
  drag-safe clicks, keyboard alternatives and explicit recording/job locks.

These are implemented source capabilities with authored regression tests, not
new Omen test results. No pilot, trained model, held-out gain or accepted real
replay has been produced. The public recorded catalog remains intentionally empty.
