"""Paired decision summaries with failure-first reporting and grouped uncertainty."""
from __future__ import annotations
from collections import Counter
from random import Random
from statistics import mean
from typing import Mapping, Sequence
from .metrics import finite, objective
from .splits import assert_disjoint


def paired_decision_report(rows: Sequence[Mapping], selected_leads: Mapping[str, int], comparator_leads: Mapping[str, int],
                           *, civilian_weight: float, expected_split: str = "test") -> dict:
    """Compare decisions on real cached five-action outcomes; no oracle selection.

    Failure counts include every episode. Conditional finite differences include
    only episodes where BOTH selected policies have valid complete outcomes.
    Negative delta means selected minus comparator is lower, not a safety claim.
    """
    from models.residual import validate_candidate_rows
    episodes = validate_candidate_rows(rows, expected_split)
    assert_disjoint(rows)
    if set(selected_leads) != set(episodes) or set(comparator_leads) != set(episodes):
        raise ValueError("each decision map must include every episode exactly once")
    if any(r["status"] == "infrastructure_error" for r in rows):
        raise ValueError("infrastructure failures require declared resolution before decision comparison")
    records = []
    for eid, candidates in episodes.items():
        by_lead = {row["lead_s"]: row for row in candidates}
        if selected_leads[eid] not in by_lead or comparator_leads[eid] not in by_lead:
            raise ValueError(f"decision selects unavailable candidate: {eid}")
        chosen, reference = by_lead[selected_leads[eid]], by_lead[comparator_leads[eid]]
        cj, rj = objective(chosen, civilian_weight), objective(reference, civilian_weight)
        feasible = [value for row in candidates if (value := objective(row, civilian_weight)) is not None]
        records.append({"episode_id": eid, "demand_group_id": chosen["demand_group_id"],
                        "selected_lead_s": chosen["lead_s"], "comparator_lead_s": reference["lead_s"],
                        "selected_status": chosen["status"], "comparator_status": reference["status"],
                        "selected_infeasible": cj is None, "comparator_infeasible": rj is None,
                        "selected_j_s": cj, "comparator_j_s": rj,
                        "paired_delta_j_s": cj - rj if cj is not None and rj is not None else None,
                        "conditional_regret_s": cj - min(feasible) if cj is not None and feasible else None,
                        "civilian_delta_s": finite(chosen["civilian_mean_excess_s"], "civilian delay", nonnegative=False) -
                            finite(reference["civilian_mean_excess_s"], "civilian delay", nonnegative=False)
                            if cj is not None and rj is not None else None,
                        "all_candidates_infeasible": not feasible})
    finite_pairs = [r for r in records if r["paired_delta_j_s"] is not None]
    deltas = [r["paired_delta_j_s"] for r in finite_pairs]
    civilian_deltas = sorted(r["civilian_delta_s"] for r in finite_pairs)
    # Nearest-rank empirical p95, explicitly conditional on paired feasibility.
    p95 = civilian_deltas[max(0, (95 * len(civilian_deltas) + 99) // 100 - 1)] if civilian_deltas else None
    return {"schema": "afterlight.decision-comparison.v1", "split": expected_split,
            "episodes": len(records), "demand_groups": len({r["demand_group_id"] for r in records}),
            "selected_failures": sum(r["selected_infeasible"] for r in records),
            "comparator_failures": sum(r["comparator_infeasible"] for r in records),
            "selected_status_counts": dict(Counter(r["selected_status"] for r in records)),
            "comparator_status_counts": dict(Counter(r["comparator_status"] for r in records)),
            "all_candidates_infeasible_episodes": sum(r["all_candidates_infeasible"] for r in records),
            "changed_action_rate": mean(r["selected_lead_s"] != r["comparator_lead_s"] for r in records),
            "paired_feasible_episodes": len(finite_pairs),
            "conditional_mean_delta_j_s": mean(deltas) if deltas else None,
            "conditional_improved_fraction": mean(d < 0 for d in deltas) if deltas else None,
            "conditional_worsened_fraction": mean(d > 0 for d in deltas) if deltas else None,
            "conditional_civilian_harm_p95_s": p95,
            "records": records,
            "interpretation": "Failures cover all episodes. Finite differences and civilian harm are conditional on BOTH decisions completing validly; not an unconditional policy benefit."}


def grouped_bootstrap_interval(records: Sequence[Mapping], *, field: str = "paired_delta_j_s", seed: int = 0,
                               resamples: int = 2000, min_groups: int = 10) -> dict:
    """Resample whole demand groups, preserving all dispatch variants together.

    Returns no interval for small support. Conditional values remain conditional;
    no result from this function upgrades missing/failed episodes to finite ones.
    """
    if resamples < 100 or min_groups < 2:
        raise ValueError("at least 100 resamples and two minimum groups required")
    grouped: dict[str, list[float]] = {}
    for row in records:
        if row.get(field) is not None:
            grouped.setdefault(row["demand_group_id"], []).append(finite(row[field], field, nonnegative=False))
    if len(grouped) < min_groups:
        return {"interval": None, "groups": len(grouped), "reason": "insufficient independent demand groups",
                "minimum_groups": min_groups}
    groups = sorted(grouped)
    rng = Random(seed)
    means = []
    for _ in range(resamples):
        sample = [v for _ in groups for v in grouped[rng.choice(groups)]]
        means.append(mean(sample))
    means.sort()
    low, high = means[int(.025 * (resamples - 1))], means[int(.975 * (resamples - 1))]
    return {"interval": [low, high], "level": .95, "method": "whole-demand-group percentile bootstrap",
            "groups": len(groups), "resamples": resamples, "seed": seed,
            "estimand": "episode-weighted mean over finite paired outcomes; failures reported separately"}
