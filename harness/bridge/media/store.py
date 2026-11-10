"""Short SQLite transactions, immutable revisions, explicit ownership."""
from contextlib import contextmanager, nullcontext
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import stat
from uuid import uuid4

from . import domain as d
from .access import require_access


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


SCHEMA = [
    'CREATE TABLE media_meta(workspace_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)',
    '''CREATE TABLE media_entities(id TEXT PRIMARY KEY,kind TEXT NOT NULL,workspace_id TEXT NOT NULL,
       owner_user_id TEXT NOT NULL,visibility TEXT NOT NULL CHECK(visibility IN ('owner_only','workspace')),
       revision INTEGER NOT NULL CHECK(revision>0),created_at TEXT NOT NULL)''',
    '''CREATE TABLE media_revisions(entity_id TEXT NOT NULL REFERENCES media_entities(id),
       revision INTEGER NOT NULL CHECK(revision>0),content TEXT NOT NULL,sha256 TEXT NOT NULL,
       created_at TEXT NOT NULL,PRIMARY KEY(entity_id,revision))''',
    '''CREATE TRIGGER media_revision_no_update BEFORE UPDATE ON media_revisions
       BEGIN SELECT RAISE(ABORT,'immutable revision'); END''',
    '''CREATE TRIGGER media_revision_no_delete BEFORE DELETE ON media_revisions
       BEGIN SELECT RAISE(ABORT,'immutable revision'); END''',
]

JOB_SCHEMA = [
    '''CREATE TABLE media_jobs(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,owner_user_id TEXT NOT NULL,
       request_id TEXT NOT NULL,input_digest TEXT NOT NULL,input TEXT NOT NULL,kind TEXT NOT NULL,
       project_id TEXT,state TEXT NOT NULL,attempt_id TEXT,worker_run_id TEXT,sent INTEGER NOT NULL DEFAULT 0,
       output TEXT,receipt TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
       UNIQUE(workspace_id,owner_user_id,request_id))''',
    'CREATE INDEX media_job_queue ON media_jobs(state,created_at)',
]

SOURCE_SCHEMA = [
    '''CREATE TABLE media_source_state(workspace_id TEXT NOT NULL,owner_user_id TEXT NOT NULL,
       source_id TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(workspace_id,owner_user_id,source_id))''',
]
EXPORT_SCHEMA = [
    '''CREATE TABLE media_exports(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,owner_user_id TEXT NOT NULL,
       mode TEXT NOT NULL,refs TEXT NOT NULL,review_ref TEXT,manifest TEXT NOT NULL,
       relative_name TEXT NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL)''',
]
SCHEMAS = {1:SCHEMA, 2:SCHEMA+JOB_SCHEMA, 3:SCHEMA+JOB_SCHEMA+SOURCE_SCHEMA,
           4:SCHEMA+JOB_SCHEMA+SOURCE_SCHEMA+EXPORT_SCHEMA}


def safe(root, path):
    path = Path(path).absolute()
    if '..' in path.parts or not path.is_relative_to(root):
        raise ValueError('UNSAFE_PATH')
    cursor = path
    while True:
        if cursor.exists() or cursor.is_symlink():
            info = cursor.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('UNSAFE_PATH')
            if cursor.is_file() and info.st_nlink != 1:
                raise ValueError('UNSAFE_PATH')
        if cursor == root: break
        cursor = cursor.parent
    return path


