"""Audited train/validation selection. No test outcomes are opened here.

Optional ML is imported only after an explicit request and sufficient finite
training labels. These entry points are for the designated Omen environment.
"""
from __future__ import annotations
from datetime import datetime, timezone
from importlib import metadata
import json
from pathlib import Path
import platform
from typing import Mapping

from .metrics import excess_queue_area, finite, objective, verify_pair
from .protocol import assert_episode_coverage, digest
from .selectors import (analytical_artifact, fixed_lead_artifact, learned_artifact,
                        freeze_selectors, validate_prediction_inputs)
from .splits import assert_disjoint
from .study_manifest import (POLICIES, assert_study_runtime, file_hash, load_study,
                             read_json, validate_pilot_world_binding)

RAW_FILES = ('lifecycle.json', 'tripinfo.xml', 'outcome.json', 'command.json', 'signal-audit-input.json')


def _contained(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('Artifact path must be relative POSIX text')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != relative:
        raise ValueError('Unsafe artifact path')
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Artifact symbolic links are not accepted')
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('Artifact path escapes collection')
    return target


def verify_collection(study_directory: Path, collection_directory: Path, expected_split: str) -> dict:
    """Verify complete eligible evidence, preserving invalid/censored policy rows.

    A split mismatch is rejected using collection.json BEFORE opening outcomes.
    This function currently cannot read test outcomes, even if explicitly asked.
    """
    if expected_split not in {'train', 'validation'}:
        raise ValueError('Selection verifier accepts train/validation only; test remains unreleased')
    from sim.audit import audit_lifecycle, audit_world_signals
    from sim.network import read_network
    from models.residual import validate_candidate_rows
    envelope = load_study(study_directory, require_frozen=True)
    study, root = envelope['study'], collection_directory.resolve()
    manifest_path = _contained(root, 'collection.json')
    manifest = read_json(manifest_path)
    if manifest.get('split') != expected_split:
        raise ValueError('Collection split differs from requested train/validation role; outcomes not opened')
    if manifest.get('schema') != 'afterlight.collection.v1' or manifest.get('status') != 'completed':
        raise ValueError('Selection requires one completed collection attempt; never pool partial retries')
    for key, expected in {'study_sha256':envelope['sha256'], 'protocol_sha256':digest(study['protocol']),
                          'source':study['source'], 'dependencies':study['dependencies'],
                          'sumo_version':study['pilot_evidence']['sumo_version']}.items():
        if manifest.get(key) != expected:
            raise ValueError(f'Collection provenance mismatch: {key}')
    episodes = [episode for episode in study['episodes'] if episode['split'] == expected_split]
    planned = {(episode['episode_id'], policy, lead):
               (episode, f"worlds/{episode['case_id']}/{policy}" + (f'-{lead}' if lead is not None else ''))
               for episode in episodes for policy, lead in POLICIES}
    inventory = manifest.get('world_inventory')
    if not isinstance(inventory, list) or len(inventory) != len(planned):
        raise ValueError('Collection inventory is incomplete')
    seen = set()
    for item in inventory:
        key = (item['episode_id'], item['policy'], item['lead_s'])
        if key not in planned or key in seen or item.get('state') != 'audited' or item.get('runner_invoked') is not True:
            raise ValueError('Collection includes duplicate, unaudited or unattempted worlds')
        episode, directory = planned[key]
        if item.get('case_id') != episode['case_id'] or item.get('directory') != directory:
            raise ValueError('Collection inventory directory/case mismatch')
        seen.add(key)
    for key, expected in {'recorded_worlds':len(planned), 'runner_invocations':len(planned), 'unattempted_worlds':0}.items():
        if manifest.get(key) != expected:
            raise ValueError('Collection completion counts disagree with planned worlds')
    budget = study['budget']['split_start_budgets_s'][expected_split]
    runtime = finite(manifest['runtime_total_s'], 'collection runtime')
    if manifest.get('split_start_budget_s') != budget or manifest.get('wall_budget_overrun_s') != max(0, runtime-budget):
        raise ValueError('Collection runtime/start-budget metadata mismatch')
    rows = read_json(_contained(root, 'outcomes.json'))
    candidates = read_json(_contained(root, 'candidate-outcomes.json'))
    if not isinstance(rows, list) or len(rows) != len(planned) or candidates != [r for r in rows if r.get('policy') == 'fixed']:
        raise ValueError('Collection row/candidate inventory mismatch')
    files = {name:file_hash(_contained(root,name)) for name in ('collection.json','outcomes.json','candidate-outcomes.json')}
    network = read_network(study_directory / study['network']['directory'] / 'network.net.xml')
    seen.clear()
    for row in rows:
        key = (row['episode_id'], row['policy'], row['lead_s'])
        if key not in planned or key in seen:
            raise ValueError('Duplicate or unknown scalar world')
        seen.add(key)
        episode, directory = planned[key]
        expected_fields = {name:episode[name] for name in ('episode_id','case_id','demand_group_id','split','regime','seed',
            'dispatch_s','pickup_id','hospital_id','route_family','demand_sha256','network_sha256')}
        expected_fields.update(study_sha256=envelope['sha256'], protocol_sha256=digest(study['protocol']),
            source_commit=study['source']['source_commit'], source_code_sha256=study['source']['source_code_sha256'],
            dependencies=study['dependencies'], sumo_version=study['pilot_evidence']['sumo_version'],
            audit_status='passed', priority_deadline_audit='passed', raw_world_directory=directory)
        if any(row.get(name) != value for name,value in expected_fields.items()):
            raise ValueError('Scalar identity/source/audit differs from frozen collection')
        world_dir = _contained(root, directory)
        hashes = row.get('raw_files_sha256')
        if not isinstance(hashes, Mapping) or set(hashes) != set(RAW_FILES):
            raise ValueError('Collection lacks exact original raw evidence byte hashes')
        for name in RAW_FILES:
            actual = file_hash(_contained(root, directory+'/'+name))
            if hashes[name] != actual:
                raise ValueError(f'Raw collection evidence changed: {directory}/{name}')
            files[directory+'/'+name] = actual
        raw = read_json(world_dir/'outcome.json')
        validate_pilot_world_binding(row,raw,{'civilian_weight':study['spec']['civilian_weight']})
        signal = read_json(world_dir/'signal-audit-input.json')
        if row.get('signal_audit_input_sha256') != hashes['signal-audit-input.json'] or any(
                signal.get(name) != raw.get(name) for name in ('policy','status','decision','metrics','events')):
            raise ValueError('Compact signal trace differs from raw outcome or recorded hash')
        audit_world_signals(signal,network,episode['dispatch_s'],simulation_step_s=study['spec']['timing']['step_s'])
        demand = read_json(study_directory / episode['demand_directory'] / 'demand.json')
        audit_lifecycle(demand,read_json(world_dir/'lifecycle.json'),world_dir/'tripinfo.xml',row)
        if row['horizon_s'] != study['protocol']['horizon_s'] or row['drain_end_s'] != study['protocol']['drain_end_s']:
            raise ValueError('Collected common window differs from protocol')
        finite(row['runtime_s'],'audited world runtime')
    for episode in episodes:
        same = [row for row in rows if row['episode_id']==episode['episode_id']]
        ordinary = next(row for row in same if row['policy']=='ordinary')
        for row in same:
            verify_pair(row,ordinary)
            window = study['protocol']['recovery_window_s']
            area = excess_queue_area(row['queue_samples'],ordinary['queue_samples'],*window)
            if row.get('recovery_window_s') != window or row.get('recovery_excess_queue_area_vehicle_s') != area or row.get('queue_scope') != study['protocol']['queue_scope']:
                raise ValueError('Recorded recovery metric differs from common-window recomputation')
    assert_disjoint(candidates,study['protocol']['group_assignments'])
    assert_episode_coverage(candidates,study['protocol'],expected_split)
    validate_candidate_rows(candidates,expected_split)
    validate_prediction_inputs(candidates,{'sha256':digest(study['protocol']),'protocol':study['protocol']})
    return {'manifest':manifest,'rows':rows,'candidate_rows':candidates,'files_sha256':files}


def ml_runtime() -> dict:
    """Read actual optional package metadata; never installs or upgrades anything."""
    from sim.network import ROOT
    versions = {name:metadata.version(name) for name in ('scikit-learn','numpy','scipy','joblib','threadpoolctl')}
    if versions['scikit-learn'] != '1.7.2':
        raise ValueError('Selection requires the declared scikit-learn 1.7.2 environment')
    return {'python':platform.python_version(),'packages':versions,
            'requirements_ml_sha256':file_hash(ROOT/'requirements-ml.txt')}


def _write(path: Path, value: object) -> None:
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False);handle.write('\n')


