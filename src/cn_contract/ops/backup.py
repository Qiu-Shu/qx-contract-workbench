"""Authenticated fictional backups, raw-schema verification and durable restore fence.

No key is generated or looked up from an environment variable. This development
service accepts only the registered independent fictional originals. Production
key custody, latest external high-water checkpoint and host approval are absent.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import stat
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from zipfile import ZipFile, ZIP_STORED, BadZipFile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from ..domain import BackupConfig, BackupReport, BackupArchiveHeader, BackupManifestEvidence, Role
from ..persistence import Database, DocumentRow, ExportRow, SessionRow
from ..security import ServiceError, _principal
from . import storage

MAGIC = b'CN_SYNTHETIC_BACKUP_V1\n'
LIMIT = 256*1024*1024
FILE_LIMIT = 50*1024*1024
MAX_MEMBERS = 1024


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def strict_json(raw):
    if len(raw) > 4*1024*1024:
        raise ValueError('MANIFEST_LIMIT')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: raise ValueError('DUPLICATE_KEY')
            result[k] = v
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda v: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
        todo = [(result, 0)]
        while todo:
            value, depth = todo.pop()
            if depth > 30: raise ValueError('MANIFEST_DEPTH')
            if isinstance(value, dict): todo.extend((v, depth+1) for v in value.values())
            elif isinstance(value, list): todo.extend((v, depth+1) for v in value)
        return result
    except (RecursionError, UnicodeError, json.JSONDecodeError):
        raise ValueError('INVALID_MANIFEST') from None


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('UNSAFE_MEMBER')
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).is_absolute() or str(path) != value:
        raise ValueError('UNSAFE_MEMBER')
    for part in path.parts:
        if part in ('.', '..') or part.rstrip(' .') != part or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', part):
            raise ValueError('UNSAFE_MEMBER')
    return Path(*path.parts)


def redirected(path):
    from .file_paths import filesystem_path
    try:
        meta = filesystem_path(path).lstat()
        return stat.S_ISLNK(meta.st_mode) or bool(getattr(meta, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024))
    except OSError:
        return True


def checked_root(path, *, create=False):
    from .file_paths import filesystem_path, application_path
    path = filesystem_path(path)
    # Inspect every existing component before resolving, including junctions.
    for parent in (path, *path.parents):
        if parent.exists() and redirected(parent): raise ValueError('REDIRECTED_ROOT')
    if create: path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir(): raise ValueError('MISSING_ROOT')
    return application_path(path.resolve(strict=True))


def checked_file(path, root, *, limit=FILE_LIMIT):
    from .file_paths import filesystem_path
    root = filesystem_path(checked_root(root))
    path = filesystem_path(path)
    if not path.resolve(strict=True).is_relative_to(root): raise ValueError('FILE_OUTSIDE_ROOT')
    for parent in (path, *path.parents):
        if redirected(parent): raise ValueError('REDIRECTED_FILE')
        if parent == root: break
    meta = path.stat()
    if meta.st_nlink != 1 or not stat.S_ISREG(meta.st_mode) or meta.st_size > limit:
        raise ValueError('INVALID_FILE')
    with path.open('rb') as stream:
        actual = os.fstat(stream.fileno())
        if (actual.st_dev, actual.st_ino, actual.st_nlink, actual.st_size) != (meta.st_dev, meta.st_ino, 1, meta.st_size):
            raise ValueError('FILE_CHANGED')
        raw = stream.read(limit+1)
    if len(raw) != meta.st_size: raise ValueError('FILE_CHANGED')
    return raw


class SyntheticKeyStore:
    """Explicit public fictional test material only; no production credential API."""
    def __init__(self, keys):
        if not isinstance(keys, dict) or any(not isinstance(k, str) or not k.startswith('synthetic-') or type(v) is not bytes or len(v) != 32 for k, v in keys.items()):
            raise ValueError('SYNTHETIC_KEY_REFERENCE_REQUIRED')
        self.__keys = dict(keys)

    def resolve(self, reference):
        if reference not in self.__keys: raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
        return self.__keys[reference]


def _admin(actor, db):
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if principal is None: raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    if Role.ADMIN not in principal.roles: raise ServiceError('CROSS_MATTER_DENIED', 403)


def _schema(connection):
    return [(kind, name, table, ' '.join(sql.split())) for kind, name, table, sql in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name")]


def _tables(connection):
    result = {}
    for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if not re.fullmatch(r'[a-z_]+', name): raise ValueError('UNKNOWN_TABLE_NAME')
        rows = connection.execute('SELECT * FROM "'+name+'"').fetchall()
        result[name] = {'count': len(rows), 'sha256': digest(encode(sorted(rows, key=lambda row: encode(row))))}
    return result


def schema_reference(settings):
    from ..storage_schema import CURRENT_VERSION, normalized_schema
    return normalized_schema(CURRENT_VERSION)


def validate_raw_database(path, settings, *, expected_schema=None):
    # Must precede Database(), whose normal constructor creates missing objects.
    reference = expected_schema if expected_schema is not None else schema_reference(settings)
    checked_file(Path(path), Path(path).parent, limit=LIMIT)
    with closing(sqlite3.connect('file:'+Path(path).as_posix()+'?mode=ro', uri=True)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('DATABASE_INTEGRITY')
        if _schema(connection) != reference: raise ValueError('DATABASE_SCHEMA_MISMATCH')
        return _tables(connection)


def _file_references(db, *, allow_assistant=True):
    from ..exports.storage import ExportRecordRow, sha
    from ..assistant.attachment_integrity import file_references
    items = file_references(db, allowed=allow_assistant)
    for row in db.scalars(select(DocumentRow)):
        value = strict_json(row.payload.encode())
        if row.sha256 != value['sha256'] or str(row.id) != value['id'] or row.matter_id != value['matter_id']:
            raise ValueError('DOCUMENT_RECORD_MISMATCH')
        target = safe_relative(value['storage_ref']).as_posix()
        if target != f'{row.matter_id}/{row.id}/original.bin': raise ValueError('DOCUMENT_REFERENCE_MISMATCH')
        items.append({'logical_ref': value['storage_ref'], 'physical_ref': target, 'sha256': row.sha256, 'size': value['byte_size'], 'record_ref': row.id, 'kind': 'original', 'matter_id': row.matter_id})
    for row in db.scalars(select(ExportRow)):
        value = strict_json(row.payload.encode())
        if value['id'] != row.id or value['matter_id'] != row.matter_id: raise ValueError('EXPORT_RECORD_MISMATCH')
        filename = str(UUID(row.id))+'.docx'
        items.append({'logical_ref': value['storage_ref'], 'physical_ref': 'derived_exports/'+filename, 'sha256': value['content_sha256'], 'size': None, 'record_ref': row.id, 'kind': 'export', 'matter_id': row.matter_id})
    for row in db.scalars(select(ExportRecordRow).where(ExportRecordRow.kind == 'patch_result')):
        value = strict_json(row.payload.encode())
        if sha(value) != row.sha256: raise ValueError('PATCH_RECORD_MISMATCH')
        if value.get('status') != 'applied': continue
        filename = Path(value['storage_ref']).name
        if filename != str(UUID(Path(filename).stem))+'.docx': raise ValueError('PATCH_REFERENCE_MISMATCH')
        items.append({'logical_ref': value['storage_ref'], 'physical_ref': 'derived_exports/'+filename, 'sha256': value['target_sha256'], 'size': None, 'record_ref': row.ref, 'kind': 'patch', 'matter_id': row.matter_id})
    return items


def _registered_hashes():
    from ..review.synthetic import EXPECTED_HASHES
    from ..acceptance.registry import load_dataset
    from ..acceptance.assisted_registry import load_seed_policy
    return (set(EXPECTED_HASHES.values()) | {s.sha256 for s in load_dataset()}
            | set(load_seed_policy().document_hashes))


def _collect_files(db):
    root = checked_root(db.info['database'].storage_root)
    registered = _registered_hashes()
    files, refs = {}, _file_references(db, allow_assistant=False)
    for item in refs:
        if item['kind'] == 'original' and item['sha256'] not in registered:
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
        logical = Path(item['logical_ref'])
        if storage.quarantined(db):
            path = storage.relocation(item['logical_ref'], item['sha256'], db)
        else: path = logical if logical.is_absolute() else root/logical
        raw = checked_file(path, root)
        if digest(raw) != item['sha256'] or item['size'] is not None and len(raw) != item['size']:
            raise ValueError('FILE_HASH_MISMATCH')
        name = 'files/'+item['physical_ref']
        if name in files and files[name] != raw: raise ValueError('FILE_REFERENCE_COLLISION')
        files[name] = raw
        item['size'] = len(raw)
    return files, refs


def backup_and_verify(config, *, database, actor, key_resolver, restore_parent):
    config = BackupConfig.model_validate_json(config.model_dump_json())
    if not isinstance(database, Database) or type(key_resolver) is not SyntheticKeyStore:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    key = key_resolver.resolve(config.key_ref)  # Reject before creating anything.
    with database.session() as db:
        _admin(actor, db)
        from ..persistence import MatterRow
        from ..documents.local_materials import is_local
        if any(is_local(identifier,db) for identifier in db.scalars(select(MatterRow.id))):
            raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    root = checked_root(config.storage_ref, create=True)
    restore_root = checked_root(restore_parent, create=True)
    if root.is_relative_to(database.storage_root) or restore_root.is_relative_to(database.storage_root):
        raise ValueError('BACKUP_ROOT_OVERLAPS_SOURCE')
    source_path = Path(database.engine.url.database).absolute()
    schema = schema_reference(database.settings)
    validate_raw_database(source_path, database.settings, expected_schema=schema)
    archive_id = uuid4()
    # SQLite BEGIN IMMEDIATE is the maintenance write barrier. A separate read
    # connection performs native backup while this barrier protects referenced
    # transaction-owned immutable file bytes; no main-db file copy or live delete.
    with TemporaryDirectory(prefix='cn-synthetic-backup-') as temp:
        snapshot = Path(temp)/'database.db'
        with database.session() as db:
            _admin(actor, db)
            if any(is_local(identifier,db) for identifier in db.scalars(select(MatterRow.id))):
                raise ServiceError('DATA_POLICY_UNAPPROVED',409)
            files, refs = _collect_files(db)
            with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            tables = validate_raw_database(snapshot, database.settings, expected_schema=schema)
            database_raw = snapshot.read_bytes()
        manifest = {'version': 1, 'archive_id': str(archive_id), 'synthetic_only': True, 'created_at': datetime.now(timezone.utc).isoformat(),
            'source_database_sha256': digest(database_raw), 'schema_sha256': digest(encode(schema)), 'tables': tables,
            'files': refs, 'retention_days': config.retention_days, 'latest_external_checkpoint': None,
            'limitations': ['INDEPENDENT_FICTIONAL_DATA_ONLY', 'LATEST_EXTERNAL_HIGHWATER_UNKNOWN', 'PRODUCTION_KEY_CUSTODY_UNAPPROVED']}
        raw_manifest = encode(manifest)
        plain = BytesIO()
        with ZipFile(plain, 'w', compression=ZIP_STORED) as archive:
            archive.writestr('manifest.json', raw_manifest)
            archive.writestr('database.db', database_raw)
            for name, raw in sorted(files.items()): archive.writestr(name, raw)
        if len(plain.getbuffer()) > LIMIT: raise ValueError('ARCHIVE_LIMIT')
        header = encode({'version': 1, 'archive_id': str(archive_id), 'key_ref': config.key_ref, 'synthetic_only': True})
        nonce = os.urandom(12)
        aad = MAGIC+len(header).to_bytes(4, 'big')+header
        encrypted = aad+nonce+AESGCM(key).encrypt(nonce, plain.getvalue(), aad)
        destination = root/(str(archive_id)+'.cnbak')
        with destination.open('xb') as stream:
            stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
    return restore_backup(destination, key_resolver=key_resolver, restore_parent=restore_root, settings=database.settings)


def _decode_archive(path, resolver):
    path = Path(path).absolute()
    raw = checked_file(path, path.parent, limit=LIMIT+4096)
    if not raw.startswith(MAGIC): raise ValueError('ARCHIVE_FORMAT')
    offset = len(MAGIC)
    length = int.from_bytes(raw[offset:offset+4], 'big')
    if not 1 <= length <= 2048 or len(raw) < offset+4+length+28: raise ValueError('ARCHIVE_FORMAT')
    offset += 4
    header = strict_json(raw[offset:offset+length]); offset += length
    BackupArchiveHeader.model_validate(header)
    key = resolver.resolve(header['key_ref'])
    try: plain = AESGCM(key).decrypt(raw[offset:offset+12], raw[offset+12:], raw[:offset])
    except InvalidTag: raise ValueError('ARCHIVE_AUTHENTICATION_FAILED') from None
    return raw, header, plain


def restore_backup(backup_ref, *, key_resolver, restore_parent, settings):
    if type(key_resolver) is not SyntheticKeyStore: raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    raw, header, plain = _decode_archive(backup_ref, key_resolver)
    if len(plain) > LIMIT: raise ValueError('ARCHIVE_LIMIT')
    try:
        with ZipFile(BytesIO(plain)) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > MAX_MEMBERS or len(names) != len(set(n.casefold() for n in names)):
                raise ValueError('ARCHIVE_MEMBER_COLLISION')
            for entry in entries:
                safe_relative(entry.filename)
                if entry.is_dir() or entry.file_size > FILE_LIMIT or stat.S_ISLNK(entry.external_attr >> 16) or entry.file_size/max(entry.compress_size, 1) > 100:
                    raise ValueError('ARCHIVE_MEMBER_LIMIT')
            if sum(e.file_size for e in entries) > LIMIT: raise ValueError('ARCHIVE_LIMIT')
            manifest_raw = archive.read('manifest.json')
            manifest = strict_json(manifest_raw)
            BackupManifestEvidence.model_validate(manifest)
            if manifest.get('archive_id') != header['archive_id'] or manifest.get('version') != 1 or manifest.get('synthetic_only') is not True:
                raise ValueError('MANIFEST_IDENTITY')
            refs = manifest['files']
            allowed = {'database.db', 'manifest.json'} | {'files/'+safe_relative(i['physical_ref']).as_posix() for i in refs}
            if set(names) != allowed: raise ValueError('ARCHIVE_ALLOWLIST')
            payloads = {name: archive.read(name) for name in allowed}
    except (BadZipFile, RuntimeError, KeyError, TypeError, UnicodeError, EOFError):
        raise ValueError('INVALID_ARCHIVE') from None
    if digest(payloads['database.db']) != manifest['source_database_sha256']: raise ValueError('DATABASE_HASH_MISMATCH')
    from ..storage_schema import SUPPORTED_VERSIONS, normalized_schema
    schema = next((reference for version in SUPPORTED_VERSIONS
                   if digest(encode(reference := normalized_schema(version))) == manifest['schema_sha256']), None)
    if schema is None: raise ValueError('DATABASE_SCHEMA_MISMATCH')
    # All byte/hash/schema validation completes in a temporary root before the
    # new restore directory is allocated. No historical database is overwritten.
    with TemporaryDirectory(prefix='cn-synthetic-restore-check-') as temp:
        path = Path(temp)/'database.db'; path.write_bytes(payloads['database.db'])
        if validate_raw_database(path, settings, expected_schema=schema) != manifest['tables']:
            raise ValueError('DATABASE_ROWS_MISMATCH')
        check = Database('sqlite:///'+str(path), Path(temp)/'files', settings, initialize_schema=False)
        try:
            _mark_storage_flags(check)
            with check.session() as db:
                actual = _file_references(db, allow_assistant=False)
                if [{k: v for k, v in i.items() if k != 'size'} for i in actual] != [{k: v for k, v in i.items() if k != 'size'} for i in refs]:
                    raise ValueError('FILE_RECORD_MANIFEST_MISMATCH')
                registered = _registered_hashes()
                for item in refs:
                    file_raw = payloads['files/'+item['physical_ref']]
                    if digest(file_raw) != item['sha256'] or len(file_raw) != item['size'] or item['kind'] == 'original' and item['sha256'] not in registered:
                        raise ValueError('FILE_HASH_MISMATCH')
        finally: check.engine.dispose()
    parent = checked_root(restore_parent, create=True)
    # A failed write or safety delta never exposes an authoritative new root.
    # TemporaryDirectory only owns its checked newly created child of parent.
    with TemporaryDirectory(prefix='.restore-staging-', dir=parent) as staging:
        root = Path(staging)/'ready'; root.mkdir()
        database_path = root/'database.db'; database_path.write_bytes(payloads['database.db'])
        protected = root/'protected'; protected.mkdir()
        for name, file_raw in payloads.items():
            if not name.startswith('files/'): continue
            target = protected/safe_relative(name[6:]); target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream: stream.write(file_raw)
            target.chmod(stat.S_IREAD)
        # Only this fully verified staging copy may change; old table counts and
        # archive bytes were checked before any schema upgrade.
        from ..schema_migrations import upgrade_database
        with closing(sqlite3.connect(database_path)) as connection:
            upgrade_database(connection)
        validate_raw_database(database_path, settings)
        restored = Database('sqlite:///'+str(database_path), protected, settings, initialize_schema=False)
        _mark_storage_flags(restored)
        fence = uuid4()
        try:
            with restored.session() as db:
                for old in db.scalars(select(SessionRow)): old.revoked = True
                from ..web.storage import JobRow, event
                jobs = list(db.scalars(select(JobRow).where(JobRow.state.in_(('queued', 'running')))))
                for job in jobs:
                    job.state = 'blocked'; job.stage = '恢复隔离，外部发送高水位待人工核对'; job.error_code = 'BLOCKED_LIVE'; event(job, db)
                from ..assistant.service import quarantine_runs
                assistant_jobs = quarantine_runs(db)
                storage_payload = {'restored_at': datetime.now(timezone.utc).isoformat(), 'state': 'quarantined', 'external_highwater': None,
                    'old_sessions_revoked': True, 'jobs_quarantined': len(jobs), 'assistant_jobs_quarantined': assistant_jobs,
                    'live_egress': False, 'current_approvals_valid': False}
                db.add(storage.RestoreFenceRow(ref=str(fence), archive_sha256=digest(raw), manifest_sha256=digest(manifest_raw), payload=encode(storage_payload).decode()))
                grouped = {}
                for item in refs:
                    key = (item['logical_ref'], item['sha256'])
                    record = grouped.setdefault(key, {**item, 'record_refs': []})
                    if record['physical_ref'] != item['physical_ref']: raise ValueError('RELOCATION_COLLISION')
                    record['record_refs'].append(item['record_ref'])
                for (logical, sha), item in grouped.items():
                    existing = db.get(storage.FileRelocationRow, (logical, sha))
                    if existing is not None:
                        if existing.physical_ref != item['physical_ref']: raise ValueError('RELOCATION_COLLISION')
                    else: db.add(storage.FileRelocationRow(logical_ref=logical, sha256=sha, physical_ref=item['physical_ref'], archive_sha256=digest(raw), record_refs=encode(item['record_refs']).decode()))
            from ..queries.ledger import recover_inflight
            recover_inflight(restored)
            with restored.session() as db:
                for item in refs:
                    physical = storage.relocation(item['logical_ref'], item['sha256'], db)
                    if digest(checked_file(physical, protected)) != item['sha256']: raise ValueError('RESTORED_FILE_HASH_MISMATCH')
            restored_hash = digest(database_path.read_bytes())
        finally: restored.engine.dispose()
        published = parent/str(uuid4())
        root.rename(published)
    return BackupReport(backup_ref=str(Path(backup_ref).absolute()), restored_at=datetime.now(timezone.utc), ok=True, differences=(),
        archive_sha256=digest(raw), manifest_sha256=digest(manifest_raw), restored_root=str(published), restored_database_sha256=restored_hash,
        verified_file_count=len({i['physical_ref'] for i in refs}), source_table_counts={k: v['count'] for k, v in manifest['tables'].items()}, quarantine_ref=fence,
        limitations=('SYNTHETIC_ONLY', 'OLD_SESSIONS_REVOKED', 'ALL_PENDING_JOBS_QUARANTINED', 'CURRENT_APPROVALS_FENCED', 'EXTERNAL_HIGHWATER_UNKNOWN', 'PRODUCTION_BLOCKED'))


def _mark_storage_flags(database):
    for prefix in ('authority', 'rule', 'fact', 'review', 'provider', 'query', 'export', 'web', 'ops'):
        setattr(database, '_'+prefix+'_storage_initialized', True)
    # Existing services use plural flags; matching them is explicit, no DDL.
    for prefix in ('authorities', 'rules', 'facts', 'providers', 'queries'):
        setattr(database, '_'+prefix+'_storage_initialized', True)


def open_restored_database(report, *, settings):
    report = BackupReport.model_validate_json(report.model_dump_json())
    if not report.ok or report.restored_root is None or report.quarantine_ref is None: raise ValueError('VERIFIED_RESTORE_REQUIRED')
    root = checked_root(report.restored_root)
    validate_raw_database(root/'database.db', settings)
    database = Database('sqlite:///'+str(root/'database.db'), root/'protected', settings, initialize_schema=False)
    _mark_storage_flags(database)
    with database.session() as db:
        fence = db.scalar(select(storage.RestoreFenceRow).where(storage.RestoreFenceRow.ref == str(report.quarantine_ref)))
        if not fence or fence.archive_sha256 != report.archive_sha256 or fence.manifest_sha256 != report.manifest_sha256:
            database.engine.dispose(); raise ValueError('RESTORE_FENCE_MISMATCH')
    return database
