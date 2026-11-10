"""Frozen assistant-model-v1 DDL captured from a4c3c67 before Jev extension."""

ASSISTANT_MODEL_V1_ROWS = (('index', 'sqlite_autoindex_assistant_model_attempts_1', 'assistant_model_attempts', None),
 ('index', 'sqlite_autoindex_assistant_model_attempts_2', 'assistant_model_attempts', None),
 ('index', 'sqlite_autoindex_assistant_model_outputs_1', 'assistant_model_outputs', None),
 ('index', 'sqlite_autoindex_assistant_model_outputs_2', 'assistant_model_outputs', None),
 ('index', 'sqlite_autoindex_assistant_model_outputs_3', 'assistant_model_outputs', None),
 ('index', 'sqlite_autoindex_assistant_model_receipts_1', 'assistant_model_receipts', None),
 ('table',
  'assistant_model_attempts',
  'assistant_model_attempts',
  'CREATE TABLE assistant_model_attempts (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id),\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        policy_id TEXT NOT NULL, config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL,\n'
  '        request_sha256 TEXT NOT NULL, input_json TEXT NOT NULL, config_json TEXT NOT NULL,\n'
  '        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,\n'
  '        state TEXT NOT NULL CHECK(state IN '
  "('reserved','sending','sent_unknown','received','failed_before_send')),\n"
  '        claim_sha256 TEXT, updated_at TEXT NOT NULL)'),
 ('table',
  'assistant_model_outputs',
  'assistant_model_outputs',
  'CREATE TABLE assistant_model_outputs (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        attempt_id TEXT NOT NULL UNIQUE REFERENCES assistant_model_attempts(id),\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        run_id TEXT NOT NULL UNIQUE REFERENCES assistant_runs(id),\n'
  '        scope_json TEXT NOT NULL, output_json TEXT NOT NULL, created_at TEXT NOT NULL)'),
 ('table',
  'assistant_model_receipts',
  'assistant_model_receipts',
  'CREATE TABLE assistant_model_receipts (\n'
  '        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_model_attempts(id),\n'
  '        receipt_json TEXT NOT NULL, created_at TEXT NOT NULL)'),
 ('trigger',
  'immutable_assistant_model_attempts_delete',
  'assistant_model_attempts',
  'CREATE TRIGGER immutable_assistant_model_attempts_delete BEFORE DELETE ON assistant_model_attempts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_claim',
  'assistant_model_attempts',
  'CREATE TRIGGER immutable_assistant_model_claim BEFORE UPDATE OF claim_sha256\n'
  '        ON assistant_model_attempts WHEN OLD.claim_sha256 IS NOT NULL AND NEW.claim_sha256 IS NOT '
  'OLD.claim_sha256\n'
  "        BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_input',
  'assistant_model_attempts',
  'CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF\n'
  '        id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,\n'
  '        input_json,config_json,policy_json,reserved_usd,created_at\n'
  "        ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_outputs_delete',
  'assistant_model_outputs',
  'CREATE TRIGGER immutable_assistant_model_outputs_delete BEFORE DELETE ON assistant_model_outputs BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_outputs_update',
  'assistant_model_outputs',
  'CREATE TRIGGER immutable_assistant_model_outputs_update BEFORE UPDATE ON assistant_model_outputs BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_receipts_delete',
  'assistant_model_receipts',
  'CREATE TRIGGER immutable_assistant_model_receipts_delete BEFORE DELETE ON assistant_model_receipts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_model_receipts_update',
  'assistant_model_receipts',
  'CREATE TRIGGER immutable_assistant_model_receipts_update BEFORE UPDATE ON assistant_model_receipts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"))
