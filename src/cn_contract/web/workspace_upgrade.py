"""Native-only, precisely bounded additive upgrade with a pre-change DB backup.

The marker is finalized after SQLite commits. A crash in that gap is accepted
only with the receipt, intact legacy backup and exact expected schema delta.
"""
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
from uuid import uuid4

from ..intake.schema import STATEMENTS
from ..ops.file_paths import sqlite_readonly_uri
from ..schema_migrations import requires_foreign_keys_off, statements_for
from ..storage_schema import VERSIONS, identify_schema, schema_rows


def _rows(db):
    return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def _hash(rows):
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()


def _file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path,value):
    from .local_server import _safe_file
    _safe_file(path)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


def _write_marker(root,marker):
    _atomic_json(root/'workspace.json',marker)


def pending_matches(db,root,marker):
    from .local_server import _safe_file
    try:
        actual = _rows(db)
        target = identify_schema(actual, native=True)
        if target == VERSIONS[0]:return False
        previous = VERSIONS[VERSIONS.index(target) - 1]
        before = schema_rows(previous, native=True)
        receipt_path = root/('upgrade-' + target + '.json')
        _safe_file(receipt_path)
        if not receipt_path.is_file() or receipt_path.stat().st_size>4096:return False
        receipt=json.loads(receipt_path.read_text('utf-8'))
        prefix = target.split('-v', 1)[0]
        if (type(receipt) is not dict
                or set(receipt)!={'format','workspace_id','before_schema','after_schema','backup','backup_sha256'}
                or type(receipt['format']) is not int or receipt['format']!=1
                or receipt['workspace_id']!=marker['workspace_id']
                or receipt['before_schema']!=marker['schema_sha256'] or receipt['before_schema']!=_hash(before)
                or receipt['after_schema']!=_hash(actual)
                or not re.fullmatch(r'upgrade-backups/'+prefix+r'-[0-9a-f]{32}/before\.db',receipt['backup'])):
            return False
        backup=root/receipt['backup']
        for path in (backup,backup.parent,backup.parent.parent):_safe_file(path)
        if not backup.is_file() or _file_hash(backup)!=receipt['backup_sha256']:return False
        with closing(sqlite3.connect(sqlite_readonly_uri(backup),uri=True)) as saved:
            return (_rows(saved)==before
                and saved.execute('PRAGMA quick_check').fetchall()==[('ok',)]
                and not saved.execute('PRAGMA foreign_key_check').fetchall()
                and saved.execute('SELECT id FROM local_workspace_identity').fetchall()==[(marker['workspace_id'],)])
    except (ValueError,TypeError,KeyError,sqlite3.Error,OSError):return False


def upgrade(root):
    """Caller holds workspace worker lock and has validated paths and policy."""
    from .local_server import _safe_file
    marker=json.loads((root/'workspace.json').read_text('utf-8'))
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        before=_rows(db);current_hash=_hash(before)
        try:
            version=identify_schema(before,native=True)
        except ValueError:
            raise ValueError('WORKSPACE_DATABASE_MISMATCH') from None
        if (db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]
                or db.execute('PRAGMA foreign_key_check').fetchall()
                or db.execute('SELECT id FROM local_workspace_identity').fetchall()!=[(marker['workspace_id'],)]):
            raise ValueError('WORKSPACE_DATABASE_MISMATCH')
        if current_hash!=marker['schema_sha256']:
            if not pending_matches(db,root,marker):raise ValueError('WORKSPACE_DATABASE_MISMATCH')
            marker={**marker,'schema_sha256':current_hash}
            _write_marker(root,marker)
        for target in VERSIONS[VERSIONS.index(version)+1:]:
            parent=root/'upgrade-backups';_safe_file(parent)
            parent.mkdir(exist_ok=True)
            prefix=target.split('-v',1)[0]
            folder=parent/(prefix+'-'+uuid4().hex);folder.mkdir()
            backup=folder/'before.db'
            with closing(sqlite3.connect(backup)) as saved:
                db.backup(saved)
                if (_rows(saved)!=before or saved.execute('PRAGMA quick_check').fetchall()!=[('ok',)]
                        or saved.execute('PRAGMA foreign_key_check').fetchall()):
                    raise ValueError('WORKSPACE_BACKUP_INVALID')
            with backup.open('r+b') as stream:os.fsync(stream.fileno())
            after=schema_rows(target,native=True);after_hash=_hash(after)
            _atomic_json(root/('upgrade-'+target+'.json'),{'format':1,'workspace_id':marker['workspace_id'],
                'before_schema':_hash(before),'after_schema':after_hash,'backup':backup.relative_to(root).as_posix(),
                'backup_sha256':_file_hash(backup)})
            # Keep the intake fault-injection seam and its historical DDL unchanged.
            statements=STATEMENTS if target=='intake-v1' else statements_for(target)
            # A table-rebuild migration DROPs a referenced parent; open the FK
            # OFF window before BEGIN and restore enforcement after the outcome.
            fk_off=requires_foreign_keys_off(target)
            if fk_off:db.execute('PRAGMA foreign_keys=OFF')
            try:
                db.execute('BEGIN IMMEDIATE')
                try:
                    if _rows(db)!=before:raise ValueError('WORKSPACE_DATABASE_MISMATCH')
                    for sql in statements:db.execute(sql)
                    if _rows(db)!=after or db.execute('PRAGMA foreign_key_check').fetchall():
                        raise ValueError('WORKSPACE_DATABASE_MISMATCH')
                    db.commit()
                except BaseException:
                    db.rollback();raise
            finally:
                if fk_off:db.execute('PRAGMA foreign_keys=ON')
            marker={**marker,'schema_sha256':after_hash}
            _write_marker(root,marker)
            before=after
