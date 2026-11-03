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
