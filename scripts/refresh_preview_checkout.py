"""Opt-in refresh of clean preview inputs using repository line-ending attributes.

Never changes global Git configuration or normalizes manifest hashes. Refuses
staged/unstaged content edits before refreshing only manifest-listed text paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def refresh() -> None:
    manifest = json.loads((ROOT / 'preview/manifest.json').read_text(encoding='utf-8'))
    paths = sorted(set(manifest['source_files']) | set(manifest['output_files']) |
                   {path for path in manifest['runtime_assets'] if path.endswith('.json')})
    for name in paths:
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'Missing or unsafe input: {name}')
    def git(*arguments: str) -> None:
        subprocess.run(['git', *arguments], cwd=ROOT, check=True)
    # CRLF checkout conversion is not a content edit. Any actual content edit,
    # staged change, conflict, or untracked input aborts before a file is written.
    git('ls-files', '--error-unmatch', '--', *paths)
    git('diff', '--quiet', '--', *paths)
    git('diff', '--cached', '--quiet', '--', *paths)
    git('checkout-index', '--force', '--', *paths)
    print(f'Refreshed {len(paths)} clean tracked text inputs using repository attributes.')
    print('Next: python scripts/serve_preview.py --verify-only')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-clean-checkout', action='store_true', required=True,
                        help='Explicitly permit refreshing manifest-listed clean tracked files')
    parser.parse_args()
    refresh()


if __name__ == '__main__':
    main()
