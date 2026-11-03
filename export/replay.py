"""Strict paired-evidence packaging; the baseline is a distinct world, not a ghost vehicle."""
from __future__ import annotations
import json
import re
from pathlib import PurePosixPath
from pathlib import Path
from sim.network import write_json, sha256

SCHEMA = 'afterlight.replay.v1'


def validate_replay(replay: dict) -> None:
    from export.validation_base import validate_base_replay
    validate_base_replay(replay)
    validate_selection_evidence(replay)


def validate_selection_evidence(replay: dict) -> None:
    evidence=replay.get('selection_evidence')
    if evidence is None:return
    if not isinstance(evidence,dict) or evidence.get('schema')!='afterlight.selection-evidence.v1':
        raise ValueError('Unsupported optional selection evidence')
    kind=evidence.get('selector_kind')
    if kind not in {'residual_tree','analytical'}:raise ValueError('Unsupported frozen selector kind')
    hashes=('selector_sha256','study_sha256','protocol_sha256','release_sha256','report_sha256',
            'selection_sha256','trace_manifest_sha256','collection_manifest_sha256','comparison_artifact_sha256')
    if any(not isinstance(evidence.get(k),str) or not re.fullmatch(r'[0-9a-f]{64}',evidence[k]) for k in hashes):
        raise ValueError('Missing selection provenance hashes')
    for key in ('model_sha256','model_file_sha256'):
        value=evidence.get(key)
        if (kind=='analytical' and value is not None) or (kind=='residual_tree' and (not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value))):
            raise ValueError('Model identity inconsistent with selector kind')
    if replay['provenance'].get('model_sha256')!=evidence.get('model_sha256'):
        raise ValueError('Replay and selection model identities differ')
    lead=evidence.get('selected_lead_s')
    if isinstance(lead,bool) or not isinstance(lead,(int,float)) or lead not in (0,5,10,20,30):raise ValueError('Invalid selected fixed lead')
    lead=int(lead)  # Canonical JSON number spelling; 20.0 uses fixed-20 path.
    world=replay['worlds']['afterlight']
    if world.get('policy')!='fixed' or isinstance(world.get('lead_s'),bool) or world.get('lead_s')!=lead:
        raise ValueError('Selected replay must preserve recorded fixed-policy physics')
    decision=world.get('decision')
    if not isinstance(decision,dict) or decision.get('policy')!='fixed' or isinstance(decision.get('selected_lead_s'),bool) or decision.get('selected_lead_s')!=lead or decision.get('kind')!='dispatch' or decision.get('t')!=replay['scenario'].get('dispatch_s'):
        raise ValueError('Selected replay must preserve its frozen fixed-policy dispatch decision')
    if not isinstance(evidence.get('episode_id'),str) or not evidence['episode_id'] or evidence['episode_id']!=replay['scenario'].get('episode_id') or replay['scenario'].get('split')!='test':
        raise ValueError('Selected replay episode/split mismatch')
    case=evidence.get('case_id')
    if not isinstance(case,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',case):raise ValueError('Unsafe illustrative case identity')
    aliases=evidence.get('source_world_aliases')
    if not isinstance(aliases,dict) or set(aliases)!={'baseline','afterlight'}:raise ValueError('Explicit original world aliases required')
    for alias,item in aliases.items():
        if not isinstance(item,dict) or not isinstance(item.get('original_world_id'),str) or not item['original_world_id']:
            raise ValueError('Original world identity missing')
        if not isinstance(item.get('trace_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',item['trace_sha256']):raise ValueError('Original trace hash missing')
        path=item.get('trace_file')
        expected=f"worlds/{case}/"+('ordinary' if alias=='baseline' else f'fixed-{lead}')+'/rich-world.json'
        if not isinstance(path,str) or path!=expected or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or '\\' in path:
            raise ValueError('Trace path must name its retained artifact, never an external fetch')
    if not isinstance(evidence.get('interpretation'),str) or not evidence['interpretation']:
        raise ValueError('Selection interpretation required')


def save_replay(path: Path, replay: dict) -> dict:
    validate_replay(replay)
    # Preserve every measured value while avoiding megabytes of repeated
    # indentation in dense city recordings. Raw tripinfo/lifecycle are retained
    # independently; compact JSON is still directly inspectable and hash-bound.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay, separators=(',', ':'), allow_nan=False)+'\n',
                    encoding='utf-8', newline='\n')
    return {'sha256': sha256(path), 'bytes': path.stat().st_size, 'schema': SCHEMA,
            'duration_s': replay['duration_s'], 'step_s': replay['step_s']}
