"""Register an audited genuine city recording in the static viewer library.

This copies exact recorded bytes; it does not run SUMO, invent frames, deploy or
publish a website. Review resulting artifacts before a separate Git publication.
"""
from __future__ import annotations
import argparse
import json
import hashlib
import os
from pathlib import Path
import re
import uuid
from export.replay import validate_replay
from sim.audit import audit
from sim.network import ROOT, sha256


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as handle:
            json.dump(value,handle,indent=2,allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()


def _install_bytes_exclusive(target: Path, payload: bytes, expected_sha256: str) -> None:
    """No partial final filename and no overwrite, even under a concurrent writer."""
    temporary=target.with_name(f'.{target.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        if sha256(temporary)!=expected_sha256:
            raise ValueError('Copied recording digest mismatch')
        try:
            # Atomic same-filesystem publication with exclusive target name.
            # Unlike POSIX rename, link refuses to replace existing evidence.
            os.link(temporary,target)
        except FileExistsError:
            if sha256(target)!=expected_sha256:
                raise ValueError('A concurrent writer installed different recording bytes')
    finally:
        if temporary.exists(): temporary.unlink()


def register(run: Path, destination: Path) -> dict:
    source = run/'replay.json'
    source_bytes = source.read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    replay = json.loads(source_bytes)
    validate_replay(replay)
    if replay['scenario']['network_kind'] != 'city':
        raise ValueError('The city viewer library accepts city recordings only; retain fixture artifacts separately')
    provenance = replay['provenance']
    if not re.fullmatch(r'[0-9a-f]{40}',provenance['source_commit']):
        raise ValueError('A real repository source commit is required, not a unit-test fixture')
    if provenance.get('source_dirty') is not False:
        raise ValueError('Public-library registration requires a clean recorded source checkpoint')
    if provenance.get('canonical_map_sha256') != sha256(ROOT/'assets/map/city_manifest.json'):
        raise ValueError('Recording canonical map differs from current viewer assets')
    if any(world['status']=='infrastructure_error' for world in replay['worlds'].values()):
        raise ValueError('Infrastructure failures are retained locally, not registered as complete recordings')
    # Censored/invalid simulation outcomes remain admissible evidence, with
    # explicit statuses. They are never relabeled successful or omitted.
    for world in ('baseline','afterlight'):
        if not (run/world/'tripinfo.xml').is_file() or not (run/world/'lifecycle.json').is_file():
            raise ValueError('Raw SUMO lifecycle evidence is missing')
    audit_result = audit(run)
    if audit_result['replay_sha256'] != source_digest or sha256(source) != source_digest:
        raise ValueError('Recording changed during validation; no catalog registration performed')
    scenario = replay['scenario']
    identity = scenario['id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',identity):
        raise ValueError('Recording identity is not a safe filename')
    destination.mkdir(parents=True,exist_ok=True)
    lock = destination/'.catalog.lock'
    try:
        descriptor = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise RuntimeError('Catalog registration already active (or stale .catalog.lock); inspect before retrying') from exc
    os.close(descriptor)
    try:
        catalog_path = destination/'catalog.json'
        catalog = json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {'schema':'afterlight.catalog.v1','runs':[]}
        if catalog.get('schema')!='afterlight.catalog.v1' or not isinstance(catalog.get('runs'),list):
            raise ValueError('Existing recording catalog is malformed; refusing to replace it')
        ids = [entry.get('id') for entry in catalog['runs']]
        if len(ids)!=len(set(ids)) or any(not isinstance(item,str) for item in ids):
            raise ValueError('Existing recording catalog has invalid/duplicate IDs')
        digest = source_digest
        target = destination/f'{identity}.json'
        if target.exists() and sha256(target)!=digest:
            raise ValueError('This recording ID already has different bytes; prior evidence will not be overwritten')
        existing = next((entry for entry in catalog['runs'] if entry['id']==identity),None)
        if existing is not None:
            if existing.get('sha256') != digest or not target.is_file():
                raise ValueError('Existing catalog entry does not match exact recording bytes')
            return {'status':'already_registered','entry':existing,'changed':False}
        if not target.exists():
            _install_bytes_exclusive(target,source_bytes,digest)
        afterlight = replay['worlds']['afterlight']
        selected = afterlight.get('lead_s')
        policy_label = afterlight['policy'] + (f' · {selected} s lead' if selected is not None else '')
        entry = {'id':identity,'title':f'{scenario["pickup_id"]} → {scenario["hospital_id"]} · Seed {scenario["seed"]}',
                 'url':target.name,'seed':scenario['seed'],'pickup_id':scenario['pickup_id'],
                 'hospital_id':scenario['hospital_id'],'policy':policy_label,'duration_s':replay['duration_s'],
                 'sha256':digest,'bytes':target.stat().st_size,'source_commit':provenance['source_commit'],
                 'world_status':{name:world['status'] for name,world in replay['worlds'].items()},
                 'evidence_url':f'{identity}.evidence.json'}
        evidence = {'schema':'afterlight.recording-evidence.v1','replay_sha256':digest,
                    'provenance':provenance,'audit':audit_result,
                    'outcomes':json.loads((run/'outcomes.json').read_text(encoding='utf-8')),
                    'raw_outputs_note':'Full tripinfo and lifecycle files retained in original run directory; this is the compact public evidence companion.'}
        evidence_path = destination/f'{identity}.evidence.json'
        if evidence_path.exists():
            existing_evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
            if existing_evidence != evidence:
                raise ValueError('Existing evidence companion differs; refusing overwrite')
        else:
            _atomic_json(evidence_path,evidence)
        catalog['runs'].append(entry)
        _atomic_json(catalog_path,catalog)
        return {'status':'registered','entry':entry,'changed':True,
                'publication':'local files prepared only; review and Git publication are separate'}
    finally:
        lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--destination',type=Path,default=ROOT/'web/public/replays')
    args=parser.parse_args()
    print(json.dumps(register(args.run.resolve(),args.destination.resolve()),indent=2))


if __name__=='__main__': main()