def select_study(study_directory: Path, train_directory: Path, validation_directory: Path,
                 output: Path, *, fit_model: bool = False) -> dict:
    """Select once from declared train/validation evidence; no test path argument."""
    from sim.network import ROOT
    from models.residual import fit_residual, select_fixed_lead
    root = study_directory.resolve()
    envelope = load_study(root,require_frozen=True)
    study = envelope['study']
    assert_study_runtime(study)
    output = output.resolve()
    runtime_path = ROOT/'local-runtime';runtime_root = runtime_path.resolve()
    if runtime_path.is_symlink() or not runtime_root.is_relative_to(ROOT.resolve()) or output==runtime_root or not output.is_relative_to(runtime_root):
        raise ValueError('Selection output must be inside real ignored checkout local-runtime')
    for protected in (root,train_directory.resolve(),validation_directory.resolve()):
        if output==protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Selection output cannot overlap study or collection inputs')
    train = verify_collection(root,train_directory,'train')
    validation = verify_collection(root,validation_directory,'validation')
    assert_study_runtime(study)
    protocol = {'sha256':digest(study['protocol']),'protocol':study['protocol']}
    fixed_result = select_fixed_lead(validation['candidate_rows'],study['spec']['civilian_weight'])
    finite_labels = sum(objective(row,study['spec']['civilian_weight']) is not None for row in train['candidate_rows'])
    enough = finite_labels >= 2*study['spec']['model_specification']['min_samples_leaf']
    runtime = ml_runtime() if fit_model and enough and fixed_result['conclusive'] else None
    output.mkdir(parents=True,exist_ok=False)
    try:
        analytical = analytical_artifact(protocol)
        _write(output/'analytical-selector.json',analytical)
        fixed = fixed_lead_artifact(validation['candidate_rows'],protocol) if fixed_result['conclusive'] else None
        if fixed is not None:_write(output/'fixed-selector.json',fixed)
        model = None
        reason = 'model fitting not requested'
        if not fixed_result['conclusive']:reason='validation lacks a common feasible cohort; no fixed comparator can be selected honestly'
        elif fit_model and not enough:reason='insufficient finite training labels; failures retained, no model fitted'
        elif fit_model:
            model = fit_residual(train['candidate_rows'],feature_names=[f['name'] for f in study['protocol']['feature_schema']],
                civilian_weight=study['spec']['civilian_weight'],frozen_protocol=protocol,**study['spec']['model_specification'])
            if ml_runtime()!=runtime or model['model'].get('sklearn_version')!=runtime['packages']['scikit-learn']:
                raise ValueError('Optional ML runtime changed during fitting or loaded sklearn differs from package metadata')
            _write(output/'model.json',model)
            learned = learned_artifact(model,protocol)
            _write(output/'learned-selector.json',learned)
            freeze_selectors(protocol,learned,fixed,output/'learned-vs-fixed.json')
            freeze_selectors(protocol,learned,analytical,output/'learned-vs-analytical.json')
            reason='one predeclared tree fitted; no held-out outcomes accessed or gain claimed'
        if model is None and fixed is not None:
            freeze_selectors(protocol,analytical,fixed,output/'analytical-vs-fixed.json')
        assert_study_runtime(study)
        # Reverify bytes after fitting, catching changes during the operation.
        for directory,verified in ((train_directory,train),(validation_directory,validation)):
            if any(file_hash(_contained(directory,name))!=value for name,value in verified['files_sha256'].items()):
                raise ValueError('Collection artifacts changed during selection')
        if runtime is not None and ml_runtime()!=runtime:
            raise ValueError('Optional ML runtime changed before selection freeze')
        artifacts = {p.name:file_hash(p) for p in output.iterdir() if p.is_file()}
        selection = {'schema':'afterlight.study-selection.v1','study_sha256':envelope['sha256'],
            'protocol_sha256':protocol['sha256'],'source':study['source'],'simulation_dependencies':study['dependencies'],
            'status':'learned_ready' if model else ('baseline_only' if fixed else 'inconclusive'),
            'reason':reason,'fit_model_requested':fit_model,'finite_training_labels':finite_labels,
            'infeasible_training_rows':len(train['candidate_rows'])-finite_labels,'model_specification':study['spec']['model_specification'],
            'validation_fixed_selection':fixed_result,'ml_runtime':runtime,
            'collections':{'train':train['files_sha256'],'validation':validation['files_sha256']},
            'candidate_data_sha256':{'train':digest(train['candidate_rows']),'validation':digest(validation['candidate_rows'])},
            'artifacts_sha256':artifacts,'created_utc':datetime.now(timezone.utc).isoformat(),
            'test_outcomes_accessed':False,'test_release_authorized':False,
            'limitation':'Metadata guards do not independently prove human test nonaccess. No performance conclusion before released held-out evaluation.'}
        result={'sha256':digest(selection),'selection':selection}
        _write(output/'selection.json',result)
        return result
    except Exception as error:
        _write(output/'selection-failure.json',{'status':'selection_failed','reason':str(error),'source':study['source']})
        raise


