"""Source/run associations and once-only fixed-peer send claims, without bodies."""
import sqlite3
from functools import cache

STATEMENTS = (
    '''CREATE TABLE weixin_personal_runs (
        id TEXT PRIMARY KEY NOT NULL,
        mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id),
        draft_id TEXT NOT NULL REFERENCES task_drafts(id),
        draft_revision INTEGER NOT NULL CHECK(draft_revision>0),
        source_event_id TEXT NOT NULL REFERENCES task_inbox_events(id),
        business_run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id),
        model_request_id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        UNIQUE(draft_id,draft_revision))''',
    '''CREATE TABLE weixin_personal_outbox (
        client_id TEXT PRIMARY KEY NOT NULL,
        mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id),
        source_event_id TEXT NOT NULL REFERENCES task_inbox_events(id),
        result_key TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64),
        status TEXT NOT NULL CHECK(status IN ('unknown','submitted','rejected')),
        created_at TEXT NOT NULL,
        UNIQUE(mapping_id,result_key))''',
    "CREATE TRIGGER weixin_personal_runs_no_update BEFORE UPDATE ON weixin_personal_runs BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER weixin_personal_runs_no_delete BEFORE DELETE ON weixin_personal_runs BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER weixin_personal_outbox_no_delete BEFORE DELETE ON weixin_personal_outbox BEGIN SELECT RAISE(ABORT,'immutable'); END",
    '''CREATE TRIGGER weixin_personal_outbox_update BEFORE UPDATE ON weixin_personal_outbox
        WHEN OLD.status!='unknown' OR NEW.status NOT IN ('submitted','rejected')
        OR NEW.client_id!=OLD.client_id OR NEW.mapping_id!=OLD.mapping_id
        OR NEW.source_event_id!=OLD.source_event_id OR NEW.result_key!=OLD.result_key
        OR NEW.payload_sha256!=OLD.payload_sha256 OR NEW.created_at!=OLD.created_at
        BEGIN SELECT RAISE(ABORT,'immutable'); END''',
)


@cache
def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
