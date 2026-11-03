"""One bounded byte/JSON boundary shared by HTTP and generation job readers."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import stat

MAX_REPLAY_BYTES = 64 * 1024 * 1024


class ArtifactError(Exception):
    """Absent/invalid artifact, never a simulated traffic outcome."""


def reject_nonfinite(value: str):
    raise ValueError(f'Non-finite JSON: {value}')


def finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError('JSON floating-point value exceeds finite range')
    return parsed


def read_bytes(path: Path, *, limit: int | None = None) -> bytes:
    """Bound both the open file size and the actual read, including file growth."""
    maximum = MAX_REPLAY_BYTES if limit is None else limit
    try:
        if not path.is_file():
            raise ArtifactError('Artifact is not available as a regular file')
        with path.open('rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ArtifactError('Artifact must be a regular file')
            if info.st_size > maximum:
                raise ArtifactError('Artifact exceeds the local API size limit')
            payload = stream.read(maximum+1)
    except OSError as error:
        raise ArtifactError('Artifact is not available') from error
    if len(payload) > maximum:
        raise ArtifactError('Artifact exceeds the local API size limit')
    return payload


def parse_json_object(payload: bytes) -> dict:
    try:
        value = json.loads(payload,parse_constant=reject_nonfinite,parse_float=finite_float)
    except (UnicodeError,ValueError,RecursionError) as error:
        raise ArtifactError('Artifact is not readable JSON') from error
    if not isinstance(value,dict):
        raise ArtifactError('Artifact root must be an object')
    return value


def read_json(path: Path) -> dict:
    return parse_json_object(read_bytes(path))
