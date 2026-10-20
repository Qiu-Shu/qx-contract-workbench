# CH-06B1 backup implementation report

Scope: `assistant/library_integrity.py`, three older integrity version allowlists, `ops/backup.py` hookup, new library backup/upgrade tests, and the existing Judge-upgrade test current-version expectation. No schema/domain/handler edits, no commit or push.

## Evidence (synthetic Windows .venv)

- `backup-red.log`: first attempt failed due to new schema not yet allowed by older validators. Not counted as the functional RED.
- `backup-red-functional.log`: after compatibility-only version updates, malformed unfinished `tool.before` archived successfully; expected rejection failed (exit 1). This is the effective RED.
- `backup-first-green.log`: same guard after validator/hookup, 1 passed (exit 0).
- `backup-target-1.log`: 32 passed, 58.40s (exit 0). Includes native real-handler search/read history, qxbak roundtrip and repeated roundtrip, sessions revoked/run quarantined/execution refused, 23 corruption modes, normal historical revision/session changes, authenticated hostile restore rejection, cnbak guard.
- `backup-target-2.log`: 11 passed / 40 deselected, 11.88s (exit 0). `-k original_read_dependency or cnbak_restore` selects source-reference missing/cross-run/digest/time/duplicate-JSON corruption for completed and unfinished calls plus hostile cnbak restoration. Upgrade modules were deselected by this selector, not claimed tested here.
- `backup-upgrade.log`: both library and existing Judge upgrade modules, 8 passed, 22.20s (exit 0). New tests independently append frozen Judge DDL, then restore pre-library qxbak/cnbak; originals and archive unchanged, injected migration error leaves no published destination.
- `backup-rebinding-red.log`: legal historical binding revision advance incorrectly rejected (exit 1).
- `backup-rebinding-green.log`: history may have an older binding; same binding must match kind/ref, older snapshot target still checked. 1 passed / 43 deselected, 1.85s (exit 0). GREEN changes actual current scope to a new synthetic matter as well as revision.
- `backup-legacy-red.log`: old Judge schema containing new malformed tool event incorrectly archived (exit 1).
- `backup-legacy-green.log`: old known assistant schemas must not contain new tool events. 1 passed / 4 deselected, 3.50s (exit 0).

Current independent target cases: 44 library backup + 5 library upgrade + 4 existing Judge upgrade = 53. These are incremental runs, not a claimed frozen final regression; parent will run the stabilized final set.

## Checks and boundaries

Checks all fixed tool events including unfinished ones: canonical payload, UUID call identity, <=8 logical events, no duplicate call ID, contiguous sequences, nondecreasing UTC timestamps, run/message/user/session/workspace linkage, historical scope and monotone revisions. Receipt/citation JSON, digests, ordered UUID lists, ordinals and times must agree. Read-original dependencies require an earlier successful receipt in the same run/scope, matching stored hash and snapshot. No external legal-library IO for archive proof or history reads. Current session revocation/disablement and a newer composer/input/binding do not invalidate earlier snapshots.

Old cnbak refuses any new tool history. Native qxbak keeps snapshots, revokes old sessions and quarantines active runs. Restore never resumes work. Tests use independent fictional local files, no production DB or real models. No GUI, frozen binary, package-size, process-RSS or full-suite verification performed by this subagent.

## Independent review follow-up: citation content identity

Spec review found a content-addressed citation ID consistency gap. Formal regression `test_rehashed_outer_records_cannot_hide_invalid_citation_identity` mutates the internal ID and recomputes both outer JSON hashes. Both backup creation and authenticated hostile restore were accepted before the shared pure snapshot fix: `backup-citation-identity-red.log`, 2 failed / 44 deselected, 6.00s, exit 1. Shared identity generation/validation fix belongs to the service agent; no adapter/records changes were made by backup agent. GREEN pending at this entry. This is offline self-consistency verification, not renewed source or legal validity verification.

Shared fix now applied by service agent. `backup-citation-identity-green.log`: same 2 creation/restore rejection cases passed, 44 deselected, 5.01s, exit 0. No valid original archive/source was altered. Current backup target total is 46 backup + 5 new upgrade + 4 previous Judge upgrade = 55 independent cases; parent final frozen regression still determines phase acceptance.
