"""assistant-context-v1: immutable input format and ordered source relations.

New databases run the frozen model V1 statements first, then this exact ALTER
sequence, so CREATE and migration produce the same sqlite_master SQL. Partial
or unknown structures are rejected, never repaired.
"""
import sqlite3

from . import model_schema

FAMILY_TABLES = ('assistant_model_attempts', 'assistant_model_receipts',
                 'assistant_model_outputs', 'assistant_model_input_citations')
STATEMENTS = (
    '''ALTER TABLE assistant_model_attempts ADD COLUMN input_format TEXT NOT NULL
        DEFAULT 'plain-text-v1'
        CHECK(input_format IN ('plain-text-v1', 'library-context-v1'))''',
    '''DROP TRIGGER immutable_assistant_model_input''',
    '''CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF
        id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
        input_json,config_json,policy_json,reserved_usd,created_at,input_format
        ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    '''CREATE TABLE assistant_model_input_citations (
        attempt_id TEXT NOT NULL REFERENCES assistant_model_attempts(id),
        ordinal INTEGER NOT NULL CHECK(ordinal >= 0 AND ordinal < 8),
        saved_citation_id TEXT NOT NULL REFERENCES assistant_library_citations(id),
        PRIMARY KEY(attempt_id, ordinal),
        UNIQUE(attempt_id, saved_citation_id))''',
    '''CREATE TRIGGER immutable_assistant_model_input_citations_update BEFORE UPDATE
        ON assistant_model_input_citations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_assistant_model_input_citations_delete BEFORE DELETE
        ON assistant_model_input_citations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
)


def expected_objects():
    """Exact model-family rows after the context migration, derived deterministically."""
    with sqlite3.connect(':memory:') as db:
        for statement in model_schema.STATEMENTS + STATEMENTS:
            db.execute(statement)
        return db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
            "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',"
            "'assistant_model_input_citations') ORDER BY type,name").fetchall()


def expected_model_objects():
    """The exact rows the legacy model initializer may see after this migration."""
    return [row for row in expected_objects() if row[2] in model_schema.TABLES]


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
            "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',"
            "'assistant_model_input_citations') ORDER BY type,name")]
        from .material_model_schema import expected_context_objects as material_objects
        if found == material_objects():
            return
        if found == expected_objects():
            return
        # The positively identified rounds-v1 and rounds-v2 successors are
        # accepted as-is.
        from .rounds_schema import expected_objects as rounds_objects
        from .rounds_v2_schema import expected_objects as rounds_v2_objects
        from .profile_model_schema import expected_context_objects as profile_model_objects
        if found == rounds_objects() or found == rounds_v2_objects() or found == profile_model_objects():
            return
        # Only the positively identified V1 model family is migrated in place.
        if found != model_schema.expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
        migrated = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name IN "
            "('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs',"
            "'assistant_model_input_citations') ORDER BY type,name")]
        if migrated != expected_objects():
            raise ValueError('DATABASE_SCHEMA_MISMATCH')
