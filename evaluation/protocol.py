"""Content-addressed protocol freezing and pilot evidence summaries."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence
from .metrics import finite


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def freeze_protocol(protocol: Mapping, destination: Path) -> dict:
    required = {"schema", "source_commit", "group_assignments", "feature_schema", "candidate_leads_s",
                "civilian_weight", "horizon_s", "drain_end_s", "recovery_window_s", "tie_break",
                "invalid_rules", "heldout_regimes", "model_specification"}
    if missing := required - protocol.keys():
        raise ValueError(f"missing protocol fields: {sorted(missing)}")
    if protocol["schema"] != "afterlight.protocol.v1":
        raise ValueError("unsupported protocol schema")
    finite(protocol["civilian_weight"], "civilian_weight")
    if list(protocol["candidate_leads_s"]) != [0, 5, 10, 20, 30]:
        raise ValueError("candidate lead contract changed; requires a new reviewed protocol")
    horizon, drain = finite(protocol["horizon_s"], "horizon_s"), finite(protocol["drain_end_s"], "drain_end_s")
    start, end = protocol["recovery_window_s"]
    if not 0 <= finite(start, "recovery start") < finite(end, "recovery end") <= drain or drain < horizon:
        raise ValueError("invalid common horizon/drain/recovery window")
    if not protocol["group_assignments"] or set(protocol["group_assignments"].values()) != {"train", "validation", "test"}:
        raise ValueError("protocol needs nonempty disjoint train, validation and test groups")
    if protocol["tie_break"] != "smallest_lead":
        raise ValueError("unsupported tie-break")
    if not isinstance(protocol["source_commit"], str) or not protocol["source_commit"]:
        raise ValueError("source commit required")
    if not isinstance(protocol["invalid_rules"], list) or not protocol["invalid_rules"] or not all(isinstance(r, str) and r for r in protocol["invalid_rules"]):
        raise ValueError("explicit invalid outcome rules required")
    if not isinstance(protocol["heldout_regimes"], list) or not all(isinstance(r, str) and r for r in protocol["heldout_regimes"]):
        raise ValueError("heldout_regimes must be a list of regime names")
    features = protocol["feature_schema"]
    if not isinstance(features, list) or not features:
        raise ValueError("nonempty timestamped feature dictionary required")
    names = []
    for field in features:
        if not isinstance(field, dict) or not {"name", "unit", "source", "sensor_lag_s"} <= field.keys():
            raise ValueError("features require name, unit, source, sensor_lag_s")
        if not all(isinstance(field[k], str) and field[k] for k in ("name", "unit", "source")):
            raise ValueError("feature metadata must contain nonempty strings")
        finite(field["sensor_lag_s"], "feature sensor lag")
        names.append(field["name"])
    if len(set(names)) != len(names):
        raise ValueError("duplicate feature names")
    if any(not isinstance(gid, str) or not gid for gid in protocol["group_assignments"]):
        raise ValueError("nonempty demand group identities required")
    envelope = {"sha256": digest(protocol), "protocol": dict(protocol)}
    # Exclusive creation avoids overwriting a frozen test contract accidentally.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return envelope


def pilot_summary(rows: Sequence[Mapping]) -> dict:
    if not rows or any(row.get("split") != "pilot" for row in rows):
        raise ValueError("pilot summary requires nonempty exclusively pilot rows")
    runtimes = [finite(r["runtime_s"], "runtime_s") for r in rows]
    schedules: dict[str, set[str]] = {}
    for row in rows:
        if row.get("lead_s") is not None:
            if "request_plan" not in row:
                raise ValueError("lead candidate missing actual frozen request plan")
            schedules.setdefault(row["episode_id"], set()).add(digest(row["request_plan"]))
    return {
        "rollouts": len(rows), "episodes": len({r["episode_id"] for r in rows}),
        "demand_groups": len({r["demand_group_id"] for r in rows}),
        "runtime_total_s": sum(runtimes), "runtime_median_s": median(runtimes),
        "runtime_max_s": max(runtimes),
        "effective_schedules_by_episode": {k: len(v) for k, v in sorted(schedules.items())},
        "status_counts": {status: sum(r["status"] == status for r in rows) for status in sorted({r["status"] for r in rows})},
        "interpretation": "Schedule diversity is not evidence that multiple actions are useful; inspect real training outcomes before freezing budget.",
    }
