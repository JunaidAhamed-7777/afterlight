"""Small scalar residual tree with an explicit inference feature boundary.

Training is opt-in, requires scikit-learn, and must be performed on Omen.
Persistence is plain JSON, never executable pickle content.
"""
from __future__ import annotations
from typing import Mapping, Sequence
import struct
from statistics import mean
from evaluation.metrics import finite, objective
from evaluation.protocol import assert_episode_coverage, digest
from evaluation.splits import assert_disjoint

CANDIDATES = (0, 5, 10, 20, 30)
OBSERVED_FEATURES = frozenset({"queue_sum_veh", "queue_max_veh", "arrival_rate_veh_s",
    "downstream_occupancy", "route_distance_m", "route_junction_count", "eta_remaining_s", "phase_elapsed_s"})
DEFAULT_FEATURES = ("queue_sum_veh", "queue_max_veh", "downstream_occupancy", "route_distance_m",
                    "route_junction_count", "eta_remaining_s", "phase_elapsed_s")


def feature_vector(observation: Mapping, lead_s: int, analytical_cost_s: float, feature_names: Sequence[str]) -> list[float]:
    if lead_s not in CANDIDATES or isinstance(lead_s, bool):
        raise ValueError("unsupported candidate lead")
    if not feature_names or len(set(feature_names)) != len(feature_names) or not set(feature_names) <= OBSERVED_FEATURES:
        raise ValueError("feature schema contains unsupported or duplicate inputs")
    dispatch = finite(observation["dispatch_s"], "dispatch_s")
    lag = finite(observation["sensor_lag_s"], "sensor_lag_s")
    observed = finite(observation["observed_at_s"], "observed_at_s")
    if observed > dispatch - lag:
        raise ValueError("observation violates declared inference-time sensor lag")
    values = observation["values"]
    # Reject unknown fields rather than silently carrying future information.
    if set(values) != set(feature_names):
        raise ValueError("observation values differ from frozen feature schema")
    vector = [finite(values[name], name) for name in feature_names]
    if "downstream_occupancy" in values and values["downstream_occupancy"] > 1:
        raise ValueError("downstream_occupancy must be a fraction in [0, 1], not percent")
    if "route_junction_count" in values and (isinstance(values["route_junction_count"], bool) or int(values["route_junction_count"]) != values["route_junction_count"]):
        raise ValueError("route_junction_count must be an integer")
    return [*vector, float(lead_s), finite(analytical_cost_s, "analytical_cost_s", nonnegative=False)]


def validate_candidate_rows(rows: Sequence[Mapping], expected_split: str | None = None) -> dict[str, list[Mapping]]:
    assert_disjoint(rows)
    episodes: dict[str, list[Mapping]] = {}
    for row in rows:
        if expected_split is not None and row["split"] != expected_split:
            raise ValueError(f"only {expected_split} rows allowed here")
        if isinstance(row["lead_s"], bool) or row["lead_s"] not in CANDIDATES:
            raise ValueError("not a fixed-lead candidate row")
        episodes.setdefault(row["episode_id"], []).append(row)
    if not episodes:
        raise ValueError("no candidate episodes")
    for eid, candidates in episodes.items():
        if sorted(row["lead_s"] for row in candidates) != list(CANDIDATES):
            raise ValueError(f"episode {eid} must retain exactly all five candidates, including failed outcomes")
        reference = candidates[0]
        for row in candidates[1:]:
            for name in ("demand_group_id", "observation", "demand_sha256", "network_sha256", "horizon_s", "drain_end_s"):
                if row[name] != reference[name]:
                    raise ValueError(f"candidate states/provenance differ: {eid}/{name}")
    return episodes


