"""Immutable provenance for synthetic inbox delivery into the shared TaskInbox."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE weixin_dispatch_receipts (
        id TEXT PRIMARY KEY NOT NULL,
        descriptor_id TEXT NOT NULL UNIQUE REFERENCES weixin_inbox_descriptors(id),
        account_id TEXT NOT NULL REFERENCES weixin_accounts(id),
        mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id),
        actor_id TEXT NOT NULL REFERENCES users(id),
        task_binding_id TEXT NOT NULL REFERENCES task_channel_bindings(id),
        task_event_id TEXT NOT NULL UNIQUE REFERENCES task_inbox_events(id),
        source_event_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
        expected_task_cursor INTEGER NOT NULL CHECK(typeof(expected_task_cursor)='integer' AND expected_task_cursor>=0),
        next_task_cursor INTEGER NOT NULL CHECK(typeof(next_task_cursor)='integer' AND next_task_cursor=expected_task_cursor+1),
        created_at TEXT NOT NULL, receipt_sha256 TEXT NOT NULL)''',
    "CREATE TRIGGER immutable_weixin_dispatch_receipts_update BEFORE UPDATE ON weixin_dispatch_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_dispatch_receipts_delete BEFORE DELETE ON weixin_dispatch_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = [tuple(row) for row in connection.exec_driver_sql(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name='weixin_dispatch_receipts' "
            "ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
