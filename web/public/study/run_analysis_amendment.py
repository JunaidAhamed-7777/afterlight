"""Explicit checksum-bound analysis revision; original simulation stays pinned.

Freeze only prepares a descriptor/source bundle. Select fits once into a fresh
directory. Report/verify never simulate, refit or release held-out traffic.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value, indent=2, allow_nan=False)+'\n').encode())


def original_context(checkout, study_directory):
    checkout = checkout.resolve(strict=True)
    sys.path.insert(0, str(checkout))
    from sim.network import ROOT
    from sim.run import source_snapshot
    from evaluation.study_manifest import load_study, assert_study_runtime
    if ROOT.resolve() != checkout:
        raise ValueError('Original simulation modules were imported from another checkout')
    for name in ('sim.network', 'evaluation.study_manifest'):
        if not Path(sys.modules[name].__file__).resolve().is_relative_to(checkout):
            raise ValueError('Original module origin differs from the pinned checkout')
    study = load_study(study_directory, require_frozen=True, verify_inputs=True)
    assert_study_runtime(study['study'])
    if source_snapshot() != study['study']['source']:
        raise ValueError('Original physical/source snapshot changed')
    return study


def freeze_amendment(checkout, study_directory, failed_journal, failed_log, output):
    study = original_context(checkout, study_directory)
    if (study_directory/'test-release.json').exists() or (study_directory/'test-attempt.json').exists():
        raise ValueError('Amendment must be frozen before held-out release or any attempt')
    failure = json.loads(failed_journal.read_bytes())
    if failure.get('state') != 'watcher_stopped_no_test_release' or failure.get('return_code') != 1:
        raise ValueError('Expected the retained pre-fit failed watcher journal')
    arguments = failure['command']
    old_output = (checkout/arguments[arguments.index('--output')+1]).resolve()
    if old_output.exists() or b'validate_pilot_world_binding' not in failed_log.read_bytes():
        raise ValueError('Cannot establish that the retained attempt stopped before model output')
    runtime = (checkout/'local-runtime').resolve()
    if output.parent != runtime:
        raise ValueError('Amendment bundle must stay in a fresh original-checkout local-runtime directory')
    protected_paths = [study_directory.resolve(), failed_journal.resolve(), failed_log.resolve()]
    protected_paths.extend(path.parent.resolve() for path in (failed_journal, failed_log)
                           if path.parent.resolve() != runtime)
    for protected in protected_paths:
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Amendment output cannot overlap original study or failed-attempt evidence')
    output.mkdir(parents=True, exist_ok=False)
    script_directory = Path(__file__).resolve().parent
    files = {}
    for key, filename, original in [
        ('verifier', 'afterlight_analysis_amendment_v1.py', 'evaluation/study_reporting.py'),
        ('binding_helper', 'afterlight_analysis_binding_v1.py', 'evaluation/study_manifest.py'),
        ('entrypoint', 'run_analysis_amendment.py', None),
    ]:
        source = script_directory/filename
        data = source.read_bytes()
        with (output/filename).open('xb') as stream: stream.write(data)
        files[key] = {'filename': filename, 'sha256': hashlib.sha256(data).hexdigest()}
        if original:
            expected = study['study']['source']['source_files'][original]
            if file_hash(checkout/original) != expected:
                raise ValueError('Original evaluator source differs from its frozen snapshot')
            files[key].update(original_path=original, original_sha256=expected)
    original_report = (checkout/'evaluation/study_reporting.py').read_text().splitlines(True)
    revised_report = (output/files['verifier']['filename']).read_text().splitlines(True)
    original_manifest = (checkout/'evaluation/study_manifest.py').read_text()
    start = original_manifest.index('def validate_pilot_world_binding(')
    end = original_manifest.index('\ndef split_start_budgets(', start)
    original_binding = original_manifest[start:end].splitlines(True)
    revised_binding = (output/files['binding_helper']['filename']).read_text().splitlines(True)
    patch = ''.join(difflib.unified_diff(original_report, revised_report,
        fromfile='fa39f8a/evaluation/study_reporting.py', tofile=files['verifier']['filename']))
    patch += ''.join(difflib.unified_diff(original_binding, revised_binding,
        fromfile='fa39f8a/evaluation/study_manifest.py:validate_pilot_world_binding', tofile=files['binding_helper']['filename']))
    (output/'analysis-amendment.patch').write_text(patch, encoding='utf-8', newline='\n')
    files['diff'] = {'filename': 'analysis-amendment.patch', 'sha256': file_hash(output/'analysis-amendment.patch')}
    failures = {}
    for key, source, filename in [('journal', failed_journal, 'analysis-failed-selection-journal.json'),
                                  ('log', failed_log, 'analysis-failure.txt')]:
        data = source.read_bytes()
        with (output/filename).open('xb') as stream: stream.write(data)
        failures[key] = {'filename': filename, 'sha256': hashlib.sha256(data).hexdigest()}
    estimator = study['study']['protocol']['analytical_estimator']
    amendment = {
        'schema': 'afterlight.analysis-amendment.v1', 'id': 'frozen-estimator-config-v1',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'original_study_sha256': study['sha256'], 'original_protocol_sha256': digest(study['study']['protocol']),
        'original_source': study['study']['source'], 'frozen_analytical_estimator': estimator,
        'frozen_analytical_estimator_sha256': digest(estimator),
        'correction': 'Study raw verification must consume the exact full frozen estimator/config/version. The old pilot helper reconstructed defaults from integer objective weight1, producing a different serialization hash from the correctly collected float1.0 frozen config. No evidence/digest is normalized or rewritten; only the exact original frozen estimator hash is accepted.',
        'unchanged_design': ['original simulation/policy/model source and runtime guards', 'all original raw/metric/lifecycle/signal/hash audits',
            'study/protocol/inputs/scalar bytes and original analytical predictions', 'features, objective, hyperparameters, candidate leads, splits, seeds, timing and budget',
            'original pinned one-shot release and held-out collector', 'no fitting or held-out access while freezing this descriptor'],
        'failed_attempt': {'state': 'verification_failed_before_model_fit', 'model_fit_reached': False, **failures},
        'analysis_files': files,
    }
    envelope = {'sha256': digest(amendment), 'amendment': amendment}
    write_new(output/'analysis-amendment.json', envelope)
    original_context(checkout, study_directory)
    return envelope


def load_amended_analysis(checkout, study_directory, descriptor_path):
    study = original_context(checkout, study_directory)
    descriptor_bytes = descriptor_path.read_bytes()
    envelope = json.loads(descriptor_bytes)
    amendment = envelope['amendment']
    if (envelope['sha256'] != digest(amendment) or amendment['schema'] != 'afterlight.analysis-amendment.v1' or
            amendment['id'] != 'frozen-estimator-config-v1' or amendment['original_study_sha256'] != study['sha256'] or
            amendment['original_protocol_sha256'] != digest(study['study']['protocol']) or
            amendment['original_source'] != study['study']['source'] or
            digest(amendment['frozen_analytical_estimator']) != amendment['frozen_analytical_estimator_sha256'] or
            amendment['frozen_analytical_estimator_sha256'] != digest(study['study']['protocol']['analytical_estimator'])):
        raise ValueError('Analysis amendment does not bind the exact original study/source/estimator')
    bundle = descriptor_path.parent.resolve()
    for item in [*amendment['analysis_files'].values(), amendment['failed_attempt']['journal'], amendment['failed_attempt']['log']]:
        filename = item['filename']
        if Path(filename).name != filename or (bundle/filename).is_symlink() or file_hash(bundle/filename) != item['sha256']:
            raise ValueError('Frozen analysis source/diff/failure evidence changed')
    for key in ('verifier', 'binding_helper'):
        item = amendment['analysis_files'][key]
        if item['original_sha256'] != study['study']['source']['source_files'][item['original_path']]:
            raise ValueError('Amended evaluator names a different original source')
    if file_hash(Path(__file__).resolve()) != amendment['analysis_files']['entrypoint']['sha256']:
        raise ValueError('Executing entry point differs from the pre-test frozen analysis source')
    helper_path = bundle/amendment['analysis_files']['binding_helper']['filename']
    helper_name = 'afterlight_analysis_binding_v1'
    if helper_name in sys.modules and Path(sys.modules[helper_name].__file__).resolve() != helper_path:
        raise ValueError('Analysis helper was imported from another unbound location')
    helper = _load_verified_source(helper_name, helper_path,
        amendment['analysis_files']['binding_helper']['sha256'])
    module_path = bundle/amendment['analysis_files']['verifier']['filename']
    module = _load_verified_source('afterlight_analysis_amendment_v1', module_path,
        amendment['analysis_files']['verifier']['sha256'])
    binding = {'schema': 'afterlight.analysis-amendment-binding.v1', 'id': amendment['id'],
               'sha256': envelope['sha256'], 'file_sha256': hashlib.sha256(descriptor_bytes).hexdigest(),
               'implementation_sha256': amendment['analysis_files']['verifier']['sha256'],
               'binding_helper_sha256': amendment['analysis_files']['binding_helper']['sha256'],
               'entrypoint_sha256': amendment['analysis_files']['entrypoint']['sha256']}
    return module, binding, envelope


def _load_verified_source(name, path, expected_sha256):
    """Execute the exact checked source, never an independently cached .pyc."""
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('Frozen analysis source changed before compilation')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__spec__ = importlib.util.spec_from_file_location(name, path)
    module.__package__ = ''
    sys.modules[name] = module
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'select', 'review', 'report', 'verify'))
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--amendment', type=Path)
    parser.add_argument('--train', type=Path)
    parser.add_argument('--validation', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--collection', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--failed-journal', type=Path)
    parser.add_argument('--failed-log', type=Path)
    parser.add_argument('--fit-model', action='store_true')
    args = parser.parse_args()
    checkout = args.checkout.resolve(strict=True)
    def local(path):
        if path is None: raise ValueError('Missing explicit analysis input/output path')
        result = path.resolve() if path.is_absolute() else (checkout/path).resolve()
        runtime = (checkout/'local-runtime').resolve()
        if result == runtime or not result.is_relative_to(runtime): raise ValueError('Analysis paths must stay in pinned local-runtime')
        return result
    study_directory = local(args.study)
    if args.command == 'freeze':
        result = freeze_amendment(checkout, study_directory, local(args.failed_journal), local(args.failed_log), local(args.output))
        print(json.dumps({'amendment_sha256': result['sha256'], 'status': 'descriptor frozen; no fit/release/test'}, indent=2))
        return
    descriptor = local(args.amendment)
    module, binding, amendment_envelope = load_amended_analysis(checkout, study_directory, descriptor)
    if args.command == 'select':
        if (study_directory/'test-release.json').exists() or (study_directory/'test-attempt.json').exists():
            raise ValueError('Selection must precede held-out release')
        result = module.select_study(study_directory, local(args.train), local(args.validation), local(args.output),
                                     fit_model=args.fit_model, analysis_amendment=binding)
    elif args.command == 'review':
        result = module.verify_selection_artifacts(study_directory, local(args.selection))
        if result['selection'].get('analysis_amendment') != binding: raise ValueError('Selection amendment binding mismatch')
    elif args.command == 'report':
        result = module.report_study(study_directory, local(args.collection), local(args.output), analysis_amendment=binding)
    else:
        result = module.verify_report_artifacts(study_directory, local(args.collection), local(args.report), analysis_amendment=binding)
    _, final_binding, final_envelope = load_amended_analysis(checkout, study_directory, descriptor)
    if final_binding != binding or final_envelope != amendment_envelope:
        raise ValueError('Analysis amendment identity changed during the command')
    print(json.dumps({'status': 'explicit_amended_analysis_completed', 'command': args.command,
                      'sha256': result['sha256'], 'analysis_amendment': binding}, indent=2))


if __name__ == '__main__': main()
