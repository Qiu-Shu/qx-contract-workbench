"""Versioned profile-input storage; no sender or archive handler is enabled here."""
import sqlite3

from . import context_schema, model_schema, profile_schema, rounds_schema, rounds_v2_schema


REQUIRES_FOREIGN_KEYS_OFF = True
FAMILY_TABLES = context_schema.FAMILY_TABLES + profile_schema.TABLES + ('assistant_profile_handlers',)
_FAMILY_SQL = ','.join("'"+name+"'" for name in FAMILY_TABLES)
_INSERT_COLUMNS = ','.join(rounds_v2_schema._COLUMNS)

STATEMENTS = rounds_v2_schema.STATEMENTS[:3] + (
    '''CREATE TABLE assistant_model_attempts_profile (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        policy_id TEXT NOT NULL, config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL,
        request_sha256 TEXT NOT NULL, input_json TEXT NOT NULL, config_json TEXT NOT NULL,
        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','sending','sent_unknown','received','failed_before_send')),
        claim_sha256 TEXT, updated_at TEXT NOT NULL,
        input_format TEXT NOT NULL DEFAULT 'plain-text-v1'
            CHECK(input_format IN ('plain-text-v1', 'library-context-v1', 'library-context-v2', 'profile-text-v1')),
        round_no INTEGER NOT NULL DEFAULT 1 CHECK(round_no >= 1 AND round_no <= 4),
        UNIQUE(run_id, round_no))''',
    f'INSERT INTO assistant_model_attempts_profile ({_INSERT_COLUMNS}) '
    f'SELECT {_INSERT_COLUMNS} FROM assistant_model_attempts',
    'DROP TABLE assistant_model_attempts',
    'ALTER TABLE assistant_model_attempts_profile RENAME TO assistant_model_attempts',
) + rounds_v2_schema.STATEMENTS[7:] + (
    '''CREATE TABLE assistant_profile_handlers (
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        event_seq INTEGER NOT NULL CHECK(typeof(event_seq) = 'integer' AND event_seq > 0),
        handler_id TEXT NOT NULL CHECK(handler_id = 'profile.save'),
        handler_version TEXT NOT NULL CHECK(handler_version = '1'),
        attempt_id TEXT NOT NULL UNIQUE REFERENCES assistant_model_attempts(id),
        output_id TEXT NOT NULL UNIQUE REFERENCES assistant_model_outputs(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        profile_receipt_sequence INTEGER CHECK(profile_receipt_sequence IS NULL OR
            (typeof(profile_receipt_sequence) = 'integer' AND profile_receipt_sequence > 0)),
        outcome TEXT NOT NULL CHECK(outcome IN ('applied','unchanged','blocked')),
        reason_code TEXT CHECK(reason_code IS NULL OR reason_code IN ('version_conflict','save_failed')),
        basis_sha256 TEXT NOT NULL CHECK(typeof(basis_sha256) = 'text' AND length(basis_sha256) = 64
            AND length(CAST(basis_sha256 AS BLOB)) = 64
            AND basis_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL,
        PRIMARY KEY(run_id,event_seq,handler_id,handler_version),
        UNIQUE(conversation_id,profile_receipt_sequence),
        FOREIGN KEY(run_id,event_seq) REFERENCES assistant_run_events(run_id,seq),
        FOREIGN KEY(conversation_id,profile_receipt_sequence)
            REFERENCES assistant_profile_receipts(conversation_id,sequence),
        CHECK((outcome = 'blocked' AND reason_code IS NOT NULL AND profile_receipt_sequence IS NULL) OR
            (outcome IN ('applied','unchanged') AND reason_code IS NULL AND profile_receipt_sequence IS NOT NULL)))''',
) + tuple(
    f"CREATE TRIGGER immutable_assistant_profile_handlers_{operation} BEFORE {operation.upper()} "
    "ON assistant_profile_handlers BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"
    for operation in ('update', 'delete')
)


def _found(raw):
    return [tuple(row) for row in raw.execute(
        'SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN ('+_FAMILY_SQL+') ORDER BY type,name')]


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in (model_schema.STATEMENTS + context_schema.STATEMENTS + rounds_schema.STATEMENTS
                          + rounds_v2_schema.STATEMENTS + profile_schema.STATEMENTS + STATEMENTS):
            db.execute(statement)
        return _found(db)


def expected_model_objects():
    return [row for row in expected_objects() if row[2] in model_schema.TABLES]


def expected_context_objects():
    return [row for row in expected_objects() if row[2] in context_schema.FAMILY_TABLES]


def initialize_storage(database):
    """Only rebuild the complete known predecessor, never repair a partial family."""
    raw = database.engine.raw_connection()
    try:
        found = _found(raw)
        expected = expected_objects()
        if found == expected:
            return
        previous = sorted(rounds_v2_schema.expected_objects() + profile_schema.expected_objects(),
                          key=lambda row: (row[0], row[1]))
        if found != previous:
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
        raw.execute('PRAGMA foreign_keys=OFF')
        try:
            raw.execute('BEGIN IMMEDIATE')
            try:
                if _found(raw) != found:
                    raise ValueError('DATABASE_SCHEMA_MISMATCH')
                for statement in STATEMENTS:
                    raw.execute(statement)
                if _found(raw) != expected:
                    raise ValueError('DATABASE_SCHEMA_MISMATCH')
                if raw.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('DATABASE_INTEGRITY')
                raw.execute('COMMIT')
            except BaseException:
                raw.execute('ROLLBACK')
                raise
        finally:
            raw.execute('PRAGMA foreign_keys=ON')
    finally:
        raw.close()
