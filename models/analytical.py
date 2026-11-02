"""Explicit coarse no-learning clearance-cost surrogate.

This predicts a scalar objective, not measured ambulance/civilian outcomes. Its
misspecification is intentional and visible; residual labels must come from SUMO.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Mapping
from evaluation.metrics import finite
from evaluation.protocol import digest
from .residual import CANDIDATES, DEFAULT_FEATURES, choose_candidate, feature_vector


@dataclass(frozen=True)
class AnalyticalConfig:
    queue_headway_s: float = 2.0
    transition_loss_s: float = 4.0  # yellow 3 + all-red 1; min-green may add delay.
    ordinary_cycle_s: float = 58.0  # two (25 green + 3 yellow + 1 all-red) stages.
    civilian_weight: float = 1.0
    civilian_cost_scale: float = 1.0

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            finite(value, key)
        if self.queue_headway_s == 0 or self.ordinary_cycle_s == 0:
            raise ValueError("headway and cycle must be positive")


def estimate_candidates(observation: Mapping, config: AnalyticalConfig = AnalyticalConfig()) -> dict:
    """Queue service benefit minus a lost-service waiting-area approximation.

    ETA already contains queue_sum * queue_headway. Lead beyond transition loss
    can discharge queues in parallel at route junctions; occupancy discounts that
    service. Civilian delay surrogate is the triangular lost-service area per
    ordinary cycle, multiplied by controlled junction count and congestion.
    It is NOT a trustworthy all-demand delay estimate before calibration.
    Phase elapsed is deliberately not used because the snapshot may be yellow.
    """
    feature_vector(observation, 0, 0, DEFAULT_FEATURES)
    x = observation["values"]
    count = x["route_junction_count"]
    queue_delay = config.queue_headway_s * x["queue_sum_veh"]
    freeflow = max(0.0, x["eta_remaining_s"] - queue_delay)
    occupancy = x["downstream_occupancy"]
    scores = []
    for lead in CANDIDATES:
        service_s = max(0.0, lead - config.transition_loss_s) * count * (1.0 - occupancy)
        predicted_ambulance = freeflow + max(0.0, queue_delay - service_s)
        predicted_civilian = config.civilian_cost_scale * count * lead * lead / (2.0 * config.ordinary_cycle_s) * (1.0 + occupancy)
        scores.append({"lead_s": lead, "analytical_cost_s": predicted_ambulance + config.civilian_weight * predicted_civilian,
                       "predicted_ambulance_s": predicted_ambulance, "predicted_civilian_delay_surrogate_s": predicted_civilian})
    return {"version": "queue-lost-service-v1", "config": asdict(config), "scores": scores,
            "uses_future_demand": False, "prediction_not_measurement": True,
            "limitation": "Aggregated coarse cost surrogate; ignores individual phase age, min-green residual, route ETA clipping and future arrivals. Not experimental traffic metrics."}


def choose_lead(observation: Mapping, *, civilian_weight: float = 1.0, model: Mapping | None = None,
                expected_protocol_sha256: str | None = None, config: AnalyticalConfig | None = None) -> dict:
    config = config or AnalyticalConfig(civilian_weight=civilian_weight)
    if config.civilian_weight != civilian_weight:
        raise ValueError("analytical objective weight mismatch")
    estimates = estimate_candidates(observation, config)
    if model is not None:
        metadata = model["model"]
        if not expected_protocol_sha256 or metadata.get("protocol_sha256") != expected_protocol_sha256:
            raise ValueError("learned inference requires the exact frozen protocol hash")
        if metadata.get("civilian_weight") != civilian_weight:
            raise ValueError("model objective weight mismatch")
        if metadata.get("analytical_config_sha256") != digest({"version": estimates["version"], "config": estimates["config"]}):
            raise ValueError("model analytical estimator metadata mismatch")
    choice = choose_candidate(observation, {r["lead_s"]: r["analytical_cost_s"] for r in estimates["scores"]}, DEFAULT_FEATURES, model)
    return {"lead_s": choice["lead_s"], "candidate_scores": choice["scores"],
            "model_sha256": model["sha256"] if model else None, "method": choice["method"],
            "analytical": estimates, "prediction_not_measurement": True}
