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

from ..intake.schema import STATEMENTS, expected_objects


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
    receipt_path=root/'upgrade-intake-v1.json'
    _safe_file(receipt_path)
    if not receipt_path.is_file() or receipt_path.stat().st_size>4096:return False
    try:
        receipt=json.loads(receipt_path.read_text('utf-8'))
        if (set(receipt)!={'format','workspace_id','before_schema','after_schema','backup','backup_sha256'}
                or receipt['format']!=1 or receipt['workspace_id']!=marker['workspace_id']
                or receipt['before_schema']!=marker['schema_sha256']
                or not re.fullmatch(r'upgrade-backups/intake-[0-9a-f]{32}/before\.db',receipt['backup'])):
            return False
        actual=_rows(db); expected=expected_objects(); names={r[1] for r in expected}
        if ([r for r in actual if r[1] in names]!=expected
                or _hash([r for r in actual if r[1] not in names])!=receipt['before_schema']
                or _hash(actual)!=receipt['after_schema']):return False
        backup=root/receipt['backup']
        for path in (backup,backup.parent,backup.parent.parent):_safe_file(path)
        if not backup.is_file() or _file_hash(backup)!=receipt['backup_sha256']:return False
        with closing(sqlite3.connect(backup.as_uri()+'?mode=ro',uri=True)) as saved:
            return (_hash(_rows(saved))==receipt['before_schema']
                and saved.execute('PRAGMA quick_check').fetchall()==[('ok',)]
                and saved.execute('SELECT id FROM local_workspace_identity').fetchall()==[(marker['workspace_id'],)])
    except (ValueError,TypeError,KeyError,sqlite3.Error,OSError):return False


def upgrade(root):
    """Caller holds workspace worker lock and has validated paths and policy."""
    from .local_server import _safe_file
    marker=json.loads((root/'workspace.json').read_text('utf-8'))
    expected=expected_objects();names={r[1] for r in expected}
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        before=_rows(db);current_hash=_hash(before)
        if (db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]
                or db.execute('SELECT id FROM local_workspace_identity').fetchall()!=[(marker['workspace_id'],)]):
            raise ValueError('WORKSPACE_DATABASE_MISMATCH')
        if current_hash!=marker['schema_sha256']:
            if not pending_matches(db,root,marker):raise ValueError('WORKSPACE_DATABASE_MISMATCH')
            _write_marker(root,{**marker,'schema_sha256':current_hash})
            return
        present=[r for r in before if r[1] in names]
        if present:
            if present!=expected:raise ValueError('WORKSPACE_DATABASE_MISMATCH')
            return
        parent=root/'upgrade-backups';_safe_file(parent)
        parent.mkdir(exist_ok=True)
        folder=parent/('intake-'+uuid4().hex);folder.mkdir()
        backup=folder/'before.db'
        with closing(sqlite3.connect(backup)) as saved:
            db.backup(saved)
            if _rows(saved)!=before or saved.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
                raise ValueError('WORKSPACE_BACKUP_INVALID')
        with backup.open('r+b') as stream:os.fsync(stream.fileno())
        after_hash=_hash(sorted(before+expected,key=lambda r:(r[0],r[1])))
        _atomic_json(root/'upgrade-intake-v1.json',{'format':1,'workspace_id':marker['workspace_id'],
            'before_schema':current_hash,'after_schema':after_hash,'backup':backup.relative_to(root).as_posix(),
            'backup_sha256':_file_hash(backup)})
        # DDL must be explicitly transactional; sqlite3 otherwise autocommits it.
        db.execute('BEGIN IMMEDIATE')
        try:
            if _rows(db)!=before:raise ValueError('WORKSPACE_DATABASE_MISMATCH')
            for sql in STATEMENTS:db.execute(sql)
            if _hash(_rows(db))!=after_hash:raise ValueError('WORKSPACE_DATABASE_MISMATCH')
            db.commit()
        except BaseException:
            db.rollback();raise
        _write_marker(root,{**marker,'schema_sha256':after_hash})
