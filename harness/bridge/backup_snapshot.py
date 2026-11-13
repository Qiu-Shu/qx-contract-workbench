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
import struct
import subprocess
import sys
import time
from urllib.parse import quote

MAX_FILES = 20000
MAX_BYTES = 2 * 1024**3
MAX_FILE = 512 * 1024**2
MANIFEST = 'backup-manifest.json'
PG_ROOT = '.local/case-memory-runtime'
SETTINGS = json.loads((Path(__file__).resolve().parent.parent/'config/backup-settings.json').read_text(encoding='utf-8'))


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


class _LocalPath(type(Path())):
    """Only validated worker paths carry the Win32 extended prefix internally."""


def public_path(path):
    value=str(path)
    return value[4:] if isinstance(path,_LocalPath) and value.startswith('\\\\?\\') else value


def local_path(value):
    path = Path(public_path(value))
    if os.name != 'nt' or not path.is_absolute() or not re.match(r'^[a-zA-Z]:[\\/]', str(path)):
        fail('BACKUP_LOCAL_WINDOWS_PATH_REQUIRED')
    if '..' in path.parts or ':' in str(path)[2:]:
        fail('BACKUP_INVALID_PATH')
    for part in path.parts[1:]:
        member(part)
    path = _LocalPath('\\\\?\\'+str(path))
    for item in [path, *path.parents]:
        try:
            s = item.lstat()
        except FileNotFoundError:
            continue
        if getattr(s, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            fail('BACKUP_LINKED_PATH')
        if not stat.S_ISDIR(s.st_mode) and (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1):
            fail('BACKUP_LINKED_PATH')
    return _LocalPath(os.path.realpath(path))


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
    if not kernel.GetVolumeInformationW(Path(public_path(path)).anchor, None, 0, None, None, ctypes.byref(flags), None, 0) or not flags.value & 8:
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
            path = local_path(path)
            handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                fail('BACKUP_SOURCE_BUSY')
            handles.append(handle)
            local_path(path)
        yield
    finally:
        for handle in reversed(handles):
            kernel.CloseHandle(handle)


def inventory(root, scopes, policies=('protect',), directories=None):
    found = {}
    visited_dirs = set()
    def visit(path):
        local_path(path)
        if path.is_dir():
            name = member(path.relative_to(root).as_posix())
            visited_dirs.add(name)
            if len(visited_dirs) > MAX_FILES:
                fail('BACKUP_SIZE_LIMIT')
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            name = member(path.relative_to(root).as_posix())
            s = path.stat()
            found[name] = (s.st_size, s.st_mtime_ns, s.st_ino)
            if len(found) > MAX_FILES or s.st_size > MAX_FILE:
                fail('BACKUP_SIZE_LIMIT')
    for scope in scopes:
        if scope['policy'] in policies:
            visit(root / member(scope['path']))
    if sum(v[0] for v in found.values()) > MAX_BYTES:
        fail('BACKUP_SIZE_LIMIT')
    if directories is not None:
        directories.update(visited_dirs)
    return found


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_postgres_wal(database, control, check):
    def lsn(value):
        if not re.fullmatch(r'[0-9A-F]+/[0-9A-F]+', value):
            fail('BACKUP_POSTGRES_CHECK_FAILED')
        high, low = value.split('/')
        return (int(high,16) << 32) + int(low,16)
    checkpoint = control.get('Latest checkpoint location','')
    if lsn(checkpoint) != lsn(control.get("Latest checkpoint's REDO location",'')):
        fail('BACKUP_POSTGRES_NOT_COLD')
    segment = control.get("Latest checkpoint's REDO WAL file",'')
    timeline = control.get("Latest checkpoint's TimeLineID",'')
    if not re.fullmatch(r'[0-9A-F]{24}',segment) or not re.fullmatch(r'[1-9][0-9]*',timeline):
        fail('BACKUP_POSTGRES_CHECK_FAILED')
    wal = database/'pg_wal'/segment
    segment_size = int(control.get('Bytes per WAL segment','0'))
    if not wal.is_file() or wal.stat().st_size != segment_size or segment_size < 40:
        fail('BACKUP_POSTGRES_CHECK_FAILED')
    # Fixed Windows x64 PostgreSQL 18 layout: XLogLongPageHeaderData, aligned to 8 bytes.
    # pg_waldump validates record CRCs but does not compare this ID with pg_control.
    with wal.open('rb') as stream:
        header = stream.read(40)
    if struct.unpack_from('<QII',header,24) != (int(control['Database system identifier']),segment_size,int(control['WAL block size'])):
        fail('BACKUP_POSTGRES_CHECK_FAILED')
    record = check('pg_waldump.exe',['-p',public_path(database/'pg_wal'),'-s',checkpoint,'-t',timeline,'-n','1'])
    match = re.fullmatch(r'rmgr: XLOG\s+.*?lsn: ([0-9A-F]+/[0-9A-F]+),.*?desc: CHECKPOINT_SHUTDOWN redo ([0-9A-F]+/[0-9A-F]+); tli ([0-9]+);.*',record.strip())
    if not match or lsn(match[1]) != lsn(checkpoint) or lsn(match[2]) != lsn(checkpoint) or match[3] != timeline:
        fail('BACKUP_POSTGRES_CHECK_FAILED')


def inspect_postgres(root, tools):
    """Read-only tools: never execute a restored configuration or start a user's database."""
    if not tools:
        fail('BACKUP_POSTGRES_TOOLS_REQUIRED')
    tools = local_path(tools)
    pin = read_json(Path(__file__).resolve().parent.parent/'config/postgres-backup-runtime.json')
    for name, expected in pin['files'].items():
        target = local_path(tools/member(name))
        if not target.is_file() or digest(target) != expected:
            fail('BACKUP_POSTGRES_TOOLS_UNVERIFIED')
    actual_dlls = {p.name.lower() for p in (tools/'bin').iterdir() if p.suffix.lower() == '.dll'}
    if actual_dlls != {Path(n).name.lower() for n in pin['files'] if n.endswith('.dll')}:
        fail('BACKUP_POSTGRES_TOOLS_UNVERIFIED')
    database = root/PG_ROOT/'database'
    if not database.is_dir():
        fail('BACKUP_POSTGRES_LAYOUT_INVALID')
    identity_path = root/PG_ROOT/'instance.json'
    if not identity_path.is_file() or identity_path.stat().st_size > 4096:
        fail('BACKUP_POSTGRES_IDENTITY_INVALID')
    identity = read_json(identity_path)
    if (not isinstance(identity, dict) or not re.fullmatch(r'[a-f0-9-]{36}', str(identity.get('id'))) or
        not re.fullmatch(r'[a-f0-9]{64}', str(identity.get('databasePassword')))):
        fail('BACKUP_POSTGRES_IDENTITY_INVALID')
    for name in ('postmaster.pid', 'backup_label', 'tablespace_map', 'recovery.signal', 'standby.signal'):
        if (database/name).exists():
            fail('BACKUP_POSTGRES_NOT_COLD')
    for name in ('base','global','pg_wal','pg_xact','pg_multixact','pg_tblspc','pg_logical','pg_notify',
                 'pg_replslot','pg_serial','pg_snapshots','pg_stat','pg_stat_tmp','pg_subtrans','pg_twophase',
                 'pg_commit_ts','pg_dynshmem'):
        if not (database/name).is_dir():
            fail('BACKUP_POSTGRES_LAYOUT_INVALID')
    if any((database/'pg_tblspc').iterdir()):
        fail('BACKUP_POSTGRES_EXTERNAL_TABLESPACE')
    version = database/'PG_VERSION'
    if not version.is_file() or version.read_bytes() != (pin['major']+'\n').encode('ascii'):
        fail('BACKUP_POSTGRES_VERSION_UNSUPPORTED')
    env = {k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP')}
    env.update(LC_ALL='C',LANG='C',LANGUAGE='C')
    def check(name,args):
        # Native PostgreSQL tools append forward-slash suffixes, which Win32 extended paths reject.
        result = subprocess.run([public_path(tools/'bin'/name),*args],cwd=public_path(tools/'bin'),env=env,stdin=subprocess.DEVNULL,
                                capture_output=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or result.stderr or len(result.stdout)>65536:
            fail('BACKUP_POSTGRES_CHECK_FAILED')
        return result.stdout.decode('utf-8')
    control = {}
    for line in check('pg_controldata.exe',[public_path(database)]).splitlines():
        if ':' in line:
            key,value=line.split(':',1);control[key.strip()]=value.strip()
    if control.get('Database cluster state') != 'shut down':
        fail('BACKUP_POSTGRES_NOT_COLD')
    if control.get('pg_control version number') != pin['controlVersion'] or control.get('Catalog version number') != pin['catalogVersion']:
        fail('BACKUP_POSTGRES_VERSION_UNSUPPORTED')
    if control.get('Data page checksum version') != '1':
        fail('BACKUP_POSTGRES_CHECKSUMS_REQUIRED')
    system_id = control.get('Database system identifier','')
    if not re.fullmatch(r'[0-9]+',system_id):
        fail('BACKUP_POSTGRES_CHECK_FAILED')
    check_postgres_wal(database,control,check)
    check('pg_checksums.exe',['--check','-D',public_path(database)])
    return {'major':pin['major'],'controlVersion':pin['controlVersion'],'catalogVersion':pin['catalogVersion'],
            'systemIdentifier':system_id,'instanceId':identity['id'],'checksumVersion':1,
            'controlSha256':digest(database/'global/pg_control')}


def readonly_database_uri(path):
    # Encode the device prefix as a filename, not a URI authority; preserve read-only validation.
    return 'file:'+quote(str(local_path(path)),safe=':')+'?mode=ro&immutable=1'


def check_database(path):
    with contextlib.closing(sqlite3.connect(readonly_database_uri(path), uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            fail('BACKUP_DATABASE_INVALID')


def check_references(root):
    for base in ['workspace', 'workspace/knowledge']:
        database = root / base / '.qx-materials/index.sqlite'
        if not database.exists():
            continue
        with contextlib.closing(sqlite3.connect(readonly_database_uri(database), uri=True)) as db:
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


def create_snapshot(source, destination, plan, pg_tools=None):
    source = local_path(source)
    destination = local_path(destination)
    if source == destination or source in destination.parents or destination in source.parents:
        fail('BACKUP_OVERLAPPING_PATHS')
    has_postgres = any(s['path'] == PG_ROOT+'/database' for s in plan['scopes'])
    if has_postgres and not pg_tools:
        fail('BACKUP_POSTGRES_TOOLS_REQUIRED')
    policies = ('protect','review-settings','cold-postgres') if has_postgres else ('protect','review-settings')
    directories = set()
    before = inventory(source, plan['scopes'], policies, directories)
    settings = [s for s in SETTINGS if s['sourcePath'] in before]
    relocated = {s['sourcePath']:s['path'] for s in settings}
    if any(before[name][0] > 1024*1024 for name in relocated):
        fail('BACKUP_SETTINGS_UNSUPPORTED')
    selected = {member(f['path']): f['bytes'] for f in plan['files'] if f['policy'] in policies}
    if {k: v[0] for k, v in before.items()} != selected or len({k.casefold() for k in before}) != len(before):
        fail('BACKUP_SOURCE_CHANGED')
    if shutil.disk_usage(destination.parent).free < sum(selected.values()) * 3 + 64 * 1024**2:
        fail('BACKUP_SPACE_REQUIRED')
    paths = {source, *(source/name for name in directories)}
    for name in before:
        target = source / name
        paths.add(target)
        paths.update(p for p in target.parents if p == source or source in p.parents)
    owned = False
    try:
        with frozen(paths):
            observed_dirs = set()
            if inventory(source, plan['scopes'], policies, observed_dirs) != before or observed_dirs != directories:
                fail('BACKUP_SOURCE_CHANGED')
            private_directory(destination); owned = True
            raw = destination / '_raw'; raw.mkdir()
            for name in sorted(directories):
                (raw/name).mkdir(parents=True,exist_ok=True)
                (destination/name).mkdir(parents=True,exist_ok=True)
            for name in before:
                target = raw / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
                source_stat = (source/name).stat()
                os.utime(target, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
            postgres = inspect_postgres(raw,pg_tools) if has_postgres else None
            postgres_files = {n for n in before if has_postgres and n.startswith(PG_ROOT+'/database/')}
            databases = set()
            for name in before:
                if name in postgres_files or name in relocated:
                    continue
                with (raw / name).open('rb') as stream:
                    if stream.read(16) == b'SQLite format 3\x00':
                        databases.add(name)
                if re.search(r'\.(sqlite|db)$', name, re.I) and name not in databases:
                    fail('BACKUP_DATABASE_INVALID')
            sidefiles = {n + suffix for n in databases for suffix in ('-wal', '-shm', '-journal')}
            for name in before:
                if name in sidefiles:
                    continue
                if name not in postgres_files and re.search(r'\.(sqlite|db)-(wal|shm|journal)$', name, re.I):
                    fail('BACKUP_ORPHAN_DATABASE_SIDEFILE')
                target = destination / relocated.get(name,name); target.parent.mkdir(parents=True, exist_ok=True)
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
            observed_dirs = set()
            if inventory(source, plan['scopes'], policies, observed_dirs) != before or observed_dirs != directories:
                fail('BACKUP_SOURCE_CHANGED')
            shutil.rmtree(raw)
        files = [{'path': relocated.get(n,n), 'bytes': (destination/relocated.get(n,n)).stat().st_size, 'sha256': digest(destination/relocated.get(n,n)),
                  'mtimeNs': (destination/relocated.get(n,n)).stat().st_mtime_ns,
                  'kind': 'sqlite' if n in databases else 'file'} for n in sorted(before) if n not in sidefiles]
        manifest = {'schema': 1, 'scope': 'business-data', 'applicationComplete': False,
                    'activation': 'manual-review-required', 'sourceRoot': public_path(source),
                    'scopes': plan['scopes'], 'files': files,
                    'settings': settings,
                    'directories': sorted(p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_dir())}
        if postgres is not None:
            manifest['postgres'] = postgres
        (destination/MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        return verify_snapshot(destination,pg_tools)
    except BaseException:
        if owned:
            shutil.rmtree(destination)
        raise


def verify_snapshot(root, pg_tools=None):
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
    actual_dirs = set()
    actual = inventory(root, [{'path': p.name, 'policy': 'protect'} for p in root.iterdir()], directories=actual_dirs)
    if set(actual) != set(expected) | {MANIFEST}:
        fail('BACKUP_FILE_SET_MISMATCH')
    settings = [s for s in SETTINGS if s['path'] in expected]
    if manifest.get('settings',[]) != settings or any(n.startswith('.qx-restore-review/') and n not in {s['path'] for s in settings} for n in expected):
        fail('BACKUP_SETTINGS_MANIFEST_INVALID')
    if 'directories' in manifest:
        declared = manifest['directories']
        if not isinstance(declared,list) or len(declared)>MAX_FILES or len(set(declared))!=len(declared) or {member(n) for n in declared} != actual_dirs:
            fail('BACKUP_DIRECTORY_SET_MISMATCH')
    postgres = manifest.get('postgres')
    if (root/PG_ROOT/'database').exists():
        if not postgres or 'directories' not in manifest:
            fail('BACKUP_POSTGRES_MANIFEST_INVALID')
    elif postgres:
        fail('BACKUP_POSTGRES_MANIFEST_INVALID')
    for name, entry in expected.items():
        target = root / name
        if target.stat().st_size != entry['bytes'] or digest(target) != entry['sha256']:
            fail('BACKUP_FILE_HASH_MISMATCH')
        if target.stat().st_mtime_ns != entry['mtimeNs']:
            fail('BACKUP_FILE_TIME_MISMATCH')
        if entry['kind'] == 'sqlite':
            check_database(target)
    check_references(root)
    if postgres and inspect_postgres(root,pg_tools) != postgres:
        fail('BACKUP_POSTGRES_IDENTITY_MISMATCH')
    return {'fileCount': len(entries), 'databaseCount': sum(f['kind'] == 'sqlite' for f in entries),
            'archiveFiles': len(entries)+1, 'manifestSha256': digest(root/MANIFEST),
            'sourceRoot': manifest['sourceRoot'], 'applicationComplete': False,'postgresIncluded':bool(postgres),
            'settingsCount':len(settings)}


def review_snapshot(root, pg_tools=None):
    root = local_path(root)
    scopes = [{'path':p.name,'policy':'protect'} for p in root.iterdir()]
    directories = set()
    before = inventory(root,scopes,directories=directories)
    with frozen([root,*(root/n for n in before),*(root/n for n in directories)]):
        result = review_frozen_snapshot(root,pg_tools)
        observed_dirs = set()
        scopes = [{'path':p.name,'policy':'protect'} for p in root.iterdir()]
        if inventory(root,scopes,directories=observed_dirs) != before or observed_dirs != directories:
            fail('BACKUP_SOURCE_CHANGED')
        return result


def review_frozen_snapshot(root, pg_tools):
    checked = verify_snapshot(root,pg_tools)
    root = local_path(root)
    manifest = read_json(root/MANIFEST)
    settings = []
    for entry in manifest.get('settings',[]):
        item = {'id':entry['id'],'status':'review-required','suggested':{}}
        try:
            value = read_json(root/entry['path'])
        except (ValueError,UnicodeError):
            value = None
        if isinstance(value,dict):
            if entry['id'] == 'desktop-locale' and value.get('locale') in ('zh','zh-CN','zh-TW','en','en-US'):
                item['suggested'] = {'locale':value['locale']}
            if entry['id'] == 'wechat-preferences':
                for key,choices in [('format',('plain','raw')),('delivery',('whole','stream'))]:
                    if value.get(key) in choices:
                        item['suggested'][key] = value[key]
        settings.append(item)
    blockers = ['settings-review','credentials-reauthorization','application-activation-not-implemented']
    if (root/'.local/dsh-home/qx-wechat/qx-pending.json').exists() or (root/'.local/dsh-home/storages').exists():
        blockers.append('pending-work-review')
    if checked['postgresIncluded']:
        blockers.extend(['postgres-instance-registration','hindsight-api-validation'])
    return {'schema':1,'verified':True,'activation':'blocked','applicationComplete':False,
            'fileCount':checked['fileCount'],'postgresIncluded':checked['postgresIncluded'],'settings':settings,
            'databaseCount':checked['databaseCount'],'manifestSha256':checked['manifestSha256'],'sourceRoot':checked['sourceRoot'],
            'reauthorization':['model-api-keys','wechat-login','other-profile-secrets'],'blockers':blockers}


def copy_verified_snapshot(root, destination, manifest_sha256, pg_tools=None):
    """Copy a frozen verified restore; the delivered restore remains the immutable reference."""
    root=local_path(root);destination=local_path(destination)
    source=local_path(read_json(root/MANIFEST)['sourceRoot'])
    for original in (root,source):
        if original==destination or original in destination.parents or destination in original.parents:
            fail('BACKUP_OVERLAPPING_PATHS')
    if destination.exists():
        fail('BACKUP_TARGET_EXISTS')
    scopes=[{'path':p.name,'policy':'protect'} for p in root.iterdir()]
    directories=set();before=inventory(root,scopes,directories=directories)
    owned=False
    try:
        with frozen([root,*(root/n for n in before),*(root/n for n in directories)]):
            checked=verify_snapshot(root,pg_tools)
            if checked['manifestSha256']!=manifest_sha256:
                fail('BACKUP_REVIEW_STALE')
            if shutil.disk_usage(destination.parent).free < sum(v[0] for v in before.values())+64*1024**2:
                fail('BACKUP_SPACE_REQUIRED')
            private_directory(destination);owned=True
            for name in sorted(directories):
                (destination/name).mkdir(parents=True,exist_ok=True)
            for name in before:
                shutil.copy2(root/name,destination/name)
            observed_dirs=set()
            if inventory(root,[{'path':p.name,'policy':'protect'} for p in root.iterdir()],directories=observed_dirs)!=before or observed_dirs!=directories:
                fail('BACKUP_SOURCE_CHANGED')
            result=verify_snapshot(destination,pg_tools)
            if result['manifestSha256']!=manifest_sha256:
                fail('BACKUP_REVIEW_STALE')
            return result
    except BaseException:
        if owned:
            shutil.rmtree(destination)
        raise


PREPARED_MANIFEST='.local/restore-prepared-manifest.json'
ACTIVATION_RECEIPT='.local/restore-activation.json'


def prepared_contents(root):
    directories=set()
    found=inventory(root,[{'path':p.name,'policy':'protect'} for p in root.iterdir()],directories=directories)
    files=[]
    for name in sorted(found):
        if name in (PREPARED_MANIFEST,ACTIVATION_RECEIPT):
            continue
        target=root/name
        files.append({'path':name,'bytes':target.stat().st_size,'sha256':digest(target),'mtimeNs':str(target.stat().st_mtime_ns)})
    return {'schema':1,'files':files,'directories':sorted(directories)}


def seal_prepared(root):
    root=local_path(root)
    if (root/PREPARED_MANIFEST).exists():
        fail('BACKUP_TARGET_EXISTS')
    manifest=prepared_contents(root)
    (root/PREPARED_MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    return {'preparedManifestSha256':digest(root/PREPARED_MANIFEST),'fileCount':len(manifest['files'])}


def verify_prepared(root, destination=None):
    root=local_path(root);expected=local_path(destination) if destination else root
    directories=set();scopes=[{'path':p.name,'policy':'protect'} for p in root.iterdir()]
    before=inventory(root,scopes,directories=directories)
    with frozen([root,*(root/n for n in before),*(root/n for n in directories)]):
        receipt=read_json(root/ACTIVATION_RECEIPT)
        if (receipt.get('schema')!=1 or receipt.get('phase')!='prepared' or
            local_path(receipt.get('data',''))!=expected or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',str(receipt.get('id',''))) or
            digest(root/PREPARED_MANIFEST)!=receipt.get('preparedManifestSha256') or
            (root/MANIFEST).exists() or (root/'.qx-restore-review').exists()):
            fail('BACKUP_PREPARED_CHANGED')
        if read_json(root/PREPARED_MANIFEST)!=prepared_contents(root):
            fail('BACKUP_PREPARED_CHANGED')
        observed_dirs=set()
        if inventory(root,[{'path':p.name,'policy':'protect'} for p in root.iterdir()],directories=observed_dirs)!=before or observed_dirs!=directories:
            fail('BACKUP_PREPARED_CHANGED')
        return receipt


def main():
    request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    action = request['action']
    if action == 'create':
        result = create_snapshot(request['source'], request['destination'], request['plan'], request.get('pgTools'))
    elif action == 'verify':
        result = verify_snapshot(request['root'],request.get('pgTools'))
    elif action == 'review':
        result = review_snapshot(request['root'],request.get('pgTools'))
    elif action == 'copy-verified':
        result = copy_verified_snapshot(request['root'],request['destination'],request['manifestSha256'],request.get('pgTools'))
    elif action == 'seal-prepared':
        result = seal_prepared(request['root'])
    elif action == 'verify-prepared':
        result = verify_prepared(request['root'],request.get('destination'))
    elif action == 'private-directory':
        result = {'path': public_path(private_directory(request['path']))}
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
