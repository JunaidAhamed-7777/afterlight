"""Stable experiment identities, separate from output paths and visual sampling."""
from __future__ import annotations
import hashlib
import json
import math


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def episode_identity(*, network_kind: str, regime: str, seed: int, network_sha256: str,
                     demand_sha256: str, dispatch_s: float, horizon_s: float,
                     drain_s: float, step_s: float) -> str:
    if network_kind not in ('fixture','city') or regime not in ('sparse','moderate','heavy','asymmetric'):
        raise ValueError('Unknown network/regime identity')
    if isinstance(seed,bool) or not isinstance(seed,int) or seed < 0:
        raise ValueError('Nonnegative integer seed required')
    if not network_sha256 or not demand_sha256:
        raise ValueError('Input hashes required')
    values = (dispatch_s,horizon_s,drain_s,step_s)
    if any(not math.isfinite(v) for v in values) or not 0 <= dispatch_s < horizon_s or drain_s < 0 or step_s <= 0:
        raise ValueError('Invalid experiment timing identity')
    # Normalize numerical representation: 60 and 60.0 identify the same time.
    inputs = {'network_sha256':network_sha256,'demand_sha256':demand_sha256,
              'dispatch_s':float(dispatch_s),'horizon_s':float(horizon_s),
              'drain_s':float(drain_s),'step_s':float(step_s)}
    return f'{network_kind}-{regime}-{seed}-{_digest(inputs)[:16]}'


def run_identity(episode_id: str, policy: str, lead_s: int | None = None) -> str:
    if not episode_id or policy not in ('ordinary','immediate','fixed','analytical','learned'):
        raise ValueError('Unknown episode or policy')
    if policy in ('ordinary','immediate'):
        if lead_s is not None:
            raise ValueError('Ordinary/immediate policy has no lead action')
        return f'{episode_id}-{policy}'
    if isinstance(lead_s,bool) or lead_s not in (0,5,10,20,30):
        raise ValueError('Candidate policy requires actual selected lead')
    return f'{episode_id}-{policy}-{lead_s}'
