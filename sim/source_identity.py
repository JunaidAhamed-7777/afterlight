"""Read-only source identity from Git objects/index and actual bytes, not stat cache.

Git status can retain false dirty entries on some Windows filesystems. This
check never refreshes/rewrites the index and never uses status as evidence.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

DIRECTORIES = ('sim','policies','models','evaluation','export')
MAP = 'assets/map/city_manifest.json'
SCOPE = (*DIRECTORIES, MAP)


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(['git', *arguments], cwd=root, stderr=subprocess.PIPE)


def _path(raw: bytes) -> str:
    name = os.fsdecode(raw)
    path = PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or '..' in path.parts or path.as_posix()!=name:
        raise ValueError('Unsafe scoped Git path')
    if name!=MAP and not any(name.startswith(directory+'/') for directory in DIRECTORIES):
        raise ValueError('Git returned path outside requested source scope')
    return name


def parse_tree(raw: bytes) -> dict[str, tuple[str,str]]:
    result = {}
    for entry in raw.split(b'\0'):
        if not entry:continue
        metadata, name = entry.split(b'\t',1)
        mode, kind, oid = metadata.decode('ascii').split(' ')
        path = _path(name)
        if path in result or kind!='blob' or mode not in {'100644','100755'}:
            raise ValueError('Duplicate or nonregular source tree entry')
        result[path] = (mode,oid)
    return result


def parse_index(raw: bytes) -> dict[str, tuple[str,str]]:
    result = {}
    for entry in raw.split(b'\0'):
        if not entry:continue
        metadata, name = entry.split(b'\t',1)
        mode, oid, stage = metadata.decode('ascii').split(' ')
        path = _path(name)
        if path in result or stage!='0' or mode not in {'100644','100755'}:
            raise ValueError('Unmerged, duplicate or nonregular source index entry')
        result[path] = (mode,oid)
    return result


def blob_id(data: bytes, algorithm: str) -> str:
    if algorithm not in {'sha1','sha256'}:
        raise ValueError('Unsupported Git object format')
    return hashlib.new(algorithm,b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()


def _redirected(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _safe_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    current = root
    for part in parts:
        current = current/part
        if _redirected(current):
            raise ValueError('Source symlink/junction is not an ordinary checkout file')
    if not current.resolve().is_relative_to(root) or not current.is_file():
        raise ValueError('Missing or escaping source file')
    return current


def _python_files(root: Path) -> tuple[set[str], bool]:
    """Include ignored Python additions; never recurse into redirected folders."""
    names = set()
    unsafe = False
    def fail_walk(error: OSError) -> None:
        raise error
    for directory in DIRECTORIES:
        start = root/directory
        if _redirected(start):
            unsafe = True
            continue
        if not start.exists():
            continue
        for current, folders, files in os.walk(start, followlinks=False, onerror=fail_walk):
            parent = Path(current)
            kept = []
            for folder in folders:
                child = parent/folder
                if _redirected(child) or not child.resolve().is_relative_to(root):
                    unsafe = True
                else:
                    kept.append(folder)
            folders[:] = kept
            for filename in files:
                if filename.casefold().endswith('.py'):
                    names.add((parent/filename).relative_to(root).as_posix())
    return names, unsafe


def source_snapshot(root: Path) -> dict:
    """Preserve the public four-field manifest contract; fail closed on errors."""
    root = root.resolve()
    files = {}
    commit = 'unavailable'
    dirty: bool | None = None
    cache = {}
    unsafe = False
    def read(relative: str) -> bytes:
        if relative not in cache:
            cache[relative] = _safe_file(root,relative).read_bytes()
        return cache[relative]
    try:
        names, unsafe = _python_files(root)
        names.add(MAP)
        for relative in sorted(names):
            try:
                files[relative] = hashlib.sha256(read(relative)).hexdigest()
            except (OSError,ValueError):
                unsafe = True
        commit = _git(root,'rev-parse','--verify','HEAD').decode('ascii').strip()
        algorithm = _git(root,'rev-parse','--show-object-format').decode('ascii').strip()
        if algorithm not in {'sha1','sha256'} or len(commit)!={'sha1':40,'sha256':64}[algorithm] or any(c not in '0123456789abcdef' for c in commit):
            raise ValueError('Invalid HEAD/object format')
        tree_raw = _git(root,'ls-tree','-r','-z','--full-tree',commit,'--',*SCOPE)
        index_raw = _git(root,'ls-files','--stage','-z','--',*SCOPE)
        untracked_raw = _git(root,'ls-files','--others','--exclude-standard','-z','--',*SCOPE)
        try:
            tree, index = parse_tree(tree_raw), parse_index(index_raw)
        except ValueError:
            # Unmerged stages and nonregular entries are real dirty states,
            # not a reason to trust cached status or read a symlink target.
            dirty = True
        else:
            dirty = unsafe or tree!=index or bool(untracked_raw)
            if names-set(tree):
                dirty = True
            for relative,(mode,oid) in tree.items():
                try:
                    path = _safe_file(root,relative)
                    if blob_id(read(relative),algorithm)!=oid:
                        dirty = True
                    # Git's executable mode is not represented by Windows
                    # filesystem permission bits. HEAD/index mode still agrees.
                    if os.name!='nt' and bool(path.stat().st_mode & 0o111)!=(mode=='100755'):
                        dirty = True
                except (OSError,ValueError):
                    dirty = True
        # Detect concurrent ref/index/inventory changes without refreshing the
        # stat cache, invoking filters, or writing any repository metadata.
        if (_git(root,'rev-parse','--verify','HEAD').decode('ascii').strip()!=commit or
            _git(root,'ls-files','--stage','-z','--',*SCOPE)!=index_raw or
            _git(root,'ls-files','--others','--exclude-standard','-z','--',*SCOPE)!=untracked_raw or
            _python_files(root)!=(names-{MAP},unsafe)):
            dirty = True
        if dirty is False:
            # The two digests above use identical initial bytes. Before calling
            # that snapshot clean, also ensure no actual file changed while
            # Git/index inventories were being inspected (ignore stat cache).
            for relative, original in cache.items():
                try:
                    path = _safe_file(root,relative)
                    if path.read_bytes()!=original:
                        dirty = True
                    if os.name!='nt' and relative in tree and bool(path.stat().st_mode & 0o111)!=(tree[relative][0]=='100755'):
                        dirty = True
                except (OSError,ValueError):
                    dirty = True
    except (OSError,ValueError,UnicodeError,subprocess.CalledProcessError):
        dirty = None
    payload = json.dumps(files,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'source_commit':commit,'source_dirty':dirty,'source_code_sha256':hashlib.sha256(payload).hexdigest(),'source_files':files}
