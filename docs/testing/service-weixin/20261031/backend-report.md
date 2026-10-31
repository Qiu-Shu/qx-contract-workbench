# Task 2 backend implementation report — candidate for independent review

Workspace: D:/Documents/ChatGPT/律所项目
Branch: codex/contract-review-v2; base: 58a67f1. Candidate commit: a42646106d41dde43865228b55fc63db8764b285.
Status: candidate independently reviewed; four findings fixed in review round 1; limited re-review pending. No Task 3 frontend work performed.

## Delivered scope
- Workspace/owner/session-scoped service connection with native start/verify/disable and authenticated global status/QR. Independent poll and 0.2s collector implement 5-second silence without long-poll delay; explicit hold/continue, acknowledgment, late material versions, target draft/busy fences, per-target authorization and original-context reply are retained.
- Durable events, unassigned originals, batch revisions, clarification answers, exact business/task/model-source links, immutable complete poll/cursor journal, and once-only outbox in the SAME database. New schema weixin-service-v1 has 90 tables, additive to all 81 predecessor tables. No legacy fixed-chat records or old object SQL/hashes reinterpreted.
- Actual attachment registration/parse → existing business.submit → existing configured Main provider/task manager → original-event outbox. Four workflows are routed through existing material workflow machinery. Synthetic tests use fake Main and actual JevProvider with fake HTTP transport; no real calls.
- SharedJudgeService uses desktop_entry's configured JudgeRuntime/provider, with separate owner/session/scope/config/input claims, minimal input, once-only unknown state and stale result discard. No extra credential storage/platform. Task 3 must restore existing saved Jev config through the existing native command.
- New versioned qx-jev-service-intake-v1 actually calls four fixed Jev questions in one request BEFORE routing: readiness, existing/new relation, workflow (including court), material_kind. Explicit user routing wins; ambiguous multiple matters still clarify regardless of confidence. Primary-intent fallback and parsed material classification also reuse same provider. Legacy purpose/template/hash unchanged. Desktop shared endpoint accepts service_intake but desktop Enter remains explicit (consume only workflow/material suggestions).
- Expanded all relevant schema acceptance/integrity/upgrade/backup paths; no new assets requiring static resource registration. Existing Python imports connect packaged runtime.

## Meaningful verification evidence
Commands use .venv/Scripts/python.exe -m pytest; all data/credentials/transports synthetic.
1. Initial routing RED: missing service_routing import, one collection error, exit 1; then routing 3 passed. Initial integration groups were expanded incrementally; intermediate results are not final-source evidence.
2. Early old runtime/routing regression: 72 passed, 2 failed, exit 1, 250.65s. Old hardcoded current-version assertions updated; superseded by targeted final checks below.
3. task-2-service-final.log: 21 passed / exit 0 / 44.78s, after new four-question Jev scope and 90-table schema. Subsequent source change removed redundant primary-intent call when intake already supplies workflow.
4. task-2-final-targeted.log: 110 passed / exit 0 / 47.84s, on frozen implementation source. Includes all new 21 service/routing/Jev tests, legacy Jev codec/routing, personal desktop, and legacy runtime exact-schema/migration/status tests.
5. task-2-regression.log: 339 passed, 2 failed / exit 1 / 415.70s. This run started before final source updates; NEVER represented as final all-green. Both failures are test_weixin_personal.py legacy schema expectation excluding only two old additions. Full original failure log preserved.
6. task-2-personal-schema-red.log: independently reproduced the same 2 failures on latest schema. The shell wrapper subsequently displayed the file and returned 0; pytest result itself is 2 failed (6.69s). Test now excludes exactly the new service_schema registered table objects, preserving comparison of every predecessor object's SQL outside the original two CHECK changes. Separate test checks ALL 81 immediate-predecessor tables/objects unchanged.
7. task-2-backup-schema.log: 3 passed / exit 0 / 15.52s. Both corrected native/non-native migration tests plus actual MockTransport download of three 20MiB originals → >50MiB workbench.db → create_workspace_backup → restore_workspace_backup → full service integrity and exact bytes/hash checks.
8. task-2-regression-final.log: 344 passed / exit 0 / 425.73s. Started from a426461 and overlapped later source/test fixes; NOT pure frozen-commit evidence. Final repaired-source evidence is the dedicated 113-test group below. Command covers full test_weixin_personal_runtime.py, test_weixin_personal.py, test_weixin_personal_desktop.py, test_weixin_service_runtime.py, test_weixin_service_routing.py, test_shared_judge_service.py, tests/unit/test_jev_codec.py, test_jev_contract_routing.py, test_jev_provider.py, test_native_judge_authorization.py, test_assistant_judge_upgrade_backup.py. The actual count is 344, replacing the earlier estimate of 342.
9. git diff --check exit 0. Original tracked source line endings restored; no unrelated whole-file newline diffs.

