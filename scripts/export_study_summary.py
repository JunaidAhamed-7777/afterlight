"""Publish a small read-only summary of an actually verified released study.

Run on Omen after report creation. This script never fits, selects, releases or
simulates. Verification imports come from the explicitly pinned checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import lzma
from pathlib import Path
from statistics import mean
import sys

GRID_DECODED_LIMIT = 128*1024*1024
GRID_TRANSFER_LIMIT = 4*1024*1024
GRID_DECODER_MEMORY_LIMIT = 128*1024*1024


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_no_overlap(output: Path, protected_directories: tuple[Path, ...]) -> None:
    for protected in protected_directories:
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Summary output cannot overlap original evidence or frozen selection')


def compressed_grid(source: Path, *, kind: str, split: str, url: str,
                    expected_sha256: str) -> tuple[bytes, dict]:
    """Lossless original-byte publication; no JSON rewriting or sample thinning."""
    if source.is_symlink() or source.stat().st_size > GRID_DECODED_LIMIT:
        raise ValueError('Original scalar grid exceeds its 128 MiB bound or is a symlink')
    raw = source.read_bytes()
    if len(raw) > GRID_DECODED_LIMIT or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Original scalar grid differs from its pre-test/report byte identity')
    packed = lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6)
    if len(packed) > GRID_TRANSFER_LIMIT:
        raise ValueError('Lossless scalar grid exceeds its 4 MiB physical transfer bound')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=GRID_DECODER_MEMORY_LIMIT)
    restored = decoder.decompress(packed, max_length=GRID_DECODED_LIMIT+1)
    if not decoder.eof or decoder.unused_data or restored != raw:
        raise ValueError('Lossless original grid failed bounded single-stream roundtrip')
    return packed, {'kind': kind, 'split': split, 'source_file': source.name, 'url': url,
                    'encoding': 'xz', 'sha256': expected_sha256, 'bytes': len(raw),
                    'transfer_sha256': hashlib.sha256(packed).hexdigest(), 'transfer_bytes': len(packed)}


def optional_mean(records: list[dict], field: str) -> float | None:
    values = [record[field] for record in records if record[field] is not None]
    return mean(values) if values else None


def paired_records_csv(study_envelope: dict, report_envelope: dict) -> bytes:
    """Human-readable case records; unavailable targets remain blank, never zero."""
    episodes = {item['episode_id']: item for item in study_envelope['study']['episodes'] if item['split'] == 'test'}
    buffer = io.StringIO(newline='')
    fields = ['comparison', 'case_id', 'seed', 'regime', 'route_family', 'pickup_id', 'hospital_id',
              'episode_id', 'demand_group_id', 'selected_lead_s', 'comparator_lead_s',
              'selected_status', 'comparator_status', 'selected_infeasible', 'comparator_infeasible',
              'selected_j_s', 'comparator_j_s', 'paired_delta_j_s', 'delta_ambulance_s',
              'delta_civilian_s', 'delta_recovery_vehicle_s']
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    row_count = 0
    comparisons = report_envelope['report']['comparisons']
    for comparison, content in comparisons.items():
        seen = set()
        for record in content['records']:
            episode = episodes[record['episode_id']]
            if record['episode_id'] in seen or record['demand_group_id'] != episode['demand_group_id']:
                raise ValueError('CSV record identity differs from the frozen test inventory')
            seen.add(record['episode_id'])
            row = {'comparison': comparison,
                   **{key: episode[key] for key in ('case_id', 'seed', 'regime', 'route_family', 'pickup_id', 'hospital_id')},
                   **{key: record[key] for key in ('episode_id', 'demand_group_id', 'selected_lead_s', 'comparator_lead_s',
                       'selected_status', 'comparator_status', 'selected_infeasible', 'comparator_infeasible',
                       'selected_j_s', 'comparator_j_s', 'paired_delta_j_s')},
                   'delta_ambulance_s': record['conditional_delta_ambulance_s'],
                   'delta_civilian_s': record['civilian_delta_s'],
                   'delta_recovery_vehicle_s': record['conditional_delta_recovery_vehicle_s']}
            writer.writerow(row)
            row_count += 1
        if seen != set(episodes):
            raise ValueError('CSV comparison omits declared test episodes')
    if row_count != len(episodes)*len(comparisons):
        raise ValueError('CSV record count does not reconcile')
    return buffer.getvalue().encode('utf-8')


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
    with path.open('xb') as stream:
        stream.write(json_bytes(value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True, help='Clean pinned scientific worktree')
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--collection', type=Path, required=True, help='Original single released test collection')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--train', type=Path, required=True, help='Original complete training collection')
    parser.add_argument('--validation', type=Path, required=True, help='Original complete validation collection')
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory within pinned local-runtime')
    parser.add_argument('--max-pack-bytes', type=int, default=4*1024*1024,
                        help='Physical proof-pack ceiling; default 4 MiB, never omit required rows to fit')
    args = parser.parse_args()
    checkout = args.checkout.resolve(strict=True)
    sys.path.insert(0, str(checkout))
    from evaluation.study_manifest import load_study, read_json, assert_study_runtime
    from evaluation.study_reporting import verify_report_artifacts, verify_released_test_collection, _contained

    def local(path: Path) -> Path:
        resolved = path.resolve() if path.is_absolute() else (checkout/path).resolve()
        if resolved == checkout/'local-runtime' or not resolved.is_relative_to((checkout/'local-runtime').resolve()):
            raise ValueError('Scientific inputs/outputs must stay inside the pinned local-runtime')
        return resolved

    study_dir, collection, report_dir, output = map(local, (args.study, args.collection, args.report, args.output))
    train_dir, validation_dir = map(local, (args.train, args.validation))
    assert_no_overlap(output, (study_dir, collection, report_dir, train_dir, validation_dir))
    if not 0 < args.max_pack_bytes <= 32*1024*1024:
        raise ValueError('An explicit positive proof-pack bound of at most 32 MiB is required')
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
        sources['learned_selector'] = selection_dir/'learned-selector.json'
        sources['comparison_learned_vs_fixed'] = selection_dir/'learned-vs-fixed.json'
        sources['comparison_learned_vs_analytical'] = selection_dir/'learned-vs-analytical.json'
    else:
        sources['comparison_analytical_vs_fixed'] = selection_dir/'analytical-vs-fixed.json'
    payloads = {}
    artifacts = []
    filenames = {}
    for kind, source in sources.items():
        if source.stat().st_size > 4*1024*1024:
            raise ValueError('Small public proof companion exceeds its 4 MiB bound')
        data = source.read_bytes()
        filename = {'protocol': 'protocol.json', 'release': 'release.json'}.get(kind, source.name)
        filenames[kind] = filename
        payloads[filename] = data
        artifacts.append({'kind': kind, 'url': filename,
                          'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    verified_contents = {
        'report': report, 'study': study, 'selection': selection, 'release': context['release'],
        'protocol': {'sha256': report['report']['protocol_sha256'], 'protocol': study['study']['protocol']},
    }
    for kind, expected in verified_contents.items():
        if json.loads(payloads[filenames[kind]]) != expected:
            raise ValueError('Proof companion changed after verification: '+kind)
    release = context['release']['release']
    if hashlib.sha256(payloads['selection.json']).hexdigest() != release['selection_file_sha256']:
        raise ValueError('Copied selection bytes differ from the pre-test release')
    if hashlib.sha256(payloads['release.json']).hexdigest() != context['release_file_sha256']:
        raise ValueError('Copied release bytes differ from verified report evidence')
    for kind in set(sources) - set(verified_contents):
        if kind in sources:
            filename = filenames[kind]
            expected = release['selection_artifacts_sha256'][sources[kind].name]
            if hashlib.sha256(payloads[filename]).hexdigest() != expected:
                raise ValueError('Copied selector/model bytes differ from the pre-test release')
            if kind.startswith('comparison_') and expected != release['comparison_artifacts_sha256'][sources[kind].name]:
                raise ValueError('Copied comparison envelope differs from the pre-test release')
    grid_specs = [
        ('train_candidates', 'train', _contained(train_dir, 'candidate-outcomes.json'),
         'train-candidates.json.xz', selection['selection']['collections']['train']['candidate-outcomes.json']),
        ('validation_candidates', 'validation', _contained(validation_dir, 'candidate-outcomes.json'),
         'validation-candidates.json.xz', selection['selection']['collections']['validation']['candidate-outcomes.json']),
        ('test_candidates', 'test', _contained(collection, 'candidate-outcomes.json'),
         'test-candidates.json.xz', report['report']['collection_files_sha256']['candidate-outcomes.json']),
        ('test_outcomes', 'test', _contained(collection, 'outcomes.json'),
         'test-outcomes.json.xz', report['report']['collection_files_sha256']['outcomes.json']),
    ]
    grids = []
    for kind, split, source, url, expected in grid_specs:
        packed, entry = compressed_grid(source, kind=kind, split=split, url=url, expected_sha256=expected)
        payloads[url] = packed
        grids.append(entry)
        artifacts.append({'kind': kind, 'url': url, 'sha256': entry['transfer_sha256'], 'bytes': len(packed)})
    reproduction = {
        'schema': 'afterlight.study-reproduction.v1',
        **{key: report['report'][key] for key in ('study_sha256', 'protocol_sha256', 'selection_sha256', 'release_sha256')},
        'report_sha256': report['sha256'],
        'decoded_limit_bytes': GRID_DECODED_LIMIT, 'transfer_limit_bytes': GRID_TRANSFER_LIMIT,
        'decoder_memory_limit_bytes': GRID_DECODER_MEMORY_LIMIT, 'files': grids,
    }
    reproduction_bytes = json_bytes(reproduction)
    payloads['reproduction.json'] = reproduction_bytes
    artifacts.append({'kind': 'reproduction', 'url': 'reproduction.json',
                      'sha256': hashlib.sha256(reproduction_bytes).hexdigest(), 'bytes': len(reproduction_bytes)})
    csv_bytes = paired_records_csv(study, report)
    payloads['paired-records.csv'] = csv_bytes
    artifacts.append({'kind': 'paired_records', 'url': 'paired-records.csv',
                      'sha256': hashlib.sha256(csv_bytes).hexdigest(), 'bytes': len(csv_bytes)})
    summary = project_summary(study, report, selection, context['release'], artifacts)
    summary_bytes = json_bytes(summary)
    if len(summary_bytes) > 1024*1024:
        raise ValueError('Public study summary exceeds its 1 MiB interface bound')
    manifest = {'schema': 'afterlight.study-summary-manifest.v1', 'url': 'summary.json',
                'sha256': hashlib.sha256(summary_bytes).hexdigest(), 'bytes': len(summary_bytes)}
    manifest_bytes = json_bytes(manifest)
    if len(manifest_bytes) > 16*1024:
        raise ValueError('Public study manifest exceeds its 16 KiB interface bound')
    total_pack_bytes = sum(map(len, payloads.values()))+len(summary_bytes)+len(manifest_bytes)
    if total_pack_bytes > args.max_pack_bytes:
        raise ValueError('Complete proof pack exceeds its physical byte budget; keep all rows and revise media budget explicitly')
    # All publication bytes are derived before reserving a fresh destination.
    # Original scientific source, outcome files and existing reports stay intact.
    output.mkdir(parents=True, exist_ok=False)
    try:
        for filename, data in payloads.items():
            with (output/filename).open('xb') as stream:
                stream.write(data)
        with (output/'summary.json').open('xb') as stream:
            stream.write(summary_bytes)
        assert_study_runtime(study['study'])
        for kind, source in sources.items():
            artifact = next(item for item in artifacts if item['kind'] == kind)
            if file_sha256(source) != artifact['sha256'] or file_sha256(output/artifact['url']) != artifact['sha256']:
                raise ValueError('Original or copied proof companion changed during export')
        if any(file_sha256(output/item['url']) != item['sha256'] for item in artifacts):
            raise ValueError('A generated publication artifact changed during export')
        if any(file_sha256(source) != expected for _, _, source, _, expected in grid_specs):
            raise ValueError('An original scalar grid changed during export')
        if file_sha256(output/'summary.json') != manifest['sha256']:
            raise ValueError('Generated summary changed during export')
        # Completion marker is installed only after every original/copy/grid
        # verification succeeds. Publishing callers still check process success.
        with (output/'manifest.json').open('xb') as stream:
            stream.write(manifest_bytes)
        print(json.dumps({'status': 'verified_read_only_study_summary', **manifest,
                          'mode': summary['mode'], 'counts': summary['counts'],
                          'total_pack_bytes': total_pack_bytes,
                          'decoded_grid_bytes': sum(item['bytes'] for item in grids)}, indent=2))
    except Exception as error:
        write_json_new(output/'export-failure.json', {'status': 'failed_not_publishable', 'reason': str(error)})
        raise


if __name__ == '__main__':
    main()
