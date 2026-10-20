"""Additive Jev ledger on the existing run; no second queue or main-run fields."""
import sqlite3


TABLES = ('assistant_judge_attempts', 'assistant_judge_receipts', 'assistant_judge_decisions')
STATEMENTS = (
    '''CREATE TABLE assistant_judge_attempts (
        id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        message_id TEXT NOT NULL REFERENCES assistant_messages(id),
        actor_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),
        purpose TEXT NOT NULL CHECK(purpose IN ('primary_intent','material_kind','possible_result_guarantee')),
        policy_id TEXT NOT NULL, authorization_id TEXT NOT NULL,
        config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL, input_hash TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, request_json TEXT NOT NULL, config_json TEXT NOT NULL,
        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','sending','not_sent','sent_unknown','received')),
        claim_sha256 TEXT, updated_at TEXT NOT NULL, UNIQUE(run_id,purpose))''',
    '''CREATE TABLE assistant_judge_receipts (
        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_judge_attempts(id),
        receipt_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE assistant_judge_decisions (
        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_judge_attempts(id),
        decision_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TRIGGER immutable_assistant_judge_input BEFORE UPDATE OF
        id,run_id,conversation_id,message_id,actor_id,session_id,purpose,policy_id,authorization_id,
        config_sha256,policy_sha256,input_hash,source_sha256,request_json,config_json,policy_json,reserved_usd,created_at
        ON assistant_judge_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_assistant_judge_claim BEFORE UPDATE OF claim_sha256
        ON assistant_judge_attempts WHEN OLD.claim_sha256 IS NOT NULL AND NEW.claim_sha256 IS NOT OLD.claim_sha256
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
            "('assistant_judge_attempts','assistant_judge_receipts','assistant_judge_decisions') ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
