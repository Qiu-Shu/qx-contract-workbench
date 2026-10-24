"""Native-only, offline local backups. Restore publishes a separate fenced copy.

No HTTP callers, key persistence, cloud transfer, or changes to fictional backup
policy. The source worker must be stopped; the same OS lock guards maintenance.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
import time
from uuid import uuid4
from zipfile import ZipFile, ZIP_STORED

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import select

from ..config import load_settings
from ..domain import WorkspaceBackupManifest
from ..persistence import Database, SessionRow
from . import storage
from .file_paths import filesystem_path, application_path
from .backup import (checked_root, digest, encode, strict_json, safe_relative, redirected,
                     _file_references, _mark_storage_flags)

MAGIC = b'QX_LOCAL_WORKSPACE_1\n'
LIMIT = 2 * 1024**3
FILE_LIMIT = 512 * 1024**2
MAX_FILES = 20000
CHUNK = 1024**2
HEADER_SIZE = len(MAGIC) + 16 + 12


def _key(passphrase, salt):
    if type(passphrase) is not str or not 12 <= len(passphrase) <= 128:
        raise ValueError('BACKUP_PASSPHRASE_INVALID')
    return hashlib.scrypt(passphrase.encode('utf-8'), salt=salt, n=32768, r=8, p=1,
                          dklen=32, maxmem=64*1024**2)


def _relative(name):
    path = safe_relative(name)
    if any(ord(c) < 32 or c in '<>"|?*' for c in name):
        raise ValueError('UNSAFE_MEMBER')
    return path


@contextmanager
def _reader(path, root, *, limit=FILE_LIMIT):
    path, root = filesystem_path(path), filesystem_path(checked_root(root))
    if not path.resolve(strict=True).is_relative_to(root): raise ValueError('FILE_OUTSIDE_ROOT')
    for parent in (path, *path.parents):
        if redirected(parent): raise ValueError('REDIRECTED_FILE')
        if parent == root: break
    before = path.stat()
    if before.st_nlink != 1 or not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError('FILE_LIMIT_OR_LINK')
    with path.open('rb') as stream:
        actual = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns):
            raise ValueError('FILE_CHANGED')
        yield stream
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink):
            raise ValueError('FILE_CHANGED')


def _copy(source, target=None, *, limit=FILE_LIMIT):
    checksum, size = hashlib.sha256(), 0
    while chunk := source.read(CHUNK):
        size += len(chunk)
        if size > limit: raise ValueError('FILE_LIMIT')
        checksum.update(chunk)
        if target is not None: target.write(chunk)
    return {'size':size, 'sha256':checksum.hexdigest()}


def _file(path, root, *, limit=FILE_LIMIT):
    with _reader(path, root, limit=limit) as stream: return _copy(stream, limit=limit)


def _inventory(root):
    root = filesystem_path(root)
    protected = filesystem_path(checked_root(root/'protected'))
    files = [root/'workbench.db', root/'workspace.json']
    for directory, folders, names in os.walk(protected, followlinks=False, onerror=lambda exc: (_ for _ in ()).throw(exc)):
        for name in folders:
            if redirected(Path(directory)/name): raise ValueError('REDIRECTED_FILE')
        files.extend(Path(directory)/name for name in names)
        if len(files) > MAX_FILES: raise ValueError('FILE_COUNT_LIMIT')
    result, total, seen = [], 0, set()
    for path in sorted(files):
        name = path.relative_to(root).as_posix(); _relative(name)
        if name.casefold() in seen: raise ValueError('DUPLICATE_FILE')
        seen.add(name.casefold())
        item = {'path':name, **_file(path, root)}
        total += item['size']
        if total > LIMIT: raise ValueError('ARCHIVE_LIMIT')
        result.append(item)
    return result


def _validate_database(root):
    # Known schema is independent of the archive and its own claimed hash.
    root = application_path(root)
    from ..web.local_server import _marker, _schema_hash
    marker = strict_json(filesystem_path(root/'workspace.json').read_bytes())
    expected = _marker()
    if (type(marker) is not dict or set(marker) != set(expected)|{'workspace_id','schema_sha256'}
            or any(marker[k] != v for k,v in expected.items())):
        raise ValueError('WORKSPACE_POLICY_MISMATCH')
    from ..storage_schema import identify_schema
    with closing(sqlite3.connect((root/'workbench.db').as_uri()+'?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA trusted_schema=OFF')
        rows = connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        try: identify_schema(rows, native=True)
        except ValueError: raise ValueError('WORKSPACE_SCHEMA_MISMATCH') from None
        if (_schema_hash(connection) != marker['schema_sha256']
                or connection.execute('SELECT id FROM local_workspace_identity').fetchall() != [(marker['workspace_id'],)]
                or connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]
                or connection.execute('PRAGMA foreign_key_check').fetchall()):
            raise ValueError('WORKSPACE_DATABASE_MISMATCH')
    return marker


def _references(root, inventory, *, source=False):
    root = application_path(root)
    files = {i['path']:i for i in inventory}
    database = Database('sqlite:///'+str(root/'workbench.db'), filesystem_path(root/'protected'), load_settings(), initialize_schema=False)
    try:
        with database.session() as db:
            refs = _file_references(db)
            for item in refs:
                name = 'protected/'+item['physical_ref']; _relative(name)
                entry = files.get(name)
                if (entry is None or entry['sha256'] != item['sha256']
                        or item['size'] is not None and entry['size'] != item['size']):
                    raise ValueError('FILE_REFERENCE_MISMATCH')
                if source:
                    logical = Path(item['logical_ref'])
                    if storage.quarantined(db): logical = storage.relocation(item['logical_ref'],item['sha256'],db)
                    elif not logical.is_absolute(): logical = root/'protected'/logical
                    if filesystem_path(logical) != filesystem_path(root/name): raise ValueError('FILE_REFERENCE_LOCATION')
            return refs
    finally: database.engine.dispose()


def _encrypt(plain, target, passphrase):
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC+salt+nonce
    encryptor = Cipher(algorithms.AES(_key(passphrase,salt)),modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    with plain.open('rb') as source, target.open('xb') as output:
        output.write(header)
        while chunk := source.read(CHUNK): output.write(encryptor.update(chunk))
        output.write(encryptor.finalize()); output.write(encryptor.tag)
        output.flush(); os.fsync(output.fileno())


def _decrypt(archive, target, passphrase):
    with _reader(archive, archive.parent, limit=LIMIT+HEADER_SIZE+16) as source:
        size = os.fstat(source.fileno()).st_size
        header = source.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE or not header.startswith(MAGIC) or size < HEADER_SIZE+16:
            raise ValueError('ARCHIVE_FORMAT')
        source.seek(-16,2); tag = source.read(16); source.seek(HEADER_SIZE)
        salt, nonce = header[len(MAGIC):len(MAGIC)+16], header[-12:]
        decryptor = Cipher(algorithms.AES(_key(passphrase,salt)),modes.GCM(nonce,tag)).decryptor()
        decryptor.authenticate_additional_data(header)
        remaining = size-HEADER_SIZE-16
        try:
            with target.open('xb') as output:
                while remaining:
                    chunk = source.read(min(CHUNK,remaining))
                    if not chunk: raise ValueError('ARCHIVE_TRUNCATED')
                    remaining -= len(chunk); output.write(decryptor.update(chunk))
                output.write(decryptor.finalize())
                output.flush(); os.fsync(output.fileno())
        except InvalidTag: raise ValueError('ARCHIVE_AUTHENTICATION_FAILED') from None


def _unpack(plain, root):
    with ZipFile(plain) as archive:
        infos = archive.infolist()
        if not 3 <= len(infos) <= MAX_FILES+1: raise ValueError('FILE_COUNT_LIMIT')
        seen, total = set(), 0
        for info in infos:
            _relative(info.filename)
            if info.filename.casefold() in seen: raise ValueError('DUPLICATE_FILE')
            seen.add(info.filename.casefold()); total += info.file_size
            mode = info.external_attr >> 16
            if (info.is_dir() or info.compress_type != ZIP_STORED or info.file_size > FILE_LIMIT
                    or info.file_size != info.compress_size or info.flag_bits & 1
                    or stat.S_IFMT(mode) not in (0,stat.S_IFREG) or total > LIMIT):
                raise ValueError('ARCHIVE_MEMBER_INVALID')
        if 'manifest.json' not in seen or archive.getinfo('manifest.json').file_size > 4*1024**2:
            raise ValueError('MANIFEST_LIMIT')
        manifest_raw = archive.read('manifest.json')
        manifest = WorkspaceBackupManifest.model_validate(strict_json(manifest_raw))
        entries = manifest.model_dump(mode='json')['files']
        if len(entries) > MAX_FILES or len(entries) != len({i['path'] for i in entries}):
            raise ValueError('MANIFEST_FILES_INVALID')
        if {i['path'] for i in entries}|{'manifest.json'} != {i.filename for i in infos}:
            raise ValueError('MANIFEST_FILES_INVALID')
        if not {'workbench.db','workspace.json'} <= {i['path'] for i in entries}:
            raise ValueError('MANIFEST_FILES_INVALID')
        filesystem_path(root).mkdir(); filesystem_path(root/'protected').mkdir()
        for item in entries:
            name = item['path']; relative = _relative(name)
            if name not in ('workbench.db','workspace.json') and not name.startswith('protected/'):
                raise ValueError('UNEXPECTED_FILE')
            destination = filesystem_path(root/relative)
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(name) as source, destination.open('xb') as output:
                actual = _copy(source, output)
                output.flush(); os.fsync(output.fileno())
            if actual != {k:item[k] for k in ('size','sha256')}: raise ValueError('FILE_HASH_MISMATCH')
    marker = _validate_database(root)
    if marker['workspace_id'] != str(manifest.workspace_id): raise ValueError('WORKSPACE_ID_MISMATCH')
    refs = _references(root, entries)
    return manifest, digest(manifest_raw), refs


def _publish(encrypted,destination,expected):
    # Only ciphertext crosses into the chosen destination (including other disks).
    destination=filesystem_path(destination)
    temporary=destination.parent/('.qx-'+str(uuid4())+'.partial')
    created=False
    try:
        with temporary.open('xb') as output:
            created=True
            with _reader(encrypted,encrypted.parent,limit=LIMIT+HEADER_SIZE+16) as source:
                actual=_copy(source,output,limit=LIMIT+HEADER_SIZE+16)
            output.flush();os.fsync(output.fileno())
        if actual!=expected or _file(temporary,temporary.parent,limit=LIMIT+HEADER_SIZE+16)!=expected:
            raise ValueError('ARCHIVE_VERIFY_FAILED')
        # Atomic no-replace publish, always within the destination volume.
        os.link(temporary,destination)
    finally:
        if created:temporary.unlink()


def create_workspace_backup(directory, destination, passphrase, *, data_parent):
    from ..web.local_server import _open_workspace, _worker_lock
    _key(passphrase,b'0'*16)
    root = _open_workspace(directory,data_parent=data_parent)
    destination = application_path(Path(destination).absolute())
    parent = checked_root(destination.parent)
    destination = parent/destination.name
    if (filesystem_path(destination).exists() or filesystem_path(destination).is_symlink()
            or filesystem_path(destination).is_relative_to(filesystem_path(root))):
        raise ValueError('BACKUP_DESTINATION_INVALID')
    _relative(destination.name)
    with _worker_lock(root), TemporaryDirectory(prefix='.qx-backup-',dir=filesystem_path(root)) as temporary:
        stage = Path(temporary); snapshot = stage/'snapshot'; snapshot.mkdir()
        (snapshot/'protected').mkdir()
        marker = _validate_database(root)
        # SQLite backup includes any committed WAL. Worker lock excludes writers.
        deadline = time.monotonic()+60
        def progress(*_):
            if time.monotonic()>deadline: raise ValueError('BACKUP_DATABASE_TIMEOUT')
        with closing(sqlite3.connect((root/'workbench.db').as_uri()+'?mode=ro',uri=True)) as source:
            with closing(sqlite3.connect(snapshot/'workbench.db')) as target:
                source.backup(target,pages=256,progress=progress)
        (snapshot/'workspace.json').write_bytes((root/'workspace.json').read_bytes())
        inventory = _inventory(root)
        _references(root,inventory,source=True)
        # Only database snapshot bytes may differ from a live WAL main file.
        for entry in inventory:
            if entry['path'] == 'workbench.db': entry.update(_file(snapshot/'workbench.db',snapshot))
        _validate_database(snapshot)
        manifest = WorkspaceBackupManifest(format='qx-local-workspace-v1',archive_id=uuid4(),
            workspace_id=marker['workspace_id'],created_at=datetime.now(timezone.utc),files=inventory)
        plain = stage/'archive.zip'
        with ZipFile(plain,'x',compression=ZIP_STORED,allowZip64=True) as archive:
            archive.writestr('manifest.json',manifest.model_dump_json().encode('utf-8'))
            for item in inventory:
                original = (snapshot if item['path']=='workbench.db' else root)/item['path']
                with _reader(original, original.parent) as source, archive.open(item['path'],'w',force_zip64=True) as output:
                    if _copy(source,output) != {k:item[k] for k in ('size','sha256')}: raise ValueError('FILE_CHANGED')
        if plain.stat().st_size > LIMIT: raise ValueError('ARCHIVE_LIMIT')
        # Detect material changes during the cut without trusting file timestamps.
        second = _inventory(root)
        if [i for i in second if i['path']!='workbench.db'] != [i for i in inventory if i['path']!='workbench.db']:
            raise ValueError('FILE_CHANGED')
        encrypted = stage/'archive.qxbak'; _encrypt(plain,encrypted,passphrase)
        verified = stage/'verified.zip'; _decrypt(encrypted,verified,passphrase)
        if _file(plain,stage,limit=LIMIT) != _file(verified,stage,limit=LIMIT): raise ValueError('ARCHIVE_VERIFY_FAILED')
        _unpack(verified,stage/'verified')
        summary = _file(encrypted,stage,limit=LIMIT+HEADER_SIZE+16)
        _publish(encrypted,destination,summary)
    return {'archive_path':str(destination),'archive_sha256':summary['sha256'],
            'bytes':summary['size'],'file_count':len(inventory),'workspace_id':marker['workspace_id'],
            'created_at':manifest.created_at.isoformat(),'verified':True}


def _fence(root, refs, archive_hash, manifest_hash):
    root = application_path(root)
    database = Database('sqlite:///'+str(root/'workbench.db'),filesystem_path(root/'protected'),load_settings(),initialize_schema=False)
    _mark_storage_flags(database)
    try:
        with database.session() as db:
            for row in db.scalars(select(SessionRow)): row.revoked = True
            from ..web.storage import JobRow, event
            pending = list(db.scalars(select(JobRow).where(JobRow.state.in_(('queued','running')))))
            for job in pending:
                job.state='blocked'; job.stage='恢复副本仅供核对'; job.error_code='BLOCKED_LIVE'; event(job,db)
            from ..assistant.providers.attempts import recover_attempts
            from ..assistant.providers.judge_attempts import recover_attempts as recover_judges
            judge_attempts = recover_judges(db)
            model_attempts = recover_attempts(db)
            from ..assistant.service import quarantine_runs
            assistant_jobs = quarantine_runs(db)
            from ..task_drafts.service import quarantine_executions
            task_executions = quarantine_executions(db)
            db.add(storage.RestoreFenceRow(ref=str(uuid4()),archive_sha256=archive_hash,
                manifest_sha256=manifest_hash,payload=encode({'restored_at':datetime.now(timezone.utc).isoformat(),
                'state':'quarantined','old_sessions_revoked':True,'jobs_quarantined':len(pending),
                'assistant_jobs_quarantined':assistant_jobs,
                'task_executions_quarantined':task_executions,'task_inbox_enabled':False,
                'weixin_inbox_enabled':False,
                'weixin_dispatch_enabled':False,
                'model_attempts_interrupted':model_attempts,
                'judge_attempts_interrupted':judge_attempts,
                'live_egress':False,'current_approvals_valid':False,'external_highwater':None}).decode()))
            grouped = {}
            for item in refs:
                key = (item['logical_ref'],item['sha256'])
                if key in grouped and grouped[key]['physical_ref'] != item['physical_ref']:
                    raise ValueError('RELOCATION_COLLISION')
                grouped.setdefault(key,{**item,'record_refs':[]})['record_refs'].append(item['record_ref'])
            for (logical,sha),item in grouped.items():
                old = db.get(storage.FileRelocationRow,(logical,sha))
                if old and old.physical_ref != item['physical_ref']: raise ValueError('RELOCATION_COLLISION')
                if not old: db.add(storage.FileRelocationRow(logical_ref=logical,sha256=sha,
                    physical_ref=item['physical_ref'],archive_sha256=archive_hash,record_refs=encode(item['record_refs']).decode()))
        from ..queries.ledger import recover_inflight
        recover_inflight(database)
        with database.session() as db:
            for item in refs: storage.relocation(item['logical_ref'],item['sha256'],db)
    finally: database.engine.dispose()


def restore_workspace_backup(archive, restore_parent, passphrase):
    archive = Path(archive).absolute()
    summary = _file(archive,archive.parent,limit=LIMIT+HEADER_SIZE+16)
    parent = checked_root(restore_parent,create=True)
    with TemporaryDirectory(prefix='.qx-restore-',dir=filesystem_path(parent)) as temporary:
        stage = Path(temporary); plain = stage/'archive.zip'
        _decrypt(archive,plain,passphrase)
        root = application_path(stage/'workspace')
        manifest, manifest_hash, refs = _unpack(plain,root)
        # _unpack also verifies newly created backups: it must never migrate.
        # Here all historical bytes/references have passed validation, and only
        # an isolated restore copy is upgraded under the native maintenance lock.
        from ..web.local_server import _worker_lock
        from ..web.workspace_upgrade import upgrade
        with _worker_lock(root): upgrade(root)
        _fence(root,refs,summary['sha256'],manifest_hash)
        _validate_database(root)
        if _file(archive,archive.parent,limit=LIMIT+HEADER_SIZE+16) != summary:
            raise ValueError('ARCHIVE_CHANGED')
        for item in manifest.files:
            if item.path.startswith('protected/'):
                path=root/_relative(item.path)
                if _file(path,root) != {'size':item.size,'sha256':item.sha256}: raise ValueError('RESTORED_FILE_CHANGED')
                filesystem_path(path).chmod(stat.S_IREAD)
        published = parent/str(uuid4()); filesystem_path(root).rename(filesystem_path(published))
    return {'archive_sha256':summary['sha256'],'restored_root':str(published),
            'workspace_id':str(manifest.workspace_id),'file_count':len(manifest.files),
            'quarantined':True,'restored_at':datetime.now(timezone.utc).isoformat()}
