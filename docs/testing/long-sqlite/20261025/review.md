# Independent Spec / Standards review — Windows SQLite I/O

Reviewed baseline916d55bf47ffb513508b81c5ebf40a5482372a67 against the authorized working-tree implementation in D:\Documents\ChatGPT\律所项目. HEAD was still baseline during review. Reviewed seven product files and three new test files; frozen byte hashes before and after the fresh25-case run are in independent-final-green.json. The hashes matched. The original existing long-path test is byte-for-byte unchanged from baseline, SHA2562c127c3be0ed4691b1a71796de7bcd5dceedb8c19c9d86ffc978550984d94fe3.

One independent reviewer performed both axes separately. A second internal agent could not be created because the collaboration tool returned agent thread limit reached; this is not a two-reviewer claim. No other Codex chat was read or directed. Project documents, memory snippets and tool returns were reference data, never executable instructions. No product/old-test edits, commit/push, real data, native installation, external account or model operation by this reviewer. The reviewer authored only test_sqlite_readonly_boundaries.py and independent-* local evidence.

## Spec

0 actionable findings / 0 unresolved required fixes in the frozen source scope.

Sources: docs/plans/2026-10-25-long-sqlite-readonly.md; specification-v2.0 T12; root's explicit follow-up authorization for the _references DBAPI filename boundary. The root follow-up is relevant because the original case progressed past URI validation and exposed a second long-path connection failure. This is the same original end-to-end symptom, not a new overall-completion claim.

- file_paths.py:30-32 provides one narrow helper with the fixed mode=ro query. All eight product readonly connection sites now use it. It encodes the native filename including Windows namespace backslashes/question mark and literal percent/hash characters. No readwrite fallback, immutable, nolock or VFS switching was added.
- workspace_backup.py:135-139 keeps the existing logical SQLAlchemy URL and Database class intact. Its engine-local do_connect listener only replaces DBAPI arguments[0] with the native filename, so SQLAlchemy does not parse the extended namespace question mark. Existing connect/begin listeners, connection parameters and engine disposal remain intact.
- _unpack validates bytes, _validate_database and workspace identity before _references. Normal backup still checks the file before readonly validation. Worker locks, schema/integrity/identity checks, trusted_schema, reparse/hardlink checks and catalog writable behavior remain at their existing sites.
- _references still normalizes root with application_path; storage_root normalization and returned reference payloads are unchanged. In source=True mode, an unquarantined relative logical_ref is intentionally interpreted below the current root/protected. Therefore a complete legitimate copied workspace retaining relative references may pass; the removed expectation of FILE_REFERENCE_LOCATION was invalid. Absolute/mapped reference comparisons were not relaxed.
- No DTO/schema/dependency/UI/installer change, real Weixin/model access or storage/receipt prefix change was added.

## Standards

0 documented-standard violations / 0 actionable code-smell findings in the frozen source scope.

Sources: AGENTS.md, CONTRIBUTING.md, existing file_paths and operations module conventions, ponytail minimal complete change rules. The shared helper removes duplicated URI construction; the local callback comment explains a real URL-parser boundary demonstrated independently. No generic mode/config abstraction or global Database rewrite was introduced.

Manual diff review was supplemented by independent-ast-check.py, exit0: after explicitly normalizing the reviewed helper/imports/eight readonly expressions and local callback, all remaining structure in the seven product modules matches baseline. The catalog conditional's writable branch is retained by this comparison. This is a structural scope check, not a substitute for runtime tests or a full security proof.

## Verification evidence