## Concrete persistence choice / bounds
Unassigned original bytes are immutable same-DB BLOBs (20MiB per media, 20 media per pending batch) so restart does not lose a file before business identity exists. After assignment the existing protected attachment store is reused; original intake BLOB stays immutable for evidence. This increases database size. Actual desktop workspace_backup has identical create/restore 512MiB per member and 2GiB total limits; the >50MiB probe passes. The older ops.backup synthetic-only format has 50MiB per member but explicitly refuses service records via allow_assistant=False; it is not the desktop service backup path. No limits broadened.

## Scope / limits for reviewer and Task 3
- Pending intake persists, but disconnected global status omits batch listing until authenticated reconnect; persistent history is not deleted.
- Reply context capabilities are intentionally ephemeral. After restart, without original source-context redelivery, completed result remains on desktop with an explanatory notice; no guessing current context/recipient and no unknown resend.
- Jev availability reports configuration, not live credential validity. No Chinese accuracy guarantee/calibration performed. Fixed jev-1.13.0 retained. No real TypeSafe/DeepSeek/Weixin requests or stored credential/profile reads.
- No UI interaction, production upgrade, installation, deployment, or Task 3 JS edits. Current user-installed runtime untouched. Parent performs independent review and installation safety gate.
- User WIP docs/TASK_STATUS.md (4 lines) and unrelated untracked docs preserved, excluded from commit.
- Exact Task 3 contract: task-2-interfaces.md. All source changes are reviewable in task-2-review-package.md.


## Independent review round 1 — four confirmed findings addressed
Source: task-2-review.md, candidate a426461. Repair commit: 82e0e7bf5699feb81754356c29f9204a7888da62. No schema/API changes; only service routing/records/runtime and associated runtime tests.

1. P1 explicit readiness: one interpreter recognizes negative wait clauses inside longer instructions, supported completion/start phrases release held state, latest explicit message wins earlier holds, and explicit start cannot be changed to wait by Jev. Real loopback Jev tests return opposite readiness suggestions for both directions; no Main during hold and exactly one after release.
2. P2 clarification new matter: the offered bare new-matter answer is appended to the existing clarify batch before normal split logic. Actual two completed matters + ambiguous file + answer creates one new execution with all three original-batch events; later separate detailed new-business requests still split.
3. P2 selection crash: read existing immutable selection receipt; reconstruct its pre-selection materials revision while preserving other current scope fields, and pass the exact request through the existing receipt hash check. Changes to other scope or current material revision still conflict. Injected failure AFTER real select_materials commit then normal retry executes Main once and creates one run link.
4. P2 original completeness: compare exact event/media declared pairs with persisted original rows, then validate existing hashes. Deletion under temporarily removed triggers (restored exact SQL) now raises SERVICE_MEDIA_INTEGRITY. Existing full archive restore and the 3x20MiB restore remain covered.

RED/GREEN evidence:
- pytest tests/integration/test_weixin_service_runtime.py -k test_review -q: task-2-review-red.log, 5 failed / exit 1 / 10.68s. Four scenarios reached their intended bug assertion; initial clarification fixture used empty conversations that correctly do not count as matters, so its failure was a fixture defect and not claimed as valid bug RED.
- Corrected clarification setup executes two existing matters. Temporarily loaded only a426461 service_records.py for this probe and restored repaired bytes in finally. pytest tests/integration/test_weixin_service_runtime.py::test_review_new_matter_clarification_keeps_original_files -q: task-2-review-clarification-red.log, 1 failed / pytest exit 1 / 4.96s at expected Main count 3 vs actual 2. Script reports pytest exit 1 and itself exits 0 after restoring source. This is the valid second-finding RED.
- Intermediate task-2-review-green.log: 4 passed, 1 failed / exit 1 / 10.27s; remaining failure was the empty-conversation fixture just described. Preserved, not called final green.
- Final repair-source group: .venv/Scripts/python.exe -m pytest tests/integration/test_weixin_service_runtime.py tests/integration/test_weixin_service_routing.py tests/integration/test_shared_judge_service.py tests/unit/test_jev_codec.py tests/unit/test_jev_contract_routing.py tests/integration/test_weixin_personal.py::test_schema_expands_only_two_checks_and_preserves_historical_objects tests/integration/test_weixin_personal_runtime.py::test_exact_successor_migration_preserves_every_predecessor_object -q
  task-2-review-green-final.log: 113 passed / exit 0 / 75.42s. Implementation source was unchanged during this final group; only original line endings subsequently normalized. Includes all five review regression scenarios, service execution/backup/source-fence cases, actual configured Jev transport, routing, codec/hash compatibility, native/non-native prior migration, and exact 81-table predecessor preservation.
