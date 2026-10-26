"""Append-only, request-bound evidence snapshots, independent of model profiles."""
import sqlite3

TABLE = 'assistant_evidence_revisions'
STATEMENTS = (
    '''CREATE TABLE assistant_evidence_revisions (
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
        request_id TEXT NOT NULL, request_json TEXT NOT NULL CHECK(length(request_json)<=2097152),
        request_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL CHECK(length(snapshot_json)<=2097152),
        snapshot_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL REFERENCES sessions(id), created_at TEXT NOT NULL,
        PRIMARY KEY(conversation_id,revision), UNIQUE(conversation_id,request_id))''',
    "CREATE TRIGGER immutable_assistant_evidence_revisions_update BEFORE UPDATE ON assistant_evidence_revisions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_evidence_revisions_delete BEFORE DELETE ON assistant_evidence_revisions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as db:
        found=[tuple(r) for r in db.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='assistant_evidence_revisions' ORDER BY type,name")]
        if found:
            if found!=expected_objects():raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:db.exec_driver_sql(statement)