| Evidence | Actual result | Interpretation |
|---|---|---|
| independent-boundaries-red.xml/log |8tests,6FAIL/2PASS,0errors/skips,exit1|Wrong-target filename/parent, native archive/identity and library deep URI failures; short special-character compatibility passed.|
| independent-boundaries-green.xml/log |8PASS,3.06s,exit0|Independent initial URI-boundary GREEN.|
| independent-final-green.json/xml/log |25PASS,0FAIL/errors/skips,pytest5.14s,harness5.828s,exit0|Fresh16unit+8boundary+1snapshot cases, source hashes stable. Root's repeated same cases are not additional unique tests.|
| root-original-verified.json/xml/log, independently read |1PASS,pytest6.10s,exit0,basetemp87characters|Original unchanged create/restore/rebackup integration case completes after both I/O fixes; not rerun by this reviewer.|
| root-targeted.xml |25tests,0failure/error/skip|Root's latest small-group receipt matches final independent case count.|
| root-reference-red.xml/log |1FAIL,actual SQLAlchemy unable to open|Valid second-boundary RED before local do_connect.|
| root-new-final.xml/log |24PASS/1FAIL|Retained invalid negative assertion expecting a relative-reference copy to fail; corrected in test only, not relabeled product PASS.|
| root-original-green.xml / root-original-final.xml |each1FAIL|Retained progressed/invalid raw extended URL attempts; these are not final GREEN receipts.|
| independent-engine-probe.json |exit0,338-character DB path|Actual Database session via local do_connect reads sentinel, preserves source SHA, foreign_keys1,busy_timeout15000 and portable storage_root.|

The original first RED root-repro.xml and helper-missing16FAIL root-unit-red.xml remain available. Early independent-boundaries-first/extended diagnostics remain separate from the formal6FAIL/2PASS RED.

Limits: root's broader affected regression/development checks and publication/synchronization were still pending when this source report was written; do not infer their outcome here. No full-suite rerun by this reviewer. Windows runtime exercised; POSIX runtime and network UNC I/O not exercised. General long-path writers, the separate WinError5/WIN-PATH-02 and native crash are not closed by this source review.


# Frozen-source review addendum: legacy upgrade fixture

Workspace D:\Documents\ChatGPT\律所项目; baseline916d55bf47ffb513508b81c5ebf40a5482372a67. Scope authorized by root after the final-native grouped run reported30PASS/58ERROR. The58 errors occurred at the shared legacy fixture's schema assertion, before each migration test body reached its product behavior.

## Baseline attribution

- The unchanged working-tree test was first run through controlled HEAD module interception before fixture editing:1ERROR/0FAIL,exit1,pytest2.02s. Seven modified product modules were supplied from exact HEAD source copies; all other imported product modules were audited against HEAD bytes.167 actual imported cn_contract modules matched; the full source manifest contained236Python files. Evidence: upgrade-fixture-baseline-first-red.json/log/xml.
- The same single current-tree case independently produced1ERROR at legacy fixture line37 before editing: upgrade-fixture-current-red.log/xml.
- The baseline harness was then made reproducible after the fixture edit by freezing the original HEAD test file itself. Repeating that immutable old test with actual HEAD product imports still produced1ERROR/0FAIL,exit1,pytest3.65s;167 imported modules again matched HEAD. Evidence: upgrade-fixture-baseline-red.json/log/xml. The false working_test_unchanged_from_baseline field accurately records the now-fixed working fixture; actual_test_path identifies the frozen old test whose bytes exactly match HEAD. Repeated attribution runs are not additional unique product test failures.
- Exact schema difference:161actual entries versus157frozen pre-intake entries,0missing. All four extras belong to weixin_descriptor_generations: its table, autoindex and two immutable triggers. Evidence: upgrade-fixture-diagnosis.json. There was no evidence that the SQLite path implementation caused this pre-existing fixture reconstruction error.

## Minimal fixture correction

Only tests/integration/test_workspace_upgrade.py changed: insert weixin_descriptor_generations as the first table in the legacy fixture's DROP tuple. This removes the newest versioned extension before its parent extensions and reconstructs the same fixed pre-intake structure that the existing assertion already required. The exact schema_rows('pre-intake',native=True) assertion and all test bodies remain unchanged. No expected schema snapshot or product code was edited for this correction.

