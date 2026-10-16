"""Fixed assistant-v1 schema shared by initialization and explicit upgrades."""
import sqlite3


STATEMENTS = (
    '''CREATE TABLE assistant_conversations (
        id TEXT PRIMARY KEY NOT NULL, workspace_id TEXT NOT NULL,
        owner_id TEXT NOT NULL REFERENCES users(id),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        scope_kind TEXT NOT NULL CHECK(scope_kind IN ('conversation','intake','matter')),
        scope_ref TEXT,
        binding_revision INTEGER NOT NULL CHECK(binding_revision > 0),
        input_revision INTEGER NOT NULL CHECK(input_revision >= 0),
        materials_revision INTEGER NOT NULL CHECK(materials_revision >= 0),
        composer_revision INTEGER NOT NULL CHECK(composer_revision >= 0),
        projection_intake_id TEXT REFERENCES intake_cases(id),
        display_title TEXT NOT NULL, draft_input TEXT NOT NULL,
        created_at TEXT NOT NULL, archived_at TEXT,
        CHECK((scope_kind='conversation' AND scope_ref IS NULL) OR
              (scope_kind!='conversation' AND scope_ref IS NOT NULL)),
        UNIQUE(owner_id, request_id))''',
    '''CREATE TABLE assistant_messages (
        id TEXT PRIMARY KEY NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        role TEXT NOT NULL CHECK(role IN ('user','assistant')),
        content TEXT NOT NULL, created_at TEXT NOT NULL,
        source_revision INTEGER NOT NULL CHECK(source_revision > 0))''',
    '''CREATE TABLE assistant_runs (
        id TEXT PRIMARY KEY NOT NULL,
        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),
        message_id TEXT NOT NULL UNIQUE REFERENCES assistant_messages(id),
        actor_id TEXT NOT NULL REFERENCES users(id),
        session_id TEXT NOT NULL REFERENCES sessions(id),
        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        scope_snapshot TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('queued','preparing','routing','retrieving',
            'generating','persisting','completed','cancelled','failed','interrupted','awaiting_input','blocked')),
        requested_skill TEXT CHECK(requested_skill IN ('client_reply','material_organize',
            'contract_review','content_draft','legal_research')),
        selected_provider TEXT, selected_model TEXT, budget_json TEXT,
        cancel_requested INTEGER NOT NULL CHECK(cancel_requested IN (0,1)),
        created_at TEXT NOT NULL,
        UNIQUE(conversation_id, request_id))''',
    '''CREATE TABLE assistant_run_events (
        run_id TEXT NOT NULL REFERENCES assistant_runs(id),
        seq INTEGER NOT NULL CHECK(seq > 0), event_type TEXT NOT NULL,
        audience TEXT NOT NULL CHECK(audience IN ('internal','client')),
        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(run_id, seq))''',
    'CREATE INDEX assistant_owner ON assistant_conversations(owner_id, id)',
    '''CREATE UNIQUE INDEX assistant_user_input ON assistant_messages(conversation_id, source_revision)
        WHERE role='user' ''',
    '''CREATE UNIQUE INDEX assistant_active_run ON assistant_runs(conversation_id)
        WHERE state IN ('queued','preparing','routing','retrieving','generating','persisting')''',
    "CREATE TRIGGER immutable_assistant_conversations_delete BEFORE DELETE ON assistant_conversations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_messages_update BEFORE UPDATE ON assistant_messages BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_messages_delete BEFORE DELETE ON assistant_messages BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_run_events_update BEFORE UPDATE ON assistant_run_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_run_events_delete BEFORE DELETE ON assistant_run_events BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    "CREATE TRIGGER immutable_assistant_runs_delete BEFORE DELETE ON assistant_runs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END",
    '''CREATE TRIGGER immutable_assistant_run_input BEFORE UPDATE OF conversation_id,message_id,
        actor_id,session_id,request_id,request_sha256,scope_snapshot,requested_skill,created_at
        ON assistant_runs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''',
)


def expected_objects():
    with sqlite3.connect(':memory:') as db:
        for statement in STATEMENTS:
            db.execute(statement)
        return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def initialize_storage(database):
    with database.engine.begin() as connection:
        found = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE name='assistant_conversations'").first()
        if not found:
            for statement in STATEMENTS:
                connection.exec_driver_sql(statement)
