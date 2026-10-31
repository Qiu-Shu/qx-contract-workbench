"""Additive service intake records in the existing workspace database."""
import sqlite3
from functools import cache

STATEMENTS = (
    '''CREATE TABLE weixin_service_connections (
        id TEXT PRIMARY KEY NOT NULL, account_id TEXT NOT NULL UNIQUE REFERENCES weixin_accounts(id),
        workspace_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id), peer_id TEXT NOT NULL,
        initial_cursor TEXT NOT NULL, cursor TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0), created_at TEXT NOT NULL)''',
    '''CREATE TABLE weixin_service_polls (
        id TEXT PRIMARY KEY NOT NULL, connection_id TEXT NOT NULL REFERENCES weixin_service_connections(id),
        revision INTEGER NOT NULL CHECK(revision>0), expected_cursor TEXT NOT NULL, next_cursor TEXT NOT NULL,
        event_ids_json TEXT NOT NULL, response_sha256 TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(connection_id,revision))''',
    '''CREATE TABLE weixin_service_events (
        id TEXT PRIMARY KEY NOT NULL, connection_id TEXT NOT NULL REFERENCES weixin_service_connections(id),
        event_id TEXT NOT NULL, source_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(connection_id,event_id))''',
    '''CREATE TABLE weixin_service_media (
        event_id TEXT NOT NULL REFERENCES weixin_service_events(id), media_id TEXT NOT NULL,
        data BLOB NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(event_id,media_id))''',
    '''CREATE TABLE weixin_service_batches (
        id TEXT PRIMARY KEY NOT NULL, connection_id TEXT NOT NULL REFERENCES weixin_service_connections(id),
        revision INTEGER NOT NULL CHECK(revision>0), state TEXT NOT NULL CHECK(state IN
        ('collecting','held','clarify','waiting','routed','executing','completed')),
        deadline TEXT NOT NULL, conversation_id TEXT REFERENCES assistant_conversations(id),
        draft_id TEXT REFERENCES task_drafts(id), workflow TEXT, decision_json TEXT,
        created_at TEXT NOT NULL)''',
    '''CREATE TABLE weixin_service_batch_events (
        batch_id TEXT NOT NULL REFERENCES weixin_service_batches(id),
        event_id TEXT NOT NULL UNIQUE REFERENCES weixin_service_events(id), PRIMARY KEY(batch_id,event_id))''',
    '''CREATE TABLE weixin_service_runs (
        id TEXT PRIMARY KEY NOT NULL, batch_id TEXT NOT NULL UNIQUE REFERENCES weixin_service_batches(id),
        connection_id TEXT NOT NULL REFERENCES weixin_service_connections(id),
        draft_id TEXT NOT NULL REFERENCES task_drafts(id), draft_revision INTEGER NOT NULL,
        source_event_id TEXT NOT NULL REFERENCES weixin_service_events(id),
        business_run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id), model_request_id TEXT NOT NULL UNIQUE,
        scope_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE weixin_service_outbox (
        client_id TEXT PRIMARY KEY NOT NULL, connection_id TEXT NOT NULL REFERENCES weixin_service_connections(id),
        source_event_id TEXT NOT NULL REFERENCES weixin_service_events(id), result_key TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('unknown','submitted','rejected')),
        created_at TEXT NOT NULL, UNIQUE(connection_id,result_key))''',
    '''CREATE TABLE assistant_shared_judgments (
        id TEXT PRIMARY KEY NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL REFERENCES sessions(id), conversation_id TEXT REFERENCES assistant_conversations(id),
        batch_id TEXT REFERENCES weixin_service_batches(id),
        request_json TEXT NOT NULL, config_json TEXT NOT NULL, input_hash TEXT NOT NULL,
        result_json TEXT, state TEXT NOT NULL CHECK(state IN ('unknown','received','discarded')),
        created_at TEXT NOT NULL, CHECK((conversation_id IS NULL)!=(batch_id IS NULL)))''',
)
for table in ('weixin_service_polls','weixin_service_events','weixin_service_media','weixin_service_batch_events','weixin_service_runs'):
    for operation in ('UPDATE','DELETE'):
        STATEMENTS += (f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable'); END",)
for table in ('weixin_service_connections','weixin_service_batches','weixin_service_outbox','assistant_shared_judgments'):
    STATEMENTS += (f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'immutable'); END",)
STATEMENTS += (
    '''CREATE TRIGGER weixin_service_batch_update BEFORE UPDATE ON weixin_service_batches
        WHEN NEW.id!=OLD.id OR NEW.connection_id!=OLD.connection_id OR NEW.created_at!=OLD.created_at
        OR NEW.revision NOT IN (OLD.revision,OLD.revision+1)
        OR (OLD.conversation_id IS NOT NULL AND NEW.conversation_id IS NOT OLD.conversation_id)
        OR (OLD.draft_id IS NOT NULL AND NEW.draft_id IS NOT OLD.draft_id)
        OR OLD.state='completed'
        OR (OLD.state='executing' AND (NEW.state!='completed' OR NEW.revision!=OLD.revision
            OR NEW.workflow IS NOT OLD.workflow OR NEW.decision_json IS NOT OLD.decision_json))
        BEGIN SELECT RAISE(ABORT,'immutable'); END''',
    '''CREATE TRIGGER weixin_service_batch_event_insert BEFORE INSERT ON weixin_service_batch_events
        WHEN (SELECT state FROM weixin_service_batches WHERE id=NEW.batch_id) NOT IN ('collecting','held','waiting','clarify')
        OR (SELECT connection_id FROM weixin_service_batches WHERE id=NEW.batch_id)
            !=(SELECT connection_id FROM weixin_service_events WHERE id=NEW.event_id)
        BEGIN SELECT RAISE(ABORT,'immutable'); END''',
    '''CREATE TRIGGER weixin_service_connection_update BEFORE UPDATE ON weixin_service_connections
        WHEN NEW.id!=OLD.id OR NEW.account_id!=OLD.account_id OR NEW.workspace_id!=OLD.workspace_id
        OR NEW.initial_cursor!=OLD.initial_cursor
        OR NEW.owner_id!=OLD.owner_id OR NEW.peer_id!=OLD.peer_id OR NEW.created_at!=OLD.created_at
        OR NEW.revision!=OLD.revision+1 BEGIN SELECT RAISE(ABORT,'immutable'); END''',
    '''CREATE TRIGGER weixin_service_outbox_update BEFORE UPDATE ON weixin_service_outbox
        WHEN OLD.status!='unknown' OR NEW.status NOT IN ('submitted','rejected')
        OR NEW.client_id!=OLD.client_id OR NEW.connection_id!=OLD.connection_id
        OR NEW.source_event_id!=OLD.source_event_id OR NEW.result_key!=OLD.result_key
        OR NEW.payload_sha256!=OLD.payload_sha256 OR NEW.created_at!=OLD.created_at
        BEGIN SELECT RAISE(ABORT,'immutable'); END''',
    '''CREATE TRIGGER assistant_shared_judgments_update BEFORE UPDATE ON assistant_shared_judgments
        WHEN OLD.state!='unknown' OR NEW.state NOT IN ('received','discarded') OR NEW.id!=OLD.id
        OR NEW.actor_id!=OLD.actor_id OR NEW.session_id!=OLD.session_id OR NEW.conversation_id IS NOT OLD.conversation_id
        OR NEW.batch_id IS NOT OLD.batch_id
        OR NEW.request_json!=OLD.request_json OR NEW.config_json!=OLD.config_json OR NEW.input_hash!=OLD.input_hash
        OR NEW.created_at!=OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable'); END''',
)


@cache
def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