def verify_selection_artifacts(study_directory: Path, selection_directory: Path) -> dict:
    """Verify selector freeze content/bytes for an explicit later release gate.

    Reads selection artifacts only, never train/validation/test outcome files.
    Returns the original verified envelope; caller must enforce its release mode.
    """
    from models.residual import CANDIDATES
    study_envelope = load_study(study_directory, require_frozen=True)
    study = study_envelope['study']
    assert_study_runtime(study)
    root = selection_directory.resolve()
    envelope = read_json(_contained(root,'selection.json'))
    selection = envelope['selection']
    if envelope.get('sha256') != digest(selection) or selection.get('schema') != 'afterlight.study-selection.v1':
        raise ValueError('Selection envelope hash/schema mismatch')
    expected = {'study_sha256':study_envelope['sha256'],'protocol_sha256':digest(study['protocol']),
        'source':study['source'],'simulation_dependencies':study['dependencies'],
        'model_specification':study['spec']['model_specification'],
        'test_outcomes_accessed':False,'test_release_authorized':False}
    if any(selection.get(key) != value for key,value in expected.items()):
        raise ValueError('Selection source/protocol/configuration provenance mismatch')
    status = selection.get('status')
    filenames = {'analytical-selector.json'}
    if status in {'baseline_only','learned_ready'}:filenames.add('fixed-selector.json')
    if status == 'baseline_only':filenames.add('analytical-vs-fixed.json')
    elif status == 'learned_ready':filenames.update(('model.json','learned-selector.json','learned-vs-fixed.json','learned-vs-analytical.json'))
    elif status != 'inconclusive':raise ValueError('Unknown selection status')
    hashes = selection.get('artifacts_sha256')
    if not isinstance(hashes, Mapping) or set(hashes) != filenames:
        raise ValueError('Selection artifact inventory does not match status')
    if {path.name for path in root.iterdir()} != filenames | {'selection.json'}:
        raise ValueError('Selection directory has missing or unexpected artifacts')
    artifacts = {}
    for name in filenames:
        path = _contained(root,name)
        if file_hash(path) != hashes[name]:raise ValueError('Selection artifact bytes changed')
        artifacts[name] = read_json(path)
    protocol = {'sha256':digest(study['protocol']),'protocol':study['protocol']}
    analytical = analytical_artifact(protocol)
    if artifacts['analytical-selector.json'] != analytical:
        raise ValueError('Analytical selector differs from frozen protocol')
    for split in ('train','validation'):
        if not isinstance(selection.get('collections',{}).get(split),Mapping) or not selection['collections'][split]:
            raise ValueError('Selection lacks original verified collection byte inventory')
        expected_files = {'collection.json','outcomes.json','candidate-outcomes.json'}
        for episode in study['episodes']:
            if episode['split'] != split:continue
            for policy,lead in POLICIES:
                directory=f"worlds/{episode['case_id']}/{policy}"+(f'-{lead}' if lead is not None else '')
                expected_files.update(directory+'/'+name for name in RAW_FILES)
        if set(selection['collections'][split])!=expected_files or any(
                not isinstance(value,str) or len(value)!=64 for value in selection['collections'][split].values()):
            raise ValueError('Selection collection byte inventory differs from full declared worlds')
        candidate_hash = selection.get('candidate_data_sha256',{}).get(split)
        if not isinstance(candidate_hash,str) or len(candidate_hash)!=64:
            raise ValueError('Selection lacks canonical candidate row identity')
    finite_labels = selection.get('finite_training_labels')
    excluded = selection.get('infeasible_training_rows')
    if any(isinstance(value,bool) or not isinstance(value,int) or value<0 for value in (finite_labels,excluded)):
        raise ValueError('Selection training-label accounting is invalid')
    expected_rows = 5*sum(episode['split']=='train' for episode in study['episodes'])
    if finite_labels+excluded != expected_rows:
        raise ValueError('Selection training-label inventory differs from study')
    fixed_result = selection['validation_fixed_selection']
    fixed = artifacts.get('fixed-selector.json')
    if fixed is None:
        if fixed_result.get('conclusive'):raise ValueError('Inconclusive status contradicts fixed comparator')
        return envelope
    content = fixed['selector']
    validation_groups = sorted(g for g,split in study['protocol']['group_assignments'].items() if split=='validation')
    if (fixed.get('sha256')!=digest(content) or content.get('schema')!='afterlight.selector.v1' or content.get('kind')!='fixed'
            or content.get('protocol_sha256')!=protocol['sha256'] or not fixed_result.get('conclusive')
            or content.get('validation_selection')!=fixed_result or content.get('lead_s')!=fixed_result.get('lead_s')
            or isinstance(content.get('lead_s'),bool) or content.get('lead_s') not in CANDIDATES
            or content.get('validation_groups')!=validation_groups
            or content.get('validation_data_sha256')!=selection['candidate_data_sha256']['validation']):
        raise ValueError('Fixed comparator validation provenance mismatch')
    selected = analytical
    comparisons = [('analytical-vs-fixed.json',analytical,fixed)]
    if status=='learned_ready':
        model = artifacts['model.json']
        selected = learned_artifact(model,protocol)
        metadata_model = model['model']
        ml = selection.get('ml_runtime')
        if (selection.get('fit_model_requested') is not True or not isinstance(ml,Mapping)
                or ml.get('packages',{}).get('scikit-learn')!='1.7.2'
                or metadata_model.get('sklearn_version')!='1.7.2'
                or metadata_model.get('training_data_sha256')!=selection['candidate_data_sha256']['train']
                or metadata_model.get('finite_training_labels')!=finite_labels
                or metadata_model.get('excluded_infeasible_labels')!=excluded
                or metadata_model.get('parameters')!={**study['spec']['model_specification'],'random_state':0}
                or metadata_model.get('training_groups')!=sorted(g for g,split in study['protocol']['group_assignments'].items() if split=='train')
                or finite_labels<2*study['spec']['model_specification']['min_samples_leaf']
                or artifacts['learned-selector.json']!=selected):
            raise ValueError('Learned selector/runtime/training provenance mismatch')
        from sim.network import ROOT
        if ml.get('requirements_ml_sha256')!=file_hash(ROOT/'requirements-ml.txt') or not ml.get('python') or any(
                not isinstance(ml.get('packages',{}).get(name),str) or not ml['packages'][name]
                for name in ('numpy','scipy','joblib','threadpoolctl')):
            raise ValueError('Optional ML runtime inventory is incomplete or lock changed')
        comparisons=[('learned-vs-fixed.json',selected,fixed),('learned-vs-analytical.json',selected,analytical)]
    for name,chosen,comparator in comparisons:
        expected_pair={'schema':'afterlight.selector-freeze.v1','protocol_sha256':protocol['sha256'],
                       'selected':chosen,'comparator':comparator}
        if artifacts[name]!={'sha256':digest(expected_pair),'selectors':expected_pair}:
            raise ValueError('Comparison freeze differs from declared selectors')
    return envelope
