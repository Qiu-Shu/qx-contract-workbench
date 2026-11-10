"""Frozen assistant-v1 sqlite_master rows from 00b106c; do not regenerate.

Historical recognition must not depend on future schema initializer changes.
"""

ASSISTANT_V1_ROWS = (('index',
  'assistant_active_run',
  'assistant_runs',
  'CREATE UNIQUE INDEX assistant_active_run ON assistant_runs(conversation_id)\n'
  "        WHERE state IN ('queued','preparing','routing','retrieving','generating','persisting')"),
 ('index',
  'assistant_owner',
  'assistant_conversations',
  'CREATE INDEX assistant_owner ON assistant_conversations(owner_id, id)'),
 ('index',
  'assistant_user_input',
  'assistant_messages',
  'CREATE UNIQUE INDEX assistant_user_input ON assistant_messages(conversation_id, '
  'source_revision)\n'
  "        WHERE role='user' "),
 ('index', 'sqlite_autoindex_assistant_conversations_1', 'assistant_conversations', None),
 ('index', 'sqlite_autoindex_assistant_conversations_2', 'assistant_conversations', None),
 ('index', 'sqlite_autoindex_assistant_messages_1', 'assistant_messages', None),
 ('index', 'sqlite_autoindex_assistant_run_events_1', 'assistant_run_events', None),
 ('index', 'sqlite_autoindex_assistant_runs_1', 'assistant_runs', None),
 ('index', 'sqlite_autoindex_assistant_runs_2', 'assistant_runs', None),
 ('index', 'sqlite_autoindex_assistant_runs_3', 'assistant_runs', None),
 ('table',
  'assistant_conversations',
  'assistant_conversations',
  'CREATE TABLE assistant_conversations (\n'
  '        id TEXT PRIMARY KEY NOT NULL, workspace_id TEXT NOT NULL,\n'
  '        owner_id TEXT NOT NULL REFERENCES users(id),\n'
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,\n'
  "        scope_kind TEXT NOT NULL CHECK(scope_kind IN ('conversation','intake','matter')),\n"
  '        scope_ref TEXT,\n'
  '        binding_revision INTEGER NOT NULL CHECK(binding_revision > 0),\n'
  '        input_revision INTEGER NOT NULL CHECK(input_revision >= 0),\n'
  '        materials_revision INTEGER NOT NULL CHECK(materials_revision >= 0),\n'
  '        composer_revision INTEGER NOT NULL CHECK(composer_revision >= 0),\n'
  '        projection_intake_id TEXT REFERENCES intake_cases(id),\n'
  '        display_title TEXT NOT NULL, draft_input TEXT NOT NULL,\n'
  '        created_at TEXT NOT NULL, archived_at TEXT,\n'
  "        CHECK((scope_kind='conversation' AND scope_ref IS NULL) OR\n"
  "              (scope_kind!='conversation' AND scope_ref IS NOT NULL)),\n"
  '        UNIQUE(owner_id, request_id))'),
 ('table',
  'assistant_messages',
  'assistant_messages',
  'CREATE TABLE assistant_messages (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  "        role TEXT NOT NULL CHECK(role IN ('user','assistant')),\n"
  '        content TEXT NOT NULL, created_at TEXT NOT NULL,\n'
  '        source_revision INTEGER NOT NULL CHECK(source_revision > 0))'),
 ('table',
  'assistant_run_events',
  'assistant_run_events',
  'CREATE TABLE assistant_run_events (\n'
  '        run_id TEXT NOT NULL REFERENCES assistant_runs(id),\n'
  '        seq INTEGER NOT NULL CHECK(seq > 0), event_type TEXT NOT NULL,\n'
  "        audience TEXT NOT NULL CHECK(audience IN ('internal','client')),\n"
  '        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,\n'
  '        PRIMARY KEY(run_id, seq))'),
 ('table',
  'assistant_runs',
  'assistant_runs',
  'CREATE TABLE assistant_runs (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        message_id TEXT NOT NULL UNIQUE REFERENCES assistant_messages(id),\n'
  '        actor_id TEXT NOT NULL REFERENCES users(id),\n'
  '        session_id TEXT NOT NULL REFERENCES sessions(id),\n'
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,\n'
  '        scope_snapshot TEXT NOT NULL,\n'
  "        state TEXT NOT NULL CHECK(state IN ('queued','preparing','routing','retrieving',\n"
  '            '
  "'generating','persisting','completed','cancelled','failed','interrupted','awaiting_input','blocked')),\n"
  "        requested_skill TEXT CHECK(requested_skill IN ('client_reply','material_organize',\n"
  "            'contract_review','content_draft','legal_research')),\n"
  '        selected_provider TEXT, selected_model TEXT, budget_json TEXT,\n'
  '        cancel_requested INTEGER NOT NULL CHECK(cancel_requested IN (0,1)),\n'
  '        created_at TEXT NOT NULL,\n'
  '        UNIQUE(conversation_id, request_id))'),
 ('trigger',
  'immutable_assistant_conversations_delete',
  'assistant_conversations',
  'CREATE TRIGGER immutable_assistant_conversations_delete BEFORE DELETE ON '
  "assistant_conversations BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_messages_delete',
  'assistant_messages',
  'CREATE TRIGGER immutable_assistant_messages_delete BEFORE DELETE ON assistant_messages BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_messages_update',
  'assistant_messages',
  'CREATE TRIGGER immutable_assistant_messages_update BEFORE UPDATE ON assistant_messages BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_run_events_delete',
  'assistant_run_events',
  'CREATE TRIGGER immutable_assistant_run_events_delete BEFORE DELETE ON assistant_run_events '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_run_events_update',
  'assistant_run_events',
  'CREATE TRIGGER immutable_assistant_run_events_update BEFORE UPDATE ON assistant_run_events '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_run_input',
  'assistant_runs',
  'CREATE TRIGGER immutable_assistant_run_input BEFORE UPDATE OF conversation_id,message_id,\n'
  '        '
  'actor_id,session_id,request_id,request_sha256,scope_snapshot,requested_skill,created_at\n'
  "        ON assistant_runs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_runs_delete',
  'assistant_runs',
  'CREATE TRIGGER immutable_assistant_runs_delete BEFORE DELETE ON assistant_runs BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"))
