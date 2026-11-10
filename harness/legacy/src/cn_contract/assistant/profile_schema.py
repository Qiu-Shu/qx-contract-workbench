"""Append-only profile revisions and atomic intake-projection receipts."""
import sqlite3


TABLES = ('assistant_profile_revisions', 'assistant_profile_receipts')
STATEMENTS = (
    '''CREATE TABLE assistant_profile_revisions (
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        revision INTEGER NOT NULL CHECK(typeof(revision) = 'integer' AND revision > 0),
        profile_json TEXT NOT NULL CHECK(length(profile_json) <= 2097152),
        profile_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(conversation_id,revision))''',
    '''CREATE TABLE assistant_profile_receipts (
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        sequence INTEGER NOT NULL CHECK(typeof(sequence) = 'integer' AND sequence > 0),
        request_id TEXT NOT NULL,
        request_json TEXT NOT NULL CHECK(length(request_json) <= 2097152),
        request_sha256 TEXT NOT NULL,
        profile_revision INTEGER CHECK(profile_revision IS NULL OR
            (typeof(profile_revision) = 'integer' AND profile_revision > 0)),
        profile_changed INTEGER NOT NULL CHECK(profile_changed IN (0,1)),
        intake_id TEXT REFERENCES intake_cases(id),
        intake_revision INTEGER,
        intake_sha256 TEXT,
        projection_changed INTEGER NOT NULL CHECK(projection_changed IN (0,1)),
        consultation_origin TEXT NOT NULL CHECK(consultation_origin IN ('user','profile_summary')),
        event_type TEXT NOT NULL CHECK(event_type IN ('profile.saved','profile.unchanged')),
        audience TEXT NOT NULL CHECK(audience = 'internal'),
        actor_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL REFERENCES sessions(id),
        created_at TEXT NOT NULL,
        PRIMARY KEY(conversation_id,sequence),
        UNIQUE(conversation_id,request_id),
        FOREIGN KEY(conversation_id,profile_revision)
            REFERENCES assistant_profile_revisions(conversation_id,revision),
        FOREIGN KEY(intake_id,intake_revision) REFERENCES intake_revisions(intake_id,revision),
        CHECK((intake_id IS NULL AND intake_revision IS NULL AND intake_sha256 IS NULL) OR
            (intake_id IS NOT NULL AND intake_revision IS NOT NULL AND intake_sha256 IS NOT NULL
             AND typeof(intake_revision) = 'integer' AND intake_revision > 0)),
        CHECK(profile_changed = 0 OR profile_revision IS NOT NULL),
        CHECK(projection_changed = 0 OR intake_id IS NOT NULL),
        CHECK((profile_changed = 0 AND projection_changed = 0 AND event_type = 'profile.unchanged') OR
            ((profile_changed = 1 OR projection_changed = 1) AND event_type = 'profile.saved')))''',
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
            "('assistant_profile_revisions','assistant_profile_receipts') ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
