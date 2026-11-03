"""Explicit study-only correction: bind the EXACT frozen analytical estimator.

Original simulation, scalar rows, hashes, objectives and legacy pilot verifier
remain untouched. Every original raw/metric/decision/timing guard is retained.
"""
from dataclasses import asdict
from models.analytical import AnalyticalConfig, ESTIMATOR_VERSION, estimate_candidates
from policies.scheduler import Timing, timing_for_network
from evaluation.protocol import digest


def validate_frozen_estimator_world_binding(row, raw, plan):
    expected_timing = asdict(timing_for_network(plan['network']))
    if raw['metrics'].get('controller_timing', asdict(Timing())) != expected_timing:
        raise ValueError('study raw controller timing differs from declared network profile')
    for key in ('policy', 'lead_s', 'status', 'sumo_version'):
        if row.get(key) != raw.get(key):
            raise ValueError(f'study scalar/raw outcome mismatch: {key}')
    for key, value in raw['metrics'].items():
        row_key = 'simulator_runtime_s' if key == 'runtime_s' else key
        if row.get(row_key) != value:
            raise ValueError(f'study scalar/raw metric mismatch: {key}')
    decision = raw['decision']
    for key in ('observation', 'request_plan'):
        if row.get(key) != decision[key]:
            raise ValueError(f'study scalar/raw decision mismatch: {key}')
    estimator = plan['analytical_estimator']
    if (set(estimator) != {'version', 'config'} or estimator['version'] != ESTIMATOR_VERSION or
            set(estimator['config']) != set(asdict(AnalyticalConfig())) or
            estimator['config']['civilian_weight'] != plan['civilian_weight']):
        raise ValueError('Exact frozen analytical estimator/version/configuration required')
    estimates = estimate_candidates(decision['observation'], AnalyticalConfig(**estimator['config']))
    reconstructed = {'version': estimates['version'], 'config': estimates['config']}
    expected_hash = digest(estimator)
    if digest(reconstructed) != expected_hash:
        raise ValueError('Analytical constructor changed the exact frozen estimator identity')
    cost = next((score['analytical_cost_s'] for score in estimates['scores'] if score['lead_s'] == row['lead_s']), None)
    if row.get('analytical_config_sha256') != expected_hash or row.get('analytical_cost_s') != cost:
        raise ValueError('Study prediction/config differs from the exact frozen observation-only estimator')
