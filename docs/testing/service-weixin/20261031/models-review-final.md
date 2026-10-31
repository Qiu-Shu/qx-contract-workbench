# Task 1 scoped final re-review

Reviewed repair: `580b8a6..f8859123adc67066070f2cea5215e4e143162326`. This follows the initial Task 1 review of `9b2d801..580b8a6` and checks only its single P2 and the repair's IPC/state effects.

## Verdict

- **SPEC: PASS for the reviewed Task 1 implementation.** The sole prior P2 is addressed.
- **QUALITY: PASS for this scoped review.** No remaining actionable defect identified in the repair or its named caller paths.
- These are code-review conclusions. The expanded Python group's final result remains pending; it is not counted as PASS. No Task 2/3, installation, live model/Weixin or legal-quality acceptance is implied.

## Finding disposition

| Prior finding / repair obligation | Disposition | Evidence |
| --- | --- | --- |
| P2: explicit automatic off becomes on after credential replacement, leave/reopen unconfigured settings, then configure | **ADDRESSED** | `desktop/main.cjs:268-272` projects the saved preference when unconfigured; `desktop/model-settings.cjs:15-17` preserves that boolean; `desktop/setup-model.js:70-71,79-80` reads it into the checkbox. Integrated focused reproduction now configures with false and leaves persisted false intact. |
| Default-on behavior when preference is absent | **ADDRESSED / preserved** | Same existing `automaticAnalysisEnabled` helper; no new preference store or changed default was introduced by the repair. Existing affected-suite evidence includes default/restart/model-switch cases. |
| Settings IPC permission and state isolation | **ADDRESSED / preserved** | Existing `isAllowed`, pending-operation lock, captured guard, pre/post-operation checks and state/model projection validations are unchanged. Focused reproduction confirmed wrong UI mode and wrong sender are `ACCESS_DENIED`; no preference is returned in the denied-mode response. |
| Jev settings independence and unavailable runtime | **ADDRESSED / preserved** | Preference projection is restricted to successful Main settings results in configured/unconfigured states; unavailable remains unchanged. Focused reproduction confirmed Jev runtime status has no automatic preference. |

**NOT ADDRESSED items: none within this review scope.**

## Independent focused check

One standalone Node probe reused the existing navigation `fixture()` and page `page()` test helpers. It joined the actual main-process settings wrapper, registered settings IPC handlers, and actual setup renderer through the fake DOM/backend, instead of injecting a hardcoded preference into the page. It used a separate temporary synthetic settings directory, checked its resolved parent/name before cleanup, and accessed no real settings or credentials.

Sequence: configured/off → synthetic credential replacement → verify persisted false → leave settings without backend restart → verify runtime-status denied in ready mode → reopen settings → verify actual IPC returns unconfigured/false and checkbox false → verify wrong sender denied and Jev preference absent → configure through actual IPC → verify callback false and persisted false.

**Actual result: exit 0**, one focused end-to-end synthetic scenario with permission and Jev projection assertions:

```text
{"scenario":"explicit off -> replace credential -> leave/reopen unconfigured settings -> configure","status":"PASS","configurationCall":["configure","deepseek-flash",false],"persistedAutomatic":false,"wrongMode":"ACCESS_DENIED","wrongFrame":"ACCESS_DENIED","judgeHasAutomaticPreference":false}
```

## Other evidence and boundaries

Read the fixed commit diff and `.local/service-weixin-20261031/task-1-review-fix-package.md`, the updated implementation report, and raw repair log tails. Implementer evidence: three targeted RED failures before repair, then **93 passed / 0 failed** across six affected test files after repair; schema/diff checks reported exit 0. The reviewer inspected those results and did not rerun their suites. The earlier 412-test desktop run belongs to `580b8a6`, not a complete desktop rerun on `f885912`.

The original expanded Python run is still tracked separately and must retain its actual final result, including earlier test-expectation failures and separately verified repairs. This pending run does not reopen the resolved P2 and is not represented as passing here.

Only this report was added. Product source, Git index/HEAD, real model/profile/Weixin state and Task 2/3 were not changed; no subagents were used.
