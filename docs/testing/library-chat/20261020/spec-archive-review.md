# CH-06B2a — Focused archive audit (confirmed finding)

**[P2] Validate `research.accepted` before declaring a backup/restoration valid.**

Location: `src/cn_contract/assistant/research.py:99–102` adds the required acceptance record, but `src/cn_contract/assistant/library_integrity.py:110–111` skips all non-`tool.*` records. The reader's `research.py:39–51` requires its call ID and request digest to match. Existing archive guards therefore do not ensure that an accepted backup can render the new research history.

Specification: “新 message/run 和唯一初始 `tool.before` 在同一短事务提交”; “恢复副本可读历史、不可执行”; “备份恢复反例先失败后通过” (`docs/plans/2026-10-20-library-chat-execution.md`). The new `research.accepted` record is part of the reader's persistent identity contract, so this is a concrete omission from the existing backup-integrity boundary, not a new optional feature.

Independent probe: one completed synthetic research with a valid B1 receipt; change only `research.accepted.call_id` to another valid UUID and restore exact immutable trigger DDL. `backup._file_references` accepts it; actual `.qxbak` creation and restoration both succeed; authenticated restored request/history lookup then raises `LIBRARY_RECORD_INVALID`, while the B1 receipt remains present. This models corrupted input, not an ordinary UI write or a new way to bypass SQL triggers.

Evidence: `.local/library-chat-20261020/spec-archive-probe.py`, `.log`, `.xml`, `.exit`: **1 passed in 3.63s; pytest exit 0**, meaning the defect was reproduced by observational assertions. No product changes were made. Initial fixture-import collection error (exit 2) was preserved separately; the probe import path was corrected before this successful execution.

Required fix: validate the new workflow's acceptance identity/sequence and required initial call in offline archive checks, sharing a pure validator with the runtime reader where practical. Do not require a currently active historical session or current source-library access. Add corruption rejection for archive creation/restoration. No full suite was rerun here.

## Resolution after independent recheck

**Closed.** The shared pure `research_records.initial_call` now checks the persisted acceptance identity for both runtime/history and offline archive validation. Research traces without a valid acceptance/tool pair are rejected; completed runs require their receipt. Historical session validity and live library availability are not prerequisites.

The first patch introduced a separate legacy-compatibility regression: query text containing `local-research-v1` was wrongly taken as workflow ownership. Independent result `spec-archive-fix-red.*`: **1 failed, 3 passed in 8.06s**, exit 1. History now uses the pure validator's `None` classification, preserving old B1 data without adopting it as a new runnable workflow.

Final independent `spec-archive-fix-green.*`: **4 passed in 8.46s**, pytest exit 0. Both changed call ID and changed request digest are rejected at backup creation and actual authenticated archive restoration; only archive creation was temporarily bypassed to form corrupt input, with restore validation untouched. Revoked old sessions/newer drafts/offline library remain restorable, and literal marker text in old B1 queries remains data. Final hashes are in `spec-final-inputs.json` (4 fix files verified, 21 changed/new product files captured, 13 frontend freeze hashes still match).

Original pre-fix observation, initial collection error and regression RED outputs are retained. No full suite or production-data test was performed by this reviewer.
