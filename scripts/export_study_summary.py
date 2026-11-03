"""Publish a small read-only summary of an actually verified released study.

Run on Omen after report creation. This script never fits, selects, releases or
simulates. Verification imports come from the explicitly pinned checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_no_overlap(output: Path, protected_directories: tuple[Path, ...]) -> None:
    for protected in protected_directories:
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Summary output cannot overlap original evidence or frozen selection')


def optional_mean(records: list[dict], field: str) -> float | None:
    values = [record[field] for record in records if record[field] is not None]
    return mean(values) if values else None


def project_summary(study_envelope: dict, report_envelope: dict,
                    selection_envelope: dict, release_envelope: dict,
                    artifacts: list[dict]) -> dict:
    """Project verified evidence. The CLI performs full raw verification first."""
    study = study_envelope['study']
    report = report_envelope['report']
    selection = selection_envelope['selection']
    release = release_envelope['release']
    mode = report['mode']
    if mode not in {'learned', 'baseline_only'} or report['status'] != 'audited_released_test_evidence':
        raise ValueError('Only a completed, explicitly released report can be published')
    if report['automatic_benefit_claim'] is not False:
        raise ValueError('A study summary cannot create an automatic benefit claim')
    if (report['study_sha256'] != study_envelope['sha256'] or
            report['selection_sha256'] != selection_envelope['sha256'] or
            report['release_sha256'] != release_envelope['sha256'] or
            selection['source'] != study['source'] or report['source'] != study['source']):
        raise ValueError('Study, report, selection and release identities differ')
    expected_ids = ['learned-vs-fixed', 'learned-vs-analytical'] if mode == 'learned' else ['analytical-vs-fixed']
    if set(report['comparisons']) != set(expected_ids):
        raise ValueError('The report lacks its full frozen comparator set')
    split_counts = Counter(episode['split'] for episode in study['episodes'])
    test_groups = {episode['demand_group_id'] for episode in study['episodes'] if episode['split'] == 'test'}
    test_worlds = sum(report['all_world_status_counts'].values())
    if test_worlds != split_counts['test'] * 7:
        raise ValueError('Reported world count differs from the complete seven-world inventory')
    fixed_lead = selection['validation_fixed_selection']['lead_s']
    comparisons = []
    status_names = ('completed', 'censored', 'invalid', 'infrastructure_error')
    for key in expected_ids:
        comparison = report['comparisons'][key]
        if (comparison['episodes'] != split_counts['test'] or
                comparison['demand_groups'] != len(test_groups) or
                len(comparison['records']) != split_counts['test']):
            raise ValueError('Comparison omits declared test episodes or demand groups')
        uncertainty = comparison['uncertainty']
        if any(set(comparison[field]) - set(status_names) for field in ('selected_status_counts', 'comparator_status_counts')):
            raise ValueError('Unknown selected/comparator status')
        if (sum(comparison['selected_status_counts'].values()) != comparison['episodes'] or
                sum(comparison['comparator_status_counts'].values()) != comparison['episodes']):
            raise ValueError('Selected/comparator status inventories do not reconcile')
        if any(comparison[field].get('infrastructure_error', 0) for field in ('selected_status_counts', 'comparator_status_counts')):
            raise ValueError('Infrastructure failures cannot become a published complete study')
        comparisons.append({
            'id': key,
            'selected_label': 'Residual tree' if mode == 'learned' else 'Analytical',
            'comparator_label': 'Analytical' if key.endswith('vs-analytical') else f'Fixed · {fixed_lead:g} s',
            **{field: comparison[field] for field in (
                'episodes', 'demand_groups', 'paired_feasible_episodes', 'selected_failures',
                'comparator_failures', 'changed_action_rate')},
            **{field: {status: comparison[field].get(status, 0) for status in status_names}
               for field in ('selected_status_counts', 'comparator_status_counts')},
            'mean_delta_j_s': comparison['conditional_mean_delta_j_s'],
            'interval_95_j_s': uncertainty['interval'],
            'interval_groups': uncertainty['groups'],
            'interval_reason': uncertainty.get('reason'),
            'mean_delta_ambulance_s': optional_mean(comparison['records'], 'conditional_delta_ambulance_s'),
            'mean_delta_civilian_s': optional_mean(comparison['records'], 'civilian_delta_s'),
        })
    by_kind = {artifact['kind']: artifact for artifact in artifacts}
    model_sha = release['selected_model_sha256']
    if (mode == 'learned') != (model_sha is not None):
        raise ValueError('Model identity does not match the released study mode')
    if model_sha is not None and by_kind.get('model', {}).get('sha256') != model_sha:
        raise ValueError('Published model bytes differ from the pre-test frozen model')
    return {
        'schema': 'afterlight.study-summary.v1',
        'status': report['status'], 'mode': mode,
        'scope': 'offline_cached_candidate_selection',
        'automatic_benefit_claim': False,
        'counts': {'train': split_counts['train'], 'validation': split_counts['validation'],
                   'test': split_counts['test'], 'test_worlds': test_worlds,
                   'test_demand_groups': len(test_groups)},
        'holdouts': {'regimes': study['protocol']['heldout_regimes'],
                     'route_families': study['protocol']['heldout_route_families']},
        'objective': {'civilian_weight': study['protocol']['civilian_weight'],
                      'definition': 'Ambulance journey seconds + all-demand mean civilian excess seconds'},
        'fixed_lead_s': fixed_lead,
        'comparisons': comparisons,
        'provenance': {
            'source_commit': study['source']['source_commit'],
            'source_code_sha256': study['source']['source_code_sha256'],
            **{key: report[key] for key in ('study_sha256', 'protocol_sha256', 'selection_sha256',
                                          'release_sha256', 'test_attempt_sha256')},
            'report_sha256': report_envelope['sha256'],
            'report_file_sha256': by_kind['report']['sha256'],
            'model_sha256': model_sha,
        },
        'artifacts': artifacts,
    }


def write_json_new(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True, help='Clean pinned scientific worktree')
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--collection', type=Path, required=True, help='Original single released test collection')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory within pinned local-runtime')
    args = parser.parse_args()
    checkout = args.checkout.resolve(strict=True)
    sys.path.insert(0, str(checkout))
    from evaluation.study_manifest import load_study, read_json, assert_study_runtime
    from evaluation.study_reporting import verify_report_artifacts, verify_released_test_collection

    def local(path: Path) -> Path:
        resolved = path.resolve() if path.is_absolute() else (checkout/path).resolve()
        if resolved == checkout/'local-runtime' or not resolved.is_relative_to((checkout/'local-runtime').resolve()):
            raise ValueError('Scientific inputs/outputs must stay inside the pinned local-runtime')
        return resolved

    study_dir, collection, report_dir, output = map(local, (args.study, args.collection, args.report, args.output))
    assert_no_overlap(output, (study_dir, collection, report_dir))
    # Verification is read-only: deterministic report/interval recomputation,
    # exact raw inventories and all source/selector/release bindings are checked.
    report = verify_report_artifacts(study_dir, collection, report_dir)
    verified = verify_released_test_collection(study_dir, collection)
    context = verified['release_context']
    selection_dir = context['selection_directory']
    assert_no_overlap(output, (selection_dir,))
    study = load_study(study_dir, require_frozen=True, verify_inputs=True)
    selection = read_json(selection_dir/'selection.json')
    sources = {
        'report': report_dir/'report.json', 'study': study_dir/'study.json',
        'protocol': study_dir/'frozen-protocol.json', 'selection': selection_dir/'selection.json',
        'release': study_dir/'test-release.json', 'fixed_selector': selection_dir/'fixed-selector.json',
        'analytical_selector': selection_dir/'analytical-selector.json',
    }
    if report['report']['mode'] == 'learned':
        sources['model'] = selection_dir/'model.json'
    payloads = {}
    artifacts = []
    for kind, source in sources.items():
        if source.stat().st_size > 4*1024*1024:
            raise ValueError('Small public proof companion exceeds its 4 MiB bound')
        data = source.read_bytes()
        filename = kind.replace('_', '-')+'.json'
        payloads[filename] = data
        artifacts.append({'kind': kind, 'url': filename,
                          'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    verified_contents = {
        'report': report, 'study': study, 'selection': selection, 'release': context['release'],
        'protocol': {'sha256': report['report']['protocol_sha256'], 'protocol': study['study']['protocol']},
    }
    for kind, expected in verified_contents.items():
        if json.loads(payloads[kind+'.json']) != expected:
            raise ValueError('Proof companion changed after verification: '+kind)
    release = context['release']['release']
    if hashlib.sha256(payloads['selection.json']).hexdigest() != release['selection_file_sha256']:
        raise ValueError('Copied selection bytes differ from the pre-test release')
    if hashlib.sha256(payloads['release.json']).hexdigest() != context['release_file_sha256']:
        raise ValueError('Copied release bytes differ from verified report evidence')
    for kind in ('fixed_selector', 'analytical_selector', 'model'):
        if kind in sources:
            filename = kind.replace('_', '-')+'.json'
            expected = release['selection_artifacts_sha256'][sources[kind].name]
            if hashlib.sha256(payloads[filename]).hexdigest() != expected:
                raise ValueError('Copied selector/model bytes differ from the pre-test release')
    summary = project_summary(study, report, selection, context['release'], artifacts)
    # All publication bytes are derived before reserving a fresh destination.
    # Original scientific source, outcome files and existing reports stay intact.
    output.mkdir(parents=True, exist_ok=False)
    try:
        for filename, data in payloads.items():
            with (output/filename).open('xb') as stream:
                stream.write(data)
        write_json_new(output/'summary.json', summary)
        if (output/'summary.json').stat().st_size > 1024*1024:
            raise ValueError('Public study summary exceeds its 1 MiB interface bound')
        manifest = {'schema': 'afterlight.study-summary-manifest.v1', 'url': 'summary.json',
                    'sha256': file_sha256(output/'summary.json'), 'bytes': (output/'summary.json').stat().st_size}
        write_json_new(output/'manifest.json', manifest)
        if (output/'manifest.json').stat().st_size > 16*1024:
            raise ValueError('Public study manifest exceeds its 16 KiB interface bound')
        assert_study_runtime(study['study'])
        for kind, source in sources.items():
            artifact = next(item for item in artifacts if item['kind'] == kind)
            if file_sha256(source) != artifact['sha256'] or file_sha256(output/artifact['url']) != artifact['sha256']:
                raise ValueError('Original or copied proof companion changed during export')
        print(json.dumps({'status': 'verified_read_only_study_summary', **manifest,
                          'mode': summary['mode'], 'counts': summary['counts']}, indent=2))
    except Exception as error:
        write_json_new(output/'export-failure.json', {'status': 'failed_not_publishable', 'reason': str(error)})
        raise


if __name__ == '__main__':
    main()
