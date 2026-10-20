"""Append-only local-library receipts and source snapshots on existing runs."""
import sqlite3


TABLES = ('assistant_handler_receipts', 'assistant_library_citations')
STATEMENTS = (
    '''CREATE TABLE assistant_handler_receipts (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        event_seq INTEGER NOT NULL CHECK(event_seq > 0),
        handler_id TEXT NOT NULL CHECK(handler_id IN ('legal_library.search','legal_library.read_original')),
        handler_version TEXT NOT NULL CHECK(handler_version = '1'),
        payload_sha256 TEXT NOT NULL,
        request_json TEXT NOT NULL CHECK(length(request_json) <= 8192),
        result_json TEXT NOT NULL CHECK(length(result_json) <= 262144),
        result_sha256 TEXT NOT NULL,
        scope_json TEXT NOT NULL CHECK(length(scope_json) <= 4096),
        created_at TEXT NOT NULL,
        UNIQUE(run_id,event_seq,handler_id,handler_version),
        FOREIGN KEY(run_id,event_seq) REFERENCES assistant_run_events(run_id,seq))''',
    '''CREATE TABLE assistant_library_citations (
        id TEXT PRIMARY KEY NOT NULL,
        receipt_id TEXT NOT NULL REFERENCES assistant_handler_receipts(id),
        ordinal INTEGER NOT NULL CHECK(ordinal >= 0 AND ordinal < 8),
        citation_json TEXT NOT NULL CHECK(length(citation_json) <= 32768),
        citation_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(receipt_id,ordinal))''',
) + tuple(
    f"CREATE TRIGGER immutable_{table}_{operation} BEFORE {operation.upper()} ON {table} "
    "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"
    for table in TABLES for operation in ('update', 'delete')
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
            "('assistant_handler_receipts','assistant_library_citations') ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
