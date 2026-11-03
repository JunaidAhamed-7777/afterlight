# Recorded evidence export

Ordinary paired runs use `python -m export.catalog --run <run> --destination
web/public/replays`. Registration audits raw evidence and preserves exact replay
bytes. It is not deployment, proof of improvement, or permission to hide invalid
outcomes.

For dense recordings, use lossless transport compression:

```powershell
python -m export.catalog --run local-runtime/<audited-run> --destination web/public/replays --gzip --title "Westhaven response"
```

The published `.json.gz` must be below 20 MiB physically and decode to below
128 MiB. Catalog `sha256` and `bytes` always identify the **original recorded
JSON bytes**; `transfer_sha256` and `transfer_bytes` identify the gzip file.
Compression is roundtrip-checked before any destination files are installed.
The viewer decompresses before raw-byte checksum/schema validation. Repacking
keeps the same scenario identity and evidence companion; raw simulation journals
are retained locally. A human title changes presentation only. The owner's
50 MB total shipped-asset ceiling is measured against actual deployed file bytes,
not decoded JSON memory size.

## Frozen-selector illustrative replay

`selected_replay` closes the gap between a scientific candidate-selection result
and an interactive recording without running traffic again. Run it **on Omen
only**, after a complete released study and report:

```powershell
python -m export.selected_replay --study local-runtime/<frozen-study> --collection local-runtime/<released-test-collection> --report local-runtime/<report> --case <predeclared-case-id> --output local-runtime/<new-selected-export>
```

Requirements:

- The case was one of at most three test cases declared **before study freeze**.
- Its ordinary world and all five fixed-lead candidates were captured during the
  one original collection attempt, within the frozen byte budgets. Missing traces
  cause a refusal, never a rerun, pose reconstruction or substitute case.
- The study, source, model/selector, release, complete collection and final report
  pass their existing checks. Report verification recomputes deterministic metrics
  and intervals from released outcomes; it does not fit or rerun simulation.
- The model/analytical selector chooses a lead from the original lagged
  observation, not from which candidate had the best outcome.

The selected world still says physical policy `fixed`. Only display world IDs
are aliased to `baseline`/`afterlight`; original full-world bytes and raw SUMO
outputs remain retained with their hashes. Separate `selection_evidence` describes
why the frozen selector chose this recorded candidate. Invalid or censored
selected outcomes are preserved, never swapped for a nicer-looking run.

This helper writes only a fresh ignored local export and runs the normal paired
artifact audit. Public catalog registration has separate **20 MiB physical /
128 MiB decoded** per-recording caps when using gzip. A scalar study may sample
vehicle poses too coarsely for a polished public replay; retain that scientific
evidence without publishing it as a visual demo. No model,
trace, selected replay or benefit is supplied as a fake fallback. Source is
implemented; actual Omen end-to-end acceptance remains required.

The current source-pinned study has a disclosed
[pre-test analysis correction](../docs/ANALYSIS_AMENDMENT.md). For its report,
use the explicit main-checkout adapter after final report verification:

```powershell
.venv\Scripts\python.exe scripts/export_selected_amended.py --checkout C:/Github/afterlight-final-study-v4 --study local-runtime/expanded-city-study-v4 --collection local-runtime/study-test-v4 --report local-runtime/study-report-v4 --amendment local-runtime/analysis-amendment-v1/analysis-amendment.json --case test-sparse-01 --output local-runtime/study-selected-offline-v4
```

This uses the unchanged original trace verification, replay assembly, frozen
selector decisions and paired raw audit. It records both the amendment and the
adapter's exact source hash. An existing or rejected evidence directory receives
no new files. Its final identity-failure marker is permitted only after creating
a fresh owned export. The current study's scientific traces are sampled at
5 seconds; this selected export stays offline and cannot inherit the dense
0.5-second public-demo presentation checks. No resampling or rerun supplies
missing physical poses.


Public city registration now requires captures at every recorded integration
boundary when simulation-step provenance is present. A 2 s or 5 s vehicle trace
cannot be promoted to a public city demo for a 0.5 s simulation: interpolation
can otherwise move stopped vehicles across a red stop line before an actual
green event. Coarse scalar-study evidence is retained locally; fresh exploratory
visual captures use `--sample 0.5`. Compression preserves every actual sample.

The read-only presentation audit checks the deployed catalog's transfer and
decoded hashes, every actual 0.5 s pose sample, exact recorded signal timelines,
and geometrically eligible interpolated front-bumper stop-line crossings:

```powershell
node --experimental-strip-types web/scripts/audit-presentation.mjs --output local-runtime/new-presentation-review.json
```

It exits unsuccessfully for red crossings, unresolved controlled movements,
missing exact timelines, corrupt files or an existing report destination.
The report binds the catalog, audit source, production timeline helper and viewer
TypeScript module hashes, including the production validators and catalog binding.
Malformed recordings, mismatched catalog metadata and empty crossing coverage
cannot produce a passing review.
Mixed movements use the declared ambulance route or a uniquely matching future
outgoing-lane pose and heading; unresolved cases remain failures. This checks the
replay presentation, while the separate raw SUMO tripinfo/lifecycle audit checks
scientific artifact consistency. Neither is a real-world safety certification.
