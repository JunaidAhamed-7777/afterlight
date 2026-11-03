"""Explicit saved-input study workflow. Omen only; no implicit collection or fitting."""
import argparse
import json
from pathlib import Path
from .study_manifest import freeze_study, prepare_study, read_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="verify measured pilot and save bounded study inputs; no traffic rollout")
    prepare.add_argument("--spec", type=Path, required=True)
    prepare.add_argument("--pilot-dir", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    freeze = commands.add_parser("freeze", help="freeze verified saved inputs/protocol at the clean pinned source commit")
    freeze.add_argument("--study", type=Path, required=True)
    select = commands.add_parser("select", help="verify train/validation collections and freeze selectors; never opens test outcomes")
    select.add_argument("--study", type=Path, required=True)
    select.add_argument("--train", type=Path, required=True)
    select.add_argument("--validation", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--fit-model", action="store_true", help="explicitly fit the one frozen tree specification if eligible")
    report = commands.add_parser("report", help="verify the released test attempt and write a descriptive report; no fitting or simulation")
    report.add_argument("--study", type=Path, required=True)
    report.add_argument("--collection", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_study(read_json(args.spec), args.pilot_dir, args.output)
        study = result["study"]
        summary = {"study_sha256": result["sha256"], "episodes": study["budget"]["episodes"],
                   "expected_rollouts": study["budget"]["expected_rollouts"], "status": "inputs prepared; no traffic outcomes generated; protocol not yet frozen"}
    elif args.command == "report":
        from .study_reporting import report_study
        result = report_study(args.study, args.collection, args.output)
        summary = {"report_sha256": result["sha256"], "status": result["report"]["status"],
                   "mode": result["report"]["mode"], "automatic_benefit_claim": False}
    elif args.command == "select":
        from .study_reporting import select_study
        result = select_study(args.study, args.train, args.validation, args.output, fit_model=args.fit_model)
        summary = {"selection_sha256": result["sha256"], "status": result["selection"]["status"],
                   "reason": result["selection"]["reason"], "test_release_authorized": False}
    else:
        result = freeze_study(args.study)
        summary = {"protocol_sha256": result["sha256"], "status": "protocol frozen; test outcomes remain unreleased"}
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