def select_fixed_lead(validation_rows: Sequence[Mapping], civilian_weight: float) -> dict:
    """Lexicographic: minimum failures, then mean J on common feasible episodes.

    Common-feasible comparison prevents a lead from improving its apparent mean
    merely by failing on hard episodes. All-infeasible validation is inconclusive.
    """
    episodes = validate_candidate_rows(validation_rows, "validation")
    if any(row["status"] == "infrastructure_error" for row in validation_rows):
        raise ValueError("infrastructure failures need declared retry/resolution before selecting a fixed lead")
    costs = {eid: {row["lead_s"]: objective(row, civilian_weight) for row in rows} for eid, rows in episodes.items()}
    common = [eid for eid, values in costs.items() if all(v is not None for v in values.values())]
    scores = []
    for lead in CANDIDATES:
        failures = sum(values[lead] is None for values in costs.values())
        mean_cost = finite(mean(costs[eid][lead] for eid in common), "fixed-lead mean", nonnegative=False) if common else None
        scores.append({"lead_s": lead, "infeasible_count": failures, "common_feasible_mean_j_s": mean_cost})
    best = min(scores, key=lambda s: (s["infeasible_count"], s["common_feasible_mean_j_s"] or 0, s["lead_s"]))
    return {"lead_s": best["lead_s"], "scores": scores, "common_feasible_episodes": len(common),
            "episodes": len(episodes), "conclusive": bool(common), "tie_break": "smallest_lead"}


def fit_residual(train_rows: Sequence[Mapping], *, feature_names: Sequence[str], civilian_weight: float,
                 frozen_protocol: Mapping, max_depth: int = 3, min_samples_leaf: int = 5) -> dict:
    validate_candidate_rows(train_rows, "train")
    protocol = frozen_protocol["protocol"]
    protocol_sha256 = frozen_protocol["sha256"]
    if protocol_sha256 != digest(protocol):
        raise ValueError("frozen protocol hash mismatch")
    assert_disjoint(train_rows, protocol["group_assignments"])
    if list(feature_names) != [field["name"] for field in protocol["feature_schema"]]:
        raise ValueError("training feature schema differs from frozen protocol")
    if civilian_weight != protocol["civilian_weight"]:
        raise ValueError("training objective weight differs from frozen protocol")
    analytical_config_sha256 = digest(protocol["analytical_estimator"])
    if any(row.get("analytical_config_sha256") != analytical_config_sha256 for row in train_rows):
        raise ValueError("candidate analytical estimator differs from frozen protocol")
    for row in train_rows:
        if row.get("source_commit") != protocol["source_commit"]:
            raise ValueError("training run source commit differs from frozen protocol")
        if row["horizon_s"] != protocol["horizon_s"] or row["drain_end_s"] != protocol["drain_end_s"]:
            raise ValueError("training outcome window differs from frozen protocol")
        required_lag = max(field["sensor_lag_s"] for field in protocol["feature_schema"])
        if row["observation"]["sensor_lag_s"] < required_lag:
            raise ValueError("training observation lag is shorter than frozen feature lag")
    assert_episode_coverage(train_rows, protocol, "train")
    specification = protocol["model_specification"]
    if specification.get("max_depth") != max_depth or specification.get("min_samples_leaf") != min_samples_leaf:
        raise ValueError("training hyperparameters differ from frozen protocol")
    if not isinstance(max_depth, int) or not isinstance(min_samples_leaf, int) or not 1 <= max_depth <= 8 or min_samples_leaf < 1:
        raise ValueError("bounded integer tree parameters required")
    features, labels = [], []
    for row in train_rows:
        vector = feature_vector(row["observation"], row["lead_s"], row["analytical_cost_s"], feature_names)
        actual = objective(row, civilian_weight)
        if actual is not None:
            features.append(vector)
            labels.append(finite(actual - row["analytical_cost_s"], "residual training label", nonnegative=False))
    if len(labels) < 2 * min_samples_leaf:
        raise ValueError("too few finite training labels; retain failures and report inconclusive")
    from sklearn import __version__ as sklearn_version
    from sklearn.tree import DecisionTreeRegressor
    estimator = DecisionTreeRegressor(max_depth=max_depth, min_samples_leaf=min_samples_leaf, random_state=0)
    estimator.fit(features, labels)
    tree = estimator.tree_
    model = {"schema": "afterlight.residual-tree.v1", "protocol_sha256": protocol_sha256,
             "feature_names": list(feature_names), "civilian_weight": civilian_weight,
             "analytical_config_sha256": analytical_config_sha256,
             "training_rows": len(train_rows), "finite_training_labels": len(labels),
             "excluded_infeasible_labels": len(train_rows) - len(labels),
             "training_groups": sorted({row["demand_group_id"] for row in train_rows}),
             "training_data_sha256": digest(train_rows), "sklearn_version": sklearn_version,
             "source_commit": protocol["source_commit"],
             "parameters": {"max_depth": max_depth, "min_samples_leaf": min_samples_leaf, "random_state": 0},
             "nodes": [{"left": int(tree.children_left[i]), "right": int(tree.children_right[i]),
                        "feature": int(tree.feature[i]), "threshold": float(tree.threshold[i]),
                        "value": float(tree.value[i][0][0])} for i in range(tree.node_count)],
             "limitation": "Regression does not predict feasibility; headline evaluation must count selected-action failures."}
    return {"sha256": digest(model), "model": model}


