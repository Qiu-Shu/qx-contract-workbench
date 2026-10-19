# CH-04H native approval window — implementation evidence

Frozen 2026-10-19 by the native confirmation UI sub-agent. Scope is the five new `desktop/model-approval-*` / `desktop/model-approval.{html,css,js}` product files and `desktop/tests/model-approval-window.test.cjs`; no main, package, existing preload or coordinator edits were made by this agent. No commit created.

## Contract

`createModelApprovalWindow({BrowserWindow,ipcMain,session})` returns `{confirm,close}`. `confirm({parent,details,guard})` resolves a strict boolean. Details are restricted to content, fixed model ID, decimal USD amount string and fixed DeepSeek recipient. One owned modal, an ephemeral independent session, exact file URL and exact main-frame sender checks, strict boolean decisions, and a successful state read precede acceptance. The main process closes on stale guard, Escape, parent closure, renderer failure, timeout (120 seconds) or explicit close. Per-window listeners and timers are removed; optional session cleanup failure cannot prevent settlement.

Preload exposes only `desktopApproval.state()` and `desktopApproval.decide(boolean)`. CSP and request filtering prohibit network resources; navigation, popups, webviews, downloads and permissions are blocked. Window uses sandbox, context isolation and web security with Node integration off.

The full text is rendered using textContent without truncation (tested through 65,536 UTF-8 bytes). Cancel receives focus after load; approval remains disabled until state arrives. Page departure discards late state and clears displayed text. The fixed selectors are `#approval-content`, `#approval-model`, `#approval-budget`, `#approval-cancel`, `#approval-confirm`; button names are “取消” and “确认本次发送”. Narrow layout wraps model IDs and uses a single-column facts layout; the document and full text can scroll.

## Actual verification

- `node --test desktop/tests/model-approval-window.test.cjs`: exit 0, 10 tests passed, 0 failed; duration 86.8386 ms. Full output: `window-final.log`, exit record: `window-final.exit`.
- Initial missing-window 3 RED: `window-red.log`; initial missing-UI/preload 3 RED: `window-ui-red.log`; session-cleanup synchronous failure 1 RED: `window-cleanup-red.log`. All are retained and the last issue has a passing regression.
- `node --check desktop/model-approval-window.cjs`, `node --check desktop/model-approval-preload.cjs`, `node --check desktop/model-approval.js`: each exit 0.
- `git diff --check --` the six owned paths: no diagnostics. These are new untracked files, so that command does not itself validate their complete contents.

These tests use synthetic BrowserWindow, IPC, session and DOM fixtures. They verify decisions, lifecycle, XSS-safe text rendering and API restrictions; they do not constitute actual Electron security or visual acceptance. Root owns real Electron checks, 100/150/200% screenshots, integration, broader regression and source snapshots. No real key, private material, external model request, installer or installation was used here.

Exact six-file SHA-256 snapshot is in `window-source-sha256.json`; window module SHA-256 is `f1de114f401b763b504ea383b55d1a76eaf6558a09c334b104cd949f86c1a339`.

## Final focus correction after real Electron inspection

Root's real Electron screenshots exposed an initial-viewport issue: focusing the lower Cancel button could scroll the default-size window away from recipient/model/budget. The UI now uses `focus({preventScroll:true})` on all controlled Cancel focus paths and removes the HTML autofocus attribute to avoid a second browser-controlled focus. No CSS, window security or coordinator behavior changed.

A targeted synthetic DOM focus regression first failed (10 pass / 1 fail, exit 1; `window-focus-red.log/.exit`), then all 11 tests passed after the change (exit 0, 104.049 ms; `window-focus-green.log/.exit`). Command: `node --test desktop/tests/model-approval-window.test.cjs`. `node --check desktop/model-approval.js` also exited 0. This test asserts the no-scroll focus contract; root will verify actual initial `scrollY` and viewport screenshots in Electron.

The final six-file snapshot is `window-focus-final-sha256.json`; the earlier snapshot remains historical evidence. Only `model-approval.js`, `model-approval.html` and the window test changed in this correction.
