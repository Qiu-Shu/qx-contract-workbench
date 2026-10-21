"""Additive model ledger schema; attempts keep immutable approval/input evidence."""
import sqlite3


TABLES = ('assistant_model_attempts', 'assistant_model_receipts', 'assistant_model_outputs')
STATEMENTS = (
    '''CREATE TABLE assistant_model_attempts (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        policy_id TEXT NOT NULL, config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL,
        request_sha256 TEXT NOT NULL, input_json TEXT NOT NULL, config_json TEXT NOT NULL,
        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','sending','sent_unknown','received','failed_before_send')),
        claim_sha256 TEXT, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE assistant_model_receipts (
        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_model_attempts(id),
        receipt_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE assistant_model_outputs (
        id TEXT PRIMARY KEY NOT NULL,
        attempt_id TEXT NOT NULL UNIQUE REFERENCES assistant_model_attempts(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id),
        scope_json TEXT NOT NULL, output_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF
        id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
        input_json,config_json,policy_json,reserved_usd,created_at
        ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_assistant_model_claim BEFORE UPDATE OF claim_sha256
        ON assistant_model_attempts WHEN OLD.claim_sha256 IS NOT NULL AND NEW.claim_sha256 IS NOT OLD.claim_sha256
        BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
) + tuple(
    f"CREATE TRIGGER immutable_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"
    for table in TABLES
) + tuple(
    f"CREATE TRIGGER immutable_{table}_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"
    for table in TABLES[1:]
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
            "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs') ORDER BY type,name")]
        if found:
            # The positively identified context-v1, rounds-v1 and rounds-v2
            # successors are also accepted; partial migrations and unknown
            # structures stay rejected.
            from .context_schema import expected_model_objects
            from .rounds_schema import expected_model_objects as rounds_model_objects
            from .rounds_v2_schema import expected_model_objects as rounds_v2_model_objects
            if (found != expected_objects() and found != expected_model_objects()
                    and found != rounds_model_objects() and found != rounds_v2_model_objects()):
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
