# Task 3 implementation report — 2026-10-31

Status: implemented and committed for independent root review. No packaging/install/push. Engineering fixtures only; no real model/Weixin calls, keys, profile or legal materials.

BASE: `3740816fccaddc23e68e22e5f0314b69b5fda19f`
HEAD: `b2f04b8aaaa50bc9c6a08dbc9704a51abb4e9b86`
Commit: `feat: connect global Weixin service and shared desktop Jev intake`

## Behavior and scope

- Personal Weixin panel moved into the global sidebar before business abilities. All existing `personal-weixin-*` IDs retained. Added `personal-weixin-judge`, `personal-weixin-batches`, `intake-material-suggestion`. Existing component, typography, warm palette and native details/forms remain.
- Native start now reads the authenticated global workspace UUID and sends `session_token,workspace_id,automatic_policy`. Empty chat is valid; no conversation create/save or dummy CID. Model-control supports both new service and legacy payloads, strictly rejecting mixed authority.
- Bootstrap supplies `workspace_id` on authenticated global disconnected status, both before service construction and after disabling. Only minimal runtime/route changes; no persistence or DTO redesign.
- Service capture guard belongs only to this bridge: current authenticated cookie/actor, native window/main frame, workspace/backend identity, valid assistant page and native policy stay required. Same-workspace page navigation does not invalidate it. Main/Jev ordinary send approval capture retains document epoch and conversation URL guards. Logout, backend/window close, native settings and policy changes retire service authority.
- Global status projects safe batch metadata and real configured Jev availability. QR URL never crosses renderer IPC; authenticated global QR endpoint is used. Activity link uses existing `open` behavior. Changed global batch state refreshes existing history; selected-chat refresh reuses conflict/draft guards. No background navigation or composer replacement.
- Existing button regression remains fixed: background reads never disable/re-enable disconnect, explicit action is busy, duplicate operations do not queue, disconnect ACK immediately clears the old connection.
- Shared Jev restores from the existing OS credential store; known saved model is restored, legacy saved TypeSafe credential can restore the fixed Jev model, explicit disable persists. Missing/rejected credential/runtime is not presented as verified. Jev preference save failure disables only Jev; Main remains configured. No new key store.
- Desktop `send` can call authenticated shared `service_intake` only when native Main runtime says automatic analysis is ON. High-confidence four-workflow suggestions supplement local rule routing; explicit skill/context/task choices win. Material-kind suggestion is displayed as a source/scope-bound, pending-verification hint and does not relabel original files or invent task metadata. Its judgment record uses the existing backend shared ledger.
- Desktop Enter still sends that turn. Intake readiness/relation never introduces a message-collection delay, changes the conversation, or adds a per-send approval. Timeout/unavailable/low confidence/foreign scope use existing fallback. Duplicate Enter while awaiting Jev makes one judgment and one business request. Composer edits including retyping the same text, scope changes and conversation changes discard stale replies. Unknown business/model writes use original recovery behavior, not repeat POSTs.

## RED → GREEN and verification

All commands below ran in `D:\Documents\ChatGPT\律所项目`. Node counts are the runner's reported tests (some existing script modules include additional assert checks internally).

| Command | Exit/count | Evidence |
|---|---|---|
| `node --test desktop/tests/personal-weixin-control.test.cjs scripts/test_assistant_weixin_personal.mjs` before implementation | 1; 33 total, 30 pass, 3 fail | task-3-red.log; intended failures: service payload, sidebar placement, no-dummy-chat start |
| `node --test scripts/test_assistant_business.mjs` before intake implementation | 1; 14 total, 12 pass, 2 fail | task-3-intake-red.log |
| `node --test desktop/tests/model-bridge.test.cjs` before restoration helper | 1; 6 total, 5 pass, 1 fail | task-3-judge-red.log |
| `node --test desktop/tests/personal-weixin-control.test.cjs desktop/tests/personal-weixin-bridge.test.cjs scripts/test_assistant_weixin_personal.mjs` | 0; 44 pass | task-3-green-initial.log |
| `node --test scripts/test_assistant_business.mjs desktop/tests/model-bridge.test.cjs` | 0; 20 pass | task-3-intake-green.log |
| `.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_service_runtime.py -k global_http -q` | 0; 1 pass, 19 deselected | task-3-bootstrap-green.log |
| `node --test desktop/tests/*.test.cjs` first broad run | 1; 416 total, 414 pass, 2 fail | task-3-desktop-all.log; old navigation/Jev copy expectations updated to accepted requirements |
| `node --test scripts/test_assistant*.mjs` first broad run | 1; 478 total, 477 pass, 1 module failed | task-3-frontend-all.log; actual Promise-identity regression fixed by preserving ordinary send delegation |
| `node --test scripts/test_assistant*.mjs` FINAL after duplicate/stale/fallback coverage | 0; 481 pass | task-3-frontend-final-green.log |
| `node --test desktop/tests/*.test.cjs` FINAL after Jev save-failure isolation coverage | 0; 418 pass | task-3-desktop-final-green.log |
| `.venv/Scripts/python.exe -m pytest tests/integration/test_weixin_service_runtime.py tests/integration/test_shared_judge_service.py tests/integration/test_weixin_personal_desktop.py tests/integration/test_assistant_pages.py tests/integration/test_assistant_frontend.py -k 'not browser_module_behaviour' -q` | 0; 52 pass, 16 deselected; 86.03s | task-3-python-final.log; excluded Node subtests are covered by full direct final Node run |
| `git diff --check` and `git diff --cached --check` | 0 | before commit; unchanged original per-line endings restored, preventing whole-file diff noise |