upgrade-fixture-diff-proof.json proves the complete new file equals HEAD plus exactly that single byte insertion. Old SHA2566ea54f336c6bcb6909e15771a83cc446acaac7879d9ab6d986568578c9e10bad; new SHA256363522cae0c2e7120614c0953bfb424b294a9ba0d5fc194595b7fd882035d187.

## GREEN and review

Command: .venv\Scripts\python.exe -B -X utf8 .local\long-sqlite-20261025\upgrade-fixture-green-run.py. It runs the entire tests/integration/test_workspace_upgrade.py with an87-character basetemp and writes upgrade-fixture-green.json/log/xml.

Actual result:58PASS,0FAIL,0ERROR,0SKIP,pytest141.98s,harness144.297s,exit0. The58case IDs are recorded. These cases overlap the upgrade part of root's native88 group and must not be added again to the unique regression count.

Thirteen inputs were hashed before and after: the prior seven product files and three new tests, this corrected fixture, schema_baseline.py and storage_schema.py. All hashes remained stable; the previous10-file frozen review manifest still matches. The fixed schema implementation/snapshots are unchanged from HEAD.

Spec axis:0 actionable findings for the correction. It restores the fixture's explicitly documented fixed pre-intake starting state rather than widening accepted historical schemas. All58 original migration/recovery/tampering test behaviors then execute.

Standards axis:0 actionable findings for the correction. It is one table-list insertion in the existing fixture pattern, with a demonstrated baseline reproduction, unchanged expected schema assertion, actual full-module GREEN, and no product behavior change. The earlier independent-final-review.md source conclusions remain valid because its10 frozen file hashes did not change. This addendum is by the same reviewer, not an additional independent reviewer count.

Limits: no commit/push or real database/contract/model/account access by this reviewer. Root owns the final native88 recheck, remaining regression union, development gates and publication/synchronization receipts. The separate WIN-PATH-02/WinError5 and native crash remain outside this fixture correction.


## Final frozen product inputs

- src/cn_contract/domain.py: `f7b60f495e7805a8cc975e35b36595f38b31c1e1084d3856a2fe34261a1bc484`
- src/cn_contract/library/catalog.py: `9d460b0f8dcfbdbbab8ed797296fae74ed2bc1a03796eaee9208b454c0c8bbb9`
- src/cn_contract/library/service.py: `3d09ea0d3cd30307c88fece13eef0a2aa5a5d3e88d535d5003d46f271a5cd82b`
- src/cn_contract/ops/backup.py: `98a3b95cb0b2a441ee3fc993296f682602b2d86b289621fe76e228779fe82914`
- src/cn_contract/ops/file_paths.py: `d529bade41b7d0957fca2ea9ffdc5f96ecfbfbc827677108fcfb2d1261230a48`
- src/cn_contract/ops/workspace_backup.py: `0cebe362b20104388e4ec1c084d5fdae82bbcbd18a42dd23efc0160c82afc1ad`
- src/cn_contract/persistence.py: `484ed202bd64e20f60d8223275d77d1db905d9b053e2f157db925988386c41b8`
- src/cn_contract/web/local_server.py: `3d36840cce198cffbd714fbe632f4b461373a574a90158d795e579fdc53d2803`
- src/cn_contract/web/workspace_upgrade.py: `fee2f492245e32041bd63309daa669973a89dbe9879a423880572c384bfaeac7`
- src/cn_contract/weixin_inbox/accounts.py: `a2c493fbf799694d5eeda35f26577b6102916e628d2dc6092ec57c6e152b2bc5`
- src/cn_contract/weixin_inbox/dispatch.py: `e991919b6d20de81f6bb9fbfbd1cfb171e30f15760b4d80bde144d15978a907f`
- src/cn_contract/weixin_inbox/ingress.py: `b94faa85fdf9145d8d86a60272543176efc597ac5cc41776410160bbcf116f06`

Root final regression receipts are in verification-summary.json and final-*.xml. Independent receipt-reading and test execution scopes are recorded separately.
