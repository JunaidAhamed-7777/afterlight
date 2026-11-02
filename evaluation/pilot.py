"""Prepare/execute an explicitly exploratory seven-world runtime pilot on Omen.

No train/validation/test dataset is created. Preparation never invokes SUMO.
Execution requires --execute and refuses to overwrite an existing run directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import re
import importlib.metadata
from pathlib import Path
import platform
import time
from .protocol import digest, pilot_summary
from .metrics import Accounting, finite


def prepare_plan(*, network: str = "fixture", seed_start: int = 1001, seeds_per_regime: int = 3) -> dict:
    if network not in {"fixture", "city"} or not isinstance(seeds_per_regime, int) or not 1 <= seeds_per_regime <= 20:
        raise ValueError("pilot network and seeds_per_regime invalid")
    regimes = ("sparse", "moderate", "asymmetric", "heavy")
    cases = [{"id": f"{regime}-{seed_start + j * seeds_per_regime + i}", "regime": regime,
              "seed": seed_start + j * seeds_per_regime + i, "dispatch_s": 60.0,
              "demand_end_s": 180.0, "horizon_s": 240.0, "drain_s": 360.0}
             for j, regime in enumerate(regimes) for i in range(seeds_per_regime)]
    plan = {"schema": "afterlight.pilot-plan.v1", "network": network, "split": "pilot", "cases": cases,
            "policies": [{"policy": "ordinary", "lead_s": None}, {"policy": "immediate", "lead_s": None},
                         *({"policy": "fixed", "lead_s": lead} for lead in (0, 5, 10, 20, 30))],
            "step_s": .5, "sample_s": 5.0,
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
    return plan


def execute_plan(envelope: dict, output: Path) -> dict:
    """The caller is responsible for running only on the authorized Omen machine."""
    plan = validate_plan(envelope)
    # Deliberately lazy imports: plan/contract unit tests do not need SUMO.
    from sim.network import build_network, read_network, write_json
    from sim.demand import make_demand, save_demand
    from sim.run import run_world, source_commit
    from models.analytical import estimate_candidates

    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "pilot-plan.json", envelope)
    started = time.perf_counter()
    manifest = {"source_commit": source_commit(), "plan_sha256": envelope["sha256"],
                "started_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                "python_version": platform.python_version(), "processor": platform.processor(),
                "expected_worlds": len(plan["cases"]) * len(plan["policies"]),
                "split": "pilot", "status": "running"}
    write_json(output / "execution.json", manifest)
    rows = []
    write_json(output / "outcomes.json", rows)
    try:
        manifest["dependencies"] = {name: importlib.metadata.version(name) for name in ("eclipse-sumo", "traci", "sumolib")}
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
            for policy in plan["policies"]:
                name = policy["policy"] + (f"-{policy['lead_s']}" if policy["lead_s"] is not None else "")
                world_dir = case_dir / name
                identity = {"episode_id": case["id"], "demand_group_id": hashes["demand_group_id"],
                            "demand_sha256": hashes["demand_sha256"], "network_sha256": netmanifest["network_sha256"],
                            "source_commit": manifest["source_commit"], "split": "pilot", "regime": case["regime"],
                            "seed": case["seed"], "policy": policy["policy"], "lead_s": policy["lead_s"]}
                call_start = time.perf_counter()
                try:
                    world = run_world(world_id=name, policy=policy["policy"], lead_s=policy["lead_s"] or 0,
                                      network_dir=netdir, demand_dir=case_dir / "demand", demand=demand, network=network,
                                      output=world_dir, horizon_s=case["horizon_s"], drain_s=case["drain_s"],
                                      step_s=plan["step_s"], sample_s=plan["sample_s"])
                    decision = world["decision"]
                    estimates = estimate_candidates(decision["observation"])
                    row = {**identity, **world["metrics"], "request_plan": decision["request_plan"],
                           "observation": decision["observation"],
                           "analytical_config_sha256": digest({"version": estimates["version"], "config": estimates["config"]}),
                           "analytical_cost_s": next((s["analytical_cost_s"] for s in estimates["scores"] if s["lead_s"] == policy["lead_s"]), None)}
                    # Release dense in-memory trajectories between worlds. Raw
                    # scalar/lifecycle/SUMO files remain in each world directory.
                    del world
                except Exception as error:
                    failure_path = world_dir / "failure.json"
                    failure = json.loads(failure_path.read_text(encoding="utf-8")) if failure_path.exists() else {}
                    row = {**identity, "status": "infrastructure_error", "validity_reasons": [],
                           "infrastructure_reason": str(error), "ambulance_journey_s": None, "civilian_mean_excess_s": None,
                           "accounting": failure.get("accounting", {"scheduled": scheduled, "inserted": 0,
                               "completed": 0, "running": 0, "not_inserted": scheduled}),
                           "horizon_s": case["horizon_s"], "drain_end_s": case["horizon_s"] + case["drain_s"],
                           "runtime_s": time.perf_counter() - call_start, "request_plan": None}
                Accounting.from_mapping(row["accounting"])
                rows.append(row)
                write_json(output / "outcomes.json", rows)
                if row["status"] == "infrastructure_error":
                    raise RuntimeError(f"Pilot stopped after infrastructure failure in {case['id']}/{name}; record retained, remaining worlds unattempted")
        manifest["status"] = "completed_with_infrastructure_failures" if any(r["status"] == "infrastructure_error" for r in rows) else "completed"
        # Schedules unavailable on infrastructure failures must not be counted
        # as a distinct null schedule.
        report = pilot_summary(rows)
        write_json(output / "pilot-summary.json", report)
        return report
    except Exception as error:
        manifest.update(status="infrastructure_error", reason=str(error))
        raise
    finally:
        manifest["recorded_worlds"] = len(rows)
        manifest["unattempted_worlds"] = manifest["expected_worlds"] - len(rows)
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
