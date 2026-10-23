"""assistant-rounds-v2: widen input_format for the bounded-rounds wire.

The rounds-v1 CHECK predates the library-context-v2 tool-plan format and
SQLite cannot alter a CHECK in place, so the attempts table is rebuilt once
more by a fixed statement sequence. Every other object keeps its frozen
bytes. Same FK OFF discipline as the rounds-v1 rebuild: the statements DROP
a referenced parent, so callers run them with foreign_keys=OFF inside one
transaction and verify PRAGMA foreign_key_check before committing.
"""
import sqlite3

from . import context_schema, model_schema, rounds_schema

# upgrade_database must open its FK OFF window for this version.
REQUIRES_FOREIGN_KEYS_OFF = True

_COLUMNS = rounds_schema._COLUMNS + ('round_no',)
_INSERT_COLUMNS = ','.join(_COLUMNS)

STATEMENTS = (
    'DROP TRIGGER immutable_assistant_model_input',
    'DROP TRIGGER immutable_assistant_model_claim',
    'DROP TRIGGER immutable_assistant_model_attempts_delete',
    '''CREATE TABLE assistant_model_attempts_rounds (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        policy_id TEXT NOT NULL, config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL,
        request_sha256 TEXT NOT NULL, input_json TEXT NOT NULL, config_json TEXT NOT NULL,
        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','sending','sent_unknown','received','failed_before_send')),
        claim_sha256 TEXT, updated_at TEXT NOT NULL,
        input_format TEXT NOT NULL DEFAULT 'plain-text-v1'
            CHECK(input_format IN ('plain-text-v1', 'library-context-v1', 'library-context-v2')),
        round_no INTEGER NOT NULL DEFAULT 1 CHECK(round_no >= 1 AND round_no <= 4),
        UNIQUE(run_id, round_no))''',
    f'INSERT INTO assistant_model_attempts_rounds ({_INSERT_COLUMNS}) '
    f'SELECT {_INSERT_COLUMNS} FROM assistant_model_attempts',
    'DROP TABLE assistant_model_attempts',
    'ALTER TABLE assistant_model_attempts_rounds RENAME TO assistant_model_attempts',
    '''CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF
        id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
        input_json,config_json,policy_json,reserved_usd,created_at,input_format,round_no
        ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_assistant_model_claim BEFORE UPDATE OF claim_sha256
        ON assistant_model_attempts WHEN OLD.claim_sha256 IS NOT NULL AND NEW.claim_sha256 IS NOT OLD.claim_sha256
        BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    # Byte-identical to the frozen V1 trigger: an unchanged object keeps its bytes.
    "CREATE TRIGGER immutable_assistant_model_attempts_delete BEFORE DELETE ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
)


def _rows(statements):
    with sqlite3.connect(':memory:') as db:
        for statement in statements:
            db.execute(statement)
        return db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
            "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',"
            "'assistant_model_input_citations') ORDER BY type,name").fetchall()


def expected_objects():
    """Exact model-family rows after both rebuilds, derived deterministically."""
    return _rows(model_schema.STATEMENTS + context_schema.STATEMENTS
                 + rounds_schema.STATEMENTS + STATEMENTS)


def expected_model_objects():
    """The exact rows the legacy model initializer may see after this rebuild."""
    return [row for row in expected_objects() if row[2] in model_schema.TABLES]


def expected_context_objects():
    """The exact rows the context initializer may see after this rebuild."""
    return [row for row in expected_objects() if row[2] in context_schema.FAMILY_TABLES]


def expected_rounds_objects():
    """The exact rows the rounds-v1 initializer may see after this rebuild."""
    return expected_objects()


def _found(raw):
    return [tuple(row) for row in raw.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
        "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',"
        "'assistant_model_input_citations') ORDER BY type,name")]


def initialize_storage(database):
    """Migrate a positively identified rounds-v1 family; the rebuild needs FK OFF.

    The engine begin hook issues BEGIN IMMEDIATE for SQLAlchemy transactions,
    so the FK OFF window is opened on the raw driver connection instead.
    """
    raw = database.engine.raw_connection()
    try:
        found = _found(raw)
        if not found:
            return
        if found == expected_objects():
            return
        from .profile_model_schema import expected_context_objects as profile_model_objects
        if found == profile_model_objects():
            return
        # Only the positively identified rounds-v1 family is rebuilt in place.
        if found != rounds_schema.expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
        # The engine connect hook enables FK on every connection; the rebuild
        # DROPs a referenced parent, so the window must be opened before BEGIN.
        raw.execute('PRAGMA foreign_keys=OFF')
        raw.execute('BEGIN IMMEDIATE')
        try:
            for statement in STATEMENTS:
                raw.execute(statement)
            if _found(raw) != expected_objects():
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
