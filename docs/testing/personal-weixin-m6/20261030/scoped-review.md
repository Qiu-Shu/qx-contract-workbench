# M6 consolidated fix: scoped independent re-review

Base `cb39e3c178f987b81840ab2a53a2ecd9d9ba55f6`; frozen HEAD `e8e317f9abedbc33df3c58db1c1c66e40bd6b350`. Reviewed the supplied five-file diff, implementation report, original four findings and named adjacent boundaries. **Spec: PASS. Standards: PASS for this fix scope. No new Critical/Important finding.**

1. **Explicit attachment hold — ADDRESSED.** `src/cn_contract/task_drafts/service.py:19–29,259–273,319–329` recognizes bounded full-message hold/continuation forms and persists the existing paused state. Later files remain on the unique unexecuted draft; `personal_runtime.py:313` resolves their originals while paused. `advance` still executes only collecting drafts. Five meaningful tests cover punctuation, ordinary hold variants, plain pause/先别审, independent later batches, reconnect, selecting main without releasing hold, explicit continuation and duplicate replay.

2. **Reachable personal main selection/assignment — ADDRESSED.** `src/cn_contract/web/static/assistant-tasks.mjs:309–343` exposes existing main selection and same-binding assignment, preserving pending-choice protection. `task_drafts/service.py:434–470` retains ownership/revision checks and narrowly permits paused personal edits. `personal_runtime.py:368` resolves desktop-assigned material before execution. Tests reach actual mocked business/model output and fixed-peer reply in the same chat. Personal freeze/mock UI remains absent; the compatible internal nonsynthetic freeze and mock-bridge refusal are unchanged, as root directed.

3. **Same paused task resume and ambiguity — ADDRESSED.** `task_drafts/service.py:319–343` includes paused candidates and routes controls only to a unique unused draft. `assistant-tasks.mjs:335,342–343` supplies explicit desktop recovery. Tests cover paused+paused and paused+collecting ambiguity, retained unassigned files, explicit assignment, source preservation, necessary explicit pausing of the other runnable task, and eventual completion. No timestamp guess is introduced.

4. **Queued executor authority fence — ADDRESSED.** `personal_runtime.py:135–160` rechecks actual authority inside the worker before callback, closes only the captured invalid transport, consumes late exceptions and leaves database transactions before networking. Seven queue-saturation counterexamples cover logout, expiry, peer revocation, restore, target drift, config drift and epoch replacement; replacement transport stays usable and the unknown claim remains non-retriable after reconnect.

## Evidence and limits

Read raw `fix-red-python.log`, `fix-red-corrected.log`, `fix-red-node.log`, `fix-final-python.log` (**15 passed**), `fix-final-synthetic.log` (**2 passed**) and `fix-green-node.log` (**106 passed / 0 failed**). Initial14 RED includes two corrected test assumptions, not14 product defects. `fix-regression-python.log` proves **159 passed on earlier-source timing**, not exact-final coverage. Controller **28 checks** is implementer-reported; no named raw log was present. No suites rerun or additional probe needed.

Declined to judge: full regression after this commit, installation/upgrade, actual Weixin/model delivery, legal quality, production approval, unrelated WIP and the independently reviewed teammate frontend merge. This scoped PASS does not certify those gates.
