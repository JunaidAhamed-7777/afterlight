"""Register an audited genuine city recording in the static viewer library.

This copies exact recorded bytes; it does not run SUMO, invent frames, deploy or
publish a website. Review resulting artifacts before a separate Git publication.
"""
from __future__ import annotations
import argparse
import gzip
import io
import json
import hashlib
import os
from pathlib import Path
import re
import uuid
from export.replay import validate_replay
from sim.audit import audit, audit_outcomes
from sim.network import ROOT, sha256

MAX_PUBLIC_FILE_BYTES=20*1024*1024  # Strictly below the documented static-release ceiling.
MAX_DECODED_REPLAY_BYTES=128*1024*1024  # Dense 0.5 s captures; viewer/API share this boundary.


def _gzip_bytes(payload: bytes) -> bytes:
    """Lossless transport packaging; never rewrite the recorded JSON values."""
    output=io.BytesIO()
    with gzip.GzipFile(filename='',mode='wb',fileobj=output,compresslevel=9,mtime=0) as stream:
        stream.write(payload)
    encoded=output.getvalue()
    if len(encoded)>=MAX_PUBLIC_FILE_BYTES:
        raise ValueError('Compressed recording is at least 20 MiB; use bounded indexed chunks before publication')
    if gzip.decompress(encoded)!=payload:
        raise ValueError('Compressed recording failed its exact-byte roundtrip')
    return encoded

def _public_json_bytes(value: dict) -> bytes:
    payload=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if len(payload)>=MAX_PUBLIC_FILE_BYTES:
        raise ValueError('Public JSON is at least 20 MiB; compact JSON or implement indexed chunks before publication. Scientific inputs/outcomes must remain intact.')
    return payload


def _atomic_json(path: Path, value: dict) -> None:
    payload=_public_json_bytes(value)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
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


def register(run: Path, destination: Path, *, compress: bool = False, title: str | None = None) -> dict:
    source = run/'replay.json'
    limit=MAX_DECODED_REPLAY_BYTES if compress else MAX_PUBLIC_FILE_BYTES
    if source.stat().st_size>=limit:
        raise ValueError('Recording exceeds its decoded/physical limit; compact JSON or implement indexed chunks before static registration. Raw scientific evidence is unchanged.')
    with source.open('rb') as handle:
        source_bytes=handle.read(limit)
    if len(source_bytes)>=limit:
        raise ValueError('Recording grew beyond the public-file budget during registration')
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    replay = json.loads(source_bytes)
    validate_replay(replay)
    if replay['scenario']['network_kind'] != 'city':
        raise ValueError('The city viewer library accepts city recordings only; retain fixture artifacts separately')
    integration_steps=[world.get('metrics',{}).get('simulation_step_s') for world in replay['worlds'].values()]
    if any(isinstance(step,(int,float)) and not isinstance(step,bool) and replay['step_s']>step+1e-9
           for step in integration_steps):
        raise ValueError('Public city recordings must capture every integration boundary; coarse vehicle interpolation can cross red lights. Retain coarse scalar evidence locally and capture a fresh exploratory demo at --sample 0.5.')
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
    audit_result = audit(run, write_result=False)
    if audit_result['replay_sha256'] != source_digest or sha256(source) != source_digest:
        raise ValueError('Recording changed during validation; no catalog registration performed')
    scenario = replay['scenario']
    identity = scenario['id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',identity):
        raise ValueError('Recording identity is not a safe filename')
    outcomes=json.loads((run/'outcomes.json').read_text(encoding='utf-8'))
    audit_outcomes(replay,outcomes)
    evidence = {'schema':'afterlight.recording-evidence.v1','replay_sha256':source_digest,
                'provenance':provenance,'audit':audit_result,
                'outcomes':outcomes,
                'raw_outputs_note':'Full tripinfo and lifecycle files retained in original run directory; this is the compact public evidence companion.'}
    _public_json_bytes(evidence)  # Reject oversized companion before installing any public file.
    public_bytes=_gzip_bytes(source_bytes) if compress else source_bytes
    transfer_digest=hashlib.sha256(public_bytes).hexdigest()
    if title is not None and (not isinstance(title,str) or not title.strip() or len(title)>120):
        raise ValueError('Recording title must be a nonempty label of at most 120 characters')
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
        target = destination/(f'{identity}.json.gz' if compress else f'{identity}.json')
        if target.exists() and sha256(target)!=transfer_digest:
            raise ValueError('This recording ID already has different bytes; prior evidence will not be overwritten')
        existing = next((entry for entry in catalog['runs'] if entry['id']==identity),None)
        if existing is not None:
            if existing.get('sha256') != digest:
                raise ValueError('Existing catalog entry does not match exact recording bytes')
        afterlight = replay['worlds']['afterlight']
        selected = afterlight.get('lead_s')
        policy_label = afterlight['policy'] + (f' · {selected} s lead' if selected is not None else '')
        entry = {'id':identity,'title':title or (existing or {}).get('title') or f'{scenario["pickup_id"]} → {scenario["hospital_id"]} · Seed {scenario["seed"]}',
                 'url':target.name,'seed':scenario['seed'],'pickup_id':scenario['pickup_id'],
                 'hospital_id':scenario['hospital_id'],'policy':afterlight['policy'],
                 'lead_s':selected,'policy_label':policy_label,'duration_s':replay['duration_s'],
                 'sha256':digest,'bytes':len(source_bytes),'source_commit':provenance['source_commit'],
                 'world_status':{name:world['status'] for name,world in replay['worlds'].items()},
                 'evidence_url':f'{identity}.evidence.json'}
        if compress:
            entry.update(encoding='gzip',transfer_bytes=len(public_bytes),transfer_sha256=transfer_digest)
        evidence_path = destination/f'{identity}.evidence.json'
        if evidence_path.exists():
            existing_evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
            if existing_evidence != evidence:
                raise ValueError('Existing evidence companion differs; refusing overwrite')
        if existing is not None:
            if existing==entry and target.is_file() and evidence_path.is_file():
                return {'status':'already_registered','entry':existing,'changed':False}
            catalog['runs'][catalog['runs'].index(existing)]=entry
        else:
            catalog['runs'].append(entry)
        _public_json_bytes(catalog)  # Check every public JSON budget before installing artifacts.
        if not target.exists():
            _install_bytes_exclusive(target,public_bytes,transfer_digest)
        if not evidence_path.exists():
            _atomic_json(evidence_path,evidence)
        _atomic_json(catalog_path,catalog)
        return {'status':'registered','entry':entry,'changed':True,
                'publication':'local files prepared only; review and Git publication are separate'}
    finally:
        lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--destination',type=Path,default=ROOT/'web/public/replays')
    parser.add_argument('--gzip',action='store_true',help='losslessly gzip replay transport; retain original decoded SHA256 and byte count')
    parser.add_argument('--title',help='short human-readable recording label')
    args=parser.parse_args()
    print(json.dumps(register(args.run.resolve(),args.destination.resolve(),compress=args.gzip,title=args.title),indent=2))


if __name__=='__main__': main()
