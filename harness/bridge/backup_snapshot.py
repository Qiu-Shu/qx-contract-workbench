"""Private snapshot worker. The desktop coordinator must hold the host maintenance lease."""
import contextlib
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import time

MAX_FILES = 20000
MAX_BYTES = 2 * 1024**3
MAX_FILE = 512 * 1024**2
MANIFEST = 'backup-manifest.json'


def fail(code):
    raise ValueError(code)


def member(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        fail('BACKUP_INVALID_MEMBER')
    parts = value.split('/')
    if any(p in ('', '.', '..') or p[-1:] in (' ', '.') or
           re.search(r'[\\:\x00-\x1f<>"|?*]', p) or
           re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', p, re.I) for p in parts):
        fail('BACKUP_INVALID_MEMBER')
    return value


def local_path(value):
    path = Path(value)
    if os.name != 'nt' or not path.is_absolute() or not re.match(r'^[a-zA-Z]:[\\/]', str(path)):
        fail('BACKUP_LOCAL_WINDOWS_PATH_REQUIRED')
    if '..' in path.parts or ':' in str(path)[2:]:
        fail('BACKUP_INVALID_PATH')
    for part in path.parts[1:]:
        member(part)
    for item in [path, *path.parents]:
        try:
            s = item.lstat()
        except FileNotFoundError:
            continue
        if getattr(s, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            fail('BACKUP_LINKED_PATH')
        if not stat.S_ISDIR(s.st_mode) and (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1):
            fail('BACKUP_LINKED_PATH')
    return Path(os.path.realpath(path))


def private_directory(value):
    """Apply a protected current-user-only DACL in the directory creation itself."""
    path = local_path(value)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    flags = wintypes.DWORD()
    if not kernel.GetVolumeInformationW(path.anchor, None, 0, None, None, ctypes.byref(flags), None, 0) or not flags.value & 8:
        fail('BACKUP_ACL_UNSUPPORTED')
    token = wintypes.HANDLE()
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        fail('BACKUP_ACL_FAILED')
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            fail('BACKUP_ACL_FAILED')
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_text = wintypes.LPWSTR()
        advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            fail('BACKUP_ACL_FAILED')
        try:
            sddl = 'D:P(A;OICI;FA;;;' + sid_text.value + ')'
        finally:
            kernel.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
    finally:
        kernel.CloseHandle(token)
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
        fail('BACKUP_ACL_FAILED')
    class Attributes(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('descriptor', ctypes.c_void_p), ('inherit', wintypes.BOOL)]
    attrs = Attributes(ctypes.sizeof(Attributes), descriptor, False)
    try:
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)):
            fail('BACKUP_DIRECTORY_CREATE_FAILED')
    finally:
        kernel.LocalFree(descriptor)
    return path


@contextlib.contextmanager
def frozen(paths):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []
    try:
        for path in sorted(set(paths), key=lambda p: (len(p.parts), str(p))):
            local_path(path)
            handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                fail('BACKUP_SOURCE_BUSY')
            handles.append(handle)
            local_path(path)
        yield
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def inventory(root, scopes):
    found = {}
    def visit(path):
        local_path(path)
        if path.is_dir():
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            name = member(path.relative_to(root).as_posix())
            s = path.stat()
            found[name] = (s.st_size, s.st_mtime_ns, s.st_ino)
            if len(found) > MAX_FILES or s.st_size > MAX_FILE:
                fail('BACKUP_SIZE_LIMIT')
    for scope in scopes:
        if scope['policy'] == 'protect':
            visit(root / member(scope['path']))
    if sum(v[0] for v in found.values()) > MAX_BYTES:
        fail('BACKUP_SIZE_LIMIT')
    return found


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_database(path):
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            fail('BACKUP_DATABASE_INVALID')


def check_references(root):
    for base in ['workspace', 'workspace/knowledge']:
        database = root / base / '.qx-materials/index.sqlite'
        if not database.exists():
            continue
        with contextlib.closing(sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='materials'").fetchone():
                continue
            for name, size, sha in db.execute('SELECT path,size,sha256 FROM materials'):
                target = root / base / member(name)
                if not target.is_file() or target.stat().st_size != size or digest(target) != sha:
                    fail('BACKUP_MATERIAL_REFERENCE_INVALID')
    vault = root / '.qx-private/uploads'
    for manifest in vault.glob('documents/*/manifest.json'):
        data = read_json(manifest)
        originals = list(manifest.parent.glob('original.*'))
        if len(originals) != 1 or digest(originals[0]) != data.get('sha256'):
            fail('BACKUP_PRIVATE_REFERENCE_INVALID')
        for field in ('safe_file', 'mapping_file'):
            target = vault / member(data.get(field))
            if not target.is_file():
                fail('BACKUP_PRIVATE_REFERENCE_INVALID')
    for reviewed in vault.glob('documents/*/reviewed-*.json'):
        data = read_json(reviewed)
        target = vault / member(data.get('safe_file'))
        if not target.is_file() or digest(target) != data.get('sha256'):
            fail('BACKUP_PRIVATE_REFERENCE_INVALID')


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail('BACKUP_INVALID_MANIFEST')
            result[key] = value
        return result
    if path.stat().st_size > 16 * 1024**2:
        fail('BACKUP_INVALID_MANIFEST')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def create_snapshot(source, destination, plan):
    source = local_path(source)
    destination = local_path(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        fail('BACKUP_OVERLAPPING_PATHS')
    before = inventory(source, plan['scopes'])
    selected = {member(f['path']): f['bytes'] for f in plan['files'] if f['policy'] == 'protect'}
    if {k: v[0] for k, v in before.items()} != selected or len({k.casefold() for k in before}) != len(before):
        fail('BACKUP_SOURCE_CHANGED')
    if shutil.disk_usage(destination.parent).free < sum(selected.values()) * 3 + 64 * 1024**2:
        fail('BACKUP_SPACE_REQUIRED')
    paths = {source}
    for name in before:
        target = source / name
        paths.add(target)
        paths.update(p for p in target.parents if p == source or source in p.parents)
    owned = False
    try:
        with frozen(paths):
            if inventory(source, plan['scopes']) != before:
                fail('BACKUP_SOURCE_CHANGED')
            private_directory(destination); owned = True
            raw = destination / '_raw'; raw.mkdir()
            for name in before:
                target = raw / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
                source_stat = (source/name).stat()
                os.utime(target, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
            databases = set()
            for name in before:
                with (raw / name).open('rb') as stream:
                    if stream.read(16) == b'SQLite format 3\x00':
                        databases.add(name)
                if re.search(r'\.(sqlite|db)$', name, re.I) and name not in databases:
                    fail('BACKUP_DATABASE_INVALID')
            sidefiles = {n + suffix for n in databases for suffix in ('-wal', '-shm', '-journal')}
            for name in before:
                if name in sidefiles:
                    continue
                if re.search(r'\.(sqlite|db)-(wal|shm|journal)$', name, re.I):
                    fail('BACKUP_ORPHAN_DATABASE_SIDEFILE')
                target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
                if name in databases:
                    deadline = time.monotonic() + 60
                    def progress(*_):
                        if time.monotonic() > deadline:
                            fail('BACKUP_DATABASE_TIMEOUT')
                    with contextlib.closing(sqlite3.connect(raw / name)) as src, contextlib.closing(sqlite3.connect(target)) as dst:
                        src.backup(dst, pages=256, progress=progress)
                        dst.execute('PRAGMA journal_mode=DELETE')
                    check_database(target)
                else:
                    shutil.copyfile(raw / name, target)
                    source_stat = (raw/name).stat()
                    os.utime(target, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
            if inventory(source, plan['scopes']) != before:
                fail('BACKUP_SOURCE_CHANGED')
            shutil.rmtree(raw)
        files = [{'path': n, 'bytes': (destination/n).stat().st_size, 'sha256': digest(destination/n),
                  'mtimeNs': (destination/n).stat().st_mtime_ns,
                  'kind': 'sqlite' if n in databases else 'file'} for n in sorted(before) if n not in sidefiles]
        manifest = {'schema': 1, 'scope': 'business-data', 'applicationComplete': False,
                    'activation': 'manual-review-required', 'sourceRoot': str(source),
                    'scopes': plan['scopes'], 'files': files}
        (destination/MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        return verify_snapshot(destination)
    except BaseException:
        if owned:
            shutil.rmtree(destination)
        raise


def verify_snapshot(root):
    root = local_path(root)
    local_path(root / MANIFEST)
    manifest = read_json(root / MANIFEST)
    if (manifest.get('schema') != 1 or manifest.get('scope') != 'business-data' or
        manifest.get('applicationComplete') is not False or manifest.get('activation') != 'manual-review-required'):
        fail('BACKUP_INVALID_MANIFEST')
    entries = manifest.get('files')
    if not isinstance(entries, list) or len(entries) > MAX_FILES:
        fail('BACKUP_INVALID_MANIFEST')
    expected = {}; seen = set()
    for entry in entries:
        name = member(entry['path'])
        if name.casefold() in seen or name.casefold() == MANIFEST:
            fail('BACKUP_INVALID_MANIFEST')
        if entry['kind'] not in ('sqlite', 'file') or type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_FILE:
            fail('BACKUP_INVALID_MANIFEST')
        expected[name] = entry
        seen.add(name.casefold())
    actual = inventory(root, [{'path': p.name, 'policy': 'protect'} for p in root.iterdir()])
    if set(actual) != set(expected) | {MANIFEST}:
        fail('BACKUP_FILE_SET_MISMATCH')
    for name, entry in expected.items():
        target = root / name
        if target.stat().st_size != entry['bytes'] or digest(target) != entry['sha256']:
            fail('BACKUP_FILE_HASH_MISMATCH')
        if target.stat().st_mtime_ns != entry['mtimeNs']:
            fail('BACKUP_FILE_TIME_MISMATCH')
        if entry['kind'] == 'sqlite':
            check_database(target)
    check_references(root)
    return {'fileCount': len(entries), 'databaseCount': sum(f['kind'] == 'sqlite' for f in entries),
            'archiveFiles': len(entries)+1, 'manifestSha256': digest(root/MANIFEST),
            'sourceRoot': manifest['sourceRoot'], 'applicationComplete': False}


def main():
    request = json.load(sys.stdin)
    action = request['action']
    if action == 'create':
        result = create_snapshot(request['source'], request['destination'], request['plan'])
    elif action == 'verify':
        result = verify_snapshot(request['root'])
    elif action == 'private-directory':
        result = {'path': str(private_directory(request['path']))}
    elif action == 'publish':
        source = local_path(request['source']); target = local_path(request['target'])
        # Windows rename fails if the destination already exists, including an empty directory.
        os.rename(source, target)
        result = {'published': True}
    else:
        fail('BACKUP_INVALID_ACTION')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) and re.fullmatch(r'BACKUP_[A-Z_]+', str(error)) else 'BACKUP_WORKER_FAILED'
        print(json.dumps({'error': code}))
        sys.exit(1)
