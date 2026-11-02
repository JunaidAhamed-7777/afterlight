"""Outcome validity and common-clock metrics (seconds and vehicle-seconds)."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence


def finite(value: object, name: str, *, nonnegative: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"invalid {name}: {value}")
    return result


@dataclass(frozen=True)
class Accounting:
    scheduled: int
    inserted: int
    completed: int
    running: int
    not_inserted: int

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.scheduled != self.inserted + self.not_inserted:
            raise ValueError("scheduled != inserted + not_inserted")
        if self.inserted != self.completed + self.running:
            raise ValueError("inserted != completed + running; removed/teleported traffic must be invalid")

    @property
    def drained(self) -> bool:
        return self.completed == self.scheduled and not self.running and not self.not_inserted

    @classmethod
    def from_mapping(cls, value: Mapping) -> Accounting:
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


def objective(outcome: Mapping, civilian_weight: float) -> float | None:
    """None denotes infeasibility/unavailable evidence, never a finite penalty.

    Malformed accounting raises rather than silently classifying corrupt records.
    Infrastructure failures are retained by callers but are not traffic outcomes.
    """
    weight = finite(civilian_weight, "civilian_weight")
    accounting = Accounting.from_mapping(outcome["accounting"])
    if outcome["status"] not in {"completed", "censored", "invalid", "infrastructure_error"}:
        raise ValueError("unknown outcome status")
    if outcome["status"] != "completed" or outcome.get("validity_reasons") or not accounting.drained:
        return None
    ambulance = outcome.get("ambulance_journey_s")
    civilian = outcome.get("civilian_mean_excess_s")
    if ambulance is None or civilian is None:
        return None
    # Excess journey time may be negative against a declared reference model.
    return finite(ambulance, "ambulance_journey_s") + weight * finite(
        civilian, "civilian_mean_excess_s", nonnegative=False
    )


def _queue_series(samples: Sequence[Mapping], start: float, end: float) -> list[tuple[float, float]]:
    rows = [(finite(s["t"], "queue timestamp"), finite(s["queue_count"], "queue_count")) for s in samples]
    if len(rows) < 2 or any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("queue timestamps must strictly increase with at least two observations")
    if rows[0][0] > start or rows[-1][0] < end:
        raise ValueError("queue observations must cover the complete prespecified window")
    return rows


def excess_queue_area(priority: Sequence[Mapping], ordinary: Sequence[Mapping], start_s: float, end_s: float) -> float:
    """Integral max(0, Q_priority - Q_ordinary), left-held samples.

    Uses a common absolute window, not policy-dependent ambulance exit times.
    Irregular grids are merged; observations are never extrapolated past coverage.
    """
    start, end = finite(start_s, "start_s"), finite(end_s, "end_s")
    if end <= start:
        raise ValueError("end_s must be after start_s")
    p, b = _queue_series(priority, start, end), _queue_series(ordinary, start, end)
    knots = sorted({start, end, *(t for t, _ in p if start < t < end), *(t for t, _ in b if start < t < end)})
    pi = bi = 0
    area = 0.0
    for left, right in zip(knots, knots[1:]):
        while pi + 1 < len(p) and p[pi + 1][0] <= left:
            pi += 1
        while bi + 1 < len(b) and b[bi + 1][0] <= left:
            bi += 1
        area += max(0.0, p[pi][1] - b[bi][1]) * (right - left)
    return area


def verify_pair(a: Mapping, b: Mapping) -> None:
    for key in ("episode_id", "demand_group_id", "demand_sha256", "network_sha256", "horizon_s", "drain_end_s"):
        if key not in a or key not in b or a[key] != b[key]:
            raise ValueError(f"unpaired outcomes: {key}")
    if a["accounting"]["scheduled"] != b["accounting"]["scheduled"]:
        raise ValueError("paired scheduled populations differ")
