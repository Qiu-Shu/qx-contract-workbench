"""Immutable target generations anchored to the original synthetic peer mapping."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE weixin_peer_generations (
        id TEXT PRIMARY KEY NOT NULL,
        root_mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id),
        generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
        request_id TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id),
        task_binding_id TEXT NOT NULL UNIQUE REFERENCES task_channel_bindings(id),
        scope_json TEXT NOT NULL, scope_sha256 TEXT NOT NULL,
        previous_generation_sha256 TEXT,
        previous_scope_sha256 TEXT NOT NULL,
        checkpoint_revision INTEGER NOT NULL CHECK(typeof(checkpoint_revision)='integer' AND checkpoint_revision>=0),
        created_at TEXT NOT NULL, reason TEXT NOT NULL, generation_sha256 TEXT NOT NULL,
        CHECK((generation=1 AND previous_generation_sha256 IS NULL) OR
              (generation>1 AND previous_generation_sha256 IS NOT NULL)),
        UNIQUE(root_mapping_id,generation), UNIQUE(root_mapping_id,request_id))''',
    "CREATE TRIGGER immutable_weixin_peer_generations_update BEFORE UPDATE ON weixin_peer_generations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_peer_generations_delete BEFORE DELETE ON weixin_peer_generations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='weixin_peer_generations' "
            "ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
