SPEC PASS
QUALITY PASS

Scope: Task 3 only, BASE 3740816fccaddc23e68e22e5f0314b69b5fda19f → HEAD b2f04b8aaaa50bc9c6a08dbc9704a51abb4e9b86. No blocking new defect identified. This gate does not certify a packaged application, live account, credential validity, legal accuracy, or production readiness.

Verified integration and strengths

- Global entry is inside the sidebar before business abilities (`src/cn_contract/web/templates/assistant.html:34`). Native start uses authenticated workspace bootstrap, with no conversation creation or renderer-supplied identity/policy (`desktop/personal-weixin.cjs:20`, `:37`, `:82`). Disconnected bootstrap exists both before service construction and after disabling (`src/cn_contract/weixin_inbox/personal_runtime.py:543`, `src/cn_contract/weixin_inbox/service_runtime.py:70`).
- Service-only capture preserves same-workspace navigation while ordinary Main/Jev approval capture retains document epoch and exact URL checks (`desktop/main.cjs:323`, `:340`). Session token and actor are rechecked around status/start/verify, workspace/backend identity is retained, late start/verify ACKs retire the captured backend (`desktop/personal-weixin.cjs:20`, `:31`, `:95`, `:108`). Logout explicitly disables before the logout POST; navigation to login invalidates the service (`src/cn_contract/web/static/assistant.mjs:323`, `desktop/main.cjs:234`).
- Shared Jev restoration uses the existing store and fixed supported model, honors explicit false, and does not advertise live credential verification (`desktop/model-bridge.cjs:52`, `desktop/main.cjs:108`). Jev persistence failures disable Jev through its own runtime (`desktop/main.cjs:294`), with a final fixture proving Main remains configured.
- Desktop assistance calls the existing authenticated `service_intake` endpoint. Request/response ScopeSnapshot and ServiceJudgeResult match the Task 2 contract; shared provider authorization, current session/owned conversation, revisions, and unknown-claim ledger remain in that service (`src/cn_contract/web/static/assistant-api.mjs:102`, `src/cn_contract/weixin_inbox/personal_runtime.py:571`, `src/cn_contract/assistant/shared_judge.py:27`). No second frontend routing/persistence store was introduced.
- Automatic OFF skips Jev. Duplicate Enter is blocked while intake waits; edits including retyping, conversation reset, changed scope/composer revision, and foreign results invalidate pending suggestions (`src/cn_contract/web/static/assistant-state.mjs:347`, `:364`, `:431`, `:456`). Desktop submission ignores readiness/relation; explicit skill/context/task choices retain priority, and confident suggestions supplement unresolved local routing (`src/cn_contract/web/static/assistant-state.mjs:370`, `src/cn_contract/web/static/assistant-business.mjs:75`). Material classification remains a suggestion with its captured scope and a visible verification qualifier (`src/cn_contract/web/static/assistant-state.mjs:367`, `src/cn_contract/web/static/assistant.mjs:79`).
- Batch changes refresh the existing list; relevant selected conversations use existing conflict/pending guards. Activity links invoke existing guarded open behavior. No poll-triggered navigation or composer overwrite was added (`src/cn_contract/web/static/assistant-weixin-personal.mjs:65`, `src/cn_contract/web/static/assistant.mjs:216`). Explicit disconnect remains once-only and background reads do not mark actions busy (`src/cn_contract/web/static/assistant-weixin-personal.mjs:37`, `:72`).

Findings

- Critical / Important: none identified in the reviewed task.
- Minor, deferred by brief: detector evidence retains four pre-existing hover-contrast warnings (#768078 on #f3f1f7; detector reports template line 0, not a precise source location). Do not claim a zero-warning accessibility audit. The fifth warning is the deliberately initially source-less QR image (`src/cn_contract/web/templates/assistant.html:48`); its authenticated source is assigned only for scanning (`src/cn_contract/web/static/assistant-weixin-personal.mjs:45`). Browser evidence confirms it loaded. No redesign requested.

Evidence checked, not rerun

- `task-3-desktop-final-green.log`: 418 tests, 418 pass, 0 fail.
- `task-3-frontend-final-green.log`: 481 tests, 481 pass, 0 fail.
- `task-3-python-final.log`: 52 passed, 16 deselected, 86.03s.
- Warning-pattern search across these three final logs returned no matches.
- `task-3-browser-confirm.log` and `ui/report.json`: synthetic component fixture at 1280/860/360, no page overflow or page errors, zero external requests, preserved draft, keyboard verification including leading zeros, zero background disabled toggles, one explicit disconnect.
- `task-3-design-detect.json`: 15 advisories and 5 warnings, as described above.

Limits and controller checks

- Browser harness deliberately supplies a fake bridge and forces `sidebar-open`; it is not full assistant bootstrap, native IPC/backend integration, packaged restart, or a closed/compact-sidebar visual acceptance. Root's packaged/real-app synthetic acceptance remains required. No live API or genuine user profile was accessed for this review.
- Task 1 budget/legacy digest behavior and Task 2 ordering, persistence recovery, routing accuracy, and outbox behavior are cross-task responsibilities. This review checked the Task 3 interface integration and relevant existing guards, not those entire subsystems again.
- Changed filenames in the brief were candidates, not mandatory edits; no missing-file defect is inferred from unchanged preload or DTO files.

Reviewer commands and focused reads

- Read brief/report/final Task 2 interface/reviewer template with PowerShell `Get-Content`; read the supplied review package, then recovered only clipped ranges after tool-output truncation. No git command was run.
- Used `rg -n` on the named changed files to locate exact call sites. Named risk checks: save/create/refresh and business routing priority (`assistant-state.mjs`, `assistant-business.mjs`); list/open/logout and native login invalidation (`assistant.mjs`, `main.cjs`, bridge tail cut off in package); shared-intake DTO/route/provider guard and CSRF/transport timeout (`domain.py`, `personal_runtime.py`, `assistant/shared_judge.py`, `assistant-api.mjs`); existing model-session workspace/automatic policy projection; compact sidebar selectors (`assistant.css`).
- Two guessed shared-Jev paths did not exist; located the actual file with `rg --files src/cn_contract | rg 'judge|shared'`. This was filename discovery, not a repository crawl of file contents.
- Read final log tails, browser JSON and detector JSON. Read/inspection shell batches completed with exit 0; nonexistent-path diagnostics and no-match warning searches were inspected, not treated as successful test evidence.
- Ran no test suite or synthetic probe: no remaining concrete doubt required execution. No source, Git, profile, or original WIP was changed. Only this requested ignored report was written.
