"""Verify a genuinely released public Study pack using bounded HTTP GETs only.

No local scientific outcome directory is read. Nothing runs at import time.
The caller must supply the exact manifest SHA from the completed publication.
This checks public hashes/accounting/arithmetic, not private raw SUMO evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from importlib.machinery import SourceFileLoader
import io
import json
import lzma
import math
from pathlib import Path
from random import Random
import re
from statistics import mean
import sys
from types import ModuleType
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MANIFEST_LIMIT = 16 * 1024
SUMMARY_LIMIT = 1024 * 1024
COMPANION_LIMIT = 4 * 1024 * 1024
GRID_LIMIT = 128 * 1024 * 1024
GRID_KINDS = {'train_candidates', 'validation_candidates', 'test_candidates', 'test_outcomes'}
STATUSES = ('completed', 'censored', 'invalid', 'infrastructure_error')
SHA = re.compile(r'[a-f0-9]{64}\Z')
LOCAL_PATH = re.compile(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*(?:/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)*\Z')
# Dependency order keeps every project import inside the verified module set.
PURE_HELPER_FILES = {
    'evaluation': 'evaluation/__init__.py',
    'evaluation.metrics': 'evaluation/metrics.py',
    'evaluation.splits': 'evaluation/splits.py',
    'evaluation.protocol': 'evaluation/protocol.py',
    'models': 'models/__init__.py',
    'models.residual': 'models/residual.py',
    'models.analytical': 'models/analytical.py',
    'evaluation.selectors': 'evaluation/selectors.py',
    'evaluation.comparison': 'evaluation/comparison.py',
}
ANALYSIS_ARTIFACTS = {
    'analysis_amendment': 'analysis-amendment.json',
    'analysis_verifier_source': 'afterlight_analysis_amendment_v1.py',
    'analysis_binding_source': 'afterlight_analysis_binding_v1.py',
    'analysis_entrypoint_source': 'run_analysis_amendment.py',
    'analysis_diff': 'analysis-amendment.patch',
    'analysis_failure_log': 'analysis-failure.txt',
    'analysis_failure_journal': 'analysis-failed-selection-journal.json',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def strict_json(data: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate published JSON key: ' + key)
            result[key] = value
        return result
    def nonfinite(value): raise ValueError('Nonfinite published JSON value: ' + value)
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number): nonfinite(value)
        return number
    return json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite_float)


def bound_scientific_modules(source_files, *, project=None):
    """Load exact released helper bytes, rejecting cached or path-shadowed code.

    Only source files are opened. No experiment, fitting function, HTTP request,
    or outcome input is invoked. The optional root supports isolated guard tests.
    """
    project = (Path(__file__).resolve().parents[2] if project is None else Path(project)).resolve(strict=True)
    paths = {}; sources = {}
    for name, relative in PURE_HELPER_FILES.items():
        path = (project / relative).resolve(strict=True)
        expected_hash = source_files[relative]
        if not path.is_relative_to(project) or not isinstance(expected_hash, str) or not SHA.fullmatch(expected_hash):
            raise ValueError('Invalid released scientific helper binding: ' + relative)
        raw = path.read_bytes()
        if sha(raw) != expected_hash: raise ValueError('Scientific helper bytes differ from the released source: ' + relative)
        paths[name] = path; sources[name] = raw

    def scientific_name(name):
        return name in ('models', 'evaluation') or name.startswith(('models.', 'evaluation.'))

    def check_origin(name, module):
        path = paths[name]
        spec = getattr(module, '__spec__', None)
        try:
            file_path = Path(module.__file__).resolve(strict=True)
            spec_path = Path(spec.origin).resolve(strict=True)
            loader_path = Path(spec.loader.path).resolve(strict=True)
            valid = (isinstance(module, ModuleType) and module.__name__ == name and spec.name == name and
                     isinstance(spec.loader, SourceFileLoader) and file_path == spec_path == loader_path == path and
                     sha(file_path.read_bytes()) == source_files[PURE_HELPER_FILES[name]])
            if path.name == '__init__.py':
                valid = valid and ([Path(p).resolve(strict=True) for p in module.__path__] == [path.parent] and
                                   [Path(p).resolve(strict=True) for p in spec.submodule_search_locations] == [path.parent])
        except (AttributeError, TypeError, ValueError, OSError):
            valid = False
        if not valid: raise ValueError('Scientific helper import origin/hash mismatch: ' + name)

    cached = {name: module for name, module in sys.modules.copy().items() if scientific_name(name)}
    if cached.keys() - PURE_HELPER_FILES.keys(): raise ValueError('Unexpected scientific helper already imported')
    for name, module in cached.items(): check_origin(name, module)
    loaded = {}
    try:
        # Compile verified bytes directly: ordinary sys.path resolution and
        # timestamp-based .pyc reuse cannot substitute another implementation.
        for name, path in paths.items():
            spec = spec_from_file_location(name, path)
            if spec is None or spec.loader is None: raise ValueError('Cannot bind scientific helper: ' + name)
            module = module_from_spec(spec)
            sys.modules[name] = module
            if '.' in name:
                parent, child = name.rsplit('.', 1)
                setattr(sys.modules[parent], child, module)
            exec(compile(sources[name], str(path), 'exec', dont_inherit=True), module.__dict__)
            check_origin(name, module)
            loaded[name] = module
        actual_names = {name for name in sys.modules.copy() if scientific_name(name)}
        if actual_names != set(PURE_HELPER_FILES): raise ValueError('Unexpected scientific helper imported during binding')
        for name, module in loaded.items():
            if sys.modules[name] is not module: raise ValueError('Scientific helper cache changed during binding: ' + name)
            check_origin(name, module)
        return loaded
    except BaseException:
        # A failed guard must not leave partially initialized project packages.
        for name in list(sys.modules):
            if scientific_name(name): sys.modules.pop(name)
        sys.modules.update(cached)
        raise


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def bounded_get(url: str, limit: int) -> bytes:
    request = Request(url, headers={'Accept': 'application/json, text/csv;q=0.9, */*;q=0.1', 'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        assert response.status == 200, ('Released publication must return HTTP200', url, response.status)
        declared = response.headers.get('Content-Length')
        if declared is not None: assert int(declared) <= limit, ('Publication exceeds transport bound', url)
        data = response.read(limit + 1)
        assert len(data) <= limit, ('Publication exceeds transport bound', url)
        encoding = response.headers.get('Content-Encoding', 'identity').lower()
        if encoding == 'gzip':
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as decoder: data = decoder.read(limit + 1)
        else: assert encoding in ('', 'identity'), ('Unexpected forced content encoding', encoding)
        assert len(data) <= limit, ('Publication exceeds decoded bound', url)
        return data


def local_url(relative: str, summary_url: str) -> str:
    assert isinstance(relative, str) and LOCAL_PATH.fullmatch(relative), ('Unsafe public artifact path', relative)
    result = urljoin(summary_url, relative)
    assert urlsplit(result).netloc == urlsplit(summary_url).netloc
    return result


def close(actual, expected, label):
    if actual is None or expected is None:
        assert actual is expected, (label, actual, expected)
    else:
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual), (label, actual)
        assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10), (label, actual, expected)


def envelope(value, key, schema):
    assert isinstance(value, dict) and set(value) == {'sha256', key}, ('Invalid public envelope', key)
    content = value[key]
    assert isinstance(content, dict) and content.get('schema') == schema, ('Invalid public schema', key)
    assert SHA.fullmatch(value['sha256']) and value['sha256'] == canonical_sha(content), ('Public envelope digest mismatch', key)
    return content


def interval_from_records(records):
    groups = defaultdict(list)
    for record in records:
        value = record['paired_delta_j_s']
        if value is not None:
            assert math.isfinite(value)
            groups[record['demand_group_id']].append(value)
    if len(groups) < 10: return None, len(groups)
    names = sorted(groups)
    rng = Random(0)
    means = []
    for _ in range(2000):
        selected = [names[rng.randrange(len(names))] for _ in names]
        means.append(mean(value for name in selected for value in groups[name]))
    means.sort()
    return [means[int(.025 * 1999)], means[int(.975 * 1999)]], len(names)


def verify_analysis_amendment(documents, raw, artifacts):
    """Bind the explicit pre-test audit correction without executing its code."""
    selection = documents['selection']['selection']; report = documents['report']['report']
    present = set(ANALYSIS_ARTIFACTS) & artifacts.keys()
    declared = 'analysis_amendment' in selection or 'analysis_amendment' in report
    if not declared and not present: return {'present': False}
    assert present == set(ANALYSIS_ARTIFACTS), 'Amended analysis requires every declared public proof companion'
    for kind, filename in ANALYSIS_ARTIFACTS.items():
        artifact = artifacts[kind]
        assert artifact['url'] == filename, ('Unexpected analysis companion URL', kind)
        assert len(raw[kind]) == artifact['bytes'] <= COMPANION_LIMIT and sha(raw[kind]) == artifact['sha256'], ('Analysis companion bytes/hash mismatch', kind)
    descriptor = documents['analysis_amendment']
    assert canonical_sha(strict_json(raw['analysis_amendment'])) == canonical_sha(descriptor), 'Descriptor object differs from original published bytes'
    amendment = envelope(descriptor, 'amendment', 'afterlight.analysis-amendment.v1')
    assert set(amendment) == {'schema', 'id', 'created_utc', 'original_study_sha256', 'original_protocol_sha256',
                              'original_source', 'frozen_analytical_estimator', 'frozen_analytical_estimator_sha256',
                              'correction', 'unchanged_design', 'failed_attempt', 'analysis_files'}
    assert amendment['id'] == 'frozen-estimator-config-v1'
    study = documents['study']['study']; protocol = documents['protocol']['protocol']
    assert amendment['original_study_sha256'] == documents['study']['sha256']
    assert amendment['original_protocol_sha256'] == documents['protocol']['sha256']
    assert canonical_sha(amendment['original_source']) == canonical_sha(study['source']), 'Analysis amendment changed original simulation provenance'
    estimator_hash = canonical_sha(protocol['analytical_estimator'])
    assert amendment['frozen_analytical_estimator_sha256'] == estimator_hash
    # Numeric equality is insufficient here: JSON int1 and float1.0 deliberately
    # retain different frozen identities even when Python compares them equal.
    assert canonical_sha(amendment['frozen_analytical_estimator']) == estimator_hash, 'Analysis amendment changed exact frozen estimator representation'
    assert isinstance(amendment['correction'], str) and amendment['correction'].strip()
    unchanged = amendment['unchanged_design']
    assert isinstance(unchanged, list) and unchanged and all(isinstance(item, str) and item.strip() for item in unchanged)
    assert len(set(unchanged)) == len(unchanged)

    def file_binding(value, kind, original=None):
        expected_keys = {'filename', 'sha256'} | ({'original_path', 'original_sha256'} if original else set())
        assert isinstance(value, dict) and set(value) == expected_keys
        assert isinstance(value['filename'], str) and LOCAL_PATH.fullmatch(value['filename']) and '/' not in value['filename']
        assert value['filename'] == ANALYSIS_ARTIFACTS[kind], ('Descriptor filename differs from public companion', kind)
        assert SHA.fullmatch(value['sha256']) and value['sha256'] == sha(raw[kind]), ('Descriptor companion binding mismatch', kind)
        if original:
            assert value['original_path'] == original
            assert value['original_sha256'] == study['source']['source_files'][original], ('Analysis amendment original source mismatch', original)

    def instant(value):
        assert isinstance(value, str)
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        assert parsed.utcoffset() is not None, 'Analysis provenance timestamps require explicit time zones'
        return parsed

    failed = amendment['failed_attempt']
    assert isinstance(failed, dict) and set(failed) == {'state', 'model_fit_reached', 'journal', 'log'}
    assert failed['state'] == 'verification_failed_before_model_fit' and failed['model_fit_reached'] is False
    # The descriptor uses the explicit public aliases even for original failed
    # log/journal copies; exact hashes preserve the original evidence bytes.
    file_binding(failed['journal'], 'analysis_failure_journal')
    file_binding(failed['log'], 'analysis_failure_log')
    journal = strict_json(raw['analysis_failure_journal'])
    assert isinstance(journal, dict) and journal.get('schema') == 'afterlight.selection-dependency-watcher.v1'
    assert journal.get('state') == 'watcher_stopped_no_test_release', 'Failure journal contradicts the declared stopped attempt'
    assert type(journal.get('return_code')) is int and journal['return_code'] == 1, 'Failure journal contradicts the declared unsuccessful selection'
    assert type(journal.get('automatic_retries')) is int and journal['automatic_retries'] == 0, 'Failure journal records an undeclared retry'
    for marker in ('model_fit_reached', 'fit_completed'):
        if marker in journal: assert journal[marker] is False, 'Failure journal contradicts the declared pre-fit failure'
    assert (instant(journal['created_utc']) <= instant(journal['invoked_utc']) <= instant(journal['stopped_utc']) <= instant(amendment['created_utc'])), 'Failure journal does not precede the frozen amendment'
    files = amendment['analysis_files']
    assert isinstance(files, dict) and set(files) == {'verifier', 'binding_helper', 'entrypoint', 'diff'}
    file_binding(files['verifier'], 'analysis_verifier_source', 'evaluation/study_reporting.py')
    file_binding(files['binding_helper'], 'analysis_binding_source', 'evaluation/study_manifest.py')
    file_binding(files['entrypoint'], 'analysis_entrypoint_source')
    file_binding(files['diff'], 'analysis_diff')
    expected_binding = {
        'schema': 'afterlight.analysis-amendment-binding.v1', 'id': amendment['id'], 'sha256': descriptor['sha256'],
        'file_sha256': sha(raw['analysis_amendment']), 'implementation_sha256': files['verifier']['sha256'],
        'binding_helper_sha256': files['binding_helper']['sha256'], 'entrypoint_sha256': files['entrypoint']['sha256'],
    }
    assert selection.get('analysis_amendment') == expected_binding, 'Selection does not bind the exact pre-test analysis amendment'
    assert report.get('analysis_amendment') == expected_binding, 'Report differs from the pre-test analysis amendment'
    release = documents['release']['release']
    assert release['selection_sha256'] == documents['selection']['sha256'], 'Original release does not bind amended selection identity'
    assert release['selection_file_sha256'] == sha(raw['selection']), 'Original release does not bind original amended selection bytes'

    created, selected, released, reported = map(instant, (amendment['created_utc'], selection['created_utc'], release['created_utc'], report['created_utc']))
    assert created <= selected <= released <= reported, 'Analysis correction was not frozen before selection and test release'
    return {'present': True, 'id': amendment['id'], 'descriptor_sha256': descriptor['sha256'],
            'descriptor_file_sha256': expected_binding['file_sha256'], 'frozen_estimator_sha256': estimator_hash,
            'original_simulation_source_unchanged': True, 'selection_report_and_original_release_bound': True,
            'all_analysis_companions_hash_verified': sorted(ANALYSIS_ARTIFACTS), 'downloaded_analysis_code_executed': False,
            'failure_journal': {'schema': journal['schema'], 'state': journal['state'], 'return_code': journal['return_code'],
                                'automatic_retries': journal['automatic_retries'],
                                'fit_stage_marker_present': any(marker in journal for marker in ('model_fit_reached', 'fit_completed')),
                                'independently_proves_no_fit': False},
            'scope': 'Checks exact public pre-test descriptor/source/failure evidence identities, stopped/unsuccessful watcher status and declared chronology. The original journal has no fit-stage marker; the descriptor pre-fit assertion depends on the retained stack/log and reviewed absence of original output. Metadata does not independently prove human nonaccess or when fitting actually began.'}


def verify_reproduction(summary, documents, raw, artifacts):
    reproduction = documents['reproduction']
    assert reproduction['schema'] == 'afterlight.study-reproduction.v1'
    assert reproduction['transfer_limit_bytes'] == COMPANION_LIMIT
    assert reproduction['decoded_limit_bytes'] == reproduction['decoder_memory_limit_bytes'] == GRID_LIMIT
    for key in ('study', 'protocol', 'selection', 'release', 'report'):
        assert reproduction[key + '_sha256'] == documents[key]['sha256']
    expected = {'train_candidates': ('train', 'candidate-outcomes.json'), 'validation_candidates': ('validation', 'candidate-outcomes.json'),
                'test_candidates': ('test', 'candidate-outcomes.json'), 'test_outcomes': ('test', 'outcomes.json')}
    assert len(reproduction['files']) == len(expected) and {row['kind'] for row in reproduction['files']} == set(expected)
    grids = {}; decoded_inventory = []
    for item in reproduction['files']:
        kind = item['kind']; split, filename = expected[kind]
        assert item['split'] == split and item['source_file'] == filename and item['encoding'] == 'xz'
        assert item['url'] == artifacts[kind]['url']
        assert item['transfer_sha256'] == artifacts[kind]['sha256'] == sha(raw[kind])
        assert item['transfer_bytes'] == artifacts[kind]['bytes'] == len(raw[kind]) <= COMPANION_LIMIT
        assert type(item['bytes']) is int and 0 < item['bytes'] <= GRID_LIMIT and SHA.fullmatch(item['sha256'])
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=GRID_LIMIT)
        decoded = decoder.decompress(raw[kind], max_length=GRID_LIMIT + 1)
        assert decoder.eof and not decoder.unused_data, ('Incomplete, trailing or concatenated XZ stream', kind)
        assert decoder.check == lzma.CHECK_CRC64, ('Unexpected reproduction stream check', kind)
        assert len(decoded) == item['bytes'] <= GRID_LIMIT and sha(decoded) == item['sha256']
        binding = documents['selection']['selection']['collections'][split][filename] if split in ('train', 'validation') else documents['report']['report']['collection_files_sha256'][filename]
        assert item['sha256'] == binding, ('Decoded original file differs from frozen evidence', kind)
        grids[kind] = strict_json(decoded)
        assert isinstance(grids[kind], list)
        decoded_inventory.append({'kind': kind, 'bytes': len(decoded), 'sha256': sha(decoded), 'rows': len(grids[kind]), 'decoder_memory_limit_bytes': GRID_LIMIT})

    # Only these unchanged, source-hash-bound pure modules are imported. No
    # simulator, fitting entry point or private outcome path is invoked.
    source = documents['study']['study']['source']
    helpers = bound_scientific_modules(source['source_files'])
    pure_sources = list(PURE_HELPER_FILES.values())
    objective = helpers['evaluation.metrics'].objective
    assert_episode_coverage = helpers['evaluation.protocol'].assert_episode_coverage
    recompute_frozen_decisions = helpers['evaluation.selectors'].recompute_frozen_decisions
    validate_prediction_inputs = helpers['evaluation.selectors'].validate_prediction_inputs
    paired_decision_report = helpers['evaluation.comparison'].paired_decision_report
    select_fixed_lead = helpers['models.residual'].select_fixed_lead
    validate_candidate_rows = helpers['models.residual'].validate_candidate_rows
    protocol = documents['protocol']
    selection = documents['selection']['selection']; report = documents['report']['report']
    for split, key in (('train', 'train_candidates'), ('validation', 'validation_candidates'), ('test', 'test_candidates')):
        rows = grids[key]
        validate_candidate_rows(rows, split)
        assert_episode_coverage(rows, protocol['protocol'], split)
        validate_prediction_inputs(rows, protocol)
        if split in ('train', 'validation'):
            assert canonical_sha(rows) == selection['candidate_data_sha256'][split]
    actual_fixed = select_fixed_lead(grids['validation_candidates'], protocol['protocol']['civilian_weight'])
    assert actual_fixed == selection['validation_fixed_selection'], 'Validation-tuned fixed choice differs from the released grid'
    if summary['mode'] == 'learned':
        model = documents['model']['model']
        train = grids['train_candidates']
        finite_labels = sum(objective(row, protocol['protocol']['civilian_weight']) is not None for row in train)
        assert model['training_rows'] == len(train) and model['finite_training_labels'] == finite_labels
        assert model['excluded_infeasible_labels'] == len(train) - finite_labels
        assert model['training_groups'] == sorted({row['demand_group_id'] for row in train})
        assert model['training_data_sha256'] == canonical_sha(train)
        envelope(documents['learned_selector'], 'selector', 'afterlight.selector.v1')
        assert documents['learned_selector']['selector']['model'] == documents['model']
        assert sha(raw['learned_selector']) == selection['artifacts_sha256']['learned-selector.json']
    outcomes = grids['test_outcomes']; candidates = grids['test_candidates']
    assert [row for row in outcomes if row['policy'] == 'fixed'] == candidates, 'Test candidate grid is not the unchanged fixed-policy outcome subset'
    test_ids = {e['episode_id'] for e in documents['study']['study']['episodes'] if e['split'] == 'test'}
    expected_worlds = {(eid, policy, lead) for eid in test_ids for policy, lead in [('ordinary', None), ('immediate', None),
                       *(('fixed', lead) for lead in protocol['protocol']['candidate_leads_s'])]}
    assert len(outcomes) == len(expected_worlds) and {(r['episode_id'], r['policy'], r['lead_s']) for r in outcomes} == expected_worlds
    assert dict(Counter(row['status'] for row in outcomes)) == report['all_world_status_counts']
    lookup = {(row['episode_id'], row['lead_s']): row for row in candidates}
    choices = []
    for comparison_id, asserted in report['comparisons'].items():
        kind = 'comparison_' + comparison_id.replace('-', '_')
        frozen = documents[kind]
        envelope(frozen, 'selectors', 'afterlight.selector-freeze.v1')
        filename = comparison_id + '.json'
        assert sha(raw[kind]) == selection['artifacts_sha256'][filename] == documents['release']['release']['comparison_artifacts_sha256'][filename]
        if summary['mode'] == 'learned': assert frozen['selectors']['selected'] == documents['learned_selector']
        else: assert frozen['selectors']['selected'] == documents['analytical_selector']
        assert frozen['selectors']['comparator'] == documents['analytical_selector' if comparison_id.endswith('vs-analytical') else 'fixed_selector']
        selected, comparator = recompute_frozen_decisions(candidates, protocol, frozen)
        recomputed = paired_decision_report(candidates, selected, comparator, civilian_weight=protocol['protocol']['civilian_weight'],
                                           frozen_protocol=protocol, frozen_selectors=frozen)
        actual_records = {record['episode_id']: record for record in asserted['records']}
        for key, value in recomputed.items():
            if key == 'records': continue
            assert asserted[key] == value, ('Recomputed frozen comparison differs', comparison_id, key)
        for record in recomputed['records']:
            actual = actual_records[record['episode_id']]
            assert all(actual[key] == value for key, value in record.items()), ('Recomputed frozen action/objective differs', comparison_id, record['episode_id'])
            chosen = lookup[(record['episode_id'], selected[record['episode_id']])]
            reference = lookup[(record['episode_id'], comparator[record['episode_id']])]
            paired = not record['selected_infeasible'] and not record['comparator_infeasible']
            for result_field, row_field in (('conditional_delta_ambulance_s', 'ambulance_journey_s'), ('conditional_delta_recovery_vehicle_s', 'recovery_excess_queue_area_vehicle_s')):
                close(actual[result_field], chosen[row_field] - reference[row_field] if paired else None, result_field)
        choices.append({'comparison': comparison_id, 'episodes': len(selected), 'frozen_model_and_comparator_choices_recomputed': True})
    return {'decoded_grids': decoded_inventory, 'scientific_helper_source_files_verified': pure_sources,
            'validation_fixed_choice_recomputed': True, 'test_candidate_full_scalar_subset_exact': True,
            'all_test_world_statuses_recomputed': True, 'frozen_decisions_and_reports_recomputed': choices}


def verify_accounting(summary, documents, raw):
    study = envelope(documents['study'], 'study', 'afterlight.study.v1')
    report = envelope(documents['report'], 'report', 'afterlight.study-report.v1')
    protocol = envelope(documents['protocol'], 'protocol', 'afterlight.protocol.v1')
    selection = envelope(documents['selection'], 'selection', 'afterlight.study-selection.v2')
    release = envelope(documents['release'], 'release', 'afterlight.test-release.v1')
    provenance = summary['provenance']
    assert report['status'] == 'audited_released_test_evidence' and report['automatic_benefit_claim'] is False
    assert summary['mode'] == report['mode'] == release['mode']
    assert report['source'] == selection['source'] == release['source'] == study['source']
    assert protocol == study['protocol']
    assert protocol['source_commit'] == provenance['source_commit'] == study['source']['source_commit']
    assert protocol['source_code_sha256'] == provenance['source_code_sha256'] == study['source']['source_code_sha256']
    for key in ('study', 'protocol', 'selection', 'release'):
        assert provenance[key + '_sha256'] == documents[key]['sha256']
        assert report[key + '_sha256'] == documents[key]['sha256']
    assert provenance['report_sha256'] == documents['report']['sha256']
    assert provenance['report_file_sha256'] == sha(raw['report'])
    assert provenance['test_attempt_sha256'] == report['test_attempt_sha256']
    assert selection['study_sha256'] == release['study_sha256'] == documents['study']['sha256']
    assert selection['protocol_sha256'] == release['protocol_sha256'] == documents['protocol']['sha256']
    assert release['selection_sha256'] == documents['selection']['sha256']
    assert release['selection_file_sha256'] == sha(raw['selection'])
    assert report['release_file_sha256'] == sha(raw['release'])
    assert report['comparison_artifacts_sha256'] == release['comparison_artifacts_sha256']
    assert selection['artifacts_sha256'] == release['selection_artifacts_sha256']
    assert selection['test_outcomes_accessed'] is False and selection['test_release_authorized'] is False
    fixed = envelope(documents['fixed_selector'], 'selector', 'afterlight.selector.v1')
    analytical = envelope(documents['analytical_selector'], 'selector', 'afterlight.selector.v1')
    assert fixed['kind'] == 'fixed' and analytical['kind'] == 'analytical'
    assert fixed['protocol_sha256'] == analytical['protocol_sha256'] == documents['protocol']['sha256']
    assert fixed['lead_s'] == summary['fixed_lead_s'] == selection['validation_fixed_selection']['lead_s']
    for key in ('fixed_selector', 'analytical_selector'):
        filename = key.replace('_', '-') + '.json'
        assert sha(raw[key]) == selection['artifacts_sha256'][filename]
    episodes = {episode['episode_id']: episode for episode in study['episodes']}
    assert len(episodes) == len(study['episodes'])
    split_groups = {split: {e['demand_group_id'] for e in episodes.values() if e['split'] == split} for split in ('train', 'validation', 'test')}
    assert all(not split_groups[a] & split_groups[b] for a, b in (('train', 'validation'), ('train', 'test'), ('validation', 'test')))
    for episode in episodes.values(): assert protocol['group_assignments'][episode['demand_group_id']] == episode['split']
    test = {key: value for key, value in episodes.items() if value['split'] == 'test'}
    assert test and all(split_groups.values()), 'The released study must retain every declared split'
    assert set(release['test_episode_ids']) == set(test) and len(release['test_episode_ids']) == len(test)
    worlds_per_episode = 2 + len(protocol['candidate_leads_s'])
    assert summary['counts'] == {**{split: sum(e['split'] == split for e in episodes.values()) for split in ('train', 'validation', 'test')},
                                'test_worlds': len(test) * worlds_per_episode, 'test_demand_groups': len(split_groups['test'])}
    assert release['expected_worlds'] == len(test) * worlds_per_episode == sum(report['all_world_status_counts'].values())
    assert set(report['all_world_status_counts']) <= set(STATUSES)
    assert not report['all_world_status_counts'].get('infrastructure_error', 0)
    assert summary['holdouts'] == {'regimes': protocol['heldout_regimes'], 'route_families': protocol['heldout_route_families']}
    for regime in protocol['heldout_regimes']:
        assert any(e['regime'] == regime for e in test.values())
        assert not any(e['regime'] == regime and e['split'] != 'test' for e in episodes.values())
    for family in protocol['heldout_route_families']:
        assert any(e['route_family'] == family for e in test.values())
        assert not any(e['route_family'] == family and e['split'] != 'test' for e in episodes.values())
    excluded_seeds = set(protocol['reserved_qualification_seeds']) | set(protocol['declared_exploration_seeds'])
    assert not {e['seed'] for e in episodes.values()} & excluded_seeds
    assert summary['objective']['civilian_weight'] == protocol['civilian_weight'] == 1
    if summary['mode'] == 'learned':
        model = envelope(documents['model'], 'model', 'afterlight.residual-tree.v1')
        assert sha(raw['model']) == provenance['model_sha256'] == release['selected_model_sha256'] == selection['artifacts_sha256']['model.json']
        assert model['protocol_sha256'] == documents['protocol']['sha256'] and model['source_commit'] == provenance['source_commit']
        assert model['training_data_sha256'] == selection['candidate_data_sha256']['train']
        assert set(model['training_groups']) <= split_groups['train'] and model['training_groups']
        assert not set(model['training_groups']) & (split_groups['test'] | split_groups['validation'])
        assert model['feature_names'] == [field['name'] for field in protocol['feature_schema']]
        selected = {'selector': {'schema': 'afterlight.selector.v1', 'kind': 'residual_tree', 'protocol_sha256': documents['protocol']['sha256'], 'model': documents['model']}}
        selected['sha256'] = canonical_sha(selected['selector'])
    else:
        assert summary['mode'] == 'baseline_only' and 'model' not in documents
        assert provenance['model_sha256'] is release['selected_model_sha256'] is None
        selected = documents['analytical_selector']
    csv_text = raw['paired_records'].decode('utf-8', errors='strict')
    reader = csv.DictReader(io.StringIO(csv_text, newline=''))
    csv_rows = list(reader)
    required_columns = ['comparison', 'case_id', 'seed', 'regime', 'route_family', 'pickup_id', 'hospital_id', 'episode_id', 'demand_group_id',
                        'selected_lead_s', 'comparator_lead_s', 'selected_status', 'comparator_status', 'selected_infeasible', 'comparator_infeasible',
                        'selected_j_s', 'comparator_j_s', 'paired_delta_j_s', 'delta_ambulance_s', 'delta_civilian_s', 'delta_recovery_vehicle_s']
    assert reader.fieldnames == required_columns
    comparisons = {row['id']: row for row in summary['comparisons']}
    expected_comparisons = {'learned-vs-fixed', 'learned-vs-analytical'} if summary['mode'] == 'learned' else {'analytical-vs-fixed'}
    assert set(comparisons) == expected_comparisons
    assert set(comparisons) == set(report['comparisons']) and len(comparisons) == len(summary['comparisons'])
    assert report['uncertainty_specification']['seed'] == 0 and report['uncertainty_specification']['resamples'] == 2000
    assert report['uncertainty_specification']['minimum_independent_groups'] == 10
    assert len(csv_rows) == len(test) * len(comparisons)
    csv_by_key = {(row['comparison'], row['episode_id']): row for row in csv_rows}
    assert len(csv_by_key) == len(csv_rows)
    arithmetic = []
    for key, shown in comparisons.items():
        content = report['comparisons'][key]
        records = content['records']
        assert len(records) == len(test) and {record['episode_id'] for record in records} == set(test)
        assert shown['episodes'] == content['episodes'] == len(test)
        assert shown['demand_groups'] == content['demand_groups'] == len(split_groups['test'])
        comparator = documents['analytical_selector'] if key.endswith('vs-analytical') else documents['fixed_selector']
        pair = {'schema': 'afterlight.selector-freeze.v1', 'protocol_sha256': documents['protocol']['sha256'], 'selected': selected, 'comparator': comparator}
        assert content['selector_freeze_sha256'] == canonical_sha(pair)
        assert content['selected_selector_sha256'] == selected['sha256'] and content['comparator_selector_sha256'] == comparator['sha256']
        for record in records:
            episode = test[record['episode_id']]
            assert record['demand_group_id'] == episode['demand_group_id']
            expected = {'comparison': key, **{name: episode[name] for name in ('case_id', 'seed', 'regime', 'route_family', 'pickup_id', 'hospital_id')},
                        **{name: record[name] for name in ('episode_id', 'demand_group_id', 'selected_lead_s', 'comparator_lead_s', 'selected_status', 'comparator_status',
                                                         'selected_infeasible', 'comparator_infeasible', 'selected_j_s', 'comparator_j_s', 'paired_delta_j_s')},
                        'delta_ambulance_s': record['conditional_delta_ambulance_s'], 'delta_civilian_s': record['civilian_delta_s'],
                        'delta_recovery_vehicle_s': record['conditional_delta_recovery_vehicle_s']}
            assert csv_by_key[(key, record['episode_id'])] == {field: '' if value is None else str(value) for field, value in expected.items()}
            for side in ('selected', 'comparator'):
                assert type(record[side + '_infeasible']) is bool
                assert record[side + '_infeasible'] == (record[side + '_j_s'] is None)
                assert record[side + '_status'] in STATUSES
                assert record[side + '_lead_s'] in protocol['candidate_leads_s']
                if not record[side + '_infeasible']:
                    assert record[side + '_status'] == 'completed'
                    assert type(record[side + '_j_s']) in (int, float) and math.isfinite(record[side + '_j_s']) and record[side + '_j_s'] >= 0
            paired = not record['selected_infeasible'] and not record['comparator_infeasible']
            for field in ('paired_delta_j_s', 'conditional_delta_ambulance_s', 'civilian_delta_s', 'conditional_delta_recovery_vehicle_s'):
                assert (record[field] is not None) == paired
                if paired: assert math.isfinite(record[field])
            if paired:
                close(record['paired_delta_j_s'], record['selected_j_s'] - record['comparator_j_s'], 'paired objective')
                close(record['paired_delta_j_s'], record['conditional_delta_ambulance_s'] + record['civilian_delta_s'], 'objective component sum')
        finite = [record for record in records if record['paired_delta_j_s'] is not None]
        assert shown['paired_feasible_episodes'] == content['paired_feasible_episodes'] == len(finite)
        for side in ('selected', 'comparator'):
            statuses = Counter(record[side + '_status'] for record in records)
            assert shown[side + '_status_counts'] == {status: statuses[status] for status in STATUSES}
            assert {status: content[side + '_status_counts'].get(status, 0) for status in STATUSES} == shown[side + '_status_counts']
            assert shown[side + '_failures'] == content[side + '_failures'] == sum(record[side + '_infeasible'] for record in records)
        for shown_field, record_field in (('mean_delta_j_s', 'paired_delta_j_s'), ('mean_delta_ambulance_s', 'conditional_delta_ambulance_s'), ('mean_delta_civilian_s', 'civilian_delta_s')):
            close(shown[shown_field], mean(record[record_field] for record in finite) if finite else None, shown_field)
        close(shown['mean_delta_j_s'], content['conditional_mean_delta_j_s'], 'reported mean objective')
        close(shown['changed_action_rate'], sum(record['selected_lead_s'] != record['comparator_lead_s'] for record in records) / len(records), 'action rate')
        close(shown['changed_action_rate'], content['changed_action_rate'], 'report action rate')
        interval, groups = interval_from_records(records)
        assert shown['interval_groups'] == content['uncertainty']['groups'] == groups
        if interval is None:
            assert shown['interval_95_j_s'] is content['uncertainty']['interval'] is None
            assert shown['interval_reason'] == content['uncertainty']['reason'] and shown['interval_reason']
        else:
            assert shown['interval_reason'] is None
            for index in (0, 1):
                close(shown['interval_95_j_s'][index], interval[index], 'summary interval')
                close(content['uncertainty']['interval'][index], interval[index], 'report interval')
        arithmetic.append({'comparison': key, 'episodes': len(records), 'paired_feasible': len(finite), 'csv_rows': len(test), 'interval_groups': groups, 'interval_recomputed': interval})
    return {'csv_rows': len(csv_rows), 'all_test_episodes_retained_per_comparison': True, 'arithmetic': arithmetic,
            'public_envelope_and_file_bindings': True, 'scope': 'Verifies the released public companions and their arithmetic; does not read or re-audit private raw simulator outcomes or prove human test nonaccess.'}


def load_released_public_pack(base_url: str, expected_manifest_sha256: str):
    assert isinstance(expected_manifest_sha256, str), 'Supply the completed publication manifest SHA-256 explicitly'
    expected_manifest_sha256 = expected_manifest_sha256.lower()
    assert SHA.fullmatch(expected_manifest_sha256), 'Supply the completed publication manifest SHA-256 explicitly'
    manifest_url = urljoin(base_url, 'study/manifest.json')
    manifest_bytes = bounded_get(manifest_url, MANIFEST_LIMIT)
    assert sha(manifest_bytes) == expected_manifest_sha256, 'Public manifest differs from the explicitly released publication'
    manifest = strict_json(manifest_bytes)
    assert set(manifest) == {'schema', 'url', 'sha256', 'bytes'} and manifest['schema'] == 'afterlight.study-summary-manifest.v1'
    assert manifest['url'] == 'summary.json' and SHA.fullmatch(manifest['sha256'])
    assert type(manifest['bytes']) is int and 0 < manifest['bytes'] <= SUMMARY_LIMIT
    summary_url = local_url(manifest['url'], manifest_url)
    summary_bytes = bounded_get(summary_url, SUMMARY_LIMIT)
    assert len(summary_bytes) == manifest['bytes'] and sha(summary_bytes) == manifest['sha256']
    summary = strict_json(summary_bytes)
    assert summary['schema'] == 'afterlight.study-summary.v1' and summary['status'] == 'audited_released_test_evidence'
    assert summary['scope'] == 'offline_cached_candidate_selection' and summary['automatic_benefit_claim'] is False
    inventory = summary['artifacts']
    assert isinstance(inventory, list) and 1 <= len(inventory) <= 128
    assert all(type(entry.get('bytes')) is int and entry['bytes'] > 0 for entry in inventory)
    assert len(manifest_bytes) + len(summary_bytes) + sum(entry['bytes'] for entry in inventory) <= COMPANION_LIMIT, 'Released proof pack exceeds its agreed 4 MiB physical budget'
    artifacts = {}; paths = set(); raw = {}; documents = {}; observed = []
    required = {'report', 'study', 'protocol', 'selection', 'release', 'fixed_selector', 'analytical_selector', 'paired_records', 'reproduction'} | GRID_KINDS
    if summary['mode'] == 'learned': required |= {'model', 'learned_selector', 'comparison_learned_vs_fixed', 'comparison_learned_vs_analytical'}
    else:
        assert summary['mode'] == 'baseline_only'
        required.add('comparison_analytical_vs_fixed')
    for entry in inventory:
        assert set(entry) == {'kind', 'url', 'sha256', 'bytes'}
        kind = entry['kind']
        assert isinstance(kind, str) and kind and kind not in artifacts and entry['url'] not in paths
        assert SHA.fullmatch(entry['sha256']) and type(entry['bytes']) is int and 0 < entry['bytes'] <= COMPANION_LIMIT
        url = local_url(entry['url'], summary_url)
        data = bounded_get(url, COMPANION_LIMIT)
        assert len(data) == entry['bytes'] and sha(data) == entry['sha256'], ('Public companion byte/hash mismatch', kind)
        artifacts[kind] = entry; paths.add(entry['url'])
        observed.append({'kind': kind, 'url': url, 'bytes': len(data), 'sha256': sha(data)})
        if kind in required or kind in ANALYSIS_ARTIFACTS:
            raw[kind] = data
            if (kind in required and kind != 'paired_records' and kind not in GRID_KINDS) or kind == 'analysis_amendment':
                documents[kind] = strict_json(data)
    assert required <= artifacts.keys(), ('Missing required public companions', required - artifacts.keys())
    if summary['mode'] == 'baseline_only': assert 'model' not in artifacts
    verified = verify_accounting(summary, documents, raw)
    verified['analysis_amendment'] = verify_analysis_amendment(documents, raw, artifacts)
    verified['public_reproduction'] = verify_reproduction(summary, documents, raw, artifacts)
    return {'manifest_url': manifest_url, 'manifest_sha256': sha(manifest_bytes), 'manifest': manifest,
            'summary_url': summary_url, 'summary': summary, 'companions': observed, 'verification': verified}
