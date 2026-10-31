# Task 1 independent review

Reviewed commit: `580b8a6bd92103db5c7678a0b47060e72e1a1b84`, base `9b2d801`. Scope: Task 1 only, SPEC and QUALITY. No product files, Git index or HEAD changed by this review. No subagents, real models, customer materials, credentials or Weixin connections used.

## Verdict

- **SPEC: FAIL** — one confirmed explicit-off preference lifecycle defect below.
- **QUALITY: CHANGES REQUIRED** — the same P2 defect; no additional actionable findings in the reviewed diff and named cross-call paths.
- Expanded Python suite remains **PENDING**, not PASS. At review time its log reached 76% with three failures; the implementation report identifies those earlier test expectation failures and separate repaired-test runs. This review does not reject the change merely because that suite is pending and does not count it as passing.

## Finding

**[P2] Restore the saved automatic-analysis preference when runtime is unconfigured** — `desktop/setup-model.js:123` (related `:78`, `:86`, `:99`; native path `desktop/main.cjs:149-157`, `:275-277`).

The approved design says automatic analysis defaults on but an explicit off must remain off. `reset()` now unconditionally checks the automatic-analysis checkbox, while `showRuntime()` restores its value only for a configured runtime. A normal credential replacement disables the runtime but deliberately preserves `model_auto_analysis: false`. Returning to the workbench does not restart/reconfigure that backend. When the owner reopens settings, the runtime is therefore unconfigured, the checkbox stays checked, and clicking the ordinary configure button sends `automaticAnalysis=true` and overwrites the saved off preference. The user never changed that checkbox back on. The same missing persisted-preference readback affects an unconfigured startup recovery.

Fix the preference/readback lifecycle so an unconfigured runtime can still initialize the checkbox from an explicit saved false; retain the default-on behavior only when no preference exists. Add the credential-change → leave/reopen settings → configure regression, alongside the already covered restart and configured model-switch cases.

## Focused reproduction

Reused `page()` from `desktop/tests/model-settings.test.cjs` in a standalone Node evaluation, with actual `setup-model.js` / `setup.js`, fake DOM, and synthetic API callbacks. No existing suite was rerun. Sequence:

1. Return configured Flash with automatic analysis off; checkbox is false.
2. Save a synthetic replacement credential; fake runtime changes to unconfigured; checkbox remains false in the current page.
3. Render ready, then render model-settings again; checkbox becomes true and configure is enabled.
4. Click configure; callback receives `['configure', 'deepseek-flash', true]`.
5. Assert callback's automatic argument is false: **exit 1**, one failed assertion, `true !== false`.

Actual output:

```text
{"afterCredentialChangeAndReopen":{"automatic":true,"configureDisabled":false,"runtime":"本次运行未配置模型。"}}
{"configurationCall":["configure","deepseek-flash",true]}
persisted explicit off should survive credential-change / settings reopen
true !== false
```

## Other reviewed requirements

- Main authorization DTOs require an explicit null or valid positive Decimal; missing and malformed limits remain invalid. Existing positive-policy JSON representation is unchanged and has a canonical-byte/hash regression.
- Shared `budget_exceeded` covers native ordinary/context/material/profile authorization, enqueue, claim, subsequent rounds, archive validation, and HTTP capability. Exact repository search found remaining direct comparisons only in independent Jev paths.
- Personal-Weixin nullable policy forwards to native material authorization without an additional numeric comparison; future global service-desk work is outside this review.
- Reservations, usage and unknown receipts remain recorded. Existing request identity, ownership, source/version/config binding, expiry and call count checks remain in place. Null changes only the monetary comparison.
- Jev DTOs/control continue to reject null and retain finite limits. No broadened Jev authorization was found.
- Display changes retain provider ID `deepseek-flash`. Legacy automatic-scope records accept the two known released reservation values; new Main grants use null without rewriting historical execution policy JSON.
- Existing ordinary positive-cap tests and new null/material/native/HTTP/round/archive tests support the implementation. Review relied on the supplied targeted results; full repository, installed desktop and real channel acceptance were not performed.

## Sources and boundaries

Primary sources: `.local/service-weixin-20261031/task-1-brief.md`, `docs/plans/2026-10-31-service-weixin-design.md`, `task-1-review-package.md`, `task-1-report.md`, `task-1-red-summary.md`, the fixed commit diff and the specific caller files cited above. Project standards: provided AGENTS.md, `sources/specification-v2.0.md`, `sources/upstream.lock.json`, `docs/TASK_STATUS.md`; latest approved unlimited-cost requirement supersedes the original finite-budget default. CodeGraph was used for the automatic preference call graph and source was checked against the current files. Obsidian search corroborated the approved project direction; unrelated/stale TencentDB results were not treated as current evidence.

No Task 2/3 feature review, publication, full-suite rerun, installation or live-model validation. This is an engineering review, not legal-quality or production acceptance.
