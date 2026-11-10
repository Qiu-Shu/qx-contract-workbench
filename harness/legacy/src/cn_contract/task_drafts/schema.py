"""Versioned local task intake and immutable execution snapshots."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE task_channel_bindings (
        id TEXT PRIMARY KEY NOT NULL,
        conversation_id TEXT NOT NULL UNIQUE REFERENCES assistant_conversations(id),
        channel TEXT NOT NULL CHECK(channel='synthetic'),
        cursor INTEGER NOT NULL CHECK(cursor>=0), created_at TEXT NOT NULL)''',
    '''CREATE TABLE task_inbox_events (
        id TEXT PRIMARY KEY NOT NULL, binding_id TEXT NOT NULL REFERENCES task_channel_bindings(id),
        event_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(binding_id,event_id))''',
    '''CREATE TABLE task_drafts (
        id TEXT PRIMARY KEY NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        parent_draft_id TEXT REFERENCES task_drafts(id),
        revision INTEGER NOT NULL CHECK(revision>0),
        state TEXT NOT NULL CHECK(state IN ('collecting','paused','cancelled','frozen')),
        instruction TEXT NOT NULL, main_attachment_id TEXT REFERENCES assistant_attachments(id),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE task_draft_events (
        draft_id TEXT NOT NULL REFERENCES task_drafts(id),
        event_id TEXT NOT NULL REFERENCES task_inbox_events(id),
        ordinal INTEGER NOT NULL CHECK(ordinal>0),
        PRIMARY KEY(draft_id,event_id), UNIQUE(draft_id,ordinal))''',
    '''CREATE TABLE task_executions (
        id TEXT PRIMARY KEY NOT NULL, draft_id TEXT NOT NULL UNIQUE REFERENCES task_drafts(id),
        revision INTEGER NOT NULL CHECK(revision>0),
        manifest_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('prepared','creating_matter','awaiting_facts',
            'queued','running','completed','failed','blocked')),
        matter_id TEXT REFERENCES matters(id), job_id TEXT, review_run_id TEXT,
        document_versions_json TEXT NOT NULL DEFAULT '{}',
        source_versions_json TEXT NOT NULL DEFAULT '{}',
        prepare_request_id TEXT, review_request_id TEXT, review_input_sha256 TEXT,
        error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
    '''CREATE TABLE task_media_resolutions (
        id TEXT PRIMARY KEY NOT NULL, draft_id TEXT NOT NULL REFERENCES task_drafts(id),
        event_id TEXT NOT NULL REFERENCES task_inbox_events(id),
        revision INTEGER NOT NULL CHECK(revision>0), media_id TEXT NOT NULL,
        action TEXT NOT NULL CHECK(action IN ('resolve','exclude')),
        reason TEXT, replacement_json TEXT, created_at TEXT NOT NULL,
        UNIQUE(draft_id,event_id,media_id,revision))''',
    'CREATE INDEX task_draft_conversation ON task_drafts(conversation_id,state)',
    'CREATE INDEX task_draft_event_source ON task_draft_events(event_id)',
    "CREATE TRIGGER immutable_task_binding_delete BEFORE DELETE ON task_channel_bindings BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_task_binding_identity BEFORE UPDATE OF id,conversation_id,channel,created_at
        ON task_channel_bindings BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER monotonic_task_binding_cursor BEFORE UPDATE OF cursor ON task_channel_bindings
        WHEN NEW.cursor<OLD.cursor BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_task_inbox_update BEFORE UPDATE ON task_inbox_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_task_inbox_delete BEFORE DELETE ON task_inbox_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_task_draft_delete BEFORE DELETE ON task_drafts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_task_draft_identity BEFORE UPDATE OF id,conversation_id,parent_draft_id,created_at
        ON task_drafts BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    '''CREATE TRIGGER immutable_frozen_task_draft BEFORE UPDATE ON task_drafts
        WHEN OLD.state='frozen' BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_task_draft_event_update BEFORE UPDATE ON task_draft_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_task_draft_event_delete BEFORE DELETE ON task_draft_events BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_frozen_task_draft_events BEFORE INSERT ON task_draft_events
        WHEN (SELECT state FROM task_drafts WHERE id=NEW.draft_id)='frozen'
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_task_execution_delete BEFORE DELETE ON task_executions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_task_execution_snapshot BEFORE UPDATE OF id,draft_id,revision,
        manifest_sha256,manifest_json,created_at ON task_executions
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
    "CREATE TRIGGER immutable_task_resolution_update BEFORE UPDATE ON task_media_resolutions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_task_resolution_delete BEFORE DELETE ON task_media_resolutions BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_frozen_task_resolution BEFORE INSERT ON task_media_resolutions
        WHEN (SELECT state FROM task_drafts WHERE id=NEW.draft_id)='frozen'
        BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END''',
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
            "('task_channel_bindings','task_inbox_events','task_drafts','task_draft_events',"
            "'task_executions','task_media_resolutions') ORDER BY type,name")]
        if found:
            if found != expected_objects():
                raise ValueError('DATABASE_SCHEMA_MISMATCH')
            return
        for statement in STATEMENTS:
            connection.exec_driver_sql(statement)
