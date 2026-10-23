# CH-07C3a independent Standards review

**PASS — 0 open findings.** Baseline `5d5e688b14ac53b81029184413cd37ce631b144c`; reviewed working-tree diff and new runtime/test files. Standards: AGENTS.md, CONTRIBUTING.md, central domain DTO/permission/source/cost requirements; code-review smell baseline and ponytail/full. Reviewer did not edit product files.

## Independent evidence

`run-result.json` records exact commands, UTC times and exit codes. **4 Node panel probes passed, exit 0; 5 Python history probes passed, exit 0**, no failures/cancellations/skips. Python used an explicit fresh D: temporary directory, synthetic SQLite and an in-memory provider response, with no socket/provider execution. `panel.log`, `history.log` and `history.xml` preserve raw results. The **555 recorded source/test/script/desktop inputs** are identical before/after execution and at report generation. These are independent probes, not additional author-suite counts.

- History probes corrupt the estimated cost, configuration digest, handler-event time, completion event and event audience independently. Every read rejects with VERSION_CONFLICT and leaves database state unchanged.
- Panel probes cover late responses after close, binding change within the same conversation, pagehide, exact large Decimal strings and protected HTML-shaped text through textContent only.

## Code assessment

- `providers/attempts.py:100` adds only the profile-specific read path after current ownership. `profile_history.py:54` binds message/run/scope/output/config/policy and uses existing ledger/input/output/receipt validators (`:94-107`), instead of inventing save success from model success. It stays read-only and preserves historical receipt revisions.
- `domain.py:4078` requires matching applied/unchanged receipts and excludes receipts from blocked outcomes. Existing plain/context attempt serialization is unchanged; there are no new storage tables or dependencies.
- `assistant-generation.mjs:195-222` uses current saved-draft preview and native consent, rechecks edits/scope, and routes existing/unknown requests to GET recovery without a second POST. Existing browser/plain/context branches remain distinct. Selection changes invalidate pending consent (`assistant-state.mjs:341`).
- `assistant-profile.mjs:40` checks binding/source revisions; `:65`, `:133` and `:168` clear/ignore stale content on close, switch or page exit. Values and citations use textContent and preserve decimal strings. The panel never edits or sends.
- `app.py` explicitly whitelists assistant-profile.mjs. Existing `desktop/backend.spec:15-16` collects the template/static directories; Python's local profile_history import is statically discoverable. No installer build is claimed.

No actionable documented-standard breach or smell was found. Root-owned full regression/Windows evidence is separate; this reviewer did not rerun those suites or test a real model, installed application, package, cloud or real material. WIN-PATH-02 remains outside this slice. Root owns memory recording and GitHub synchronization.
