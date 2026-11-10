"""Fixed additive schema; reused by new workspaces and the native upgrader."""
import sqlite3

STATEMENTS = (
    '''CREATE TABLE intake_cases (
        id TEXT PRIMARY KEY NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        current_revision INTEGER NOT NULL, matter_id TEXT REFERENCES matters(id),
        conversion_sha256 TEXT, UNIQUE(owner_id, request_id))''',
    '''CREATE TABLE intake_revisions (
        intake_id TEXT NOT NULL REFERENCES intake_cases(id), revision INTEGER NOT NULL,
        saved_at TEXT NOT NULL, payload TEXT NOT NULL,
        client_reply TEXT NOT NULL, internal_notes TEXT NOT NULL,
        PRIMARY KEY(intake_id, revision))''',
    'CREATE INDEX intake_owner ON intake_cases(owner_id, id)',
    "CREATE TRIGGER immutable_intake_revisions_update BEFORE UPDATE ON intake_revisions BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_intake_revisions_delete BEFORE DELETE ON intake_revisions BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_intake_cases_delete BEFORE DELETE ON intake_cases BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    # sqlite_master normalizes SQL itself; includes implicit unique/PK indexes.
    with sqlite3.connect(':memory:') as db:
        for sql in STATEMENTS:
            db.execute(sql)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='intake_cases'").first()
        if not found:
            for sql in STATEMENTS:
                connection.exec_driver_sql(sql)
