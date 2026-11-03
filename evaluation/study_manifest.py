"""Saved-input study preparation and freezing. Never runs traffic or fits models.

Runtime entry points are intended for the designated Omen environment only.
Pure validators can be exercised with explicitly synthetic unit fixtures.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Mapping

from evaluation.metrics import finite
from evaluation.protocol import digest, freeze_protocol, pilot_summary, validate_episode_inventory
from evaluation.splits import assert_disjoint
from models.analytical import AnalyticalConfig, ESTIMATOR_VERSION, estimate_candidates
from models.residual import DEFAULT_FEATURES

REGIMES = {"sparse", "moderate", "asymmetric", "heavy"}
SPLITS = {"train", "validation", "test"}
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
POLICIES = [("ordinary", None), ("immediate", None), *(("fixed", lead) for lead in (0, 5, 10, 20, 30))]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _names(value, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value) or len(value) != len(set(value)):
        raise ValueError(f"{name} must be unique nonempty names")
    return value


def validate_spec(spec: Mapping) -> dict:
    required = {"schema", "study_id", "network_kind", "cases", "timing", "budget", "civilian_weight",
                "analytical_config", "model_specification", "heldout_regimes", "heldout_route_families"}
    if not isinstance(spec, Mapping) or not required <= spec.keys() or spec["schema"] != "afterlight.study-spec.v1":
        raise ValueError("incomplete or unsupported explicit study spec")
    if not isinstance(spec["study_id"], str) or not SAFE_ID.fullmatch(spec["study_id"]):
        raise ValueError("study_id must be a safe identifier")
    if spec["network_kind"] not in {"fixture", "city"}:
        raise ValueError("unsupported study network")
    cases = spec["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("an explicit nonempty case inventory is required; no automatic dataset budget")
    timing = spec["timing"]
    keys = {"demand_end_s", "horizon_s", "drain_s", "step_s", "sample_s", "sensor_lag_s", "recovery_window_s"}
    if not isinstance(timing, Mapping) or set(timing) != keys:
        raise ValueError("timing must explicitly define the complete common simulation contract")
    values = {k: finite(timing[k], k) for k in keys - {"recovery_window_s"}}
    if values["step_s"] <= 0 or values["sample_s"] < values["step_s"] or values["sensor_lag_s"] < 1:
        raise ValueError("positive integration/sample resolution and at least one-second sensor lag required")
    if values["demand_end_s"] <= 1 or values["horizon_s"] < values["demand_end_s"] or values["drain_s"] <= 0:
        raise ValueError("demand, common horizon and drain are inconsistent")
    end = finite(values["horizon_s"] + values["drain_s"], "common endpoint")
    for value in (values["horizon_s"], end, values["sample_s"]):
        if abs(value / values["step_s"] - round(value / values["step_s"])) > 1e-9:
            raise ValueError("horizon, endpoint and sampling must align to integration step")
    window = timing["recovery_window_s"]
    if not isinstance(window, list) or len(window) != 2 or not 0 <= finite(window[0], "recovery start") < finite(window[1], "recovery end") <= end:
        raise ValueError("invalid common absolute recovery window")
    heldout = _names(spec["heldout_regimes"], "heldout_regimes")
    heldout_routes = _names(spec["heldout_route_families"], "heldout_route_families")
    if not set(heldout) <= REGIMES:
        raise ValueError("unknown held-out regime")
    ids, seen_splits, represented_regimes, represented_routes = set(), set(), set(), set()
    for case in cases:
        required_case = {"case_id", "split", "seed", "regime", "dispatch_s", "pickup_id", "hospital_id", "route_family"}
        if not isinstance(case, Mapping) or set(case) != required_case:
            raise ValueError("each case must explicitly name split, demand, dispatch, endpoints and route family")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not SAFE_ID.fullmatch(case_id) or case_id in ids:
            raise ValueError("case ids must be unique safe identifiers")
        ids.add(case_id)
        if case["split"] not in SPLITS or case["regime"] not in REGIMES:
            raise ValueError("case split/regime is invalid")
        _integer(case["seed"], "seed", 0, 2**31 - 1)
        dispatch = finite(case["dispatch_s"], "dispatch_s")
        if not max(1, values["sensor_lag_s"]) <= dispatch < values["demand_end_s"] or abs(dispatch / values["step_s"] - round(dispatch / values["step_s"])) > 1e-9:
            raise ValueError("dispatch must have lagged observations and align before demand end")
        for key in ("pickup_id", "hospital_id", "route_family"):
            if not isinstance(case[key], str) or not case[key]:
                raise ValueError("explicit nonempty route endpoints/family required")
        if (case["regime"] in heldout or case["route_family"] in heldout_routes) and case["split"] != "test":
            raise ValueError("held-out regime/route family occurs outside test")
        seen_splits.add(case["split"])
        if case["split"] == "test":
            represented_regimes.add(case["regime"])
            represented_routes.add(case["route_family"])
    if seen_splits != SPLITS or not set(heldout) <= represented_regimes or not set(heldout_routes) <= represented_routes:
        raise ValueError("all splits and all declared holdouts must be represented")
    budget = spec["budget"]
    if not isinstance(budget, Mapping) or set(budget) != {"max_episodes", "max_rollouts", "max_wall_time_s", "rationale"}:
        raise ValueError("explicit bounded pilot-based budget required")
    maximum = _integer(budget["max_episodes"], "max_episodes", 3, 10000)
    rollouts = _integer(budget["max_rollouts"], "max_rollouts", 21, 70000)
    if len(cases) > maximum or len(cases) * 7 > rollouts or finite(budget["max_wall_time_s"], "max_wall_time_s") <= 0:
        raise ValueError("declared cases exceed the explicit budget")
    if not isinstance(budget["rationale"], str) or not budget["rationale"].strip():
        raise ValueError("budget must explain the measured pilot basis")
    weight = finite(spec["civilian_weight"], "civilian_weight")
    if set(spec["analytical_config"]) != set(asdict(AnalyticalConfig())):
        raise ValueError("all analytical parameters must be explicit")
    if weight != 1 or spec["analytical_config"] != asdict(AnalyticalConfig()):
        raise ValueError("study v1 requires default analytical configuration and objective weight 1, matching the simulator")
    model = spec["model_specification"]
    if not isinstance(model, Mapping) or set(model) != {"max_depth", "min_samples_leaf"}:
        raise ValueError("one explicit shallow-tree specification required")
    _integer(model["max_depth"], "max_depth", 1, 8)
    _integer(model["min_samples_leaf"], "min_samples_leaf", 1, 100000)
    return dict(spec)


def _relative_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("saved input path must be relative POSIX text")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise ValueError("unsafe saved input path")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("saved input escapes study directory")
    return resolved


def input_inventory(root: Path) -> dict[str, str]:
    directory = root / "inputs"
    result = {}
    if directory.is_symlink():
        raise ValueError("study inputs cannot be a symbolic link")
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("study input inventory cannot contain symbolic links or escaping paths")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def assert_saved_inputs(root: Path, study: Mapping) -> None:
    recorded = study["input_files"]
    if not isinstance(recorded, Mapping) or not recorded:
        raise ValueError("study has no saved input inventory")
    for relative, expected in recorded.items():
        path = _relative_file(root, relative)
        if not relative.startswith("inputs/") or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"saved study input missing or changed: {relative}")
    if input_inventory(root) != recorded:
        raise ValueError("study input files were added, removed or changed")


def assert_study_runtime(study: Mapping) -> None:
    from sim.run import dependency_versions, source_snapshot
    current = source_snapshot()
    if current["source_dirty"] is not False or current != study["source"]:
        raise ValueError("study source is not its clean pinned implementation checkpoint; do not pull/edit during collection")
    if dependency_versions() != study["dependencies"]:
        raise ValueError("study dependency versions changed")


def validate_pilot_metadata(plan_envelope: Mapping, execution: Mapping, rows: list, summary: Mapping,
                            spec: Mapping, source: Mapping) -> int:
    """Pure gate; raw files are additionally checked by validate_pilot_evidence."""
    from evaluation.pilot import validate_plan
    plan = validate_plan(plan_envelope)
    if not 12 <= len(plan["cases"]) <= 20 or {case["regime"] for case in plan["cases"]} != REGIMES:
        raise ValueError("budgeting requires 12–20 whole pilot episodes spanning all four declared regimes")
    if execution.get("status") != "completed" or execution.get("source_dirty") is not False:
        raise ValueError("a completed clean-source pilot is required before budgeting a study")
    if execution.get("plan_sha256") != plan_envelope["sha256"] or execution.get("source_code_sha256") != source["source_code_sha256"]:
        raise ValueError("pilot plan/source does not match the current implementation")
    if plan["network"] != spec["network_kind"]:
        raise ValueError("fixture runtime cannot budget a city study or vice versa")
    for key in ("step_s", "sample_s"):
        if plan[key] != spec["timing"][key]:
            raise ValueError("study resolution differs from measured pilot; rerun matching pilot")
    for case in plan["cases"]:
        for key in ("demand_end_s", "horizon_s", "drain_s"):
            if case[key] != spec["timing"][key]:
                raise ValueError("study workload horizon differs from measured pilot")
    expected = len(plan["cases"]) * 7
    if not isinstance(rows, list) or len(rows) != expected or execution.get("expected_worlds") != expected:
        raise ValueError("pilot did not retain its full seven-world case inventory")
    if execution.get("runner_invocations") != expected or execution.get("unattempted_worlds") != 0 or execution.get("audit_failed_worlds") != 0 or execution.get("infrastructure_failed_worlds") != 0:
        raise ValueError("pilot contains unattempted, unaudited or infrastructure-failed worlds")
    if not isinstance(execution.get("sumo_version"), str) or not execution["sumo_version"]:
        raise ValueError("pilot lacks actual SUMO version")
    computed = pilot_summary(rows, civilian_weight=plan["civilian_weight"], useful_action_margin_s=plan["useful_action_margin_s"])
    if computed != summary:
        raise ValueError("pilot summary does not match retained scalar rows")
    assert_disjoint(rows)
    return expected


def validate_pilot_evidence(directory: Path, spec: Mapping, source: Mapping) -> dict:
    """Read only completed pilot artifacts, never train/validation/test results."""
    from evaluation.pilot import validate_plan
    from sim.audit import audit_lifecycle, audit_world_signals
    from sim.network import read_network
    plan_envelope = read_json(directory / "pilot-plan.json")
    plan = validate_plan(plan_envelope)
    execution = read_json(directory / "execution.json")
    rows = read_json(directory / "outcomes.json")
    summary = read_json(directory / "pilot-summary.json")
    network_manifest = read_json(directory / "network/network-manifest.json")
    expected = validate_pilot_metadata(plan_envelope, execution, rows, summary, spec, source)
    evidence_files = {name: file_hash(directory / name) for name in ("pilot-plan.json", "execution.json", "outcomes.json", "pilot-summary.json", "network/network-manifest.json")}
    net_path = directory / "network/network.net.xml"
    semantic_network = hashlib.sha256(ET.canonicalize(from_file=net_path, strip_text=True, with_comments=False).encode()).hexdigest()
    if semantic_network != network_manifest["network_sha256"] or file_hash(net_path) != network_manifest["network_file_sha256"]:
        raise ValueError("pilot network bytes changed")
    evidence_files["network/network.net.xml"] = file_hash(net_path)
    network = read_network(net_path)
    for case in plan["cases"]:
        case_rows = [row for row in rows if row["episode_id"] == case["id"]]
        if sorted((r["policy"], r["lead_s"]) for r in case_rows) != sorted(POLICIES):
            raise ValueError("pilot case lacks exactly ordinary, immediate and all five leads")
        demand_dir = directory / case["id"] / "demand"
        demand = read_json(demand_dir / "demand.json")
        realization = [v for v in demand["vehicles"] if v["id"] != "ambulance"]
        demand_hash, group_hash = file_hash(demand_dir / "demand.rou.xml"), digest(realization)
        for name in ("demand.json", "demand.rou.xml"):
            evidence_files[f"{case['id']}/demand/{name}"] = file_hash(demand_dir / name)
        for row in case_rows:
            if row.get("split") != "pilot" or row.get("audit_status") != "passed" or row.get("priority_deadline_audit") != "passed" or row.get("runner_invoked") is not True:
                raise ValueError("only actually audited pilot executions can justify a study budget")
            if row.get("source_code_sha256") != execution["source_code_sha256"] or row.get("source_commit") != execution["source_commit"]:
                raise ValueError("pilot row source differs from execution snapshot")
            if row.get("sumo_version") != execution["sumo_version"] or row.get("dependencies") != execution["dependencies"]:
                raise ValueError("pilot mixes runtime versions")
            if row["demand_sha256"] != demand_hash or row["demand_group_id"] != group_hash or row["network_sha256"] != semantic_network:
                raise ValueError("pilot demand/network identity mismatch")
            world_name = row["policy"] + (f"-{row['lead_s']}" if row["lead_s"] is not None else "")
            world_dir = directory / case["id"] / world_name
            raw = read_json(world_dir / "outcome.json")
            validate_pilot_world_binding(row, raw, plan)
            signal_path = world_dir / "signal-audit-input.json"
            if file_hash(signal_path) != row.get("signal_audit_input_sha256"):
                raise ValueError("pilot signal evidence byte hash mismatch")
            signal = read_json(signal_path)
            if any(signal.get(key) != raw.get(key) for key in ("policy", "status", "metrics", "decision", "events")):
                raise ValueError("pilot signal evidence differs from raw outcome")
            audit_world_signals(signal, network, case["dispatch_s"], simulation_step_s=plan["step_s"])
            lifecycle = read_json(world_dir / "lifecycle.json")
            audit_lifecycle(demand, lifecycle, world_dir / "tripinfo.xml", row)
            for name in ("lifecycle.json", "tripinfo.xml", "outcome.json", "command.json", "signal-audit-input.json"):
                evidence_files[f"{case['id']}/{world_name}/{name}"] = file_hash(world_dir / name)
    total_s = finite(execution["runtime_total_s"], "pilot full wall time")
    if total_s <= 0:
        raise ValueError("pilot wall time must be positive")
    estimate = finite(total_s / expected * len(spec["cases"]) * 7, "estimated study wall time")
    if estimate > spec["budget"]["max_wall_time_s"]:
        raise ValueError("explicit study wall-time budget is below measured pilot extrapolation; reduce cases or justify a new bounded budget")
    return {"schema": "afterlight.pilot-evidence.v1", "files": evidence_files,
            "plan_sha256": plan_envelope["sha256"], "source_code_sha256": execution["source_code_sha256"],
            "dependencies": execution["dependencies"], "sumo_version": execution["sumo_version"],
            "network_sha256": semantic_network, "demand_group_ids": sorted({row["demand_group_id"] for row in rows}),
            "completed_rollouts": expected, "full_wall_time_s": total_s, "estimated_study_wall_time_s": estimate,
            "learning_action_diversity_observed": summary["multiple_useful_actions_observed"],
            "interpretation": "Measured exploratory pilot basis, not a promised runtime or held-out performance result."}


def validate_pilot_world_binding(row: Mapping, raw: Mapping, plan: Mapping) -> None:
    """Bind aggregate pilot measurements to the saved simulator outcome."""
    for key in ("policy", "lead_s", "status", "sumo_version"):
        if row.get(key) != raw.get(key):
            raise ValueError(f"pilot scalar/raw outcome mismatch: {key}")
    for key, value in raw["metrics"].items():
        row_key = "simulator_runtime_s" if key == "runtime_s" else key
        if row.get(row_key) != value:
            raise ValueError(f"pilot scalar/raw metric mismatch: {key}")
    decision = raw["decision"]
    for key in ("observation", "request_plan"):
        if row.get(key) != decision[key]:
            raise ValueError(f"pilot scalar/raw decision mismatch: {key}")
    estimates = estimate_candidates(decision["observation"], AnalyticalConfig(civilian_weight=plan["civilian_weight"]))
    expected_hash = digest({"version": estimates["version"], "config": estimates["config"]})
    cost = next((score["analytical_cost_s"] for score in estimates["scores"] if score["lead_s"] == row["lead_s"]), None)
    if row.get("analytical_config_sha256") != expected_hash or row.get("analytical_cost_s") != cost:
        raise ValueError("pilot analytical prediction/config differs from recomputed observation-only estimate")


def split_start_budgets(spec: Mapping) -> dict:
    return {split: spec["budget"]["max_wall_time_s"] * sum(c["split"] == split for c in spec["cases"]) / len(spec["cases"])
            for split in sorted(SPLITS)}


def route_membership(episodes: list, heldout_families: list) -> dict:
    membership = {}
    for episode in episodes:
        route = episode["ambulance_route"]
        if not isinstance(route, list) or not route or not all(isinstance(edge, str) and edge for edge in route):
            raise ValueError("prepared ambulance route must be a nonempty edge sequence")
        entry = membership.setdefault(digest(route), {"families": set(), "splits": set()})
        entry["families"].add(episode["route_family"])
        entry["splits"].add(episode["split"])
    for entry in membership.values():
        if entry["families"].intersection(heldout_families) and entry["splits"] != {"test"}:
            raise ValueError("held-out route family shares an actual route with a non-test episode")
    return {key: {name: sorted(values) for name, values in entry.items()} for key, entry in sorted(membership.items())}


def _feature_schema(lag: float) -> list[dict]:
    units = ("vehicles", "vehicles", "fraction", "meters", "junctions", "seconds", "seconds")
    sources = ("lagged route incoming-lane queues", "lagged maximum route incoming-lane queue", "lagged downstream-lane occupancy",
               "fixed ambulance route geometry", "fixed ambulance route controlled-junction count",
               "frozen free-flow plus lagged queue ETA", "maximum lagged controller-stage elapsed time, not necessarily green")
    return [{"name": name, "unit": unit, "source": src, "sensor_lag_s": lag} for name, unit, src in zip(DEFAULT_FEATURES, units, sources)]


def prepare_study(spec: Mapping, pilot_directory: Path, output: Path) -> dict:
    from sim.network import ROOT, build_network, read_network, write_json
    from sim.demand import make_demand, save_demand
    from sim.identity import episode_identity
    from sim.run import dependency_versions, source_snapshot
    from policies.scheduler import Timing
    spec = validate_spec(spec)
    output = output.resolve()
    runtime_path = ROOT / "local-runtime"
    runtime_root = runtime_path.resolve()
    if runtime_path.is_symlink() or not runtime_root.is_relative_to(ROOT.resolve()):
        raise ValueError("local-runtime must be a real directory inside the source checkout")
    if output == runtime_root or not output.is_relative_to(runtime_root):
        raise ValueError("generated study inputs must stay inside the checkout's ignored local-runtime directory")
    source = source_snapshot()
    if source["source_dirty"] is not False or source["source_commit"] == "unavailable":
        raise ValueError("prepare requires clean committed source")
    dependencies = dependency_versions()
    evidence = validate_pilot_evidence(pilot_directory.resolve(), spec, source)
    if evidence["dependencies"] != dependencies:
        raise ValueError("pilot dependencies differ from current study runtime")
    output.mkdir(parents=True, exist_ok=False)
    try:
        network_directory = output / "inputs/network"
        network_manifest = build_network(spec["network_kind"], network_directory)
        if network_manifest["network_sha256"] != evidence["network_sha256"]:
            raise ValueError("prepared network differs from measured pilot")
        graph = read_json(network_directory / "graph.json")
        network = read_network(network_directory / "network.net.xml")
        episodes = []
        timing = spec["timing"]
        assignments = {}
        for case in spec["cases"]:
            demand = make_demand(graph, network, seed=case["seed"], regime=case["regime"], dispatch_s=case["dispatch_s"],
                                 demand_end_s=timing["demand_end_s"], pickup_id=case["pickup_id"], hospital_id=case["hospital_id"])
            relative = f"inputs/demand/{case['case_id']}"
            hashes = save_demand(demand, output / relative)
            group = hashes["demand_group_id"]
            if group in evidence["demand_group_ids"]:
                raise ValueError("study reuses a pilot demand realization; never relabel exploratory pilot data")
            if group in assignments and assignments[group] != case["split"]:
                raise ValueError("dispatch/route variants of one civilian realization cross study splits")
            assignments[group] = case["split"]
            eid = episode_identity(network_kind=spec["network_kind"], regime=case["regime"], seed=case["seed"],
                network_sha256=network_manifest["network_sha256"], demand_sha256=hashes["demand_sha256"],
                dispatch_s=case["dispatch_s"], horizon_s=timing["horizon_s"], drain_s=timing["drain_s"], step_s=timing["step_s"])
            episodes.append({**case, **hashes, "episode_id": eid, "network_sha256": network_manifest["network_sha256"],
                             "demand_directory": relative, "ambulance_route": next(v["route"] for v in demand["vehicles"] if v["id"] == "ambulance")})
        protocol = {"schema": "afterlight.protocol.v1", "source_commit": source["source_commit"],
            "source_code_sha256": source["source_code_sha256"], "group_assignments": assignments,
            "episode_inventory": [{k: row[k] for k in ("episode_id", "demand_group_id", "split", "regime", "demand_sha256", "network_sha256", "dispatch_s", "route_family", "pickup_id", "hospital_id")} for row in episodes],
            "feature_schema": _feature_schema(timing["sensor_lag_s"]), "candidate_leads_s": [0, 5, 10, 20, 30],
            "civilian_weight": spec["civilian_weight"], "horizon_s": timing["horizon_s"],
            "drain_end_s": timing["horizon_s"] + timing["drain_s"], "recovery_window_s": timing["recovery_window_s"],
            "tie_break": "smallest_lead", "invalid_rules": ["collision", "teleport", "inventory_or_tripinfo_mismatch", "evidence_audit_failed"],
            "heldout_regimes": spec["heldout_regimes"], "heldout_route_families": spec["heldout_route_families"],
            "model_specification": spec["model_specification"],
            "analytical_estimator": {"version": ESTIMATOR_VERSION, "config": spec["analytical_config"]},
            "controller_timing": asdict(Timing()), "simulation_step_s": timing["step_s"],
            "queue_scope": "all inserted active civilians with speed below 0.1 m/s; insertion backlog separately reported"}
        validate_episode_inventory(protocol, require_regimes=True)
        study = {"schema": "afterlight.study.v1", "study_id": spec["study_id"], "source": source,
            "dependencies": dependencies, "spec": spec, "budget": {**spec["budget"], "episodes": len(episodes),
            "expected_rollouts": len(episodes) * 7, "split_start_budgets_s": split_start_budgets(spec), "estimated_wall_time_s": evidence["estimated_study_wall_time_s"]},
            "pilot_evidence": evidence, "network": {"directory": "inputs/network", "manifest": network_manifest},
            "episodes": episodes, "protocol": protocol, "input_files": input_inventory(output),
            "route_membership": route_membership(episodes, spec["heldout_route_families"])}
        assert_study_runtime(study)
        validate_study_links(output, study, verify_inputs=True)
        envelope = {"sha256": digest(study), "study": study}
        write_json(output / "study.json", envelope)
        return envelope
    except Exception as error:
        write_json(output / "preparation-failure.json", {"status": "preparation_failed", "reason": str(error), "source": source})
        raise


def validate_study_links(root: Path, study: Mapping, *, verify_inputs: bool) -> None:
    """Bind collector paths and episode identities to the same frozen input set."""
    from policies.scheduler import Timing
    from sim.identity import episode_identity
    spec, protocol = study["spec"], study["protocol"]
    timing = spec["timing"]
    expected_contract = {
        "source_commit": study["source"]["source_commit"], "source_code_sha256": study["source"]["source_code_sha256"],
        "horizon_s": timing["horizon_s"], "drain_end_s": timing["horizon_s"] + timing["drain_s"],
        "recovery_window_s": timing["recovery_window_s"], "simulation_step_s": timing["step_s"],
        "feature_schema": _feature_schema(timing["sensor_lag_s"]), "controller_timing": asdict(Timing()),
        "heldout_regimes": spec["heldout_regimes"], "heldout_route_families": spec["heldout_route_families"],
        "candidate_leads_s": [0, 5, 10, 20, 30], "tie_break": "smallest_lead"}
    for key, value in expected_contract.items():
        if protocol.get(key) != value:
            raise ValueError(f"protocol differs from execution spec: {key}")
    cases = {case["case_id"]: case for case in spec["cases"]}
    episodes = study["episodes"]
    if not isinstance(episodes, list) or len(episodes) != len(cases):
        raise ValueError("prepared episode count differs from declared cases")
    by_id, by_case = {}, {}
    inventory = validate_episode_inventory(protocol, require_regimes=True)
    if study["network"]["directory"] != "inputs/network":
        raise ValueError("prepared network must use the declared safe input directory")
    network_manifest = study["network"]["manifest"]
    required_network = {"inputs/network/network.net.xml", "inputs/network/graph.json", "inputs/network/network-manifest.json"}
    if not required_network <= study["input_files"].keys():
        raise ValueError("required network files missing from exact input inventory")
    if study["input_files"]["inputs/network/network.net.xml"] != network_manifest["network_file_sha256"]:
        raise ValueError("network byte hash differs from prepared metadata")
    assignments = {}
    for episode in episodes:
        eid, case_id = episode["episode_id"], episode["case_id"]
        if eid in by_id or case_id in by_case or case_id not in cases or eid not in inventory:
            raise ValueError("duplicate, missing or unknown prepared episode/case identity")
        expected_id = episode_identity(network_kind=spec["network_kind"], regime=episode["regime"], seed=episode["seed"],
            network_sha256=episode["network_sha256"], demand_sha256=episode["demand_sha256"], dispatch_s=episode["dispatch_s"],
            horizon_s=timing["horizon_s"], drain_s=timing["drain_s"], step_s=timing["step_s"])
        if eid != expected_id:
            raise ValueError("episode identity does not match saved inputs and timing")
        by_id[eid], by_case[case_id] = episode, episode
        if any(episode.get(key) != value for key, value in cases[case_id].items()):
            raise ValueError("prepared episode differs from explicit case spec")
        if any(episode.get(key) != value for key, value in inventory[eid].items()):
            raise ValueError("prepared episode differs from frozen protocol inventory")
        relative = f"inputs/demand/{case_id}"
        if episode["demand_directory"] != relative:
            raise ValueError("demand directory must be the safe declared case input directory")
        _relative_file(root, relative + "/demand.json")
        for name, hash_key in (("demand.json", "demand_manifest_sha256"), ("demand.rou.xml", "demand_sha256")):
            if study["input_files"].get(f"{relative}/{name}") != episode[hash_key]:
                raise ValueError("episode input hashes differ from saved file inventory")
        if episode["network_sha256"] != network_manifest["network_sha256"]:
            raise ValueError("episode network differs from prepared network")
        group = episode["demand_group_id"]
        if group in study["pilot_evidence"]["demand_group_ids"]:
            raise ValueError("pilot demand groups cannot become study episodes")
        if group in assignments and assignments[group] != episode["split"]:
            raise ValueError("one demand realization crosses study splits")
        assignments[group] = episode["split"]
        if verify_inputs:
            demand = read_json(_relative_file(root, relative + "/demand.json"))
            for key in ("seed", "regime", "dispatch_s", "pickup_id", "hospital_id"):
                if demand.get(key) != episode[key]:
                    raise ValueError(f"saved demand differs from episode {key}")
            if demand.get("demand_end_s") != spec["timing"]["demand_end_s"]:
                raise ValueError("saved demand horizon differs from spec")
            civilians = [v for v in demand["vehicles"] if v["id"] != "ambulance"]
            ambulances = [v for v in demand["vehicles"] if v["id"] == "ambulance"]
            if digest(civilians) != group or len(ambulances) != 1 or ambulances[0]["route"] != episode["ambulance_route"]:
                raise ValueError("saved demand realization/ambulance route differs from episode")
    if set(by_id) != set(inventory) or set(by_case) != set(cases) or assignments != protocol["group_assignments"]:
        raise ValueError("prepared cases, protocol inventory and group assignments disagree")
    if study.get("route_membership") != route_membership(episodes, spec["heldout_route_families"]):
        raise ValueError("route-family membership audit differs from saved routes")
    if any(study["budget"].get(key) != value for key, value in spec["budget"].items()) or study["budget"].get("split_start_budgets_s") != split_start_budgets(spec):
        raise ValueError("prepared split-start budget differs from explicit whole-study allowance")
    estimate = finite(study["budget"]["estimated_wall_time_s"], "estimated study wall time")
    if estimate <= 0 or estimate > spec["budget"]["max_wall_time_s"] or estimate != study["pilot_evidence"]["estimated_study_wall_time_s"]:
        raise ValueError("prepared runtime estimate differs from measured pilot basis or bounded budget")
    if study["budget"]["episodes"] != len(episodes) or study["budget"]["expected_rollouts"] != len(episodes) * 7:
        raise ValueError("prepared budget inventory is inconsistent")
    if protocol["civilian_weight"] != spec["civilian_weight"] or protocol["model_specification"] != spec["model_specification"]:
        raise ValueError("protocol objective/model differs from declared spec")
    if protocol["analytical_estimator"] != {"version": ESTIMATOR_VERSION, "config": spec["analytical_config"]}:
        raise ValueError("protocol analytical estimator differs from declared spec")
    if verify_inputs:
        if read_json(root / "inputs/network/network-manifest.json") != network_manifest:
            raise ValueError("saved network metadata differs from study")
        net = root / "inputs/network/network.net.xml"
        semantic = hashlib.sha256(ET.canonicalize(from_file=net, strip_text=True, with_comments=False).encode()).hexdigest()
        if semantic != network_manifest["network_sha256"]:
            raise ValueError("saved network semantic hash differs from study")


def load_study(directory: Path, *, require_frozen: bool = False, verify_inputs: bool = True) -> dict:
    envelope = read_json(directory / "study.json")
    study = envelope["study"]
    if envelope["sha256"] != digest(study) or study.get("schema") != "afterlight.study.v1":
        raise ValueError("study manifest hash/schema mismatch")
    validate_spec(study["spec"])
    validate_episode_inventory(study["protocol"], require_regimes=True)
    if study["protocol"]["source_commit"] != study["source"]["source_commit"]:
        raise ValueError("study protocol/source identity mismatch")
    if verify_inputs:
        assert_saved_inputs(directory, study)
    validate_study_links(directory, study, verify_inputs=verify_inputs)
    if require_frozen:
        frozen = read_json(directory / "frozen-protocol.json")
        if frozen.get("sha256") != digest(study["protocol"]) or frozen.get("protocol") != study["protocol"]:
            raise ValueError("frozen protocol differs from prepared study")
    return envelope


def freeze_study(directory: Path) -> dict:
    envelope = load_study(directory)
    study = envelope["study"]
    assert_study_runtime(study)
    return freeze_protocol(study["protocol"], directory / "frozen-protocol.json")
