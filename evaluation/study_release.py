"""Explicit immutable held-out release and single-attempt claim; no simulation.

A release is not a performance result. Filesystem guards document access order,
not proof that humans have never seen test outcomes. No automatic retry path.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .protocol import digest
from .study_manifest import assert_saved_inputs, assert_study_runtime, file_hash, load_study, read_json


def _roots(study_directory: Path) -> tuple[Path, Path]:
    from sim.network import ROOT
    runtime_path = ROOT / 'local-runtime'
    runtime = runtime_path.resolve()
    root = study_directory.resolve()
    if runtime_path.is_symlink() or not runtime.is_relative_to(ROOT.resolve()):
        raise ValueError('Runtime root must stay inside checkout without a symlink redirect')
    if root == runtime or not root.is_relative_to(runtime):
        raise ValueError('Study release must stay inside ignored checkout local-runtime')
    return root, runtime


def _local_file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Release/selection evidence file must not be a symlink or escape its directory')
    return path


def _exclusive(path: Path, value: dict) -> None:
    # A partial write/crash deliberately leaves a blocking marker for manual
    # diagnosis. Never replace, truncate or silently recover an existing marker.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _selection(root: Path, runtime: Path, selection_directory: Path, mode: str) -> tuple[dict, str]:
    from .study_reporting import verify_selection_artifacts
    if mode not in {'learned', 'baseline_only'}:
        raise ValueError('Explicit release mode must be learned or baseline_only; no automatic fallback')
    selected = selection_directory.resolve()
    if selected == runtime or not selected.is_relative_to(runtime):
        raise ValueError('Selection artifacts must stay inside ignored checkout local-runtime')
    if (selected/'selection-failure.json').exists():
        raise ValueError('Failed/partial selection cannot authorize test release')
    envelope = verify_selection_artifacts(root, selected)
    content = envelope['selection']
    expected_status = 'learned_ready' if mode == 'learned' else 'baseline_only'
    if content['status'] != expected_status or not content['validation_fixed_selection'].get('conclusive'):
        raise ValueError('Release mode requires its complete conclusive frozen selection; inconclusive/fallback release refused')
    if content.get('test_outcomes_accessed') is not False or content.get('test_release_authorized') is not False:
        raise ValueError('Selection must explicitly precede test access and release')
    return envelope, selected.relative_to(runtime).as_posix()


def release_test(study_directory: Path, selection_directory: Path, *, mode: str) -> dict:
    root, runtime = _roots(study_directory)
    if (root/'test-release.json').exists() or (root/'test-attempt.json').exists():
        raise FileExistsError('Existing test release/attempt cannot be overwritten or automatically retried')
    study_envelope = load_study(root, require_frozen=True, verify_inputs=True)
    study = study_envelope['study']
    assert_study_runtime(study)
    selection, relative = _selection(root, runtime, selection_directory, mode)
    content = selection['selection']
    if content['study_sha256'] != study_envelope['sha256'] or content['protocol_sha256'] != digest(study['protocol']):
        raise ValueError('Selection belongs to another frozen study/protocol')
    if content['source'] != study['source'] or content['simulation_dependencies'] != study['dependencies']:
        raise ValueError('Selection runtime differs from frozen study')
    tests = [episode['episode_id'] for episode in study['episodes'] if episode['split'] == 'test']
    if not tests or len(tests) != len(set(tests)):
        raise ValueError('Release requires the entire unique frozen test episode inventory')
    comparisons = ('learned-vs-fixed.json', 'learned-vs-analytical.json') if mode == 'learned' else ('analytical-vs-fixed.json',)
    artifacts = content['artifacts_sha256']
    binding = {'schema':'afterlight.test-release.v1','study_sha256':study_envelope['sha256'],
        'protocol_sha256':digest(study['protocol']), 'source':study['source'], 'dependencies':study['dependencies'],
        'mode':mode, 'selection_sha256':selection['sha256'], 'selection_directory':relative,
        'selection_file_sha256':file_hash(_local_file(selection_directory,'selection.json')),
        'selection_artifacts_sha256':artifacts,
        'comparison_artifacts_sha256':{name:artifacts[name] for name in comparisons},
        'selected_model_sha256':artifacts.get('model.json') if mode == 'learned' else None,
        'test_episode_ids':tests, 'expected_worlds':len(tests)*7,
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'claim_policy':'One exclusive test-attempt.json; interruption/failure does not authorize automatic rerun',
        'interpretation':'Explicit pre-test artifact freeze; not independent proof of human nonaccess and not evidence of benefit'}
    result = {'sha256':digest(binding),'release':binding}
    assert_study_runtime(study)
    assert_saved_inputs(root, study)
    _exclusive(root/'test-release.json', result)
    return result


def load_test_release(study_directory: Path) -> dict:
    root, runtime = _roots(study_directory)
    envelope = read_json(_local_file(root,'test-release.json'))
    release = envelope['release']
    if envelope['sha256'] != digest(release) or release.get('schema') != 'afterlight.test-release.v1':
        raise ValueError('Test release hash/schema mismatch')
    relative = release['selection_directory']
    if not isinstance(relative,str) or '\\' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Unsafe frozen selection directory')
    selection_directory = runtime / relative
    study_envelope = load_study(root, require_frozen=True, verify_inputs=True)
    study = study_envelope['study']
    assert_study_runtime(study)
    selection, canonical_relative = _selection(root, runtime, selection_directory, release['mode'])
    if canonical_relative != relative:
        raise ValueError('Frozen selection path redirected')
    content = selection['selection']
    expected = {'study_sha256':study_envelope['sha256'], 'protocol_sha256':digest(study['protocol']),
        'source':study['source'], 'dependencies':study['dependencies'], 'selection_sha256':selection['sha256'],
        'selection_file_sha256':file_hash(_local_file(selection_directory,'selection.json')),
        'selection_artifacts_sha256':content['artifacts_sha256'],
        'test_episode_ids':[episode['episode_id'] for episode in study['episodes'] if episode['split']=='test']}
    comparisons = ('learned-vs-fixed.json','learned-vs-analytical.json') if release['mode']=='learned' else ('analytical-vs-fixed.json',)
    expected['comparison_artifacts_sha256'] = {name:content['artifacts_sha256'][name] for name in comparisons}
    expected['selected_model_sha256'] = content['artifacts_sha256'].get('model.json') if release['mode']=='learned' else None
    expected['expected_worlds'] = len(expected['test_episode_ids'])*7
    if any(release.get(key)!=value for key,value in expected.items()):
        raise ValueError('Release differs from frozen study or verified selection artifacts')
    return envelope


def claim_test_attempt(study_directory: Path, output: Path, *, expected_release_sha256: str) -> dict:
    root, runtime = _roots(study_directory)
    if (root/'test-attempt.json').exists():
        raise FileExistsError('Test attempt already claimed; no silent repeat or crash recovery')
    release = load_test_release(root)
    if expected_release_sha256 != release['sha256']:
        raise ValueError('Explicit release digest does not match verified release')
    target = output.resolve()
    if target == runtime or not target.is_relative_to(runtime):
        raise ValueError('Test output must be inside ignored checkout local-runtime')
    selected = runtime / release['release']['selection_directory']
    for protected in (root, selected):
        if target==protected or target.is_relative_to(protected) or protected.is_relative_to(target):
            raise ValueError('Test output cannot overlap frozen study or selection')
    if target.exists():
        raise FileExistsError('Test output already exists; preserve prior evidence')
    claim = {'schema':'afterlight.test-attempt.v1', 'release_sha256':release['sha256'],
        'study_sha256':release['release']['study_sha256'], 'protocol_sha256':release['release']['protocol_sha256'],
        'output_directory':target.relative_to(runtime).as_posix(), 'expected_worlds':release['release']['expected_worlds'],
        'claimed_utc':datetime.now(timezone.utc).isoformat(), 'state':'claimed_before_first_test_world',
        'interpretation':'Reservation is not proof of completed execution; marker is never automatically removed'}
    result = {'sha256':digest(claim),'attempt':claim}
    _exclusive(root/'test-attempt.json', result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--mode',choices=('learned','baseline_only'),required=True)
    args=parser.parse_args()
    result=release_test(args.study,args.selection,mode=args.mode)
    print(json.dumps({'release_sha256':result['sha256'],'mode':result['release']['mode'],
                      'status':'released; no test simulation has been started'},indent=2))


if __name__=='__main__':main()
