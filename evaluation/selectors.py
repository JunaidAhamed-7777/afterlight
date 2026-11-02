"""Freeze selector identities and recompute decisions without test outcomes.

Hash/metadata guards cannot independently prove that humans never viewed test
results. Keep freeze/access history. No function here opens a test dataset by
itself or runs a simulator.
"""
from __future__ import annotations
import json
from math import isclose
from pathlib import Path
from typing import Mapping, Sequence
from .metrics import finite
from .protocol import assert_episode_coverage, digest
from .splits import assert_disjoint


def protocol_content(envelope: Mapping) -> Mapping:
    protocol = envelope["protocol"]
    if envelope["sha256"] != digest(protocol) or protocol.get("schema") != "afterlight.protocol.v1":
        raise ValueError("protocol hash/schema mismatch")
    return protocol


def validate_prediction_inputs(rows: Sequence[Mapping], frozen_protocol: Mapping) -> None:
    """Verify recorded analytical scores against the frozen observation formula."""
    from models.analytical import AnalyticalConfig, estimate_candidates
    from models.residual import DEFAULT_FEATURES, feature_vector
    protocol = protocol_content(frozen_protocol)
    names = [field["name"] for field in protocol["feature_schema"]]
    if names != list(DEFAULT_FEATURES):
        raise ValueError("queue-lost-service-v1 requires its declared seven-feature order")
    estimator = protocol["analytical_estimator"]
    if estimator["version"] != "queue-lost-service-v1":
        raise ValueError("unsupported analytical estimator version")
    config = AnalyticalConfig(**estimator["config"])
    if config.civilian_weight != protocol["civilian_weight"]:
        raise ValueError("analytical estimator objective weight differs from protocol")
    required_lag = max(finite(field["sensor_lag_s"], "feature lag") for field in protocol["feature_schema"])
    estimator_hash = digest(estimator)
    for row in rows:
        if row.get("analytical_config_sha256") != estimator_hash:
            raise ValueError("candidate analytical estimator differs from frozen protocol")
        observation = row["observation"]
        if observation["sensor_lag_s"] < required_lag:
            raise ValueError("candidate sensor lag shorter than frozen feature lag")
        feature_vector(observation, row["lead_s"], row["analytical_cost_s"], names)
        predicted = {s["lead_s"]: s["analytical_cost_s"] for s in estimate_candidates(observation, config)["scores"]}
        if not isclose(row["analytical_cost_s"], predicted[row["lead_s"]], rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("recorded analytical candidate cost differs from frozen inference formula")


def _artifact(selector: Mapping) -> dict:
    return {"sha256": digest(selector), "selector": dict(selector)}


def analytical_artifact(frozen_protocol: Mapping) -> dict:
    protocol_content(frozen_protocol)
    return _artifact({"schema": "afterlight.selector.v1", "kind": "analytical",
                      "protocol_sha256": frozen_protocol["sha256"]})


def fixed_lead_artifact(validation_rows: Sequence[Mapping], frozen_protocol: Mapping) -> dict:
    from models.residual import select_fixed_lead
    protocol = protocol_content(frozen_protocol)
    assert_disjoint(validation_rows, protocol["group_assignments"])
    required = {g for g, split in protocol["group_assignments"].items() if split == "validation"}
    if not required or {row["demand_group_id"] for row in validation_rows} != required:
        raise ValueError("fixed-lead selection must include all declared validation demand groups")
    for row in validation_rows:
        if row.get("source_commit") != protocol["source_commit"] or row["horizon_s"] != protocol["horizon_s"] or row["drain_end_s"] != protocol["drain_end_s"]:
            raise ValueError("fixed-lead validation source/windows differ from protocol")
    assert_episode_coverage(validation_rows, protocol, "validation")
    validate_prediction_inputs(validation_rows, frozen_protocol)
    result = select_fixed_lead(validation_rows, protocol["civilian_weight"])
    if not result["conclusive"]:
        raise ValueError("validation fixed lead is inconclusive without a common feasible cohort")
    return _artifact({"schema": "afterlight.selector.v1", "kind": "fixed",
                      "protocol_sha256": frozen_protocol["sha256"], "lead_s": result["lead_s"],
                      "validation_groups": sorted(required), "validation_data_sha256": digest(validation_rows),
                      "validation_selection": result})


def learned_artifact(model_envelope: Mapping, frozen_protocol: Mapping) -> dict:
    protocol = protocol_content(frozen_protocol)
    model = model_envelope["model"]
    if model_envelope["sha256"] != digest(model) or model.get("schema") != "afterlight.residual-tree.v1":
        raise ValueError("learned model hash/schema mismatch")
    if model.get("protocol_sha256") != frozen_protocol["sha256"]:
        raise ValueError("learned model was fitted against another protocol")
    if model.get("source_commit") != protocol["source_commit"] or model.get("civilian_weight") != protocol["civilian_weight"]:
        raise ValueError("learned model source/objective mismatch")
    if model.get("analytical_config_sha256") != digest(protocol["analytical_estimator"]):
        raise ValueError("learned model analytical estimator mismatch")
    if model.get("feature_names") != [field["name"] for field in protocol["feature_schema"]]:
        raise ValueError("learned model feature order mismatch")
    train_groups = set(model.get("training_groups", []))
    if not train_groups or any(protocol["group_assignments"].get(g) != "train" for g in train_groups):
        raise ValueError("learned model training groups contain non-training data")
    return _artifact({"schema": "afterlight.selector.v1", "kind": "residual_tree",
                      "protocol_sha256": frozen_protocol["sha256"], "model": dict(model_envelope)})


def freeze_selectors(frozen_protocol: Mapping, selected: Mapping, comparator: Mapping, destination: Path) -> dict:
    """Exclusive second-stage freeze after validation/model fit, before test.

    A separate envelope avoids the circular hash of a model trained against a
    protocol that would otherwise include that same model's eventual hash.
    """
    protocol_content(frozen_protocol)
    for artifact in (selected, comparator):
        selector = artifact["selector"]
        if artifact["sha256"] != digest(selector) or selector.get("protocol_sha256") != frozen_protocol["sha256"]:
            raise ValueError("selector artifact hash/protocol mismatch")
    selectors = {"schema": "afterlight.selector-freeze.v1", "protocol_sha256": frozen_protocol["sha256"],
                 "selected": dict(selected), "comparator": dict(comparator)}
    envelope = {"sha256": digest(selectors), "selectors": selectors}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(envelope, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return envelope


def _recompute(artifact: Mapping, rows: Sequence[Mapping], frozen_protocol: Mapping) -> dict[str, int]:
    from models.analytical import AnalyticalConfig, estimate_candidates
    from models.residual import CANDIDATES, choose_candidate
    protocol = protocol_content(frozen_protocol)
    selector = artifact["selector"]
    if artifact["sha256"] != digest(selector) or selector.get("schema") != "afterlight.selector.v1" or selector.get("protocol_sha256") != frozen_protocol["sha256"]:
        raise ValueError("selector artifact hash/schema/protocol mismatch")
    observations = {row["episode_id"]: row["observation"] for row in rows}
    kind = selector["kind"]
    if kind == "fixed":
        lead = selector["lead_s"]
        validation = selector.get("validation_selection", {})
        groups = set(selector.get("validation_groups", []))
        expected_groups = {g for g, split in protocol["group_assignments"].items() if split == "validation"}
        if isinstance(lead, bool) or lead not in CANDIDATES or validation.get("lead_s") != lead or not validation.get("conclusive"):
            raise ValueError("fixed selector lacks a conclusive validation selection")
        if not groups or groups != expected_groups or not selector.get("validation_data_sha256"):
            raise ValueError("fixed selector validation provenance mismatch")
        return {eid: lead for eid in observations}
    if kind not in {"analytical", "residual_tree"}:
        raise ValueError("unsupported frozen selector")
    model = selector.get("model") if kind == "residual_tree" else None
    if kind == "residual_tree" and model is None:
        raise ValueError("residual selector is missing its trained model artifact")
    if model is not None:
        learned_artifact(model, frozen_protocol)  # Validate provenance, not just tree bytes.
    config = AnalyticalConfig(**protocol["analytical_estimator"]["config"])
    names = [field["name"] for field in protocol["feature_schema"]]
    decisions = {}
    for eid, observation in observations.items():
        estimates = estimate_candidates(observation, config)
        # ONLY frozen pre-dispatch observations are supplied. Outcome targets,
        # future trajectories, regimes and seeds never enter this computation.
        costs = {row["lead_s"]: row["analytical_cost_s"] for row in estimates["scores"]}
        decisions[eid] = choose_candidate(observation, costs, names, model)["lead_s"]
    return decisions


def recompute_frozen_decisions(rows: Sequence[Mapping], frozen_protocol: Mapping, frozen_selectors: Mapping) -> tuple[dict, dict]:
    selectors = frozen_selectors["selectors"]
    if frozen_selectors["sha256"] != digest(selectors) or selectors.get("schema") != "afterlight.selector-freeze.v1" or selectors.get("protocol_sha256") != frozen_protocol["sha256"]:
        raise ValueError("selector freeze hash/schema/protocol mismatch")
    validate_prediction_inputs(rows, frozen_protocol)
    return (_recompute(selectors["selected"], rows, frozen_protocol),
            _recompute(selectors["comparator"], rows, frozen_protocol))