class MediaStore:
    def __init__(self, workspace, actor: d.MediaActorContext):
        self.actor = d.MediaActorContext.model_validate(actor.model_dump())
        self.root = Path(workspace).absolute()
        safe(self.root, self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.internal = safe(self.root, self.root / '.qx-media')
        self.internal.mkdir(exist_ok=True)
        self.readonly = (self.internal/'RESTORED_READ_ONLY').exists()
        self.path = safe(self.root, self.internal / 'media.sqlite')
        with self.db(write=not self.readonly) as db:
            objects = {r['name']: r['sql'] for r in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if not objects:
                if self.readonly: raise PermissionError('RESTORED_READ_ONLY')
                for sql in SCHEMAS[4]: db.execute(sql)
                db.execute('INSERT INTO media_meta VALUES(?,4)', (actor.workspace_id,))
            else:
                if 'media_meta' not in objects: raise ValueError('SCHEMA_MISMATCH')
                meta = db.execute('SELECT * FROM media_meta').fetchall()
                if len(meta) != 1 or meta[0]['schema_version'] not in SCHEMAS:
                    raise ValueError('SCHEMA_MISMATCH')
                version = meta[0]['schema_version']
                expected = {sql.split()[2].split('(')[0]: sql for sql in SCHEMAS[version]}
                if set(objects) != set(expected):
                    raise ValueError('SCHEMA_MISMATCH')
                normalize = lambda sql: ' '.join(sql.split()).casefold()
                if any(normalize(objects[name]) != normalize(sql) for name, sql in expected.items()):
                    raise ValueError('SCHEMA_MISMATCH')
                if meta[0]['workspace_id'] != actor.workspace_id: raise PermissionError('ACCESS_DENIED')
                if version<4:
                    if self.readonly: raise PermissionError('RESTORED_READ_ONLY')
                    for sql in SCHEMAS[4][len(SCHEMAS[version]):]: db.execute(sql)
                    db.execute('UPDATE media_meta SET schema_version=4')
            meta = db.execute('SELECT * FROM media_meta').fetchall()
            if len(meta) != 1 or meta[0]['schema_version'] != 4:
                raise ValueError('SCHEMA_MISMATCH')
            if meta[0]['workspace_id'] != actor.workspace_id:
                raise PermissionError('ACCESS_DENIED')

    @contextmanager
    def db(self, *, write=False):
        if write and self.readonly: raise PermissionError('RESTORED_READ_ONLY')
        safe(self.root, self.path)
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            if self.readonly: connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _entity(self, db, entity_id, *, write=False):
        entity = db.execute('SELECT * FROM media_entities WHERE id=?', (entity_id,)).fetchone()
        if entity is None: raise ValueError('NOT_FOUND')
        require_access(self.actor, entity, write=write)
        return entity

    def _load(self, db, ref, *, current=False):
        ref = d.MediaRevisionRef.model_validate(ref.model_dump() if isinstance(ref, d.MediaRevisionRef) else ref)
        entity = self._entity(db, ref.entity_id)
        row = db.execute('SELECT * FROM media_revisions WHERE entity_id=? AND revision=?',
                         (ref.entity_id, ref.revision)).fetchone()
        if row is None or entity['kind'] != ref.kind or row['sha256'] != ref.content_sha256:
            raise ValueError('REFERENCE_MISMATCH')
        value = json.loads(row['content'])
        if digest(value) != row['sha256']: raise ValueError('REFERENCE_MISMATCH')
        if current and entity['revision'] != ref.revision: raise ValueError('STALE_REFERENCE')
        return {'ref': ref.model_dump(mode='json'), 'value': value,
                'visibility': entity['visibility'], 'created_at': row['created_at']}

    def load(self, ref, *, current=False):
        with self.db() as db: return self._load(db, ref, current=current)

    def head(self, entity_id):
        with self.db() as db:
            entity = self._entity(db, entity_id)
            row = db.execute('SELECT sha256 FROM media_revisions WHERE entity_id=? AND revision=?',
                             (entity_id, entity['revision'])).fetchone()
            return d.MediaRevisionRef(kind=entity['kind'], entity_id=entity_id,
                                     revision=entity['revision'], content_sha256=row['sha256'])

    def list(self, kind, *, transaction=None):
        with (nullcontext(transaction) if transaction is not None else self.db()) as db:
            rows = db.execute('''SELECT e.id,e.kind,e.revision,r.sha256 FROM media_entities e
              JOIN media_revisions r ON r.entity_id=e.id AND r.revision=e.revision
              WHERE e.kind=? AND e.workspace_id=? AND (e.owner_user_id=? OR e.visibility='workspace')
              ORDER BY e.created_at,e.id''', (kind, self.actor.workspace_id, self.actor.user_id)).fetchall()
            return [self._load(db, d.MediaRevisionRef(kind=r['kind'],entity_id=r['id'],
                       revision=r['revision'],content_sha256=r['sha256'])) for r in rows]

    def save(self, kind, value, *, expected_revision, entity_id=None, visibility='owner_only', transaction=None):
        if self.readonly: raise PermissionError('RESTORED_READ_ONLY')
        if kind not in d.INPUT_MODELS: raise ValueError('UNKNOWN_KIND')
        value = d.INPUT_MODELS[kind].model_validate(value).model_dump(mode='json')
        if type(expected_revision) is not int or expected_revision < 0: raise ValueError('INVALID_REVISION')
        if visibility not in ('owner_only', 'workspace'): raise ValueError('INVALID_VISIBILITY')
        if kind == 'conversation' and visibility != 'owner_only': raise ValueError('PRIVATE_CONVERSATION')
        if kind == 'memory' and value['confirmation'] != 'confirmed' and visibility != 'owner_only':
            raise ValueError('PRIVATE_MEMORY')
        now = d.utc_stamp()
        with (nullcontext(transaction) if transaction is not None else self.db(write=True)) as db:
            if kind in ('brief','script','shooting_plan'):
                existing=db.execute('''SELECT e.id,e.revision FROM media_entities e JOIN media_revisions r
                    ON r.entity_id=e.id AND r.revision=e.revision WHERE e.kind=? AND e.workspace_id=?
                    AND json_extract(r.content,'$.project_ref.entity_id')=?''',
                    (kind,self.actor.workspace_id,value['project_ref']['entity_id'])).fetchone()
                if existing:
                    if entity_id is not None and existing['id']!=entity_id: raise ValueError('PROJECT_CONTENT_CONFLICT')
                    entity_id=existing['id']
            if 'profile_ref' in value:
                if value['profile_ref']['kind'] != 'profile': raise ValueError('REFERENCE_MISMATCH')
                self._load(db, value['profile_ref'], current=kind!='memory')
            from .content import references
            for ref in references(value):
                self._load(db,ref,current=not(kind=='memory' and ref.kind=='profile'))
            if entity_id is None:
                if expected_revision != 0: raise ValueError('VERSION_CONFLICT')
                entity_id = str(uuid4())
                db.execute('INSERT INTO media_entities VALUES(?,?,?,?,?,?,?)',
                    (entity_id, kind, self.actor.workspace_id, self.actor.user_id, visibility, 1, now))
            else:
                entity = self._entity(db, entity_id, write=True)
                if entity['kind'] != kind: raise ValueError('REFERENCE_MISMATCH')
                if entity['revision'] != expected_revision: raise ValueError('VERSION_CONFLICT')
                db.execute('UPDATE media_entities SET revision=?,visibility=? WHERE id=?',
                           (expected_revision+1, visibility, entity_id))
            sha = digest(value)
            db.execute('INSERT INTO media_revisions VALUES(?,?,?,?,?)',
                       (entity_id, expected_revision+1, encoded(value), sha, now))
        return d.MediaRevisionRef(kind=kind, entity_id=entity_id, revision=expected_revision+1, content_sha256=sha)
