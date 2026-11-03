"""Collect one frozen train/validation split from saved inputs, on Omen only.

No demand regeneration, model fitting, test release, or automatic retries.
Every planned world remains inventoried even when collection stops early.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import time

from .metrics import Accounting, excess_queue_area, verify_pair
from .pilot import PilotAuditError, audit_pilot_world
from .protocol import digest
from .study_manifest import POLICIES, SAFE_ID, assert_saved_inputs, assert_study_runtime, load_study, read_json


def _checkpoint(path: Path, value: object) -> None:
    """Atomic replacement only inside this newly reserved collection attempt."""
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _input_directory(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError('Saved input directory must be relative POSIX text')
    path = Path(relative)
    resolved = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not resolved.is_relative_to((root / 'inputs').resolve()):
        raise ValueError('Saved input directory escapes frozen inputs')
    return resolved


def collect_split(study_directory: Path, split: str, output: Path) -> dict:
    if split not in {'train', 'validation'}:
        raise ValueError('Only train/validation collection is enabled; test requires a future verified selector-release gate')
    from sim.network import ROOT, read_network
    from sim.run import run_world
    from models.analytical import AnalyticalConfig, estimate_candidates

    root = study_directory.resolve()
    output = output.resolve()
    runtime_path = ROOT / 'local-runtime'
    runtime_root = runtime_path.resolve()
    if runtime_path.is_symlink() or not runtime_root.is_relative_to(ROOT.resolve()):
        raise ValueError('Ignored local-runtime root must not redirect outside the checkout or be a symlink')
    if output == runtime_root or not output.is_relative_to(runtime_root):
        raise ValueError('Collection output must be a new directory under ignored local-runtime')
    if output == root or output.is_relative_to(root / 'inputs') or root.is_relative_to(output):
        raise ValueError('Collection must not overlap saved study inputs or contain the study')
    envelope = load_study(root, require_frozen=True, verify_inputs=True)
    study = envelope['study']
    assert_study_runtime(study)
    episodes = [episode for episode in study['episodes'] if episode['split'] == split]
    if not episodes:
        raise ValueError('Frozen study has no episodes for requested split')
    timing = study['spec']['timing']
    expected_version = study['pilot_evidence']['sumo_version']
    if len({episode['episode_id'] for episode in episodes}) != len(episodes) or len({episode['case_id'] for episode in episodes}) != len(episodes):
        raise ValueError('Duplicate collection episode/case identity')
    if any(not isinstance(episode['case_id'], str) or not SAFE_ID.fullmatch(episode['case_id']) for episode in episodes):
        raise ValueError('Unsafe collection case identity')
    netdir = _input_directory(root, study['network']['directory'])
    for episode in episodes:
        _input_directory(root, episode['demand_directory'])
    network = read_network(netdir / 'network.net.xml')
    planned = [{'episode_id': episode['episode_id'], 'case_id': episode['case_id'],
                'policy': policy, 'lead_s': lead, 'state': 'unattempted',
                'directory': f"worlds/{episode['case_id']}/{policy}" + (f'-{lead}' if lead is not None else '')}
               for episode in episodes for policy, lead in POLICIES]
    if len(planned) > study['budget']['max_rollouts']:
        raise ValueError('Requested split exceeds frozen rollout budget')
    split_budget_s = study['budget']['split_start_budgets_s'][split]
    expected_budget_s = study['budget']['max_wall_time_s'] * len(episodes) / len(study['episodes'])
    if split_budget_s != expected_budget_s:
        raise ValueError('Frozen split allocation differs from proportional whole-study start budget')
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    manifest = {'schema': 'afterlight.collection.v1', 'study_sha256': envelope['sha256'],
                'protocol_sha256': digest(study['protocol']), 'split': split,
                'source': study['source'], 'dependencies': study['dependencies'],
                'sumo_version': expected_version, 'status': 'running', 'world_inventory': planned,
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'retry_policy': 'No automatic retries or pooling; retain this attempt and diagnose before a new explicit attempt',
                'split_start_budget_s': split_budget_s,
                'wall_budget_scope': 'Start-budget gate, not a hard cap: frozen whole-study allowance allocated in proportion to split episode count; one explicit attempt only, retries are not automatically pooled or budgeted; current world may overrun before collection stops'}
    rows = []

    def save() -> None:
        _checkpoint(output / 'outcomes.json', rows)
        _checkpoint(output / 'candidate-outcomes.json', [row for row in rows if row['policy'] == 'fixed'])
        manifest.update(recorded_worlds=len(rows), runner_invocations=sum(item.get('runner_invoked', False) for item in planned),
                        unattempted_worlds=sum(not item.get('runner_invoked', False) for item in planned),
                        runtime_total_s=time.perf_counter()-start)
        manifest['wall_budget_overrun_s'] = max(0.0, manifest['runtime_total_s']-split_budget_s)
        _checkpoint(output / 'collection.json', manifest)

    try:
        save()
        for episode in episodes:
            demand_dir = _input_directory(root, episode['demand_directory'])
            demand = read_json(demand_dir / 'demand.json')
            scheduled = sum(vehicle['id'] != 'ambulance' for vehicle in demand['vehicles'])
            episode_rows = []
            for item in [item for item in planned if item['episode_id'] == episode['episode_id']]:
                if time.perf_counter()-start >= split_budget_s:
                    raise RuntimeError('Frozen wall-time budget reached; remaining worlds retained as unattempted')
                world = None
                signal_hash = None
                world_dir = output / item['directory']
                before = time.perf_counter()
                identity = {key: episode[key] for key in ('episode_id', 'case_id', 'demand_group_id', 'split', 'regime',
                    'seed', 'dispatch_s', 'pickup_id', 'hospital_id', 'route_family', 'demand_sha256', 'network_sha256')}
                identity.update(policy=item['policy'], lead_s=item['lead_s'],
                    source_commit=study['source']['source_commit'], source_code_sha256=study['source']['source_code_sha256'],
                    study_sha256=envelope['sha256'], protocol_sha256=digest(study['protocol']))
                try:
                    assert_study_runtime(study)
                    assert_saved_inputs(root, study)
                    item['state'] = 'running'
                    save()
                    item['runner_invoked'] = True
                    world = run_world(world_id=world_dir.name, policy=item['policy'], lead_s=item['lead_s'] or 0,
                        network_dir=netdir, demand_dir=demand_dir, demand=demand, network=network, output=world_dir,
                        horizon_s=timing['horizon_s'], drain_s=timing['drain_s'], step_s=timing['step_s'],
                        sample_s=timing['sample_s'], sensor_lag_s=timing['sensor_lag_s'])
                    assert_study_runtime(study)
                    assert_saved_inputs(root, study)
                    if world.get('sumo_version') != expected_version:
                        raise RuntimeError('Actual SUMO version differs from frozen measured pilot runtime')
                    # Retain only the sampled signal portion needed to reproduce
                    # this audit; vehicle poses are not needed by scalar studies.
                    signal_evidence = {key: world[key] for key in ('policy', 'status', 'events', 'decision', 'metrics')}
                    signal_evidence['frames'] = [{'t': frame['t'], 'signals': frame['signals']} for frame in world['frames']]
                    signal_path = world_dir / 'signal-audit-input.json'
                    _checkpoint(signal_path, signal_evidence)
                    signal_hash = hashlib.sha256(signal_path.read_bytes()).hexdigest()
                    audit_pilot_world(world, network, demand, world_dir, simulation_step_s=timing['step_s'])
                    Accounting.from_mapping(world['metrics']['accounting'])
                    estimates = estimate_candidates(world['decision']['observation'], AnalyticalConfig(**study['spec']['analytical_config']))
                    estimator_hash = digest({'version': estimates['version'], 'config': estimates['config']})
                    if estimator_hash != digest(study['protocol']['analytical_estimator']):
                        raise RuntimeError('Analytical estimator differs from frozen protocol')
                    row = {**identity, **world['metrics'], 'audit_status': 'passed', 'priority_deadline_audit': 'passed',
                        'simulator_runtime_s': world['metrics']['runtime_s'], 'runtime_s': time.perf_counter()-before,
                        'sumo_version': world['sumo_version'], 'dependencies': study['dependencies'],
                        'request_plan': world['decision']['request_plan'], 'observation': world['decision']['observation'],
                        'analytical_config_sha256': estimator_hash,
                        'analytical_cost_s': next((score['analytical_cost_s'] for score in estimates['scores'] if score['lead_s'] == item['lead_s']), None),
                        'raw_world_directory': item['directory'], 'signal_audit_input_sha256': signal_hash}
                    item['state'] = 'audited'
                except Exception as error:
                    audit_failed = isinstance(error, PilotAuditError)
                    metrics = world.get('metrics', {}) if world is not None else {}
                    if world is None:
                        try:
                            metrics = read_json(world_dir / 'failure.json')
                        except (OSError, ValueError):
                            metrics = {}
                    row = {**identity, 'status': 'invalid' if audit_failed else 'infrastructure_error',
                        'audit_status': 'failed' if audit_failed else 'not_eligible',
                        'validity_reasons': list(dict.fromkeys([*metrics.get('validity_reasons', []), *(['evidence_audit_failed'] if audit_failed else [])])),
                        'failure_reason': str(error), 'accounting_unverified': True,
                        'accounting': metrics.get('accounting', {'scheduled': scheduled, 'inserted': 0, 'completed': 0, 'running': 0, 'not_inserted': scheduled}),
                        'ambulance_journey_s': None, 'civilian_mean_excess_s': None,
                        'horizon_s': timing['horizon_s'], 'drain_end_s': timing['horizon_s']+timing['drain_s'],
                        'request_plan': None, 'observation': None, 'analytical_cost_s': None,
                        'runtime_s': time.perf_counter()-before, 'raw_world_directory': item['directory'], 'signal_audit_input_sha256': signal_hash}
                    item['state'] = 'audit_failed' if audit_failed else 'infrastructure_failed'
                world = None
                rows.append(row)
                episode_rows.append(row)
                save()
                if item['state'] != 'audited':
                    raise RuntimeError(f"Collection stopped after {item['state']}: {item['directory']}; raw evidence retained")
                if time.perf_counter()-start >= split_budget_s:
                    raise RuntimeError('Frozen wall-time budget exhausted after world; remaining inventory stays unattempted')
            ordinary = next(row for row in episode_rows if row['policy'] == 'ordinary')
            for row in episode_rows:
                verify_pair(row, ordinary)
                row['recovery_window_s'] = timing['recovery_window_s']
                row['recovery_excess_queue_area_vehicle_s'] = excess_queue_area(row['queue_samples'], ordinary['queue_samples'], *timing['recovery_window_s'])
                row['queue_scope'] = study['protocol']['queue_scope']
            save()
        assert_study_runtime(study)
        assert_saved_inputs(root, study)
        manifest['status'] = 'completed'
        return manifest
    except Exception as error:
        manifest.update(status='stopped', reason=str(error))
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', required=True, type=Path)
    parser.add_argument('--split', required=True, choices=('train', 'validation'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = collect_split(args.study, args.split, args.output)
    print(json.dumps({key: result[key] for key in ('status', 'split', 'recorded_worlds', 'unattempted_worlds', 'runtime_total_s')}, indent=2))


if __name__ == '__main__':
    main()