def predict_residual(envelope: Mapping, vector: Sequence[float]) -> float:
    model = envelope["model"]
    if envelope["sha256"] != digest(model) or model["schema"] != "afterlight.residual-tree.v1":
        raise ValueError("model schema/hash mismatch")
    if not model["feature_names"] or len(set(model["feature_names"])) != len(model["feature_names"]) or not set(model["feature_names"]) <= OBSERVED_FEATURES:
        raise ValueError("invalid model feature metadata")
    if len(vector) != len(model["feature_names"]) + 2:
        raise ValueError("model feature dimension mismatch")
    try:
        # sklearn tree predict converts X to float32; preserve split boundaries.
        values = [finite(struct.unpack("f", struct.pack("f", finite(v, "model input", nonnegative=False)))[0],
                         "float32 model input", nonnegative=False) for v in vector]
    except (OverflowError, struct.error) as error:
        raise ValueError("model input outside float32 range") from error
    nodes, index = model["nodes"], 0
    visited: set[int] = set()
    while True:
        if not isinstance(index, int) or index < 0 or index >= len(nodes) or index in visited:
            raise ValueError("invalid or cyclic tree")
        visited.add(index)
        node = nodes[index]
        if node["left"] == node["right"] == -1:
            return finite(node["value"], "leaf value", nonnegative=False)
        feature = node["feature"]
        if not isinstance(feature, int) or not 0 <= feature < len(values):
            raise ValueError("invalid tree feature")
        threshold = finite(node["threshold"], "tree threshold", nonnegative=False)
        index = node["left"] if values[feature] <= threshold else node["right"]


def choose_candidate(observation: Mapping, analytical_costs: Mapping[int, float], feature_names: Sequence[str], model: Mapping | None = None) -> dict:
    if set(analytical_costs) != set(CANDIDATES):
        raise ValueError("all five candidate analytical costs required")
    if model is not None and list(feature_names) != model["model"]["feature_names"]:
        raise ValueError("feature order differs from model")
    scores = []
    for lead in CANDIDATES:
        cost = analytical_costs[lead]
        vector = feature_vector(observation, lead, cost, feature_names)
        residual = predict_residual(model, vector) if model is not None else 0.0
        scores.append({"lead_s": lead, "analytical_cost_s": cost, "predicted_residual_s": residual,
                       "predicted_j_s": finite(cost + residual, "predicted objective result", nonnegative=False)})
    chosen = min(scores, key=lambda row: (row["predicted_j_s"], row["lead_s"]))
    return {"lead_s": chosen["lead_s"], "scores": scores, "method": "residual_tree" if model else "analytical",
            "tie_break": "smallest_lead", "prediction_not_measurement": True}
