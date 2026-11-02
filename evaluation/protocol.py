"""Content-addressed protocol freezing and pilot evidence summaries."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Mapping, Sequence
from .metrics import finite, objective
from .splits import assert_disjoint


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_episode_inventory(protocol: Mapping) -> dict[str, Mapping]:
    inventory = protocol.get("episode_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("frozen protocol requires a complete episode inventory")
    by_id = {}
    for item in inventory:
        if not isinstance(item, dict) or not {"episode_id", "demand_group_id", "split", "demand_sha256", "network_sha256", "dispatch_s"} <= item.keys():
            raise ValueError("inventory episode lacks identity, split, hashes or dispatch time")
        for key in ("episode_id", "demand_group_id", "demand_sha256", "network_sha256"):
            if not isinstance(item[key], str) or not item[key]:
                raise ValueError("inventory identities and hashes must be nonempty strings")
        if item["episode_id"] in by_id or item["split"] not in {"train", "validation", "test"}:
            raise ValueError("duplicate episode id or invalid inventory split")
        finite(item["dispatch_s"], "inventory dispatch")
        by_id[item["episode_id"]] = item
    assert_disjoint(inventory, protocol["group_assignments"])
    if {item["demand_group_id"] for item in inventory} != set(protocol["group_assignments"]):
        raise ValueError("episode inventory must cover exactly all declared demand groups")
    return by_id


def assert_episode_coverage(rows: Sequence[Mapping], protocol: Mapping, split: str) -> None:
    inventory = validate_episode_inventory(protocol)
    expected = {eid for eid, item in inventory.items() if item["split"] == split}
    if not expected or {row["episode_id"] for row in rows} != expected:
        raise ValueError(f"{split} outcomes omit or add declared episodes/dispatch variants")
    for row in rows:
        item = inventory[row["episode_id"]]
        for key in ("demand_group_id", "split", "demand_sha256", "network_sha256"):
            if row.get(key) != item[key]:
                raise ValueError(f"episode differs from frozen inventory: {key}")
        dispatch = row.get("dispatch_s", row.get("observation", {}).get("dispatch_s"))
        if dispatch != item["dispatch_s"]:
            raise ValueError("episode dispatch differs from frozen inventory")


def freeze_protocol(protocol: Mapping, destination: Path) -> dict:
    required = {"schema", "source_commit", "group_assignments", "feature_schema", "candidate_leads_s",
                "civilian_weight", "horizon_s", "drain_end_s", "recovery_window_s", "tie_break",
                "invalid_rules", "heldout_regimes", "model_specification", "analytical_estimator", "episode_inventory"}
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
    validate_episode_inventory(protocol)
    envelope = {"sha256": digest(protocol), "protocol": dict(protocol)}
    # Exclusive creation avoids overwriting a frozen test contract accidentally.
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return envelope


def pilot_summary(rows: Sequence[Mapping], *, civilian_weight: float = 1.0, useful_action_margin_s: float = 1.0) -> dict:
    if not rows or any(row.get("split") != "pilot" for row in rows):
        raise ValueError("pilot summary requires nonempty exclusively pilot rows")
    finite(civilian_weight, "civilian_weight")
    finite(useful_action_margin_s, "useful_action_margin_s")
    runtimes = [finite(r["runtime_s"], "runtime_s") for r in rows]
    schedules: dict[str, set[str]] = {}
    for row in rows:
        if row.get("lead_s") is not None:
            if "request_plan" not in row:
                raise ValueError("lead candidate missing actual frozen request plan")
            if row["request_plan"] is not None:
                schedules.setdefault(row["episode_id"], set()).add(digest(row["request_plan"]))
    candidate_rows: dict[str, list[Mapping]] = {}
    for row in rows:
        if row.get("lead_s") is not None:
            candidate_rows.setdefault(row["episode_id"], []).append(row)
    outcome_diversity = {}
    useful_winners = set()
    for eid, candidates in candidate_rows.items():
        if sorted(row["lead_s"] for row in candidates) != [0, 5, 10, 20, 30]:
            outcome_diversity[eid] = {"status": "incomplete_candidate_grid"}
            continue
        if any("accounting" not in row for row in candidates):
            outcome_diversity[eid] = {"status": "outcomes_unavailable"}
            continue
        if any(row["status"] == "infrastructure_error" for row in candidates):
            outcome_diversity[eid] = {"status": "infrastructure_failure"}
            continue
        ranked = sorted((cost, row["lead_s"]) for row in candidates if (cost := objective(row, civilian_weight)) is not None)
        if not ranked:
            outcome_diversity[eid] = {"status": "all_candidates_infeasible"}
            continue
        margin = finite(ranked[1][0] - ranked[0][0], "pilot runner-up margin") if len(ranked) > 1 else None
        distinct_schedule_count = len(schedules.get(eid, set()))
        useful = len(ranked) > 1 and margin > useful_action_margin_s and distinct_schedule_count > 1
        if useful:
            useful_winners.add(ranked[0][1])
        outcome_diversity[eid] = {"status": "observed", "feasible_candidates": len(ranked),
            "oracle_lead_s": ranked[0][1], "runner_up_margin_j_s": margin,
            "useful_margin_observed": useful}
    return {
        "rollouts": len(rows), "episodes": len({r["episode_id"] for r in rows}),
        "demand_groups": len({r["demand_group_id"] for r in rows}),
        "runtime_total_s": finite(sum(runtimes), "total pilot runtime"), "runtime_median_s": median(runtimes),
        "runtime_max_s": max(runtimes),
        "effective_schedules_by_episode": {k: len(v) for k, v in sorted(schedules.items())},
        "status_counts": {status: sum(r["status"] == status for r in rows) for status in sorted({r["status"] for r in rows})},
        "outcome_diversity_by_episode": outcome_diversity,
        "distinct_useful_oracle_leads": sorted(useful_winners),
        "multiple_useful_actions_observed": len(useful_winners) >= 2,
        "civilian_weight": civilian_weight, "useful_action_margin_s": useful_action_margin_s,
        "interpretation": "Exploratory pilot oracle diagnostics only, not held-out selector performance. Different request signatures alone do not establish useful action diversity.",
    }
