"""Immutable same-target scope grants for explicit synthetic peer refreshes."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE weixin_peer_scope_grants (
        id TEXT PRIMARY KEY NOT NULL,
        mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id),
        request_id TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id),
        revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
        previous_scope_sha256 TEXT NOT NULL, scope_json TEXT NOT NULL,
        scope_sha256 TEXT NOT NULL,
        checkpoint_revision INTEGER NOT NULL CHECK(typeof(checkpoint_revision)='integer' AND checkpoint_revision>=0),
        created_at TEXT NOT NULL, reason TEXT NOT NULL, grant_sha256 TEXT NOT NULL,
        UNIQUE(mapping_id,revision), UNIQUE(mapping_id,request_id))''',
    "CREATE TRIGGER immutable_weixin_peer_scope_grants_update BEFORE UPDATE ON weixin_peer_scope_grants BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_peer_scope_grants_delete BEFORE DELETE ON weixin_peer_scope_grants BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='weixin_peer_scope_grants' "
            "ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
