"""Frozen assistant-attachments-v1 sqlite_master rows from 114a1ab; do not regenerate.

Historical recognition is independent of later attachment initializers.
"""

ASSISTANT_ATTACHMENTS_V1_ROWS = (('index', 'sqlite_autoindex_assistant_attachment_parses_1', 'assistant_attachment_parses', None),
 ('index', 'sqlite_autoindex_assistant_attachment_parses_2', 'assistant_attachment_parses', None),
 ('index', 'sqlite_autoindex_assistant_attachments_1', 'assistant_attachments', None),
 ('index', 'sqlite_autoindex_assistant_attachments_2', 'assistant_attachments', None),
 ('index', 'sqlite_autoindex_assistant_attachments_3', 'assistant_attachments', None),
 ('index', 'sqlite_autoindex_assistant_material_snapshots_1', 'assistant_material_snapshots', None),
 ('index', 'sqlite_autoindex_assistant_material_snapshots_2', 'assistant_material_snapshots', None),
 ('table',
  'assistant_attachment_parses',
  'assistant_attachment_parses',
  'CREATE TABLE assistant_attachment_parses (\n'
  '        conversation_id TEXT NOT NULL, attachment_id TEXT NOT NULL,\n'
  '        revision INTEGER NOT NULL CHECK(revision > 0),\n'
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,\n'
  '        parser_version TEXT NOT NULL, baseline_view TEXT,\n'
  '        reading_status TEXT NOT NULL CHECK(reading_status IN '
  "('readable','partial','needs_baseline','failed')),\n"
  '        result_json TEXT, result_sha256 TEXT, failure_code TEXT,\n'
  '        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,\n'
  '        PRIMARY KEY(attachment_id, revision),\n'
  '        FOREIGN KEY(conversation_id, attachment_id) REFERENCES '
  'assistant_attachments(conversation_id, id),\n'
  '        UNIQUE(conversation_id, request_id))'),
 ('table',
  'assistant_attachments',
  'assistant_attachments',
  'CREATE TABLE assistant_attachments (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        workspace_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),\n'
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,\n'
  '        original_name TEXT NOT NULL, mime TEXT NOT NULL,\n'
  '        byte_size INTEGER NOT NULL CHECK(byte_size > 0),\n'
  '        sha256 TEXT NOT NULL, storage_ref TEXT NOT NULL, policy_json TEXT NOT NULL,\n'
  '        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,\n'
  '        UNIQUE(conversation_id, request_id), UNIQUE(conversation_id, id))'),
 ('table',
  'assistant_material_snapshots',
  'assistant_material_snapshots',
  'CREATE TABLE assistant_material_snapshots (\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        revision INTEGER NOT NULL CHECK(revision > 0),\n'
  "        kind TEXT NOT NULL CHECK(kind IN ('upload','parse','selection')),\n"
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, items_json TEXT NOT NULL,\n'
  '        actor_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,\n'
  '        PRIMARY KEY(conversation_id, revision), UNIQUE(conversation_id, request_id))'),
 ('trigger',
  'immutable_assistant_attachment_parses_delete',
  'assistant_attachment_parses',
  'CREATE TRIGGER immutable_assistant_attachment_parses_delete BEFORE DELETE ON '
  "assistant_attachment_parses BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_attachment_parses_update',
  'assistant_attachment_parses',
  'CREATE TRIGGER immutable_assistant_attachment_parses_update BEFORE UPDATE ON '
  "assistant_attachment_parses BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_attachments_delete',
  'assistant_attachments',
  'CREATE TRIGGER immutable_assistant_attachments_delete BEFORE DELETE ON assistant_attachments '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_attachments_update',
  'assistant_attachments',
  'CREATE TRIGGER immutable_assistant_attachments_update BEFORE UPDATE ON assistant_attachments '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_material_snapshots_delete',
  'assistant_material_snapshots',
  'CREATE TRIGGER immutable_assistant_material_snapshots_delete BEFORE DELETE ON '
  "assistant_material_snapshots BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_material_snapshots_update',
  'assistant_material_snapshots',
  'CREATE TRIGGER immutable_assistant_material_snapshots_update BEFORE UPDATE ON '
  "assistant_material_snapshots BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"))
