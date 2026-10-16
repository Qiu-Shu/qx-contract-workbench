# CH-01 conversation storage and compatible upgrades

Base: `00c12b780a08db26da4937859837fd53b045af46`. Continue the approved v2.1 design and [migration review](chat-first-schema-migration-notes.md) in the existing branch. No new framework, dependency, real-data processing or provider calls.

## Concrete first storage version

`assistant-v1` adds the four tables needed for this slice: conversations, immutable messages, runs and immutable run events. Source/input/material/composer/binding revisions, owner and workspace scope, request hashes and idempotency are explicit. The remaining v2.1 tables arrive with their consuming tasks through further named additive upgrades; do not create unused placeholder tables or mutate a published schema version silently. Nonempty attachment selections remain unsupported until CH-03 owns those files. Saving a message queues a durable run but does not call a provider in CH-01.

Business DTOs stay in `domain.py`. The assistant module uses existing security/principal and transaction APIs without importing Web application/services. Each command rechecks the current session, owner and linked intake/matter permissions. Restored copies allow reads but reject writes at the service boundary. No UI or cloud permission is implied by owning a conversation.

## Parallel ownership and interface

- Storage/service implementer: `assistant/{__init__,schema,service}.py`, assistant DTOs in `domain.py`, and focused `test_assistant_storage.py`. Schema exports `STATEMENTS`, `expected_objects()` and `initialize_storage(database)`, using fixed SQL like intake rather than global ORM metadata. Services expose `create_conversation(actor, request, db)`, `read_conversation(actor, id, db)`, `save_draft(actor, id, request, db)`, `save_message(actor, id, request, db)` and `get_run(actor, id, db)`. No writes to bootstrap, upgrade or backup files.
- Migration implementer: fixed version identification and ordered native upgrade, `storage_bootstrap.py`, `web/workspace_upgrade.py`, `web/local_server.py`, and migration tests. Fixed old baseline is already captured in `schema_baseline.py`. No edits to assistant service/DTO/schema ownership. Preserve the intake receipt format/path, use an independent assistant receipt, and reject unknown structures even when marker hashes match them.
- Root: backup compatibility in `ops/backup.py` / `ops/workspace_backup.py`, restore tests, integration and review. Validate original old archive content before upgrading only the staging copy and applying the restore fence. Keep both native and normalized schema algorithms.

The migration module will provide `schema_rows(version, *, native=False)`, `normalized_schema(version, *, native=False)`, `identify_schema(rows, *, native=False)`, `CURRENT_VERSION`, and a database-only `upgrade_database(connection)` for an already isolated, fully verified restore staging copy. Native working-copy upgrades retain their independent backups/receipts and worker lock. The database-only helper cannot relax version validation or be used to mutate an original archive before verification.

## Required evidence

Focused RED/GREEN checks cover same-key replay/conflict, another owner, expired/revoked session, revoked membership, composer vs sent-input versions, busy runs, protected message history and restore fence. Upgrade tests cover pre-intake→intake→assistant, repeat open, failure/receipt recovery at each step, unknown/tampered schema and backups. Fixed old qxbak/cnbak tests must exercise old bytes, not a new archive relabelled as old. Run affected existing regressions, independently review both specification and repository rules, freeze and exercise the actual candidate, then record and commit verified work. Counts and limitations stay separate from earlier full regressions.
