"""Restore exact indexed preview bytes only after clean-content and hash guards.

No global configuration, index contents, normalization, or unrelated paths change.
The explicit opt-in permits atomic replacement of clean manifest-listed inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def refresh() -> None:
    manifest = json.loads((ROOT / 'preview/manifest.json').read_text(encoding='utf-8'))
    expected = {**manifest['source_files'], **manifest['output_files'],
                **{path: value for path, value in manifest['runtime_assets'].items() if path.endswith('.json')}}
    paths = sorted(expected)
    originals = {}
    for name in paths:
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or (ROOT / name).is_symlink():
            raise ValueError(f'Missing or unsafe input: {name}')
        originals[name] = path.read_bytes()

    def git(*arguments: str, capture: bool = False):
        return subprocess.run(['git', *arguments], cwd=ROOT, check=True,
                              stdout=subprocess.PIPE if capture else None)

    # Git content guards run before extracting or replacing any input.
    git('ls-files', '--error-unmatch', '--', *paths)
    git('diff', '--quiet', '--', *paths)
    git('diff', '--cached', '--quiet', '--', *paths)
    canonical = {}
    for name in paths:
        data = git('show', f':{name}', capture=True).stdout
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise ValueError(f'Indexed source does not match preview manifest: {name}; no files replaced')
        canonical[name] = data
    changed = 0
    for name in paths:
        path = ROOT / name
        if path.read_bytes() != originals[name]:
            raise ValueError(f'Input changed during refresh: {name}; stop and preserve edits')
        if originals[name] == canonical[name]:
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.afterlight-lf-', suffix='.tmp', dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(canonical[name])
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            # Recheck immediately before replacement; never overwrite new edits.
            if path.read_bytes() != originals[name]:
                raise ValueError(f'Input changed during refresh: {name}; stop and preserve edits')
            os.replace(temporary, path)
            changed += 1
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    for name in paths:
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected[name]:
            raise ValueError(f'Exact-byte refresh postcondition failed: {name}')
    git('diff', '--quiet', '--', *paths)
    git('diff', '--cached', '--quiet', '--', *paths)
    print(f'Verified {len(paths)} exact indexed text inputs; atomically refreshed {changed}.')
    print('Next: python scripts/serve_preview.py --verify-only')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-clean-checkout', action='store_true', required=True,
                        help='Permit exact-byte atomic replacement of clean manifest-listed tracked files')
    parser.parse_args()
    refresh()


if __name__ == '__main__':
    main()
