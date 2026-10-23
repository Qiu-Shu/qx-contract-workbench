# CH-07C2d independent Standards review

Result: PASS; 0 open findings. Reviewed frozen working tree (including new files) against baseline `d3c3b173af0fe3f3f0d878df6793a601e181d081`. Standards: project AGENTS.md, CONTRIBUTING.md; ponytail/full and code-review smell baseline. No product files changed by this reviewer.

## Independent execution

`run-result.json` records the exact Node command, cwd, UTC time and exit code. `probe.log` is its raw TAP output: **9 tests passed, 0 failed/cancelled/skipped, exit 0**. `inputs-before.json` and `inputs-after.json` contain identical SHA-256 values for **53 files**, including the final desktop runtime modules, package, all immediate desktop test files, domain DTO source, and the added HTTP static-route fix/test. This is a small independent probe set, not an author-suite or full-suite rerun; its count must not be added to the root suite.

Probes exercise wrong nonce/sequence/status, fatal channel timeout and late ACK rejection; old-backend-only cleanup when a late grant arrives after backend replacement and revoke fails; unawaited grant completion with callback status forgery; rejection/closed-lease behavior and lock release; hidden/symbol extra fields and deep-copy ownership; explicit packaging of new modules and their local imports.

## Reviewed boundaries

- `desktop/model-control.cjs:147` binds ACK nonce/sequence and `:153` permits only operation-specific statuses. Expired/broken channels do not reopen on later ACKs.
- `desktop/model-session.cjs:165` revalidates/copies profile data and shares the existing lock. `:183-186` saves the trusted ACK status; `:205` ignores callback status forgery. Only a fresh authorized grant receives a cleanup token (`:184`); existing never revokes another grant. Cleanup remains tied to the captured backend (`:107`).
- `desktop/profile-basis.cjs:13` is a transport validator for the central domain DTO, not a second business model; its 17-field/scope checks and intake pairing match `domain.py`. `profile-approval.cjs:32` blocks unknown and awaiting_input runs. `model-approval.cjs:293` compares complete canonical pre/post snapshots and then rechecks session identity.
- `desktop/model-approval-window.cjs:78` keeps main-frame/window identity checks, `:119` sandbox/network isolation; `:65` releases timers/listeners/window, while timeout stays 120 seconds. New display uses textContent; no Jev selector or renderer-provided budget/save plan is accepted. Existing plain/context return shape and old confirmation flow remain unchanged.
- New runtime files are explicit `desktop/package.json` entries; version remains 0.4.1. `src/cn_contract/web/app.py:588` adds only assistant-context.mjs to the existing closed static allowlist. The added HTTP import-graph test follows current static imports and preserves unknown-file rejection; it does not bypass auth or widen filesystem access.

## Scope limits

No real data/provider, installed application, installer, full Node/Python suite, or Windows GUI acceptance was executed by this reviewer. Root-owned full-suite and real-window evidence must be reported separately. This result does not close WIN-PATH-02 or complete the remaining unified chat/profile sidebar work. Root owns final memory recording and GitHub sync.
