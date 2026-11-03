"""One bounded byte/JSON boundary shared by HTTP and generation job readers."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import stat

MAX_REPLAY_BYTES = 128 * 1024 * 1024
# Explicitly opt in only for dense local generation artifacts. Public-library
# recordings, catalog/metadata readers, and ordinary JSON retain the lower cap.
MAX_LOCAL_JOB_REPLAY_BYTES = 256 * 1024 * 1024
MAX_JSON_DEPTH = 64  # Container nesting, including the root object; independent of Python recursion limits.


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


def bounded_json_text(payload: bytes, *, limit: int | None = None) -> str:
    """Reject deep UTF-8 JSON before decoding structures, with O(1) scan state.

    Brackets inside quoted strings are data. A backslash escapes precisely the
    next string character, so odd/even backslash runs and escaped quotes do not
    alter container depth. Full syntax validation remains json.loads' job.
    """
    maximum = MAX_REPLAY_BYTES if limit is None else limit
    if len(payload) > maximum:
        raise ArtifactError('Artifact exceeds the local API size limit')
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeError as error:
        raise ArtifactError('Artifact is not UTF-8 JSON') from error
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in '{[':
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ArtifactError(f'JSON container nesting exceeds depth {MAX_JSON_DEPTH}')
        elif character in '}]':
            depth -= 1
            if depth < 0:
                raise ArtifactError('Artifact has malformed JSON container nesting')
    return text


def parse_json_object(payload: bytes, *, limit: int | None = None) -> dict:
    text = bounded_json_text(payload,limit=limit)
    try:
        value = json.loads(text,parse_constant=reject_nonfinite,parse_float=finite_float)
    except (UnicodeError,ValueError,RecursionError) as error:
        raise ArtifactError('Artifact is not readable JSON') from error
    if not isinstance(value,dict):
        raise ArtifactError('Artifact root must be an object')
    return value


def read_json(path: Path) -> dict:
    return parse_json_object(read_bytes(path))
