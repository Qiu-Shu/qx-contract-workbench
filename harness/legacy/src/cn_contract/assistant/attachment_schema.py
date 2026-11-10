"""Additive assistant-attachments-v1 schema; historical originals are immutable."""
import sqlite3


TABLES = ('assistant_attachments', 'assistant_attachment_parses', 'assistant_material_snapshots')
STATEMENTS = (
    '''CREATE TABLE assistant_attachments (
        id TEXT PRIMARY KEY NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        workspace_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        original_name TEXT NOT NULL, mime TEXT NOT NULL,
        byte_size INTEGER NOT NULL CHECK(byte_size > 0),
        sha256 TEXT NOT NULL, storage_ref TEXT NOT NULL, policy_json TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        UNIQUE(conversation_id, request_id), UNIQUE(conversation_id, id))''',
    '''CREATE TABLE assistant_attachment_parses (
        conversation_id TEXT NOT NULL, attachment_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision > 0),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        parser_version TEXT NOT NULL, baseline_view TEXT,
        reading_status TEXT NOT NULL CHECK(reading_status IN ('readable','partial','needs_baseline','failed')),
        result_json TEXT, result_sha256 TEXT, failure_code TEXT,
        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        PRIMARY KEY(attachment_id, revision),
        FOREIGN KEY(conversation_id, attachment_id) REFERENCES assistant_attachments(conversation_id, id),
        UNIQUE(conversation_id, request_id))''',
    '''CREATE TABLE assistant_material_snapshots (
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        revision INTEGER NOT NULL CHECK(revision > 0),
        kind TEXT NOT NULL CHECK(kind IN ('upload','parse','selection')),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, items_json TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        PRIMARY KEY(conversation_id, revision), UNIQUE(conversation_id, request_id))''',
) + tuple(
    f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"
    for table in TABLES for action in ('UPDATE', 'DELETE')
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
            "('assistant_attachments','assistant_attachment_parses','assistant_material_snapshots') ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
