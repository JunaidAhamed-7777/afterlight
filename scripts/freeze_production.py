"""Freeze one committed static production build; default is a read-only plan.

Reuses the existing strict preview guards. --build prepares authoritative asset
copies, builds into a fresh ignored local-runtime child, and writes a manifest
outside its served site. Existing outputs are never reused or removed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SELF = 'scripts/freeze_production.py'
HELPER = 'scripts/build_preview.py'
CONFIGS = ('vercel.json', '.vercelignore', '.gitattributes', '.gitignore', 'package.json', 'package-lock.json', 'npm-shrinkwrap.json')
EXPECTED_PREPARED_FILES = 18
MAX_PRODUCTION_BYTES = 50_000_000


def sha(data): return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def ordinary(root, path):
    """Bootstrap path check before the verified helper can supply safe()."""
    relative = path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
            raise ValueError('Redirected production-freeze path')
    if not path.resolve().is_relative_to(root): raise ValueError('Production-freeze path escapes the checkout')
    return path


def owned_output(root, output):
    root = root.resolve()
    requested = Path(output)
    if '..' in requested.parts: raise ValueError('Output cannot contain parent traversal')
    target = requested if requested.is_absolute() else root / requested
    ordinary(root, target)
    runtime = ordinary(root, root / 'local-runtime')
    if target.parent != runtime or target.name in ('', '.', '..'):
        raise ValueError('Output must be a direct child of this checkout local-runtime')
    if target.exists(): raise FileExistsError('Choose a fresh production snapshot; existing output is preserved')
    if runtime.exists() and not runtime.is_dir(): raise ValueError('local-runtime must be an ordinary directory')
    return target


def load_guards(root, commit):
    if not re.fullmatch(r'[a-f0-9]{40}', commit) or git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('Supply the explicit full current HEAD')
    raw = ordinary(root, root / HELPER).read_bytes()
    if raw != git(root, 'show', commit + ':' + HELPER): raise ValueError('Preview guard bytes differ from committed HEAD')
    if ordinary(root, root / SELF).read_bytes() != git(root, 'show', commit + ':' + SELF):
        raise ValueError('Production freezer bytes differ from committed HEAD')
    spec = spec_from_file_location('afterlight_production_preview_guards', root / HELPER)
    if spec is None or spec.loader is None: raise ValueError('Cannot load preview guards')
    module = module_from_spec(spec)
    exec(compile(raw, str(root / HELPER), 'exec', dont_inherit=True), module.__dict__)
    return module


def reject_hidden_config(root):
    # Windows resolves these names without case sensitivity. Check directory
    # entries rather than relying on the older preview source-name classifier.
    for directory in (root, ordinary(root, root / 'web')):
        for path in directory.iterdir():
            name = path.name.casefold()
            if name.startswith('.env') or name == '.npmrc':
                raise ValueError('Remove case-insensitive .env*/.npmrc configuration before freezing: ' + path.name)


def tree_and_index(root, commit):
    tree = {}; index = {}
    for row in git(root, 'ls-tree', '-rz', commit).split(b'\0'):
        if not row: continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = name.decode('utf-8')
        if path.startswith('web/public/') or path in CONFIGS or path == SELF:
            if kind != 'blob' or mode not in ('100644', '100755'): raise ValueError('Nonregular committed production input')
            tree[path] = (mode, oid)
    for row in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not row: continue
        metadata, name = row.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        path = name.decode('utf-8')
        if path.startswith('web/public/') or path in CONFIGS or path == SELF:
            if stage != '0' or path in index: raise ValueError('Unmerged or duplicate production input')
            index[path] = (mode, oid)
    if tree != index: raise ValueError('Production public/config index differs from HEAD')
    if not {SELF, 'vercel.json', '.gitignore'} <= tree.keys(): raise ValueError('Commit the freezer and deployment configuration first')
    return tree


def disk_files(root, directory, guards):
    result = set()
    start = guards.safe(root, directory)
    for current, folders, files in os.walk(start, followlinks=False):
        relative = Path(current).relative_to(root).as_posix()
        for folder in folders: guards.safe(root, relative + '/' + folder)
        for filename in files:
            name = relative + '/' + filename
            if not guards.safe(root, name).is_file(): raise ValueError('Nonregular production file')
            result.add(name)
    return result


def inputs(root, commit, guards, *, prepared):
    existing = guards.snapshot(root, commit)
    expected_mirror = {'web/public/' + name: value for name, value in existing['runtime_assets'].items()}
    if len(expected_mirror) != EXPECTED_PREPARED_FILES: raise ValueError('Authoritative prepared-asset inventory must contain exactly 18 files')
    tree = tree_and_index(root, commit)
    if {name for name in tree if name.startswith('web/public/assets/')} - expected_mirror.keys():
        raise ValueError('Committed generated asset is outside the authoritative mirror')
    public = disk_files(root, 'web/public', guards)
    actual_mirror = {name for name in public if name.startswith('web/public/assets/')}
    if actual_mirror - expected_mirror.keys(): raise ValueError('Unexpected generated public asset; do not silently ship stale files')
    if prepared and actual_mirror != expected_mirror.keys(): raise ValueError('Prepared public asset file set is incomplete')
    nongenerated = public - actual_mirror
    expected_public = {name for name in tree if name.startswith('web/public/') and not name.startswith('web/public/assets/')}
    if nongenerated != expected_public: raise ValueError('Untracked or missing public production input')
    actual_configs = {name for name in CONFIGS if guards.safe(root, name).exists()}
    if actual_configs != set(CONFIGS) & tree.keys(): raise ValueError('Untracked or missing deployment configuration')
    supplemental = {}
    for name, (_, oid) in tree.items():
        if name.startswith('web/public/assets/') and not prepared: continue
        data = guards.safe(root, name).read_bytes()
        if data != git(root, 'cat-file', 'blob', oid): raise ValueError('Production input bytes differ from HEAD: ' + name)
        if os.name != 'nt' and bool(guards.safe(root, name).stat().st_mode & 0o111) != (tree[name][0] == '100755'):
            raise ValueError('Production input mode differs from HEAD: ' + name)
        supplemental[name] = sha(data)
    mirror = {}
    if prepared:
        for name, expected in expected_mirror.items():
            value = sha(guards.safe(root, name).read_bytes())
            if value != expected: raise ValueError('Prepared public asset differs from authoritative source: ' + name)
            mirror[name] = value
    if git(root, 'rev-parse', 'HEAD').decode().strip() != commit: raise ValueError('HEAD changed during production input inspection')
    return {**existing, 'supplemental_files': supplemental, 'prepared_public_assets': mirror}


def disabled_npm_configs(root, target):
    paths = {'NPM_CONFIG_USERCONFIG': target / '.disabled-user.npmrc',
             'NPM_CONFIG_GLOBALCONFIG': target / '.disabled-global.npmrc'}
    for path in paths.values():
        ordinary(root, path)
        if path.exists(): raise ValueError('Controlled npm configuration must remain absent')
    return {key: str(path) for key, path in paths.items()}


def controlled_key(key):
    return key.upper().startswith(('VITE_', 'NPM_CONFIG_')) or key.upper() in ('NODE_OPTIONS', 'NODE_ENV')


@contextmanager
def controlled_environment(npm_configs):
    removed = {key: value for key, value in os.environ.items() if controlled_key(key)}
    for key in removed: os.environ.pop(key)
    os.environ.update(npm_configs)
    try:
        yield dict(os.environ)
    finally:
        for key in list(os.environ):
            if controlled_key(key): os.environ.pop(key)
        os.environ.update(removed)


def inventory(root, directory, guards):
    result = {}
    for name in sorted(disk_files(root, directory.relative_to(root).as_posix(), guards)):
        data = guards.safe(root, name).read_bytes()
        result[(root / name).relative_to(directory).as_posix()] = {'bytes': len(data), 'sha256': sha(data)}
    if not result: raise ValueError('Production output is empty')
    return result


def source_identity(commit, sections):
    combined = {}
    for section in sections.values():
        for name, value in section.items():
            if name in combined and combined[name] != value: raise ValueError('Conflicting production input hashes')
            combined[name] = value
    return {'head': commit, 'files': dict(sorted(combined.items())),
            'source_sha256': sha(json.dumps(combined, sort_keys=True, separators=(',', ':')).encode())}


def _verify_manifest(root, manifest_path, *, expected_name, expected_manifest_sha256=None):
    root = root.resolve(); path = Path(manifest_path)
    path = path if path.is_absolute() else root / path
    ordinary(root, path)
    if path.name != expected_name or path.parent.parent != root / 'local-runtime':
        raise ValueError('Use a manifest in a direct checkout local-runtime child')
    manifest_bytes = path.read_bytes()
    if expected_manifest_sha256 is not None:
        if not re.fullmatch(r'[a-f0-9]{64}', expected_manifest_sha256) or sha(manifest_bytes) != expected_manifest_sha256:
            raise ValueError('Frozen manifest differs from the externally recorded checksum')
    manifest = json.loads(manifest_bytes)
    if manifest.get('schema') != 'afterlight.browser-build-snapshot.v2': raise ValueError('Unsupported production snapshot manifest')
    if source_identity(manifest['source']['head'], manifest['strict_inputs']) != manifest['source']:
        raise ValueError('Frozen source inventory metadata changed')
    # This is an output check, not another build. Main may advance after the
    # candidate was frozen; load current committed guards without relabeling the
    # candidate's original source commit or claiming current inputs match it.
    guards = load_guards(root, git(root, 'rev-parse', 'HEAD').decode().strip())
    actual = inventory(root, path.parent / 'site', guards)
    if actual != manifest['files'] or sum(row['bytes'] for row in actual.values()) != manifest['total_bytes']:
        raise ValueError('Frozen production file set or bytes changed')
    if path.read_bytes() != manifest_bytes: raise ValueError('Frozen manifest changed during output verification')
    return {'status': 'verified_frozen_file_set_and_bytes', 'files': len(actual), 'total_bytes': manifest['total_bytes'], 'manifest_sha256': sha(manifest_bytes)}


def verify_frozen(root, manifest_path, *, expected_manifest_sha256=None):
    return _verify_manifest(root, manifest_path, expected_name='manifest.json', expected_manifest_sha256=expected_manifest_sha256)


def freeze(root, commit, output, *, execute=False):
    root = root.resolve(); target = owned_output(root, output)
    reject_hidden_config(root)
    guards = load_guards(root, commit)
    npm_configs = disabled_npm_configs(root, target)
    with controlled_environment(npm_configs) as build_env:
        before = inputs(root, commit, guards, prepared=False)
        git(root, 'check-ignore', '--no-index', '--quiet', target.relative_to(root).as_posix() + '/site')
        versions, licenses = guards.environment(root)
        disabled_npm_configs(root, target)
        npm = guards.tool_commands()['npm']
        prepare_argv = [*npm, 'run', 'prepare:assets', '--prefix', 'web']
        build_argv = [*npm, 'run', 'build', '--prefix', 'web', '--', '--outDir', str(target / 'site'), '--emptyOutDir']
        if not execute:
            return {'status': 'plan_only_no_writes_or_build', 'source_commit': commit, 'output': str(target), 'prepared_asset_count': EXPECTED_PREPARED_FILES}
        owned_output(root, target)
        disabled_npm_configs(root, target)
        subprocess.run(prepare_argv, cwd=root, env=build_env, check=True, stdout=sys.stderr, stderr=sys.stderr)
        disabled_npm_configs(root, target)
        prepared = inputs(root, commit, guards, prepared=True)
        # The only permitted preparation changes are the authoritative mirror.
        expected_before = {**prepared, 'prepared_public_assets': {}}
        expected_before['supplemental_files'] = {name: value for name, value in prepared['supplemental_files'].items() if not name.startswith('web/public/assets/')}
        if expected_before != before: raise ValueError('Authoritative inputs changed during asset preparation')
        if guards.environment(root) != (versions, licenses): raise ValueError('Tool environment changed during asset preparation')
        disabled_npm_configs(root, target)
        owned_output(root, target)
        target.parent.mkdir(exist_ok=True)
        owned_output(root, target)
        target.mkdir(exist_ok=False)
        site = guards.safe(root, target.relative_to(root).as_posix() + '/site'); site.mkdir(exist_ok=False)
        disabled_npm_configs(root, target)
        subprocess.run(build_argv, cwd=root, env=build_env, check=True, stdout=sys.stderr, stderr=sys.stderr)
        disabled_npm_configs(root, target)
        if inputs(root, commit, guards, prepared=True) != prepared or guards.environment(root) != (versions, licenses):
            raise ValueError('Production inputs or tool environment changed during build')
        disabled_npm_configs(root, target)
        if {p.name for p in target.iterdir()} != {'site'}: raise ValueError('Unexpected file outside production site')
        files = inventory(root, site, guards)
        total_bytes = sum(value['bytes'] for value in files.values())
        if total_bytes >= MAX_PRODUCTION_BYTES: raise ValueError('Complete production site must remain below 50 MB')
        source = source_identity(commit, prepared)
        manifest = {'schema': 'afterlight.browser-build-snapshot.v2', 'source': source, 'strict_inputs': prepared,
                    'source_files_stable': True, 'build_environment': versions,
                    'build_license_sha256': {name: sha(value) for name, value in licenses.items()},
                    'compiled_env': {'VITE_API_BASE': None},
                    'build_env_policy': {'removed_patterns_case_insensitive': ['VITE_*', 'NODE_OPTIONS', 'NODE_ENV', 'npm_config_*'],
                                         'VITE_API_BASE_present': False, 'secret_values_recorded': False,
                                         'npm_config_policy': 'Distinct verified-absent user/global paths; no external user/global configuration loaded'},
                    'controlled_npm_config_paths': npm_configs,
                    'prepare_argv': prepare_argv, 'build_argv': build_argv,
                    'files': files, 'total_bytes': total_bytes}
        if git(root, 'rev-parse', 'HEAD').decode().strip() != commit: raise ValueError('HEAD changed before production manifest publication')
        manifest_bytes = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
        pending = guards.safe(root, target.relative_to(root).as_posix() + '/manifest.pending.json')
        final = guards.safe(root, target.relative_to(root).as_posix() + '/manifest.json')
        with pending.open('xb') as stream: stream.write(manifest_bytes)
        _verify_manifest(root, pending, expected_name='manifest.pending.json', expected_manifest_sha256=sha(manifest_bytes))
        # Atomic no-overwrite publication on the local filesystem. Rejected
        # postchecks retain only provisional evidence, never a final manifest.
        os.link(pending, final)
        guards.safe(root, pending.relative_to(root).as_posix()).unlink()
        return {'status': 'frozen', 'manifest': str(target / 'manifest.json'), 'manifest_sha256': sha(manifest_bytes), 'files': len(files), 'total_bytes': manifest['total_bytes']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', help='Explicit full current committed HEAD')
    parser.add_argument('--output', type=Path, help='Fresh direct child of this checkout local-runtime')
    parser.add_argument('--build', action='store_true', help='Prepare assets and compile into the fresh output')
    parser.add_argument('--verify', type=Path, help='Read-only complete frozen file-set and byte check')
    parser.add_argument('--manifest-sha256', help='Externally recorded checksum to pin the manifest during --verify')
    args = parser.parse_args()
    if args.verify:
        if args.source_commit or args.output or args.build: parser.error('--verify cannot be combined with build arguments')
        result = verify_frozen(ROOT, args.verify, expected_manifest_sha256=args.manifest_sha256)
    else:
        if args.manifest_sha256: parser.error('--manifest-sha256 requires --verify')
        if not args.source_commit or not args.output: parser.error('--source-commit and --output are required')
        result = freeze(ROOT, args.source_commit, args.output, execute=args.build)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
