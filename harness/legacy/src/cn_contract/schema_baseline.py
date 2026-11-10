"""Fixed SQLite compatibility baseline from 00c12b7 (0.4.1 / intake-v1).

No user records or workspace identity are included. Do not regenerate this old
version from a newer initializer: old archives depend on its exact SQL objects.
"""

INTAKE_V1_ROWS = (('index', 'intake_owner', 'intake_cases', 'CREATE INDEX intake_owner ON intake_cases(owner_id, id)'),
 ('index', 'sqlite_autoindex_approvals_1', 'approvals', None),
 ('index', 'sqlite_autoindex_approvals_2', 'approvals', None),
 ('index', 'sqlite_autoindex_audit_events_1', 'audit_events', None),
 ('index', 'sqlite_autoindex_authority_snapshots_1', 'authority_snapshots', None),
 ('index', 'sqlite_autoindex_authority_verifications_1', 'authority_verifications', None),
 ('index', 'sqlite_autoindex_document_versions_1', 'document_versions', None),
 ('index', 'sqlite_autoindex_document_versions_2', 'document_versions', None),
 ('index', 'sqlite_autoindex_export_records_1', 'export_records', None),
 ('index', 'sqlite_autoindex_exports_1', 'exports', None),
 ('index', 'sqlite_autoindex_fact_decisions_1', 'fact_decisions', None),
 ('index', 'sqlite_autoindex_fact_snapshots_1', 'fact_snapshots', None),
 ('index', 'sqlite_autoindex_intake_cases_1', 'intake_cases', None),
 ('index', 'sqlite_autoindex_intake_cases_2', 'intake_cases', None),
 ('index', 'sqlite_autoindex_intake_revisions_1', 'intake_revisions', None),
 ('index', 'sqlite_autoindex_matter_memberships_1', 'matter_memberships', None),
 ('index', 'sqlite_autoindex_matters_1', 'matters', None),
 ('index', 'sqlite_autoindex_ocr_candidates_1', 'ocr_candidates', None),
 ('index', 'sqlite_autoindex_ops_file_relocations_1', 'ops_file_relocations', None),
 ('index', 'sqlite_autoindex_ops_restore_fences_1', 'ops_restore_fences', None),
 ('index', 'sqlite_autoindex_page_verifications_1', 'page_verifications', None),
 ('index', 'sqlite_autoindex_party_decisions_1', 'party_decisions', None),
 ('index', 'sqlite_autoindex_party_snapshots_1', 'party_snapshots', None),
 ('index', 'sqlite_autoindex_party_snapshots_2', 'party_snapshots', None),
 ('index', 'sqlite_autoindex_policy_snapshots_1', 'policy_snapshots', None),
 ('index', 'sqlite_autoindex_provider_records_1', 'provider_records', None),
 ('index', 'sqlite_autoindex_query_ledger_1', 'query_ledger', None),
 ('index', 'sqlite_autoindex_query_ledger_2', 'query_ledger', None),
 ('index', 'sqlite_autoindex_query_plan_versions_1', 'query_plan_versions', None),
 ('index', 'sqlite_autoindex_query_plan_versions_2', 'query_plan_versions', None),
 ('index', 'sqlite_autoindex_query_records_1', 'query_records', None),
 ('index', 'sqlite_autoindex_review_model_attempts_1', 'review_model_attempts', None),
 ('index', 'sqlite_autoindex_review_operation_attempts_1', 'review_operation_attempts', None),
 ('index', 'sqlite_autoindex_review_operation_records_1', 'review_operation_records', None),
 ('index', 'sqlite_autoindex_review_proposals_1', 'review_proposals', None),
 ('index', 'sqlite_autoindex_review_proposals_2', 'review_proposals', None),
 ('index', 'sqlite_autoindex_review_runs_1', 'review_runs', None),
 ('index', 'sqlite_autoindex_rule_snapshots_1', 'rule_snapshots', None),
 ('index', 'sqlite_autoindex_sessions_1', 'sessions', None),
 ('index', 'sqlite_autoindex_sessions_2', 'sessions', None),
 ('index', 'sqlite_autoindex_source_attestations_1', 'source_attestations', None),
 ('index', 'sqlite_autoindex_source_evidence_1', 'source_evidence', None),
 ('index', 'sqlite_autoindex_users_1', 'users', None),
 ('index', 'sqlite_autoindex_users_2', 'users', None),
 ('index', 'sqlite_autoindex_web_finding_decisions_1', 'web_finding_decisions', None),
 ('index', 'sqlite_autoindex_web_http_writes_1', 'web_http_writes', None),
 ('index', 'sqlite_autoindex_web_http_writes_2', 'web_http_writes', None),
 ('index', 'sqlite_autoindex_web_jobs_1', 'web_jobs', None),
 ('index', 'sqlite_autoindex_web_jobs_2', 'web_jobs', None),
 ('table',
  'approvals',
  'approvals',
  'CREATE TABLE approvals (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tapprover_id VARCHAR(36) NOT NULL, \n'
  '\tstatus VARCHAR(20) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (matter_id, id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(approver_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'audit_events',
  'audit_events',
  'CREATE TABLE audit_events (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\taction VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id)\n'
  ')'),
 ('table',
  'authority_snapshots',
  'authority_snapshots',
  'CREATE TABLE authority_snapshots (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tsupersedes_id VARCHAR(36), \n'
  '\tclassification VARCHAR(32) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(supersedes_id) REFERENCES authority_snapshots (id)\n'
  ')'),
 ('table',
  'authority_verifications',
  'authority_verifications',
  'CREATE TABLE authority_verifications (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tauthority_id VARCHAR(36) NOT NULL, \n'
  '\tattestation_id VARCHAR(36) NOT NULL, \n'
  '\treviewer_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tevidence TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(authority_id) REFERENCES authority_snapshots (id), \n'
  '\tFOREIGN KEY(attestation_id) REFERENCES source_attestations (id), \n'
  '\tFOREIGN KEY(reviewer_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'document_versions',
  'document_versions',
  'CREATE TABLE document_versions (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tuploaded_by VARCHAR(36) NOT NULL, \n'
  '\tsupersedes_id VARCHAR(36), \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tbyte_size INTEGER NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (matter_id, id), \n'
  '\tFOREIGN KEY(matter_id, supersedes_id) REFERENCES document_versions (matter_id, id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(uploaded_by) REFERENCES users (id)\n'
  ')'),
 ('table',
  'export_records',
  'export_records',
  'CREATE TABLE export_records (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tref VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tkind VARCHAR(32) NOT NULL, \n'
  '\tparent VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tUNIQUE (ref), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'exports',
  'exports',
  'CREATE TABLE exports (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tapproval_id VARCHAR(36), \n'
  '\tsuperseded BOOLEAN NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id, approval_id) REFERENCES approvals (matter_id, id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'fact_decisions',
  'fact_decisions',
  'CREATE TABLE fact_decisions (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tsource_version INTEGER NOT NULL, \n'
  '\ttarget_version INTEGER NOT NULL, \n'
  '\tfact_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id, source_version) REFERENCES fact_snapshots (matter_id, version), \n'
  '\tFOREIGN KEY(matter_id, target_version) REFERENCES fact_snapshots (matter_id, version), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'fact_snapshots',
  'fact_snapshots',
  'CREATE TABLE fact_snapshots (\n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (matter_id, version), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'intake_cases',
  'intake_cases',
  'CREATE TABLE intake_cases (\n'
  '        id TEXT PRIMARY KEY NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),\n'
  '        request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,\n'
  '        current_revision INTEGER NOT NULL, matter_id TEXT REFERENCES matters(id),\n'
  '        conversion_sha256 TEXT, UNIQUE(owner_id, request_id))'),
 ('table',
  'intake_revisions',
  'intake_revisions',
  'CREATE TABLE intake_revisions (\n'
  '        intake_id TEXT NOT NULL REFERENCES intake_cases(id), revision INTEGER NOT NULL,\n'
  '        saved_at TEXT NOT NULL, payload TEXT NOT NULL,\n'
  '        client_reply TEXT NOT NULL, internal_notes TEXT NOT NULL,\n'
  '        PRIMARY KEY(intake_id, revision))'),
 ('table',
  'matter_memberships',
  'matter_memberships',
  'CREATE TABLE matter_memberships (\n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tuser_id VARCHAR(36) NOT NULL, \n'
  '\tcan_sign BOOLEAN NOT NULL, \n'
  '\tPRIMARY KEY (matter_id, user_id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(user_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'matters',
  'matters',
  'CREATE TABLE matters (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\ttitle TEXT NOT NULL, \n'
  '\tstatus VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tfile_count INTEGER NOT NULL, \n'
  '\ttotal_bytes INTEGER NOT NULL, \n'
  '\tPRIMARY KEY (id)\n'
  ')'),
 ('table',
  'ocr_candidates',
  'ocr_candidates',
  'CREATE TABLE ocr_candidates (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tdocument_version_id VARCHAR(36) NOT NULL, \n'
  '\tcreated_at VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id), \n'
  '\tFOREIGN KEY(document_version_id) REFERENCES document_versions (id)\n'
  ')'),
 ('table',
  'ops_file_relocations',
  'ops_file_relocations',
  'CREATE TABLE ops_file_relocations (\n'
  '\tlogical_ref TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tphysical_ref TEXT NOT NULL, \n'
  '\tarchive_sha256 VARCHAR(64) NOT NULL, \n'
  '\trecord_refs TEXT NOT NULL, \n'
  '\tPRIMARY KEY (logical_ref, sha256)\n'
  ')'),
 ('table',
  'ops_restore_fences',
  'ops_restore_fences',
  'CREATE TABLE ops_restore_fences (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tref VARCHAR(36) NOT NULL, \n'
  '\tarchive_sha256 VARCHAR(64) NOT NULL, \n'
  '\tmanifest_sha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tUNIQUE (ref)\n'
  ')'),
 ('table',
  'page_verifications',
  'page_verifications',
  'CREATE TABLE page_verifications (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tcreated_at VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'parse_snapshots',
  'parse_snapshots',
  'CREATE TABLE parse_snapshots (\n'
  '\tid INTEGER NOT NULL, \n'
  '\tdocument_version_id VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(document_version_id) REFERENCES document_versions (id)\n'
  ')'),
 ('table',
  'party_decisions',
  'party_decisions',
  'CREATE TABLE party_decisions (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tparty_id VARCHAR(36) NOT NULL, \n'
  '\tsource_revision INTEGER NOT NULL, \n'
  '\ttarget_revision INTEGER NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tbefore_hash VARCHAR(64) NOT NULL, \n'
  '\tafter_hash VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id, party_id, source_revision) REFERENCES party_snapshots (matter_id, party_id, '
  'revision), \n'
  '\tFOREIGN KEY(matter_id, party_id, target_revision) REFERENCES party_snapshots (matter_id, party_id, '
  'revision), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'party_snapshots',
  'party_snapshots',
  'CREATE TABLE party_snapshots (\n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tparty_id VARCHAR(36) NOT NULL, \n'
  '\trevision INTEGER NOT NULL, \n'
  '\trecord_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (matter_id, party_id, revision), \n'
  '\tUNIQUE (record_id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'policy_approvals',
  'policy_approvals',
  'CREATE TABLE policy_approvals (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\treviewer_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tevidence TEXT NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tFOREIGN KEY(matter_id, version) REFERENCES policy_snapshots (matter_id, version), \n'
  '\tFOREIGN KEY(reviewer_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'policy_snapshots',
  'policy_snapshots',
  'CREATE TABLE policy_snapshots (\n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\tclient_ref TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (matter_id, version), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'provider_records',
  'provider_records',
  'CREATE TABLE provider_records (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tref VARCHAR(36) NOT NULL, \n'
  '\tkind VARCHAR(32) NOT NULL, \n'
  '\tparent VARCHAR(128) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36), \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tUNIQUE (ref)\n'
  ')'),
 ('table',
  'query_ledger',
  'query_ledger',
  'CREATE TABLE query_ledger (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tplan_ref VARCHAR(36) NOT NULL, \n'
  '\titem_id VARCHAR(36) NOT NULL, \n'
  '\tpage INTEGER NOT NULL, \n'
  '\tidempotency_key VARCHAR(64) NOT NULL, \n'
  '\tpreimage TEXT NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tcall_count INTEGER NOT NULL, \n'
  '\tdispatch_token_sha256 VARCHAR(64), \n'
  '\tsend_claimed BOOLEAN NOT NULL, \n'
  '\trevision INTEGER NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(plan_ref) REFERENCES query_plan_versions (ref), \n'
  '\tUNIQUE (idempotency_key)\n'
  ')'),
 ('table',
  'query_plan_versions',
  'query_plan_versions',
  'CREATE TABLE query_plan_versions (\n'
  '\tref VARCHAR(36) NOT NULL, \n'
  '\tplan_id VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tmetadata_json TEXT NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (ref), \n'
  '\tUNIQUE (plan_id, version), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'query_records',
  'query_records',
  'CREATE TABLE query_records (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tref VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tkind VARCHAR(32) NOT NULL, \n'
  '\tparent VARCHAR(128) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tUNIQUE (ref), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'review_model_attempts',
  'review_model_attempts',
  'CREATE TABLE review_model_attempts (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\trun_id VARCHAR(36) NOT NULL, \n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tmetadata_json TEXT NOT NULL, \n'
  '\traw TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(run_id) REFERENCES review_runs (id)\n'
  ')'),
 ('table',
  'review_operation_attempts',
  'review_operation_attempts',
  'CREATE TABLE review_operation_attempts (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\trecord_id VARCHAR(36) NOT NULL, \n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tmetadata_json TEXT NOT NULL, \n'
  '\traw TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(record_id) REFERENCES review_operation_records (id)\n'
  ')'),
 ('table',
  'review_operation_records',
  'review_operation_records',
  'CREATE TABLE review_operation_records (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tphase VARCHAR(32) NOT NULL, \n'
  '\tmetadata_json TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'review_proposals',
  'review_proposals',
  'CREATE TABLE review_proposals (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\trun_id VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (run_id), \n'
  '\tFOREIGN KEY(run_id) REFERENCES review_runs (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'review_runs',
  'review_runs',
  'CREATE TABLE review_runs (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tcontext_json TEXT NOT NULL, \n'
  '\tconfig_json TEXT NOT NULL, \n'
  '\tprocessed_json TEXT NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'rule_approvals',
  'rule_approvals',
  'CREATE TABLE rule_approvals (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\trule_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\treviewer_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\trule_sha256 VARCHAR(64) NOT NULL, \n'
  '\tdependency_sha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tevidence TEXT NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tFOREIGN KEY(matter_id, rule_id, version) REFERENCES rule_snapshots (matter_id, rule_id, version), \n'
  '\tFOREIGN KEY(reviewer_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'rule_invalidations',
  'rule_invalidations',
  'CREATE TABLE rule_invalidations (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\trule_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\treason VARCHAR(80) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tFOREIGN KEY(matter_id, rule_id, version) REFERENCES rule_snapshots (matter_id, rule_id, version)\n'
  ')'),
 ('table',
  'rule_manager_grants',
  'rule_manager_grants',
  'CREATE TABLE rule_manager_grants (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tuser_id VARCHAR(36) NOT NULL, \n'
  '\tenabled VARCHAR(8) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tFOREIGN KEY(user_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'rule_snapshots',
  'rule_snapshots',
  'CREATE TABLE rule_snapshots (\n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\trule_id VARCHAR(36) NOT NULL, \n'
  '\tversion INTEGER NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tmetadata_json TEXT NOT NULL, \n'
  '\tpolicy_binding_json TEXT, \n'
  '\tsha256 VARCHAR(64) NOT NULL, \n'
  '\tPRIMARY KEY (matter_id, rule_id, version), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id)\n'
  ')'),
 ('table',
  'sessions',
  'sessions',
  'CREATE TABLE sessions (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tuser_id VARCHAR(36) NOT NULL, \n'
  '\ttoken_hash VARCHAR(64) NOT NULL, \n'
  '\tcsrf_hash VARCHAR(64) NOT NULL, \n'
  '\texpires_at VARCHAR(40) NOT NULL, \n'
  '\trevoked BOOLEAN NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(user_id) REFERENCES users (id), \n'
  '\tUNIQUE (token_hash)\n'
  ')'),
 ('table',
  'source_attestations',
  'source_attestations',
  'CREATE TABLE source_attestations (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tauthority_id VARCHAR(36) NOT NULL, \n'
  '\treviewer_id VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tclassification VARCHAR(32) NOT NULL, \n'
  '\tsource_sha256 VARCHAR(64) NOT NULL, \n'
  '\tprovenance_ref TEXT NOT NULL, \n'
  '\tevidence TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(authority_id) REFERENCES authority_snapshots (id), \n'
  '\tFOREIGN KEY(reviewer_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'source_evidence',
  'source_evidence',
  'CREATE TABLE source_evidence (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tauthority_id VARCHAR(36) NOT NULL, \n'
  '\tacquired_by VARCHAR(36) NOT NULL, \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tsource_sha256 VARCHAR(64) NOT NULL, \n'
  '\tartifact_sha256 VARCHAR(64) NOT NULL, \n'
  '\toriginal_bytes BLOB NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(authority_id) REFERENCES authority_snapshots (id), \n'
  '\tFOREIGN KEY(acquired_by) REFERENCES users (id)\n'
  ')'),
 ('table',
  'users',
  'users',
  'CREATE TABLE users (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tusername VARCHAR(128) NOT NULL, \n'
  '\tpassword_hash TEXT NOT NULL, \n'
  '\troles TEXT NOT NULL, \n'
  '\tdisabled BOOLEAN NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (username)\n'
  ')'),
 ('table',
  'web_finding_decisions',
  'web_finding_decisions',
  'CREATE TABLE web_finding_decisions (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\trun_id VARCHAR(36) NOT NULL, \n'
  '\tfinding_id VARCHAR(36) NOT NULL, \n'
  '\trun_sha256 VARCHAR(64) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tUNIQUE (id), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(run_id) REFERENCES review_runs (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'web_http_writes',
  'web_http_writes',
  'CREATE TABLE web_http_writes (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_scope VARCHAR(36) NOT NULL, \n'
  '\tresponse_matter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\taction VARCHAR(128) NOT NULL, \n'
  '\tidempotency_key VARCHAR(128) NOT NULL, \n'
  '\trequest_sha256 VARCHAR(64) NOT NULL, \n'
  '\tresponse_matter_sha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (matter_scope, actor_id, action, idempotency_key), \n'
  '\tFOREIGN KEY(response_matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')'),
 ('table',
  'web_job_events',
  'web_job_events',
  'CREATE TABLE web_job_events (\n'
  '\tsequence INTEGER NOT NULL, \n'
  '\tjob_id VARCHAR(36) NOT NULL, \n'
  '\tstate VARCHAR(20) NOT NULL, \n'
  '\terror_code VARCHAR(80), \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (sequence), \n'
  '\tFOREIGN KEY(job_id) REFERENCES web_jobs (id)\n'
  ')'),
 ('table',
  'web_jobs',
  'web_jobs',
  'CREATE TABLE web_jobs (\n'
  '\tid VARCHAR(36) NOT NULL, \n'
  '\tmatter_id VARCHAR(36) NOT NULL, \n'
  '\tactor_id VARCHAR(36) NOT NULL, \n'
  '\tsession_id VARCHAR(36) NOT NULL, \n'
  '\tkind VARCHAR(20) NOT NULL, \n'
  '\tidempotency_key VARCHAR(128) NOT NULL, \n'
  '\tinput_sha256 VARCHAR(64) NOT NULL, \n'
  '\tmatter_sha256 VARCHAR(64) NOT NULL, \n'
  '\tpayload TEXT NOT NULL, \n'
  '\tstate VARCHAR(20) NOT NULL, \n'
  '\tstage VARCHAR(80) NOT NULL, \n'
  '\terror_code VARCHAR(80), \n'
  '\tresult_ref VARCHAR(100), \n'
  '\ttimestamp VARCHAR(40) NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (matter_id, actor_id, kind, idempotency_key), \n'
  '\tFOREIGN KEY(matter_id) REFERENCES matters (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id), \n'
  '\tFOREIGN KEY(session_id) REFERENCES sessions (id)\n'
  ')'),
 ('trigger',
  'immutable_audit_events_delete',
  'audit_events',
  'CREATE TRIGGER immutable_audit_events_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_audit_events_update',
  'audit_events',
  'CREATE TRIGGER immutable_audit_events_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_authority_snapshots_delete',
  'authority_snapshots',
  'CREATE TRIGGER immutable_authority_snapshots_delete BEFORE DELETE ON authority_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_authority_snapshots_update',
  'authority_snapshots',
  'CREATE TRIGGER immutable_authority_snapshots_update BEFORE UPDATE ON authority_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_authority_verifications_delete',
  'authority_verifications',
  'CREATE TRIGGER immutable_authority_verifications_delete BEFORE DELETE ON authority_verifications BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_authority_verifications_update',
  'authority_verifications',
  'CREATE TRIGGER immutable_authority_verifications_update BEFORE UPDATE ON authority_verifications BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_document_versions_delete',
  'document_versions',
  'CREATE TRIGGER immutable_document_versions_delete BEFORE DELETE ON document_versions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_document_versions_update',
  'document_versions',
  'CREATE TRIGGER immutable_document_versions_update BEFORE UPDATE ON document_versions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_export_records_delete',
  'export_records',
  'CREATE TRIGGER immutable_export_records_delete BEFORE DELETE ON export_records BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_export_records_update',
  'export_records',
  'CREATE TRIGGER immutable_export_records_update BEFORE UPDATE ON export_records BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_fact_decisions_delete',
  'fact_decisions',
  'CREATE TRIGGER immutable_fact_decisions_delete BEFORE DELETE ON fact_decisions BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_fact_decisions_update',
  'fact_decisions',
  'CREATE TRIGGER immutable_fact_decisions_update BEFORE UPDATE ON fact_decisions BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_fact_snapshots_delete',
  'fact_snapshots',
  'CREATE TRIGGER immutable_fact_snapshots_delete BEFORE DELETE ON fact_snapshots BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_fact_snapshots_update',
  'fact_snapshots',
  'CREATE TRIGGER immutable_fact_snapshots_update BEFORE UPDATE ON fact_snapshots BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_intake_cases_delete',
  'intake_cases',
  'CREATE TRIGGER immutable_intake_cases_delete BEFORE DELETE ON intake_cases BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_intake_revisions_delete',
  'intake_revisions',
  'CREATE TRIGGER immutable_intake_revisions_delete BEFORE DELETE ON intake_revisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_intake_revisions_update',
  'intake_revisions',
  'CREATE TRIGGER immutable_intake_revisions_update BEFORE UPDATE ON intake_revisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ocr_candidates_delete',
  'ocr_candidates',
  'CREATE TRIGGER immutable_ocr_candidates_delete BEFORE DELETE ON ocr_candidates BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ocr_candidates_update',
  'ocr_candidates',
  'CREATE TRIGGER immutable_ocr_candidates_update BEFORE UPDATE ON ocr_candidates BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ops_file_relocations_delete',
  'ops_file_relocations',
  'CREATE TRIGGER immutable_ops_file_relocations_delete BEFORE DELETE ON ops_file_relocations BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ops_file_relocations_update',
  'ops_file_relocations',
  'CREATE TRIGGER immutable_ops_file_relocations_update BEFORE UPDATE ON ops_file_relocations BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ops_restore_fences_delete',
  'ops_restore_fences',
  'CREATE TRIGGER immutable_ops_restore_fences_delete BEFORE DELETE ON ops_restore_fences BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_ops_restore_fences_update',
  'ops_restore_fences',
  'CREATE TRIGGER immutable_ops_restore_fences_update BEFORE UPDATE ON ops_restore_fences BEGIN SELECT '
  "RAISE(ABORT,'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_page_verifications_delete',
  'page_verifications',
  'CREATE TRIGGER immutable_page_verifications_delete BEFORE DELETE ON page_verifications BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_page_verifications_update',
  'page_verifications',
  'CREATE TRIGGER immutable_page_verifications_update BEFORE UPDATE ON page_verifications BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_parse_snapshots_delete',
  'parse_snapshots',
  'CREATE TRIGGER immutable_parse_snapshots_delete BEFORE DELETE ON parse_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_parse_snapshots_update',
  'parse_snapshots',
  'CREATE TRIGGER immutable_parse_snapshots_update BEFORE UPDATE ON parse_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_party_decisions_delete',
  'party_decisions',
  'CREATE TRIGGER immutable_party_decisions_delete BEFORE DELETE ON party_decisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_party_decisions_update',
  'party_decisions',
  'CREATE TRIGGER immutable_party_decisions_update BEFORE UPDATE ON party_decisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_party_snapshots_delete',
  'party_snapshots',
  'CREATE TRIGGER immutable_party_snapshots_delete BEFORE DELETE ON party_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_party_snapshots_update',
  'party_snapshots',
  'CREATE TRIGGER immutable_party_snapshots_update BEFORE UPDATE ON party_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_policy_approvals_delete',
  'policy_approvals',
  'CREATE TRIGGER immutable_policy_approvals_delete BEFORE DELETE ON policy_approvals BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_policy_approvals_update',
  'policy_approvals',
  'CREATE TRIGGER immutable_policy_approvals_update BEFORE UPDATE ON policy_approvals BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_policy_snapshots_delete',
  'policy_snapshots',
  'CREATE TRIGGER immutable_policy_snapshots_delete BEFORE DELETE ON policy_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_policy_snapshots_update',
  'policy_snapshots',
  'CREATE TRIGGER immutable_policy_snapshots_update BEFORE UPDATE ON policy_snapshots BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_provider_records_delete',
  'provider_records',
  'CREATE TRIGGER immutable_provider_records_delete BEFORE DELETE ON provider_records BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_provider_records_update',
  'provider_records',
  'CREATE TRIGGER immutable_provider_records_update BEFORE UPDATE ON provider_records BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_query_ledger_delete',
  'query_ledger',
  'CREATE TRIGGER immutable_query_ledger_delete BEFORE DELETE ON query_ledger BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_query_plan_versions_delete',
  'query_plan_versions',
  'CREATE TRIGGER immutable_query_plan_versions_delete BEFORE DELETE ON query_plan_versions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_query_plan_versions_update',
  'query_plan_versions',
  'CREATE TRIGGER immutable_query_plan_versions_update BEFORE UPDATE ON query_plan_versions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_query_records_delete',
  'query_records',
  'CREATE TRIGGER immutable_query_records_delete BEFORE DELETE ON query_records BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_query_records_update',
  'query_records',
  'CREATE TRIGGER immutable_query_records_update BEFORE UPDATE ON query_records BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_model_attempts_delete',
  'review_model_attempts',
  'CREATE TRIGGER immutable_review_model_attempts_delete BEFORE DELETE ON review_model_attempts BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_model_attempts_update',
  'review_model_attempts',
  'CREATE TRIGGER immutable_review_model_attempts_update BEFORE UPDATE ON review_model_attempts BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_operation_attempts_delete',
  'review_operation_attempts',
  'CREATE TRIGGER immutable_review_operation_attempts_delete BEFORE DELETE ON review_operation_attempts '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_operation_attempts_update',
  'review_operation_attempts',
  'CREATE TRIGGER immutable_review_operation_attempts_update BEFORE UPDATE ON review_operation_attempts '
  "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_operation_records_delete',
  'review_operation_records',
  'CREATE TRIGGER immutable_review_operation_records_delete BEFORE DELETE ON review_operation_records BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_operation_records_update',
  'review_operation_records',
  'CREATE TRIGGER immutable_review_operation_records_update BEFORE UPDATE ON review_operation_records BEGIN '
  "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_proposals_delete',
  'review_proposals',
  'CREATE TRIGGER immutable_review_proposals_delete BEFORE DELETE ON review_proposals BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_proposals_update',
  'review_proposals',
  'CREATE TRIGGER immutable_review_proposals_update BEFORE UPDATE ON review_proposals BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_runs_delete',
  'review_runs',
  'CREATE TRIGGER immutable_review_runs_delete BEFORE DELETE ON review_runs BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_review_runs_update',
  'review_runs',
  'CREATE TRIGGER immutable_review_runs_update BEFORE UPDATE ON review_runs BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_approvals_delete',
  'rule_approvals',
  'CREATE TRIGGER immutable_rule_approvals_delete BEFORE DELETE ON rule_approvals BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_approvals_update',
  'rule_approvals',
  'CREATE TRIGGER immutable_rule_approvals_update BEFORE UPDATE ON rule_approvals BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_invalidations_delete',
  'rule_invalidations',
  'CREATE TRIGGER immutable_rule_invalidations_delete BEFORE DELETE ON rule_invalidations BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_invalidations_update',
  'rule_invalidations',
  'CREATE TRIGGER immutable_rule_invalidations_update BEFORE UPDATE ON rule_invalidations BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_manager_grants_delete',
  'rule_manager_grants',
  'CREATE TRIGGER immutable_rule_manager_grants_delete BEFORE DELETE ON rule_manager_grants BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_manager_grants_update',
  'rule_manager_grants',
  'CREATE TRIGGER immutable_rule_manager_grants_update BEFORE UPDATE ON rule_manager_grants BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_snapshots_delete',
  'rule_snapshots',
  'CREATE TRIGGER immutable_rule_snapshots_delete BEFORE DELETE ON rule_snapshots BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_rule_snapshots_update',
  'rule_snapshots',
  'CREATE TRIGGER immutable_rule_snapshots_update BEFORE UPDATE ON rule_snapshots BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_source_attestations_delete',
  'source_attestations',
  'CREATE TRIGGER immutable_source_attestations_delete BEFORE DELETE ON source_attestations BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_source_attestations_update',
  'source_attestations',
  'CREATE TRIGGER immutable_source_attestations_update BEFORE UPDATE ON source_attestations BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_source_evidence_delete',
  'source_evidence',
  'CREATE TRIGGER immutable_source_evidence_delete BEFORE DELETE ON source_evidence BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_source_evidence_update',
  'source_evidence',
  'CREATE TRIGGER immutable_source_evidence_update BEFORE UPDATE ON source_evidence BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_finding_decisions_delete',
  'web_finding_decisions',
  'CREATE TRIGGER immutable_web_finding_decisions_delete BEFORE DELETE ON web_finding_decisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_finding_decisions_update',
  'web_finding_decisions',
  'CREATE TRIGGER immutable_web_finding_decisions_update BEFORE UPDATE ON web_finding_decisions BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_http_writes_delete',
  'web_http_writes',
  'CREATE TRIGGER immutable_web_http_writes_delete BEFORE DELETE ON web_http_writes BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_http_writes_update',
  'web_http_writes',
  'CREATE TRIGGER immutable_web_http_writes_update BEFORE UPDATE ON web_http_writes BEGIN SELECT '
  "RAISE(ABORT, 'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_job_delete',
  'web_jobs',
  'CREATE TRIGGER immutable_web_job_delete BEFORE DELETE ON web_jobs BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_job_events_delete',
  'web_job_events',
  'CREATE TRIGGER immutable_web_job_events_delete BEFORE DELETE ON web_job_events BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_job_events_update',
  'web_job_events',
  'CREATE TRIGGER immutable_web_job_events_update BEFORE UPDATE ON web_job_events BEGIN SELECT RAISE(ABORT, '
  "'IMMUTABLE_RECORD'); END"),
 ('trigger',
  'immutable_web_job_input',
  'web_jobs',
  'CREATE TRIGGER immutable_web_job_input BEFORE UPDATE OF '
  'id,matter_id,actor_id,session_id,kind,idempotency_key,input_sha256,matter_sha256,payload,timestamp ON '
  "web_jobs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END"))
