"""Source-bound dual preview assembly. Default is read-only; --build opts in.

Usage: python scripts/build_preview.py --source-commit <full HEAD SHA> [--build]
Cloud/Linux build tool; Windows build execution is not supported by this helper.
Never installs dependencies, runs tests, changes Git state, or deletes old outputs.
Installed dependency versions are checked, not every installed package byte.
Obsolete manifest-owned chunks remain on disk but are no longer in the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ('vite', 'typescript', 'react', 'react-dom', 'scheduler', 'three')
LICENSES = {name: f'{name}/LICENSE' for name in ('react', 'react-dom', 'scheduler', 'three')}
LICENSES['vite-runtime'] = 'vite/LICENSE.md'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or not relative.parts or any(x in ('.', '..') for x in name.split('/')) or '\\' in name or ':' in name:
        raise ValueError(f'Unsafe path: {name}')
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError(f'Redirected path: {name}')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Escaping path: {name}')
    return path


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=root, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout


def is_source(name: str) -> bool:
    if name.startswith(('web/src/', 'web/scripts/')):
        return True
    if name.startswith('web/public/'):
        return not name.startswith(('web/public/assets/', 'web/public/replays/'))
    return name.startswith('web/') and name.count('/') == 1 and (
        name.endswith(('.json', '.html', '.js', '.mjs', '.cjs', '.ts'))
        or Path(name).name.startswith('.env') or Path(name).name == '.npmrc')


def is_asset(name: str) -> bool:
    return name.startswith('assets/exports/') or name in (
        'assets/map/city_manifest.json', 'assets/previews/city_overview.png')


def snapshot(root: Path, commit: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('Expected the explicit full current HEAD commit')
    entries = {}
    for record in git(root, 'ls-tree', '-rz', commit).split(b'\0'):
        if not record:
            continue
        meta, raw_name = record.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode('utf-8')
        if is_source(name) or is_asset(name) or name in ('scripts/serve_preview.py', 'scripts/build_preview.py') or name.startswith('preview/licenses/'):
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise ValueError(f'Unsupported source entry: {name}')
            entries[name] = (mode, oid)
    required = {'web/package.json', 'web/package-lock.json', 'web/index.html', 'web/tsconfig.json',
                'web/public/favicon.svg', 'scripts/serve_preview.py', 'scripts/build_preview.py'}
    if not required.issubset(entries):
        raise ValueError('Commit the complete builder and frontend sources before building')
    # Include ignored files: an ignored source or .env still affects compilation.
    disk = set()
    for folder in ('web', 'assets/exports', 'assets/map', 'assets/previews'):
        base = safe(root, folder)
        for current, dirs, files in os.walk(base, followlinks=False):
            relative_dir = Path(current).relative_to(root).as_posix()
            dirs[:] = [d for d in dirs if not (relative_dir == 'web' and d in ('node_modules', 'dist', 'tests')) and not (relative_dir == 'web/public' and d in ('assets', 'replays'))]
            for directory in dirs:
                safe(root, f'{relative_dir}/{directory}')
            for filename in files:
                name = f'{relative_dir}/{filename}'
                if is_source(name) or is_asset(name):
                    safe(root, name)
                    disk.add(name)
    expected = {n for n in entries if is_source(n) or is_asset(n)}
    if disk != expected:
        raise ValueError(f'Untracked/missing build inputs: {sorted(disk ^ expected)}')
    if (root / '.npmrc').exists() or (root / '.npmrc').is_symlink():
        raise ValueError('Remove repository .npmrc build overrides before compilation')
    if any(Path(n).name.startswith('.env') or Path(n).name == '.npmrc' for n in disk):
        raise ValueError('Remove .env/.npmrc build inputs; preview environments are explicit')
    indexed = {}
    for record in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if record:
            meta, name = record.split(b'\t', 1)
            mode, oid, stage = meta.decode().split()
            if name.decode() in entries:
                if stage != '0':
                    raise ValueError('Unmerged build input')
                indexed[name.decode()] = (mode, oid)
    if indexed != entries:
        raise ValueError('Staged build inputs differ from HEAD')
    sections = {'source_files': {}, 'runtime_assets': {}}
    for name, (_, oid) in sorted(entries.items()):
        data = safe(root, name).read_bytes()
        blob = git(root, 'cat-file', 'blob', oid)
        if os.name != 'nt' and bool(safe(root, name).stat().st_mode & 0o111) != (entries[name][0] == '100755'):
            raise ValueError(f'Working source mode differs from HEAD: {name}')
        if data != blob:
            raise ValueError(f'Actual source bytes differ from HEAD: {name}')
        section = 'runtime_assets' if is_asset(name) else 'source_files'
        sections[section][name] = digest(data)
    if git(root, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise ValueError('HEAD changed during source inspection')
    return sections


def environment(root: Path) -> tuple[dict, dict[str, bytes]]:
    locked = json.loads(safe(root, 'web/package-lock.json').read_bytes())['packages']
    versions = {}
    for name in PACKAGES:
        installed = json.loads(safe(root, f'web/node_modules/{name}/package.json').read_bytes())['version']
        if installed != locked[f'node_modules/{name}']['version']:
            raise ValueError(f'Installed {name} differs from lockfile')
        versions[name] = installed
    for command in ('node', 'npm'):
        executable = shutil.which(command)
        if executable is None:
            raise ValueError(f'{command} is not installed')
        versions[command] = subprocess.run([executable, '--version'], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip().removeprefix('v')
    licenses = {}
    for name, relative in LICENSES.items():
        original = safe(root, f'preview/licenses/{name}-LICENSE.txt').read_bytes()
        installed = safe(root, f'web/node_modules/{relative}').read_bytes()
        if name == 'vite-runtime':
            installed = installed.split(b'\n# Licenses of bundled dependencies', 1)[0].rstrip() + b'\n'
        if not original.strip() or original != installed:
            raise ValueError(f'Missing or mismatched retained runtime license: {name}')
        licenses[f'preview/licenses/{name}-LICENSE.txt'] = original
    return versions, licenses


def collect_outputs(static: Path, local: Path, favicon: bytes) -> dict[str, bytes]:
    outputs = {'preview/site/favicon.svg': favicon}
    for folder, entry in ((static, 'index.html'), (local, 'local.html')):
        outputs[f'preview/site/{entry}'] = safe(folder, 'index.html').read_bytes()
        assets = safe(folder, 'assets')
        chunks = sorted(p for p in assets.iterdir() if p.suffix in ('.js', '.css'))
        if not chunks or not any(p.suffix == '.js' for p in chunks):
            raise ValueError('Build emitted no JavaScript chunks')
        for chunk in chunks:
            payload = safe(folder, f'assets/{chunk.name}').read_bytes()
            name = f'preview/site/assets/{chunk.name}'
            if name in outputs and outputs[name] != payload:
                raise ValueError(f'Build chunk name collision: {name}')
            outputs[name] = payload
    return outputs


def allowed_output(name: str) -> bool:
    return name in ('preview/site/index.html', 'preview/site/local.html', 'preview/site/favicon.svg') or bool(
        re.fullmatch(r'preview/site/assets/[A-Za-z0-9_.-]+\.(js|css)', name))


def publish(root: Path, outputs: dict[str, bytes], manifest: dict, old_manifest: bytes) -> None:
    old = json.loads(old_manifest)
    backups = {}
    for name in outputs:
        if not allowed_output(name):
            raise ValueError(f'Not a preview output: {name}')
        path = safe(root, name)
        if path.exists():
            before = path.read_bytes()
            if old.get('output_files', {}).get(name) != digest(before):
                raise ValueError(f'Unowned or edited output: {name}')
            backups[name] = before
        else:
            backups[name] = None
    manifest_path = safe(root, 'preview/manifest.json')
    if manifest_path.read_bytes() != old_manifest:
        raise ValueError('Preview manifest changed during build')
    written = []
    try:
        for name, payload in outputs.items():
            path = safe(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Recheck each target immediately before replacing it.
            if (path.read_bytes() if path.exists() else None) != backups[name]:
                raise ValueError(f'Preview output changed during assembly: {name}')
            atomic_write(path, payload)
            written.append(name)
        if manifest_path.read_bytes() != old_manifest:
            raise ValueError('Preview manifest changed during assembly')
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + '\n').encode())
    except BaseException:
        for name in reversed(written):
            path = safe(root, name)
            if path.read_bytes() != outputs[name]:
                continue  # Never overwrite somebody else's concurrent edit.
            if backups[name] is None:
                path.unlink()  # Only our newly created output, never arbitrary files.
            else:
                atomic_write(path, backups[name])
        raise


def atomic_write(path: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.preview-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root: Path, commit: str, *, execute: bool = False) -> dict:
    inputs = snapshot(root, commit)
    versions, licenses = environment(root)
    old_manifest = safe(root, 'preview/manifest.json').read_bytes()
    plan = {'source_commit': commit, 'build_environment': versions, **inputs,
            'action': 'build' if execute else 'plan', 'tests_executed': False}
    if not execute:
        return plan
    npm = shutil.which('npm')
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('VITE_') and k not in ('NODE_OPTIONS', 'NODE_ENV')}
    # Scratch outputs are newly allocated, never a caller-selected deletion target.
    with tempfile.TemporaryDirectory(prefix='afterlight-preview-') as scratch:
        static, local = Path(scratch) / 'static', Path(scratch) / 'local'
        for output, api_base in ((static, None), (local, 'http://127.0.0.1:8765')):
            build_env = dict(env)
            if api_base:
                build_env['VITE_API_BASE'] = api_base
            subprocess.run([npm, 'run', 'build', '--prefix', 'web', '--', '--outDir', str(output), '--emptyOutDir'],
                           cwd=root, env=build_env, check=True)
        if snapshot(root, commit) != inputs or environment(root) != (versions, licenses):
            raise ValueError('Build source/runtime changed during compilation')
        outputs = collect_outputs(static, local, safe(root, 'web/public/favicon.svg').read_bytes())
        manifest = {'schema_version': 1, 'source_commit': commit, 'build_environment': versions,
            'entries': {'index.html': {'VITE_API_BASE': None}, 'local.html': {'VITE_API_BASE': 'http://127.0.0.1:8765'}},
            'validation_status': 'Compilation only. Omen tests and browser acceptance pending. No new simulation results claimed.',
            **inputs, 'output_files': {name: digest(data) for name, data in sorted({**outputs, **licenses,
                'scripts/serve_preview.py': safe(root, 'scripts/serve_preview.py').read_bytes()}.items())}}
        publish(root, outputs, manifest, old_manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--build', action='store_true', help='Explicitly run both npm compilations and assemble preview')
    args = parser.parse_args()
    if os.name == 'nt':
        parser.error('Run this build helper on the cloud/Linux computer; serve the resulting preview on Omen')
    print(json.dumps(build(ROOT, args.source_commit, execute=args.build), indent=2))


if __name__ == '__main__':
    main()
