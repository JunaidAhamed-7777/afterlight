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

ESTIMATOR_VERSION = "queue-concentration-v2"
# sim.run.dispatch_observation embeds this fixed queue component in frozen ETA.
# It is NOT the configurable service headway used to predict residual queues.
ETA_QUEUE_HEADWAY_S = 2.0


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


def _queue_residual_bounds(total: float, maximum: float, count: int,
                           headway: float, service_s: float) -> tuple[float, float]:
    """Tight residual-delay bounds for unknown per-junction queue allocation.

    Assumes identical service S seconds at each junction, q_i in [0, maximum],
    sum(q_i)=total, max(q_i)=maximum. Residual is sum(max(headway*q_i-S,0)).
    Most concentrated allocation maximizes this convex sum; spreading all but
    one maximal queue minimizes it. These are bounds inside this surrogate,
    NOT guarantees for actual traffic, lane movements or future arrivals.
    """
    if not total:
        return 0.0, 0.0
    max_delay = finite(headway * maximum, "maximum observed queue delay")
    other_delay = finite(headway * (total - maximum), "remaining observed queue delay")
    other_service = finite((count - 1) * service_s, "remaining junction service")
    lower = finite(max(0.0, max_delay - service_s) + max(0.0, other_delay - other_service),
                   "optimistic residual queue delay")
    # divmod handles exact integral observations and nonintegral detector
    # estimates without creating a fictitious extra full queue at a boundary.
    full, remainder = divmod(total, maximum)
    upper = finite(full * max(0.0, max_delay - service_s)
                   + max(0.0, finite(headway * remainder, "remainder queue delay") - service_s),
                   "concentrated residual queue delay")
    # Numerical roundoff may put a bound a few ulps outside the unsaturated
    # original delay. Clamp only to physically available *observed* delay.
    original = finite(headway * total, "total observed queue delay")
    upper = min(original, upper)
    return min(lower, upper), upper


def estimate_candidates(observation: Mapping, config: AnalyticalConfig = AnalyticalConfig()) -> dict:
    """Concentration-aware observed-queue cost, not a measured SUMO outcome.

    Queue sum/max/count refer to the same route-controlled junction groups in
    sim.run.snapshot/dispatch_observation. An empty junction cannot discharge
    another junction's queue. Use the worst residual allocation consistent with
    those aggregate observations; expose both bounds for transparent diagnostics.
    Civilian penalty has units seconds (lead^2 / cycle), but remains an uncalibrated
    mean-delay surrogate: it is not an observed all-demand waiting-area metric.
    """
    feature_vector(observation, 0, 0, DEFAULT_FEATURES)
    x = observation["values"]
    count = int(x["route_junction_count"])
    total, maximum = x["queue_sum_veh"], x["queue_max_veh"]
    if maximum > total or total > finite(count * maximum, "queue allocation capacity"):
        raise ValueError("queue sum/max/count are inconsistent junction aggregates")
    if (count == 0 or maximum == 0) and total != 0:
        raise ValueError("a positive queue requires a controlled junction and positive maximum")
    eta_queue_delay = finite(ETA_QUEUE_HEADWAY_S * total, "frozen ETA queue component")
    if x["eta_remaining_s"] < eta_queue_delay:
        raise ValueError("frozen ETA is shorter than its declared observed queue component")
    freeflow = x["eta_remaining_s"] - eta_queue_delay
    occupancy = x["downstream_occupancy"]
    scores = []
    for lead in CANDIDATES:
        service_s = finite(max(0.0, lead - config.transition_loss_s) * (1.0 - occupancy),
                           "per-junction available queue service")
        optimistic, conservative = _queue_residual_bounds(total, maximum, count, config.queue_headway_s, service_s)
        predicted_ambulance = finite(freeflow + conservative, "predicted ambulance journey")
        # Divide before multiplying to avoid needless intermediate overflow for
        # a large finite cycle. Every remaining product is checked explicitly.
        delay_per_junction = finite((lead / config.ordinary_cycle_s) * (lead / 2.0), "civilian delay per junction")
        predicted_civilian = finite(config.civilian_cost_scale * finite(count * delay_per_junction,
            "route civilian delay surrogate") * (1.0 + occupancy), "civilian delay surrogate")
        objective = finite(predicted_ambulance + finite(config.civilian_weight * predicted_civilian,
            "weighted civilian delay surrogate"), "analytical objective result")
        scores.append({"lead_s": lead, "analytical_cost_s": objective,
                       "predicted_ambulance_s": predicted_ambulance,
                       "predicted_civilian_delay_surrogate_s": predicted_civilian,
                       "effective_service_per_junction_s": service_s,
                       "residual_queue_delay_bounds_s": {"optimistic": optimistic, "conservative": conservative}})
    return {"version": ESTIMATOR_VERSION, "config": asdict(config), "scores": scores,
            "eta_queue_headway_s": ETA_QUEUE_HEADWAY_S,
            "uses_future_demand": False, "prediction_not_measurement": True,
            "limitation": "Bounds apply only to the aggregate equal-service surrogate, not traffic guarantees. Incoming-edge queues may include other turns; occupancy is route-averaged. Ignores individual phase age, min-green residual, clipped request schedules and future arrivals. Civilian penalty is uncalibrated, not a measured all-demand mean. No empirical gain claimed."}


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
