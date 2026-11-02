"""Deterministic whole-demand grouping. Never split individual candidate rows."""
from __future__ import annotations
import hashlib
from typing import Mapping, Sequence


def assign_groups(groups: Sequence[Mapping], *, salt: str, train_fraction: float = .6,
                  validation_fraction: float = .2, heldout_regimes: Sequence[str] = ()) -> dict[str, str]:
    if not salt or not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("nonempty salt and positive train/validation/test fractions required")
    result: dict[str, str] = {}
    regimes: dict[str, str] = {}
    for group in groups:
        gid, regime = group["demand_group_id"], group["regime"]
        if not isinstance(gid, str) or not gid or not isinstance(regime, str) or not regime:
            raise ValueError("group id and regime must be nonempty strings")
        if gid in regimes and regimes[gid] != regime:
            raise ValueError("one demand group cannot change regimes")
        regimes[gid] = regime
        fraction = int.from_bytes(hashlib.sha256(f"{salt}\0{gid}".encode()).digest()[:8], "big") / 2**64
        result[gid] = "test" if regime in heldout_regimes else (
            "train" if fraction < train_fraction else "validation" if fraction < train_fraction + validation_fraction else "test")
    return result


def assert_disjoint(rows: Sequence[Mapping], assignments: Mapping[str, str] | None = None) -> dict[str, int]:
    seen: dict[str, str] = {}
    episodes: dict[str, tuple[str, str]] = {}
    # A caller cannot evade grouping by relabeling an identical input hash.
    # Full demand may change with ambulance dispatch; civilian-realization hashes
    # (when supplied) additionally bind those dispatch variants together.
    hash_owners: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        gid, split = row["demand_group_id"], row["split"]
        if split not in {"train", "validation", "test", "pilot"}:
            raise ValueError(f"unknown split: {split}")
        if gid in seen and seen[gid] != split:
            raise ValueError(f"demand group leaks across splits: {gid}")
        if assignments is not None and assignments.get(gid) != split:
            raise ValueError(f"row differs from frozen assignment: {gid}")
        for field in ("demand_sha256", "demand_manifest_sha256", "demand_realization_sha256", "civilian_realization_sha256"):
            if field in row:
                value = row[field]
                if not isinstance(value, str) or not value:
                    raise ValueError(f"invalid input identity: {field}")
                identity = (field, value)
                if identity in hash_owners and hash_owners[identity] != (gid, split):
                    raise ValueError(f"identical {field} assigned different demand groups or splits")
                hash_owners[identity] = (gid, split)
        seen[gid] = split
        if "episode_id" in row:
            eid = row["episode_id"]
            if eid in episodes and episodes[eid] != (gid, split):
                raise ValueError(f"episode changes demand group or split: {eid}")
            episodes[eid] = (gid, split)
    return {split: sum(value == split for value in seen.values()) for split in ("train", "validation", "test", "pilot")}