- Long overlapping group completed 344 passed / exit 0 / 425.73s. Because some modules/subprocesses can load lazily during repairs, treat as supplementary regression, not pure a426461 or repaired-HEAD verification. No full broad rerun merely to replace this count.
- git diff --check exit 0 after fixes. UI/production runtime/user WIP remain untouched.

Re-review scope: a426461..repair HEAD; task-2-review-fix-package.md contains log/stat/full -U10 diff. No live provider/Weixin calls or stored credentials accessed. Remaining limitations in previous section continue to apply.


## Independent review round 2 — negative/conditional release
Source: task-2-review-final.md (retained unchanged). All four original findings were addressed by round 1; review found a new P1 where positive substring matching released held batches for negative readiness.

Confirmed/repaired: positive release now requires an affirmative clause. Negative, conditional and interrogative start/completion checks run first. Other recognized readiness mentions retain a wait. The same control/readiness functions still serve intake state changes and explicit-user precedence over Jev, and the later explicit event remains authoritative. Material readiness, selection receipts, source fences and API/schema were not changed. Regression includes “现在还不可以开始”, “尚未发送完毕”, conditional completion, later valid release, opposite Jev advice, and separate conditional clauses. Root's disconnected workspace bootstrap observation remains assigned to Task 3.

Exact evidence (all commands prefixed .venv/Scripts/python.exe -m pytest):
- tests/integration/test_weixin_service_routing.py tests/integration/test_weixin_service_runtime.py -k 'negative or conditional or affirmative' -q → task-2-review2-red.log: 13 failed, 8 passed, 20 deselected / exit 1 / 7.53s. Includes three actual held+synthetic-file runtime reproductions that incorrectly called Main.
- tests/integration/test_weixin_service_routing.py tests/integration/test_weixin_service_runtime.py tests/integration/test_shared_judge_service.py -q → task-2-review2-green.log: 48 passed / exit 0 / 61.97s. This covers the FIRST round-2 revision, before additional comma-separated conditional fixes, and is not presented as final-revision proof.
- tests/integration/test_weixin_service_routing.py -q → task-2-review2-conditions-red.log: 2 failed, 21 passed / exit 1 / 1.12s, exposing “等材料到齐，可以开始” and “材料发送完毕后，可以开始”. Added conditional precedence fixes.
- Same three-file command → task-2-review2-green-final.log: 50 passed / exit 0 / 58.60s. Despite its filename, this group overlaps the later short conditional repair; it is supplementary evidence, not final frozen-source proof.
- tests/integration/test_weixin_service_routing.py -q → task-2-review2-conditional-short-red.log: 1 failed, 23 passed / exit 1 / 1.07s for “等我发完，再开始”. Broadened only the conditional readiness signal from fixed positive phrases to start/completion terms.
- FINAL FROZEN REVISION: tests/integration/test_weixin_service_routing.py tests/integration/test_weixin_service_runtime.py -k 'readiness or negative or conditional or affirmative or hold_greeting' -q → task-2-review2-final-readiness.log: 27 passed, 17 deselected / exit 0 / 11.42s. This final narrow group includes all newly added negative/conditional cases, supported positive releases, latest explicit event precedence, held runtime → negative instruction → later positive release → exactly one Main call, and both existing real fake-transport Jev precedence cases. No implementation/test edits after this run except restoring exact unchanged-line endings.
- git diff --check exit 0. No broad compatibility suite repeated in round 2. User WIP, frontend, installed runtime and original round-1 review-final report untouched.

Round-2 commit and review package follow: task-2-review-fix2-package.md contains exact 82e0e7b..HEAD log/stat/full -U10 diff. Awaiting limited re-review; no live models, Weixin, credentials or real profiles accessed.

Round-2 commit: 3740816fccaddc23e68e22e5f0314b69b5fda19f (3 files, 55 insertions, 3 deletions).
