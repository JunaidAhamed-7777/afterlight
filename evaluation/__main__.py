"""Offline evidence checks. Does not launch SUMO or unlock a test set."""
import argparse
import json
from pathlib import Path
from .metrics import objective
from .protocol import freeze_protocol, pilot_summary
from .splits import assert_disjoint


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "pilot", "freeze"):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
        if name == "audit":
            command.add_argument("--civilian-weight", type=float, required=True)
        if name == "freeze":
            command.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if args.command == "freeze":
        result = freeze_protocol(data, args.output)
    elif args.command == "pilot":
        result = pilot_summary(data)
    else:
        groups = assert_disjoint(data)
        values = [objective(row, args.civilian_weight) for row in data]
        result = {"rows": len(data), "groups": groups, "finite_objectives": sum(v is not None for v in values),
                  "infeasible_or_unavailable": sum(v is None for v in values), "objectives": values}
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
