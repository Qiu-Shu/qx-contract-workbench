"""Append-only historical targets; this schema does not enable runtime delivery."""
import sqlite3


STATEMENTS=(
    '''CREATE TABLE weixin_descriptor_generations (
        descriptor_id TEXT PRIMARY KEY NOT NULL REFERENCES weixin_inbox_descriptors(id),
        generation_id TEXT NOT NULL REFERENCES weixin_peer_generations(id),
        generation_sha256 TEXT NOT NULL,
        task_binding_id TEXT NOT NULL REFERENCES task_channel_bindings(id),
        scope_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, provenance_sha256 TEXT NOT NULL)''',
    "CREATE TRIGGER immutable_weixin_descriptor_generations_update BEFORE UPDATE ON weixin_descriptor_generations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_descriptor_generations_delete BEFORE DELETE ON weixin_descriptor_generations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found=[tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='weixin_descriptor_generations' ORDER BY type,name")]
        if found:
            if found!=expected_objects():raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:connection.exec_driver_sql(statement)
