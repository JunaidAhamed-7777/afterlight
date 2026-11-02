# Evaluation tools

These modules are implementation, **not measured experiment results**. Test fixtures use explicitly synthetic inputs. All execution/acceptance is on Omen, not the cloud development PC.

From repository root, Python 3.12+:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/evaluation -p "test_*.py" -v
.\.venv\Scripts\python.exe -m evaluation audit outcomes.json --civilian-weight 1
.\.venv\Scripts\python.exe -m evaluation pilot pilot-outcomes.json
.\.venv\Scripts\python.exe -m evaluation freeze proposed-protocol.json frozen-protocol.json
```

`audit` expects an array of scalar outcome objects; it never starts simulations. Each row includes `episode_id`, `demand_group_id`, `split`, `status`, `validity_reasons`, `ambulance_journey_s`, `civilian_mean_excess_s`, and integer civilian `accounting` fields: `scheduled`, `inserted`, `completed`, `running`, `not_inserted`. Candidate rows/dispatch variants share their original demand group. Pair validation additionally requires matching `demand_sha256`, `network_sha256`, `horizon_s`, and `drain_end_s`.

Only valid fully drained completed outcomes receive finite `J = ambulance_journey_s + civilian_weight * civilian_mean_excess_s`. Null targets are retained, not imputed or silently dropped. Infrastructure failures are distinct from policy invalidity. Corrupt accounting is an error. Queue excess integrates left-held observations over a prespecified **absolute** window with full coverage; no extrapolation or exit-time realignment.

Freeze creates a new content-addressed protocol file exclusively; it cannot overwrite an existing file. The protocol records source, whole-group assignments, held-out regimes, features, five leads, weight, horizon/drain, recovery window, tie-break, invalid rules and model specification. Freeze is not evidence that the experiment was executed or that the held-out data stayed untouched. Preserve the frozen artifact and raw outcomes in a reproducible run record.
