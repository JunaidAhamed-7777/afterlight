"""Prepare/execute an explicitly exploratory seven-world runtime pilot on Omen.

No train/validation/test dataset is created. Preparation never invokes SUMO.
Execution requires --execute and refuses to overwrite an existing run directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import hashlib
import re
from pathlib import Path
import platform
import time
from .protocol import digest, pilot_summary
from .metrics import Accounting, finite, excess_queue_area, verify_pair


def prepare_plan(*, network: str = "fixture", seed_start: int = 1001, seeds_per_regime: int = 3) -> dict:
    if network not in {"fixture", "city"} or not isinstance(seeds_per_regime, int) or not 1 <= seeds_per_regime <= 20:
        raise ValueError("pilot network and seeds_per_regime invalid")
    regimes = ("sparse", "moderate", "asymmetric", "heavy")
    cases = [{"id": f"{regime}-{seed_start + j * seeds_per_regime + i}", "regime": regime,
              "seed": seed_start + j * seeds_per_regime + i, "dispatch_s": 60.0,
              "demand_end_s": 180.0, "horizon_s": 240.0, "drain_s": 360.0,
              "recovery_start_s": 60.0, "recovery_end_s": 600.0}
             for j, regime in enumerate(regimes) for i in range(seeds_per_regime)]
    plan = {"schema": "afterlight.pilot-plan.v1", "network": network, "split": "pilot", "cases": cases,
            "policies": [{"policy": "ordinary", "lead_s": None}, {"policy": "immediate", "lead_s": None},
                         *({"policy": "fixed", "lead_s": lead} for lead in (0, 5, 10, 20, 30))],
            "step_s": .5, "sample_s": 5.0, "civilian_weight": 1.0, "useful_action_margin_s": 1.0,
            "queue_scope": "all inserted active civilians with speed below 0.1 m/s; insertion backlog reported separately",
            "purpose": "Runtime, accounting, validity and actual candidate-diversity pilot; no held-out performance claim.",
            "candidate_budget_unfrozen": True,
            "infrastructure_retry_policy": "no automatic retry; retain failure and stop; rerun same plan into a new directory after diagnosis"}
    return {"sha256": digest(plan), "plan": plan}


def validate_plan(envelope: dict) -> dict:
    plan = envelope["plan"]
    if envelope["sha256"] != digest(plan) or plan["schema"] != "afterlight.pilot-plan.v1" or plan["split"] != "pilot":
        raise ValueError("invalid pilot plan or hash")
    if plan["network"] not in {"fixture", "city"}:
        raise ValueError("unsupported pilot network")
    expected = [{"policy": "ordinary", "lead_s": None}, {"policy": "immediate", "lead_s": None},
                *({"policy": "fixed", "lead_s": lead} for lead in (0, 5, 10, 20, 30))]
    if plan["policies"] != expected:
        raise ValueError("pilot must retain ordinary, immediate and all five leads")
    if finite(plan["step_s"], "step_s") <= 0 or finite(plan["sample_s"], "sample_s") < plan["step_s"]:
        raise ValueError("invalid pilot time resolution")
    finite(plan["civilian_weight"], "civilian_weight")
    finite(plan["useful_action_margin_s"], "useful_action_margin_s")
    ids = set()
    if not plan["cases"] or len(plan["cases"]) > 80:
        raise ValueError("pilot must have 1–80 explicitly listed cases")
    for case in plan["cases"]:
        if not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]) or case["id"] in ids:
            raise ValueError("case ids must be unique safe directory names")
        ids.add(case["id"])
        if case["regime"] not in {"sparse", "moderate", "asymmetric", "heavy"} or isinstance(case["seed"], bool) or not isinstance(case["seed"], int) or case["seed"] < 0:
            raise ValueError("invalid pilot regime/seed")
        dispatch = finite(case["dispatch_s"], "dispatch_s")
        demand_end = finite(case["demand_end_s"], "demand_end_s")
        horizon = finite(case["horizon_s"], "horizon_s")
        drain = finite(case["drain_s"], "drain_s")
        if not 1 <= dispatch < demand_end <= horizon or drain <= 0:
            raise ValueError("pilot timing contract invalid")
        if not 0 <= finite(case["recovery_start_s"], "recovery_start_s") < finite(case["recovery_end_s"], "recovery_end_s") <= horizon + drain:
            raise ValueError("pilot common recovery window invalid")
    return plan


class PilotAuditError(RuntimeError):
    """Measured artifact failed required scientific-validity audit."""


def audit_pilot_world(world: dict, network: dict, demand: dict, directory: Path, *, simulation_step_s: float) -> None:
    """Audit dense evidence before discarding frames or assigning a finite target."""
    from sim.audit import audit_world_signals, audit_lifecycle
    try:
        audit_world_signals(world,network,demand['dispatch_s'],simulation_step_s=simulation_step_s)
        if world['frames'][-1]['t']!=world['metrics']['drain_end_s']:
            raise ValueError('Per-world frames do not cover the common drain endpoint')
        if world['status']!=world['metrics']['status']:
            raise ValueError('World status contradicts metric status')
        lifecycle=json.loads((directory/'lifecycle.json').read_text(encoding='utf-8'))
        audit_lifecycle(demand,lifecycle,directory/'tripinfo.xml',world['metrics'])
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise PilotAuditError(f'Per-world evidence audit failed: {exc}') from exc


def execute_plan(envelope: dict, output: Path) -> dict:
    """The caller is responsible for running only on the authorized Omen machine."""
    plan = validate_plan(envelope)
    # Deliberately lazy imports: plan/contract unit tests do not need SUMO.
    from sim.network import build_network, read_network, write_json
    from sim.demand import make_demand, save_demand
    from sim.run import dependency_versions, run_world, source_snapshot
    from models.analytical import AnalyticalConfig, estimate_candidates

    source = source_snapshot()
    if source["source_dirty"] is not False or source["source_commit"] == "unavailable":
        raise ValueError("pilot requires clean committed source before execution")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "pilot-plan.json", envelope)
    started = time.perf_counter()
    manifest = {**source, "plan_sha256": envelope["sha256"],
                "started_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                "python_version": platform.python_version(), "processor": platform.processor(),
                "expected_worlds": len(plan["cases"]) * len(plan["policies"]),
                "split": "pilot", "status": "running"}
    write_json(output / "execution.json", manifest)
    rows = []
    write_json(output / "outcomes.json", rows)
    try:
        manifest["dependencies"] = dependency_versions()
        netdir = output / "network"
        netmanifest = build_network(plan["network"], netdir)
        graph = json.loads((netdir / "graph.json").read_text(encoding="utf-8"))
        network = read_network(netdir / "network.net.xml")
        for case in plan["cases"]:
            case_dir = output / case["id"]
            demand = make_demand(graph, network, seed=case["seed"], regime=case["regime"],
                                 dispatch_s=case["dispatch_s"], demand_end_s=case["demand_end_s"])
            hashes = save_demand(demand, case_dir / "demand")
            scheduled = sum(v["id"] != "ambulance" for v in demand["vehicles"])
            case_rows = []
            for policy in plan["policies"]:
                name = policy["policy"] + (f"-{policy['lead_s']}" if policy["lead_s"] is not None else "")
                world_dir = case_dir / name
                identity = {"episode_id": case["id"], "demand_group_id": hashes["demand_group_id"],
                            "demand_sha256": hashes["demand_sha256"], "network_sha256": netmanifest["network_sha256"],
                            "source_commit": manifest["source_commit"], "source_code_sha256": source["source_code_sha256"], "split": "pilot", "regime": case["regime"],
                            "seed": case["seed"], "policy": policy["policy"], "lead_s": policy["lead_s"]}
                call_start = time.perf_counter()
                world = None
                signal_hash = None
                dependencies_before = None
                dependencies_after = None
                runner_invoked = False
                try:
                    dependencies_before = dependency_versions()
                    if source_snapshot() != source:
                        raise RuntimeError("Source changed before pilot world; remaining simulations must not start")
                    if dependencies_before != manifest["dependencies"]:
                        raise RuntimeError("Dependencies changed before pilot world; mixed-runtime outcomes refused")
                    runner_invoked = True
                    world = run_world(world_id=name, policy=policy["policy"], lead_s=policy["lead_s"] or 0,
                                      network_dir=netdir, demand_dir=case_dir / "demand", demand=demand, network=network,
                                      output=world_dir, horizon_s=case["horizon_s"], drain_s=case["drain_s"],
                                      step_s=plan["step_s"], sample_s=plan["sample_s"])
                    dependencies_after = dependency_versions()
                    if source_snapshot() != source:
                        raise RuntimeError("Source changed while simulator was running; outcome not eligible as locked-source evidence")
                    if dependencies_after != manifest["dependencies"]:
                        raise RuntimeError("Dependencies changed during pilot world; outcome is not locked-runtime evidence")
                    actual_sumo = world.get("sumo_version")
                    if not isinstance(actual_sumo,str) or not actual_sumo:
                        raise RuntimeError("Pilot world omitted actual SUMO version")
                    if "sumo_version" not in manifest:
                        manifest["sumo_version"] = actual_sumo
                    elif actual_sumo != manifest["sumo_version"]:
                        raise RuntimeError("SUMO version changed between pilot worlds; mixed-simulator outcomes refused")
                    signal_evidence = {key: world[key] for key in ('policy','status','decision','metrics','events')}
                    signal_evidence['frames'] = [{'t':frame['t'],'signals':frame['signals']} for frame in world['frames']]
                    signal_path = world_dir/'signal-audit-input.json'
                    write_json(signal_path,signal_evidence)
                    signal_hash = hashlib.sha256(signal_path.read_bytes()).hexdigest()
                    audit_pilot_world(world,network,demand,world_dir,simulation_step_s=plan["step_s"])
                    decision = world["decision"]
                    estimates = estimate_candidates(decision["observation"], AnalyticalConfig(civilian_weight=plan["civilian_weight"]))
                    row = {**identity, **world["metrics"],
                           "simulator_runtime_s":world["metrics"]["runtime_s"],
                           "runtime_s":time.perf_counter()-call_start,
                           "runtime_scope":"world execution, raw output and evidence audit; aggregate checkpoint I/O included in execution.runtime_total_s",
                           "signal_audit_input_sha256":signal_hash, "audit_status":"passed", "priority_deadline_audit":"passed", "dependencies":dependencies_after, "runner_invoked":True, "sumo_version": world["sumo_version"], "request_plan": decision["request_plan"],
                           "observation": decision["observation"],
                           "analytical_config_sha256": digest({"version": estimates["version"], "config": estimates["config"]}),
                           "analytical_cost_s": next((s["analytical_cost_s"] for s in estimates["scores"] if s["lead_s"] == policy["lead_s"]), None)}
                    # Release dense in-memory trajectories between worlds. Raw
                    # scalar/lifecycle/SUMO files remain in each world directory.
                except Exception as error:
                    if runner_invoked and dependencies_after is None:
                        try:
                            dependencies_after=dependency_versions()
                        except Exception:
                            # The original failure remains primary; absent
                            # post-runtime metadata is explicit, never guessed.
                            dependencies_after=None
                    failure_path = world_dir / "failure.json"
                    try:
                        failure = json.loads(failure_path.read_text(encoding="utf-8")) if failure_path.exists() else {}
                    except (OSError,ValueError):
                        failure = {}
                    observed_metrics = world.get("metrics",{}) if world is not None else {}
                    audit_failed = isinstance(error,PilotAuditError)
                    row = {**identity, "status": "invalid" if audit_failed else "infrastructure_error",
                           "validity_reasons": list(dict.fromkeys([*observed_metrics.get("validity_reasons",[]),
                                                 *(["evidence_audit_failed"] if audit_failed else [])])),
                           "signal_audit_input_sha256":signal_hash,
                           "audit_status":"failed" if audit_failed else "not_eligible",
                           "accounting_unverified":True,
                           "infrastructure_reason": None if audit_failed else str(error),
                           "audit_reason":str(error) if audit_failed else None,
                           "ambulance_journey_s":None,"civilian_mean_excess_s":None,
                           "accounting": observed_metrics.get("accounting",failure.get("accounting", {"scheduled": scheduled, "inserted": 0,
                               "completed": 0, "running": 0, "not_inserted": scheduled})),
                           "horizon_s": case["horizon_s"], "drain_end_s": case["horizon_s"] + case["drain_s"],
                           "runtime_s": time.perf_counter() - call_start,"request_plan":None,
                           "runner_invoked":runner_invoked,"dependencies_before":dependencies_before,
                           "dependencies_after":dependencies_after,
                           "sumo_version":world.get("sumo_version") if world is not None else None,
                           "raw_world_directory":str(world_dir.relative_to(output))}
                # Frames are released only after the audit or retained-failure
                # decision. Raw SUMO/lifecycle/outcome files are never deleted.
                world = None
                if row["audit_status"]=="passed":
                    Accounting.from_mapping(row["accounting"])
                rows.append(row)
                case_rows.append(row)
                write_json(output / "outcomes.json", rows)
                if row["audit_status"] == "failed":
                    raise PilotAuditError(f"Pilot stopped after invalid evidence in {case['id']}/{name}; raw outcome retained, remaining worlds unattempted")
                if row["status"] == "infrastructure_error":
                    raise RuntimeError(f"Pilot stopped after infrastructure failure in {case['id']}/{name}; record retained, remaining worlds unattempted")
            ordinary = next(row for row in case_rows if row["policy"] == "ordinary")
            for row in case_rows:
                verify_pair(row, ordinary)
                row["recovery_excess_queue_area_vehicle_s"] = excess_queue_area(
                    row["queue_samples"], ordinary["queue_samples"], case["recovery_start_s"], case["recovery_end_s"])
                row["recovery_window_s"] = [case["recovery_start_s"], case["recovery_end_s"]]
                row["queue_scope"] = plan["queue_scope"]
            write_json(output / "outcomes.json", rows)
        manifest["status"] = "completed_with_infrastructure_failures" if any(r["status"] == "infrastructure_error" for r in rows) else "completed"
        # Schedules unavailable on infrastructure failures must not be counted
        # as a distinct null schedule.
        report = pilot_summary(rows, civilian_weight=plan["civilian_weight"], useful_action_margin_s=plan["useful_action_margin_s"])
        write_json(output / "pilot-summary.json", report)
        return report
    except Exception as error:
        manifest.update(status="invalid_evidence" if isinstance(error,PilotAuditError) else "infrastructure_error", reason=str(error))
        raise
    finally:
        manifest["recorded_worlds"] = len(rows)
        manifest["runner_invocations"] = sum(bool(row.get("runner_invoked")) for row in rows)
        manifest["preflight_rejected_worlds"] = sum(not row.get("runner_invoked",False) for row in rows)
        manifest["unattempted_worlds"] = manifest["expected_worlds"] - manifest["runner_invocations"]
        manifest["unrecorded_worlds"] = manifest["expected_worlds"] - len(rows)
        manifest["audit_failed_worlds"] = sum(row.get("audit_status")=="failed" for row in rows)
        manifest["infrastructure_failed_worlds"] = sum(row["status"]=="infrastructure_error" for row in rows)
        manifest["runtime_total_s"] = time.perf_counter() - started
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "execution.json", manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--network", choices=("fixture", "city"), default="fixture")
    parser.add_argument("--seeds-per-regime", type=int, default=3)
    parser.add_argument("--seed-start", type=int, default=1001)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.execute:
        if args.output is None:
            parser.error("--execute requires --output")
        result = execute_plan(json.loads(args.plan.read_text(encoding="utf-8")), args.output)
    else:
        result = prepare_plan(network=args.network, seed_start=args.seed_start, seeds_per_regime=args.seeds_per_regime)
        with args.plan.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
