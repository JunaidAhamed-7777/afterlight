"""Frozen-dispatch timing actions; zero lead is deliberately not immediate."""
from __future__ import annotations
import math

LEADS = (0, 5, 10, 20, 30)


def request_plan(dispatch_s: float, absolute_etas: dict[str, float], *, lead_s: int = 10,
                 immediate: bool = False) -> dict[str, float]:
    if not math.isfinite(dispatch_s) or dispatch_s < 0:
        raise ValueError("Invalid dispatch time")
    if lead_s not in LEADS:
        raise ValueError(f"Lead must be one of {LEADS}")
    if any(not math.isfinite(t) or t < dispatch_s for t in absolute_etas.values()):
        raise ValueError("ETAs must be absolute timestamps at or after dispatch")
    return {j: dispatch_s if immediate else max(dispatch_s, eta - lead_s)
            for j, eta in absolute_etas.items()}


def distinct_schedules(dispatch_s: float, absolute_etas: dict[str, float]) -> list[dict]:
    seen = set()
    result = []
    for lead in LEADS:
        plan = request_plan(dispatch_s, absolute_etas, lead_s=lead)
        key = tuple(sorted(plan.items()))
        if key not in seen:
            result.append({"lead_s": lead, "requests": plan})
            seen.add(key)
    return result
