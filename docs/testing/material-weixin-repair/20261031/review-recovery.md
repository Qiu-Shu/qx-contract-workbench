# Recovery scoped re-review — `77464fe..5219299`

## SPEC

**PASS for the reproduced recovery defect.** Read the supplied `recovery-diff.txt`, `task-recovery-report.md` and `performance-diagnosis.md`. The correction is limited to the two frontend state boundaries and two relevant test files. No new submission, timer, backend operation, permission or timeout change is introduced.

- `src/cn_contract/web/static/assistant-state.mjs:310–312` marks an already accepted `material-business-v1` result as generation tracking before the first draft read. This supplies the state used by the existing entry polling, matching ordinary generation's acknowledged-registration treatment.
- `src/cn_contract/web/static/assistant-material-generation.mjs:30–31` returns false if draft refresh fails or the captured context is stale. It does not read history against the unrefreshed message page. The accepted registration has already cleared `pending`, so this read failure does not turn into another material POST or a lookup for an unconfirmed registration.
- `scripts/test_assistant_generation_entry.mjs:45–105` exercises the actual DraftController and the shipped `coordinateGeneration` function with `document.hidden=false`: business acceptance, native authorization, one material POST, one failed draft GET and the existing polling path. The ordinary generation control passes, while the unfixed material path fails. The fixed path retains later user input, obtains saved output, performs no second POST or request lookup and stops tracking when complete.

## QUALITY

**Approved. No Critical, Important or Minor source finding in this fixed correction.** The change repairs the existing state handoff instead of creating a second recovery mechanism.

Named-risk checks, limited to the enclosing existing call paths:

1. **Accepted result accidentally becomes an unknown write or resends.** Read the surrounding material `accept`/`refresh`/`send` flow. Receipt identity/format/revision validation still precedes `host.accept`; `pending` is cleared only after proven acceptance. The added early return leaves no submission pending, and the existing poll is GET-only. The separate unknown-POST reconciliation behavior remains covered in `scripts/test_assistant_material_generation.mjs:57–65`; the new test at `:67` checks that failed draft read neither triggers history nor leaves an unknown write.
2. **Tracking gets lost before the existing poll can run.** Checked `assistant.mjs:93–124` and `assistant-generation.mjs:137–166`: the entry schedules its existing 2-second poll for tracking; the material correction now establishes tracking before the refresh can fail, and avoids the immediate stale history call that could replace it. Successful later draft/history reads clear tracking once the output is terminal. Hidden-window polling behavior is unchanged.
3. **Recovery overwrites new text or restores revoked/old data.** Checked `assistant-state.mjs:254–275` refresh and epoch/authorization handling plus material token checks. Existing dirty-text preservation and current-context checks remain. New visible-poll tests explicitly preserve text entered after the failed read and verify both authorization failure and a delayed GET after revocation leave the identity cleared and outputs absent (`test_assistant_generation_entry.mjs:107–130`). The host tracking update is restricted to the material result format, so ordinary business acceptance is not reclassified.

## Evidence

- Independently read `recovery-red.log`: **11 tests / 10 passed / 1 failed**, with the material assertion observing `error` instead of `tracking`; ordinary generation was the passing control. This is a product-state assertion, not a fixture setup failure.
- Independently read `recovery-regression.log`: **55 top-level Node results passed**, zero failures/cancellations/skips/todo, **112.9571ms**. The 36 generation groups, 6 attachment groups and 32 draft checks inside legacy scripts are included, not additional cases. No warnings were present in the retained final summary/report.
- The intermediate 17-pass run overlaps the final gate. Command exits are documented as 1 for RED and 0 for the final gate by the implementer; this reviewer did not rerun either suite.
- These tests use API fixtures and the actual controller/coordinator, not an actual browser, backend or model. They prove the scoped visible-window recovery state transition, not the latency or precise cause of the earlier package failure.

## Acceptance status and limits

**Known reproducible source gap closed; rebuilt package acceptance still pending.** The original hidden-window scene cannot by itself prove the visible-window cause: `document.hidden` intentionally suppresses polling. The corrected old-run readback reportedly displayed the saved output and exported Word with zero new model calls; that is root-provided evidence, not a new run by this reviewer. The first request's timeout and possible performance amplification remain unproven causes and were not repaired or attributed here.

This approval covers the reproduced **first draft GET fails after confirmed material acceptance** seam. It does not claim every repeated transport failure, unrelated history failure or hidden-window lifecycle is newly covered. No broader recovery requirement or new defect was inferred from unchanged code.

Keep the final integration readiness gate open until root's visible rebuilt-package test injects the one GET failure and demonstrates the saved result appears through the same-chat UI without duplicate model submission. The planned new fictional acceptance task is distinct from resending an old unknown request. Phone scan, inbound message, model response and delivery remain separate pending gates. This scoped PASS does not yet make the package ready to install.

No subagents, test reruns, model/network requests, product/index edits or user-file operations were performed. Only this review report and the authorized local project-memory summary were written.
