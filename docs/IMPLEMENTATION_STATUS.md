# Implementation checkpoints

> **Owner handoff:** cloud work stopped at the explicit November 3 halt. See
> [HANDOFF.md](../HANDOFF.md). The final split-scroll/follow/zoom/signal source is
> preserved but unbuilt and untested; the existing compiled preview remains
> bound to `975dd295` and was accepted in artifact commit `3060716`.

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
inputs, real status and validated completed recordings. Synthetic local-generation protocol checks passed on Omen, and a genuine API job completed and passed raw audit before the owner’s halt. Restart/recovery and full API lifecycle acceptance remain pending. It is not live streaming and
does not invent progress.

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

See [Omen validation log](validation/OMEN_LOG.md) for source-specific results.
At `11be524`, the complete unit/network journal passed: **500 Python checks,
four skips, and 85 Node checks**, with both network conversions warning-free.
All four desktop suites and the focused V3 pointer/fade/layout probe passed;
static network qualification passed 33 checks including all 200 city routes.

The fresh fixed-priority fixture and ordinary/ordinary negative control both
qualified. All four worlds completed their 120 scheduled civilians, with no
running/uninserted vehicles, collisions or teleports. The negative control's
trace/control equality passed. This resolves the previously observed insertion
collision for this qualification case, not every possible traffic scenario.

The sparse-city pair temporarily lost its Omen connection; inspection of the
existing journal has now resolved that unknown outcome. All nine traffic stages
exited zero in 94.98 s wall time, with matching source fingerprints and no active
process remaining. The sparse P001 → HOSP_EAST pair completed all 37 civilians
per world by 600 s. Across all six qualification worlds, collisions, teleports,
running and uninserted counts were zero at that endpoint. Signal/recovery,
automated alignment, demand/tripinfo and causality audits passed. At 240 s the
city worlds still had 21 and 20 running civilians; the common drain is essential.
Ambulance journeys were 210.5 s baseline and 182.5 s priority in this one
exploratory pair, not an aggregate policy-benefit estimate.

API restart/recovery and full lifecycle acceptance, pilot throughput/diversity
and all learned evaluation remain open gates. Scoped real-replay rendering results follow below. The
public recording catalog remains empty; no performance benefit is claimed.
The [compiled preview](../preview/README.md) permits separate browser acceptance
without npm installation, but does not waive the source-build or simulator gates.

## First genuine city viewer follow-up

At `5293ae0`, 64 Python and 89 Node checks plus the local production build
passed. Separate normal-UI checks of the real city recording at 205, 207 and
220 seconds confirmed solid/ghost matrices and world-switch isolation without
browser errors. The new automated harness failed at its journey-filtered
selection step; `5dad4cb` corrected that entry flow. Approximately 5 cm tyre
penetration was observed across 48 contacts at that earlier checkpoint.

At corrected preview `3060716` (compiled source `975dd29`), **37 Python and 90
Node checks passed**. The genuine replay harness passed at 61, 61.5 and 242 s,
including fractional playback and actual solid/ghost matrix and world-isolation
checks, without browser errors. The lowest tyre contact was 0.180000007 m,
matching the road surface. Twelve screenshots supported gross road placement;
exact stop-line and sub-centimetre visual alignment are not certified.

The preservation retry passed for both 109-file evidence copies and all 243
tracked files; original source HEAD/index were unchanged. The read-only `5293ae0`
demo remained on ports 5180/8765, while corrected staging used 5181. No promotion
or new simulation is implied. No ML dependency was installed; real API generation,
pilot and learned evaluation remain pending. Historical failures stay in the log.

## Requested next desktop UI cohort — not yet accepted

The owner requested a viewport-fixed **right-hand 3D view and playback**, with
**left-hand settings/evidence scrolling independently**. The same pass must add
greater zoom, legible per-link intersection signals, and robust ambulance follow
when pausing, scrubbing or switching worlds. Frontend/camera work is in progress;
this section records requested behavior, not implementation or test completion.
Preserve the live `5293ae0` demo while a separate new cohort is built and accepted
on Omen. Desktop remains the sole optimization/test target.

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

The current source/unit/desktop coverage is recorded at `11be524` above. It does
not establish every scientific scenario or a learned result. No pilot, trained
model, held-out gain or accepted city/public replay has been produced. The
public recorded catalog remains intentionally empty.

## Desktop V3 and current acceptance boundary

The current source-bound preview is compiled from `975dd29`; its exact output
hashes and source identity are recorded in `preview/manifest.json`.
It includes V3 modeled building details and opt-in map selection with actual
canonical markers, drag suppression, rolled-camera raycasting and a separate
local-request map-selection lock. The `11be524` source/desktop acceptance covers these changes, but does not
establish actual city playback or learned-policy performance. Desktop is the sole optimization/test target; preserve existing
responsive behavior without starting mobile-specific work.

The map allowance is 25 MB; the current enhanced GLB is 4,439,048 bytes according
to its asset manifest. Low-poly instanced vehicles and the original canonical
coordinate system remain unchanged. Source/unit/desktop checks passed at
`11be524`; the later scoped genuine-playback checks at `3060716` are recorded above.

The offline selected-replay provenance bridge is implemented in source, including
bounded predeclared trace capture, frozen-report verification, original-candidate
export and a separate desktop evidence inspector. **Real scientific capture/export
acceptance is pending**;
there is no released model or real selected capture. It selects one retained
fixed-lead candidate using a frozen selector, preserving physical policy, events
and timing. The inspector distinguishes exporter-declared artifact references
from independently verified evidence. It is not a live learned controller, and
one recording cannot establish a study conclusion. See [export contract](../export/README.md).

## API status at owner halt

The Omen halt journal reports a genuine API job completed and passed raw audit
on `3060716`. The task-owned API on port 8780 was stopped; no simulations or
test clients remained active. Restart/recovery tests were not run. The user
demo on 5180 and read-only API 8765 were preserved. The isolated validated
checkout stayed clean at `3060716`, while the original main checkout remained
`3f679def`; neither was reset or silently updated to the final source.
