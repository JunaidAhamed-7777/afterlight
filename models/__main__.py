"""Explicit optional residual training. Requires a frozen protocol and real labels.

Run only on Omen after pilot/validation design gates. No test set is opened here.
"""
import argparse
import json
from pathlib import Path
from .residual import fit_residual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-outcomes", type=Path, required=True)
    parser.add_argument("--frozen-protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve prior trained artifacts")
    envelope = json.loads(args.frozen_protocol.read_text(encoding="utf-8"))
    rows = json.loads(args.train_outcomes.read_text(encoding="utf-8"))
    protocol = envelope["protocol"]
    specification = protocol["model_specification"]
    result = fit_residual(rows, feature_names=[f["name"] for f in protocol["feature_schema"]],
                          civilian_weight=protocol["civilian_weight"], frozen_protocol=envelope,
                          max_depth=specification["max_depth"], min_samples_leaf=specification["min_samples_leaf"])
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    model = result["model"]
    print(json.dumps({"model_sha256": result["sha256"], "protocol_sha256": model["protocol_sha256"],
                      "training_rows": model["training_rows"], "finite_training_labels": model["finite_training_labels"],
                      "excluded_infeasible_labels": model["excluded_infeasible_labels"],
                      "status": "fitted; held-out decision benefit NOT established"}, indent=2))


if __name__ == "__main__":
    main()
