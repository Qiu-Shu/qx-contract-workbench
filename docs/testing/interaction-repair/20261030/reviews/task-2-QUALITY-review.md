# Task 2 QUALITY review

Current result: **PASS after Q1 correction `cc1b1f5`**. The focused rereview of `c739c7b..cc1b1f5` is recorded at the end. No remaining QUALITY finding in that correction; root may continue Task 3 under its existing scope. This does not approve packaged/live operation.

Original result: **CHANGES REQUESTED — one independent P2 regression**. Reviewed fixed range `88bb75e..aed6d575caa1c95013216757276d780b7e63e11c` (19 files). No product edits, installs, network/model/Weixin operations or broad suite reruns. The initial review did not include later fixes or Task 3. The SPEC review's separately reported delayed-send intent problem is not duplicated below.

## Q1 — P2: preserve a file selection returned while autosave is running

Changed location: `src/cn_contract/web/static/assistant-materials.mjs:71`, with the unconditional input clearing at line 154. `enqueue()` now returns whenever `busy()` is true, including ordinary `saving`; the change handler still clears `event.target.value` without reporting the rejection.

Reproduction ordering: open a permitted file picker while the draft is idle; the already scheduled draft autosave enters `saving`; return the chosen file before that save completes. The new guard discards the selected files, and the handler clears the picker. When saving finishes, the queue is empty and the material notice is empty. A subsequent send therefore has no selected attachment, despite the user's completed selection. Disabling the input after the picker has opened does not constitute preservation of its eventual result.

This is a newly introduced queue regression, independently reproduced using the existing minimal DOM fixture and real draft controller, with delayed mock save completion. The same one-case probe passes with all imported product modules frozen at `88bb75e` and fails with modules frozen at `aed6d57`. This is controlled event-order evidence; I did not claim to have exercised a native Windows file dialog. All material and draft data were fictional.

Recommended fix: retain a valid delayed selection during ordinary autosave, or preserve it with an explicit recoverable notice, while keeping revoked, changed-conversation, readonly and active-upload boundaries. Add coverage for **save starts before picker change**; the existing final autosave test only covers **queue exists before save starts**, so its success cannot detect this loss.

Targeted commands, run from `D:/Documents/ChatGPT/律所项目`:

- `node --test --test-reporter=tap .superpowers/sdd/2026-10-30-workbench-interaction-repair/task-2-quality-probe/scripts/quality-picker-autosave.mjs` — exit **1**, one test / one failed assertion, zero setup errors. Captured final state: `status=saved`, `queued=false`, `pickerValue=""`, `notice=""`. Raw log: `task-2-quality-picker-autosave.log`.
- `node --test --test-reporter=tap .superpowers/sdd/2026-10-30-workbench-interaction-repair/task-2-quality-probe-base/scripts/quality-picker-autosave.mjs` — exit **0**, one test / one passed. Same event ordering, `queued=true`. Raw log: `task-2-quality-picker-autosave-base.log`.

Each probe directory contains a copy of the fixed fixture plus its recursively imported modules obtained with `git show <commit>:<path>` (12 source files). The extra probe is ignored local review evidence, not a product test or committed source change.

## Other reviewed boundaries

- Native plain/material/profile/context approvals retain trusted captured identity, two exact snapshots, scope/composer/source/basis checks, cookie recheck after ACK and the existing runtime's one-use 120-second budget lease and cleanup. The removed popup does not add an optional Judge grant. Updated native tests inject identity/session/material changes at the first snapshot cookie recheck; this still exercises the race boundary without needing the removed dialog. No additional native authorization defect found in this fixed diff.
- Material batch writes continue through the controller's single save channel; unknown receipt reconciliation retains request identity and does not silently resend model work. Conversation/revocation invalidation and preview epochs remain. Queue-before-autosave, unknown uploads, duplicate Enter/submit and IME are covered, but the reverse picker/autosave ordering above was missing.
- Weixin Connect waits for the active native status read, rechecks status before starting, requires a saved conversation and serializes writes. Same-chat paused reconnect requires disable plus a confirmed empty status; another conversation's connection is not silently adopted. Epoch checks suppress late responses after identity changes. Incoming refresh is guarded against local pending work and is read-only; no additional independently demonstrated connection concurrency defect found.

## Verification evidence and limits

Independently read the retained raw log summaries: native **401 passed**, renderer **452 passed**, final material **21 passed**, and D: context retry **14 passed**. The original Python log has **195 passed / 13 fixture errors**, all listed as context setup failures at `LIBRARY_DISK_BUDGET`. The D: retry covers those 13 plus one overlap; **208 distinct passing tests across two runs** is the report's appropriate combined count, not a successful original single invocation. Reported command exits and source timing remain attributed to the implementer's report; this reviewer did not rerun those gates.

Only the two one-case fixed-snapshot probes above were executed by this reviewer. Actual packaged UI, native file-dialog timing, real provider dispatch and external Weixin login are not established by this review. Root's later end-to-end gates remain separate. Overall Task 2 is not approved until Q1 and the separate SPEC finding are resolved and the changed boundaries are rechecked.

## Q1 focused rereview — `c739c7b..cc1b1f5`

**PASS; Q1 closed.** Read the exact two-file correction (`assistant-materials.mjs` and its DOM tests), the report's QUALITY supplement and retained RED/GREEN/current-probe logs. No product file was edited and no test suite was rerun for this rereview. `git diff c739c7b cc1b1f5 --check` returned exit 0. Current materials/state/composer files had no uncommitted differences when the reused-current-probe imports were checked.

- Ordinary `saving` is excluded from the queue rejection guard, while upload controls remain disabled. The initial conversation's own create path does not set loading or invalidate the picker epoch; a selection queued before create completion survives the null-to-created identity transition. It is retained locally and is not automatically uploaded by save completion.
- The click captures `selectionEpoch`. Actual conversation navigation enters loading and invalidates it; moving from an existing conversation to a new conversation changes identity and invalidates it as well. The change handler rejects a mismatched epoch with a reselect notice. Ordinary same-conversation saving does not invalidate it.
- Readonly, revoked, loading, conflict, material-action and active-upload guards still reject selection. Revocation also invalidates the captured epoch. The six added cases use real controller save/create/open/revoke paths and a deferred upload, rather than simply asserting the new branch text.
- Raw `task-2-picker-red.log` confirms **31 tests / 28 passed / 3 failed**: existing-chat saving selection, initial autosave/create and stale foreign-chat selection. Raw `task-2-picker-green.log` confirms **38 tests passed / 0 failures**, including the relevant material/controller/input checks. These are overlapping gates, not additive distinct counts.
- `task-2-quality-picker-current.mjs` retains the reviewer's original one-case fixture with imports pointing to the actual shipped modules. Its retained raw log confirms **1 passed**, with `saved`, `queued=true`, empty picker value and no error notice. This execution was performed by the implementer; this reviewer independently read its source and log, without rerunning it.

The original Q1 failure remains in the frozen snapshot evidence above; the correction and its scope are now independently accepted. The separate SPEC correction at `c739c7b` was already approved by its reviewer (root-provided status); it is not re-reviewed here. Native Windows picker timing and packaged/provider/Weixin end-to-end checks remain root-owned gates, not implied by this PASS.
