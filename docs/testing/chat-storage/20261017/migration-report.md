# CH-01 migration implementation evidence

Date: 2026-10-17 (Asia/Shanghai). Base: `00c12b780a08db26da4937859837fd53b045af46`.

## Implemented ownership

- New `src/cn_contract/storage_schema.py`: fixed `pre-intake`, `intake-v1`, `assistant-v1` catalog. `INTAKE_V1_ROWS` remains the old source of truth; pre-intake removes only objects belonging to the exact two intake tables. Current adds the assistant implementer's fixed DDL objects. Exports `CURRENT_VERSION`, `SUPPORTED_VERSIONS`, `schema_rows`, `normalized_schema`, `identify_schema`. Native identity and its implicit index remain distinct from non-native archive schema.
- New `src/cn_contract/schema_migrations.py`: `upgrade_database(sqlite3_connection)` for already verified isolated restoration stages. Exact version recognition precedes writes; an active caller transaction is rejected without committing it. All missing DDL steps execute in one explicit transaction, with intermediate exact-schema and foreign-key checks. No marker, original material, HTTP or provider access.
- `web/workspace_upgrade.py`: fixed ordered native steps. Each retains its own independently verified before.db, format-1 receipt and atomic marker. The original intake STATEMENTS fault-injection seam remains. Pending intake marker recovery continues to assistant; assistant marker recovery does not re-run either completed step. Receipts, backups, identity and known before/after structures must match.
- `web/local_server.py`: known schema check before Database construction; self-consistent but unknown schemas are rejected. Existing exact-current workspaces use `initialize_schema=False` and service flags, rather than create_all/trigger initialization. New workspaces still initialize explicitly.
- `storage_bootstrap.py`: assistant schema appended after existing families; `mark_storage_initialized` sets the nine existing storage-family flags without DDL.
- Migration/bootstrap tests updated and added. No changes to assistant-owned service/DTO/schema, schema_baseline.py, ops backup implementations, or unrelated source.

## Executed checks

1. RED: `.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_storage_schema_versions.py -q --junitxml=.local/chat-storage-20261017/migration-red.xml`
   - Exit 1; 10 failed in 0.46s because the requested new version/migration modules did not exist.
   - Evidence: `migration-red.log`, `migration-red.xml`.
2. RED: `.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_workspace_upgrade.py -q -k "self_consistent or does_not_run_create_all" --junitxml=.local/chat-storage-20261017/native-red.xml`
   - Exit 1; 3 failed, 5 deselected in 2.70s. Actual existing gaps: unknown/missing-trigger schema accepted when marker matched; existing workspaces re-ran schema initialization.
   - Evidence: `native-red.log`, `native-red.xml`.
3. GREEN: `.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_storage_schema_versions.py tests/integration/test_workspace_upgrade.py tests/integration/test_storage_bootstrap.py -q --junitxml=.local/chat-storage-20261017/migration-green.xml`
   - Exit 0; **24 passed, 0 failures/errors/skips**, pytest 22.03s (JUnit 21.998s).
   - Evidence: `migration-green.log`, `migration-green.xml`.
4. `git diff --check`: exit 0 at review time. Afterwards removed only an unused import from workspace_upgrade.py.

The bootstrap test still proves old normalized SHA256 `cf9282bd4d8b60df107ba98a72c6c116435c3b553294ad135027e1f9e1bf26f4` and raw SHA256 `2c622bf427fb9ac8c93329862b0fb4acfc45cf7d07349e82800ee51090167ba0`, compares newly initialized schema against the current catalog, and checks that schema inspection does not import web.app/web.services/pdfplumber.

## Scope and handoff

This is the migration slice only. Parent owns qxbak/cnbak integration, old-archive roundtrip tests, restored-run fencing, combined regression, independent review and commit. No full-suite run, installation, real-material migration, provider request, commit or push occurred here. Native upgrade still requires the caller's existing workspace worker lock. The database-only helper is for an already completely verified isolated stage, not a replacement for original archive validation. Future schema changes require a newly named version, not mutation of the frozen intake baseline or silently changing a released assistant-v1.
