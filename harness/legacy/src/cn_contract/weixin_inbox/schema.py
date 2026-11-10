"""Additive synthetic account checkpoints and immutable complete poll journals."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE weixin_accounts (
        id TEXT PRIMARY KEY NOT NULL, workspace_id TEXT NOT NULL,
        owner_id TEXT NOT NULL REFERENCES users(id), bot_account_id TEXT NOT NULL,
        mode TEXT NOT NULL CHECK(mode='synthetic'), initial_cursor TEXT NOT NULL,
        checkpoint_revision INTEGER NOT NULL CHECK(typeof(checkpoint_revision)='integer' AND checkpoint_revision>=0),
        upstream_cursor TEXT NOT NULL, created_at TEXT NOT NULL,
        revoked_at TEXT, revoked_by TEXT REFERENCES users(id), revoke_reason TEXT,
        CHECK((revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
            OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND revoke_reason IS NOT NULL)),
        UNIQUE(workspace_id,bot_account_id))''',
    '''CREATE TABLE weixin_peer_bindings (
        id TEXT PRIMARY KEY NOT NULL, account_id TEXT NOT NULL REFERENCES weixin_accounts(id),
        sender_peer_id TEXT NOT NULL, task_binding_id TEXT NOT NULL UNIQUE REFERENCES task_channel_bindings(id),
        scope_json TEXT NOT NULL, scope_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
        revoked_at TEXT, revoked_by TEXT REFERENCES users(id), revoke_reason TEXT,
        CHECK((revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
            OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND revoke_reason IS NOT NULL)),
        UNIQUE(account_id,sender_peer_id))''',
    '''CREATE TABLE weixin_poll_receipts (
        id TEXT PRIMARY KEY NOT NULL, account_id TEXT NOT NULL REFERENCES weixin_accounts(id),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, response_sha256 TEXT NOT NULL,
        expected_revision INTEGER NOT NULL CHECK(typeof(expected_revision)='integer' AND expected_revision>=0),
        next_revision INTEGER NOT NULL CHECK(typeof(next_revision)='integer' AND next_revision=expected_revision+1),
        expected_cursor TEXT NOT NULL, next_cursor TEXT NOT NULL,
        descriptor_count INTEGER NOT NULL CHECK(typeof(descriptor_count)='integer' AND descriptor_count BETWEEN 0 AND 100),
        receipt_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(account_id,request_id), UNIQUE(account_id,next_revision))''',
    '''CREATE TABLE weixin_inbox_descriptors (
        id TEXT PRIMARY KEY NOT NULL, poll_id TEXT NOT NULL REFERENCES weixin_poll_receipts(id),
        ordinal INTEGER NOT NULL CHECK(typeof(ordinal)='integer' AND ordinal BETWEEN 1 AND 100),
        sender_peer_id TEXT, upstream_message_id TEXT, source_event_id TEXT,
        source_sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('accepted_pending_dispatch','blocked','duplicate')),
        reason TEXT CHECK(reason IS NULL OR reason IN ('sender_unbound','binding_revoked','scope_stale',
            'scope_denied','recipient_mismatch','message_unsupported','message_invalid','event_conflict',
            'previously_blocked','replayed')),
        mapping_id TEXT REFERENCES weixin_peer_bindings(id),
        prior_descriptor_id TEXT REFERENCES weixin_inbox_descriptors(id), payload_json TEXT,
        CHECK((sender_peer_id IS NULL AND upstream_message_id IS NULL AND source_event_id IS NULL)
            OR (sender_peer_id IS NOT NULL AND upstream_message_id IS NOT NULL AND source_event_id IS NOT NULL)),
        CHECK(upstream_message_id IS NULL OR (length(upstream_message_id) BETWEEN 1 AND 20
            AND upstream_message_id NOT GLOB '*[^0-9]*'
            AND (upstream_message_id='0' OR substr(upstream_message_id,1,1)!='0')
            AND (length(upstream_message_id)<20 OR upstream_message_id<='18446744073709551615'))),
        CHECK((status='accepted_pending_dispatch' AND mapping_id IS NOT NULL AND source_event_id IS NOT NULL
                AND payload_json IS NOT NULL AND reason IS NULL AND prior_descriptor_id IS NULL)
            OR (status='blocked' AND reason IS NOT NULL AND payload_json IS NULL)
            OR (status='duplicate' AND source_event_id IS NOT NULL AND prior_descriptor_id IS NOT NULL
                AND payload_json IS NULL AND reason IS NOT NULL AND reason='replayed')),
        UNIQUE(poll_id,ordinal))''',
    "CREATE TRIGGER immutable_weixin_account_delete BEFORE DELETE ON weixin_accounts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_weixin_account_identity BEFORE UPDATE OF id,workspace_id,owner_id,
        bot_account_id,mode,initial_cursor,created_at ON weixin_accounts
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER monotonic_weixin_account_checkpoint BEFORE UPDATE OF checkpoint_revision,upstream_cursor
        ON weixin_accounts WHEN NEW.checkpoint_revision!=OLD.checkpoint_revision+1
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_weixin_account_revocation BEFORE UPDATE OF revoked_at,revoked_by,revoke_reason
        ON weixin_accounts WHEN OLD.revoked_at IS NOT NULL
            OR NEW.revoked_at IS NULL OR NEW.revoked_by IS NULL OR NEW.revoke_reason IS NULL
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_weixin_peer_binding_delete BEFORE DELETE ON weixin_peer_bindings BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_weixin_peer_binding_identity BEFORE UPDATE OF id,account_id,sender_peer_id,
        task_binding_id,scope_json,scope_sha256,created_at ON weixin_peer_bindings
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_weixin_peer_binding_revocation BEFORE UPDATE OF revoked_at,revoked_by,revoke_reason
        ON weixin_peer_bindings WHEN OLD.revoked_at IS NOT NULL
            OR NEW.revoked_at IS NULL OR NEW.revoked_by IS NULL OR NEW.revoke_reason IS NULL
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_weixin_poll_receipts_update BEFORE UPDATE ON weixin_poll_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_poll_receipts_delete BEFORE DELETE ON weixin_poll_receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_inbox_descriptors_update BEFORE UPDATE ON weixin_inbox_descriptors BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_weixin_inbox_descriptors_delete BEFORE DELETE ON weixin_inbox_descriptors BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
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
            "('weixin_accounts','weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors') "
            "ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