Further intermediate logs are retained (intake initial null-vs-court rule fallback and old static Jev copy assertion). A newly added save-failure test initially asserted Main disable count zero despite startup's existing disable; the fixture assertion was corrected to compare the pre-operation count. Final check proves only Jev gains a disable call. That intermediate rerun output is in the tool transcript, not claimed as green.

## Browser / design evidence

Used existing Chrome at `C:/Program Files/Google/Chrome/Application/chrome.exe` and bundled Playwright, no browser download. Command:

`PLAYWRIGHT_MODULE=<bundled node_modules/playwright> CHROMIUM_PATH=<existing Chrome> node scripts/validate_personal_weixin_ui.mjs .local/service-weixin-20261031/ui`

First bounded component pass and confirmation: exit 0. Final evidence `task-3-browser-confirm.log`, `ui/report.json`, screenshots `ui/waiting-scan-1280.png`, `ui/waiting-scan-860.png`, `ui/waiting-scan-360.png`, `ui/verification-360.png`.

Measured 1280/860/360: no horizontal page overflow; existing sidebar 216/224/224px; global panel precedes business abilities; keyboard refresh focus; QR loaded and reachable via sidebar scrolling; keyboard verification retains leading zeros; unsent composer preserved; same-workspace navigation preserves connection; zero background disabled toggles; exactly one explicit disconnect; zero page errors; zero external requests. Initial strict QR-bound assertion failed by 0.140625 CSS pixel from browser scrolling rounding, then accepted 1px measurement tolerance. No UI polish loops; one copy reduction batch, one confirmation. Diagnostic assertion reruns did not redesign the surface.

Impeccable detector run ONCE on changed assistant template/UI targets, exit 2. `task-3-design-detect.json`: 15 low-contrast advisories, 4 pre-existing low-contrast hover warnings (`#768078` over `#f3f1f7`), 1 dynamic hidden QR `<img>` without initial src. The latter intentionally receives authenticated src only while scanning; actual browser proves loading. Existing site-wide hover palette was retained per narrow scope. This is not a zero-warning audit claim.

## Self-review and handoff

Reviewed final staged changes for authority scope, Main/Jev ordinary approval guards, duplicate Enter/unknown-write behavior, restoration OFF semantics, Jev save-error isolation, data provenance and unchanged original line endings. No new dependencies/assets/fonts; no release helpers overwritten; no new persistence store.

Original WIP `docs/TASK_STATUS.md` four added lines and original untracked plan/testing folders remain untouched and unstaged. Root-owned `docs/testing/service-weixin/` also remains untracked.

Independent review, packaged-app isolated account/API/upload/restart acceptance and installation remain with root. This report's browser evidence is a synthetic bridge/component fixture, not a real packaged application or a live account/credential test. Root should make the final project-memory record after reviewed state is confirmed.

Changed files (26):

- `desktop/main.cjs`
- `desktop/model-bridge.cjs`
- `desktop/model-control.cjs`
- `desktop/personal-weixin.cjs`
- `desktop/setup-model.js`
- `desktop/setup.html`
- `desktop/tests/judge-settings-ui.test.cjs`
- `desktop/tests/model-bridge.test.cjs`
- `desktop/tests/model-settings-acceptance.py`
- `desktop/tests/model-settings-navigation.test.cjs`
- `desktop/tests/personal-weixin-bridge.test.cjs`
- `desktop/tests/personal-weixin-control.test.cjs`
- `scripts/test_assistant_business.mjs`
- `scripts/test_assistant_weixin_personal.mjs`
- `scripts/validate_personal_weixin_ui.mjs`
- `src/cn_contract/web/static/assistant-api.mjs`
- `src/cn_contract/web/static/assistant-business.mjs`
- `src/cn_contract/web/static/assistant-state.mjs`
- `src/cn_contract/web/static/assistant-weixin-personal.css`
- `src/cn_contract/web/static/assistant-weixin-personal.mjs`
- `src/cn_contract/web/static/assistant.mjs`
- `src/cn_contract/web/templates/assistant.html`
- `src/cn_contract/weixin_inbox/personal_runtime.py`
- `src/cn_contract/weixin_inbox/service_runtime.py`
- `tests/integration/test_assistant_frontend.py`
- `tests/integration/test_weixin_service_runtime.py`
