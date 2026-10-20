"""Frozen assistant-judge-v1 DDL captured from 641a6e8 before library receipts."""

ASSISTANT_JUDGE_V1_ROWS = (('index', 'sqlite_autoindex_assistant_judge_attempts_1', 'assistant_judge_attempts', None),
 ('index', 'sqlite_autoindex_assistant_judge_attempts_2', 'assistant_judge_attempts', None),
 ('index', 'sqlite_autoindex_assistant_judge_decisions_1', 'assistant_judge_decisions', None),
 ('index', 'sqlite_autoindex_assistant_judge_receipts_1', 'assistant_judge_receipts', None),
 ('table',
  'assistant_judge_attempts',
  'assistant_judge_attempts',
  'CREATE TABLE assistant_judge_attempts (\n'
  '        id TEXT PRIMARY KEY NOT NULL,\n'
  '        run_id TEXT NOT NULL REFERENCES assistant_runs(id),\n'
  '        conversation_id TEXT NOT NULL REFERENCES assistant_conversations(id),\n'
  '        message_id TEXT NOT NULL REFERENCES assistant_messages(id),\n'
  '        actor_id TEXT NOT NULL REFERENCES users(id), session_id TEXT NOT NULL REFERENCES sessions(id),\n'
  '        purpose TEXT NOT NULL CHECK(purpose IN '
  "('primary_intent','material_kind','possible_result_guarantee')),\n"
  '        policy_id TEXT NOT NULL, authorization_id TEXT NOT NULL,\n'
  '        config_sha256 TEXT NOT NULL, policy_sha256 TEXT NOT NULL, input_hash TEXT NOT NULL,\n'
  '        source_sha256 TEXT NOT NULL, request_json TEXT NOT NULL, config_json TEXT NOT NULL,\n'
  '        policy_json TEXT NOT NULL, reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL,\n'
  "        state TEXT NOT NULL CHECK(state IN ('reserved','sending','not_sent','sent_unknown','received')),\n"
  '        claim_sha256 TEXT, updated_at TEXT NOT NULL, UNIQUE(run_id,purpose))'),
 ('table',
  'assistant_judge_decisions',
  'assistant_judge_decisions',
  'CREATE TABLE assistant_judge_decisions (\n'
  '        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_judge_attempts(id),\n'
  '        decision_json TEXT NOT NULL, created_at TEXT NOT NULL)'),
 ('table',
  'assistant_judge_receipts',
  'assistant_judge_receipts',
  'CREATE TABLE assistant_judge_receipts (\n'
  '        attempt_id TEXT PRIMARY KEY NOT NULL REFERENCES assistant_judge_attempts(id),\n'
  '        receipt_json TEXT NOT NULL, created_at TEXT NOT NULL)'),
 ('trigger',
  'immutable_assistant_judge_attempts_delete',
  'assistant_judge_attempts',
  'CREATE TRIGGER immutable_assistant_judge_attempts_delete BEFORE DELETE ON assistant_judge_attempts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_claim',
  'assistant_judge_attempts',
  'CREATE TRIGGER immutable_assistant_judge_claim BEFORE UPDATE OF claim_sha256\n'
  '        ON assistant_judge_attempts WHEN OLD.claim_sha256 IS NOT NULL AND NEW.claim_sha256 IS NOT '
  'OLD.claim_sha256\n'
  "        BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_decisions_delete',
  'assistant_judge_decisions',
  'CREATE TRIGGER immutable_assistant_judge_decisions_delete BEFORE DELETE ON assistant_judge_decisions '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_decisions_update',
  'assistant_judge_decisions',
  'CREATE TRIGGER immutable_assistant_judge_decisions_update BEFORE UPDATE ON assistant_judge_decisions '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_input',
  'assistant_judge_attempts',
  'CREATE TRIGGER immutable_assistant_judge_input BEFORE UPDATE OF\n'
  '        id,run_id,conversation_id,message_id,actor_id,session_id,purpose,policy_id,authorization_id,\n'
  '        '
  'config_sha256,policy_sha256,input_hash,source_sha256,request_json,config_json,policy_json,reserved_usd,created_at\n'
  "        ON assistant_judge_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_receipts_delete',
  'assistant_judge_receipts',
  'CREATE TRIGGER immutable_assistant_judge_receipts_delete BEFORE DELETE ON assistant_judge_receipts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_assistant_judge_receipts_update',
  'assistant_judge_receipts',
  'CREATE TRIGGER immutable_assistant_judge_receipts_update BEFORE UPDATE ON assistant_judge_receipts BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"))
