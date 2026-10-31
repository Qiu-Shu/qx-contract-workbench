# Task 2 → Task 3 backend contract (2026-10-31)

Implemented source contract; targeted synthetic backend integration tests are implemented; repair-source verification completed (113 tests); backend scoped re-review passed at 3740816; Task 3 integration b2f04b8 reviewed separately. No real credentials/model/Weixin/user profile accessed.

## Native commands
Existing `start_personal_weixin` native control dispatch is retained. `start(payload)` now accepts either:
- Service: `{session_token, workspace_id, automatic_policy}`. `automatic_policy` is `null` (collect only) or `{expected_config_version: UUID, max_total_usd: null}` (Task 1 unlimited Main budget). Start returns `{status: "started"}`. Workspace must be current authenticated local workspace. No conversation/scope required.
- Legacy fixed conversation: existing `{session_token, expected_scope, automatic_policy}` unchanged.
Existing verify `{code}` and disable commands operate current mode. The façade forwards these to service runtime. Native Main policy/session revocation disables active service. `desktop_entry.py` shares the configured `JudgeRuntime` instance with the new SharedJudgeService; restoring existing Jev configuration via existing native configure command activates this provider automatically. No new credential storage.

## Authenticated global GETs
- `/api/assistant/personal-weixin/status`
  - `state`: disconnected/starting/waiting_scan/need_verifycode/connected/paused
  - `mode`: "service"
  - `conversation_id`: null
  - `automatic`, `notice`, `qr_url` (ephemeral, do not persist)
  - `workspace_id`: current authenticated local workspace, including disconnected state and before service construction (Task 3 bootstrap addition)
  - `capabilities`: ["contract", "case", "court", "sales"]
  - `jev_available`: actual configured enabled provider status; this is NOT a live credential verification
  - `batches`: latest 50, fields `id,revision,state,conversation_id,draft_id,workflow,decision_json`.
  - batch state: collecting / held / clarify / waiting / routed / executing / completed.
  - decision_json: JSON string for `{action:wait|start|clarify|ack, relation:new|existing|unassigned, conversation_id, workflow, material_kind, notice}`; null before decision.
- `/api/assistant/personal-weixin/qr.svg`: same authenticated ephemeral QR policy as old route, no query params, 404 unless waiting_scan. Never use conversation route for global UI.
- Old conversation GETs remain compatible.

## Shared Jev assistance
`POST /api/assistant/judge/assist`, cookie login + same-origin + `X-CSRF-Token` required, body:
`{expected_scope: ScopeSnapshot, purpose:"service_intake"|"primary_intent"|"material_kind", text:string(max12000)}`.
Returns `{available:bool,result:JudgeResult|null}`. Primary-intent/material-kind retain old fixed options and template/hash. For four business abilities (including court), desktop MUST use purpose `service_intake`, whose `ServiceJudgeResult.answers` contains `readiness`, `relation`, `workflow`, `material_kind`. Desktop Enter remains explicit submission: consume workflow/material_kind suggestions only, preserve the user’s explicit choice, and do not apply Weixin readiness/relationship gates to desktop submission. Null or non-ok result means rule fallback. Only confidence >= .8 is consumed by service; no accuracy guarantee. Repeated exact session/scope/config/input shares a durable claim; unknown/interrupted requests are never resent. Scope/config/revocation change discards late result.
Call sites: service `_advance_batch` → `SharedJudgeService.assess` before creating/routing any conversation uses new `qx-jev-service-intake-v1` to answer all four questions in ONE request. The service scope is connection + batch ID/revision + owner/session/workspace, and every late response checks revision/authority again. Candidates are <=12 authorized titles using opaque answer keys `candidate_a` etc; UUIDs and session scope never enter HTTP state. Multiple materially plausible matters still require explicit title/reference even if Jev selects a high-scoring candidate. The same provider is reused for primary-intent fallback only when the intake has no workflow, and for locally parsed material excerpts; this authenticated endpoint is the reusable desktop task/material entry. Existing run-bound NativeJudgeControl authorization/ledger remains unchanged. Task 3 may call the shared endpoint for desktop assistance without a per-send dialog.

## Refresh/UI behavior
The service has no dependency on selected desktop chat. Switching/archiving unrelated chats does not disconnect. Logout must invoke existing native disable/revoke flow; every queued I/O also rechecks session and epoch. Backend intake uses independent polling and a 0.2s collector with 5s silence deadline; explicit continue/start bypasses silence, hold survives restart. Poll global status; when a batch's conversation_id/run state changes, refresh the existing conversation list and relevant conversation/history using existing APIs. No new SSE event family added.
New conversations use existing business/task/attachment records; service transport intake is additive in same database. Multi-candidate ambiguity asks for stable title/full UUID, retains original batch, and incorporates answer. Unsent drafts block only the selected target and remain unchanged. Pending file-only/hold batches visible in status. Results retain original source event/outbox; ephemeral reply context is not stored as credential data. After restart, if original reply context has not been redelivered, result stays on desktop with explanatory status (no fabricated recipient/context).


## Final persistence and assistance details
Current schema: `weixin-service-v1`, additive successor of the unchanged 81-table personal runtime schema; new workspace has 90 tables. New tables include service connections, immutable complete poll/cursor journals, immutable intake events/media, batch revisions/associations, execution links, once-only replies and shared Jev claims. Existing legacy object definitions/hashes remain unchanged. Downloaded unassigned originals are bounded BLOBs in this same DB until registering into the existing attachment store; cursor commit and receipt/source association are atomic. No second task DB, no disk path from incoming filename.
`automatic_policy:null` collects but makes no automatic Jev or Main calls. Manual authenticated shared assistance remains available. No Jev configuration means explicit rule fallback. Usage above is synthetic engineering validation, not a test of stored TypeSafe credentials or Chinese legal classification quality.

Review round 1 preserves this API. Explicit wait clauses inside an instruction hold the batch; “可以开始 / 发送完毕 / 开始 / 开始处理” release the hold and outrank Jev wait. Bare “新事项” when responding to a pending ambiguity retains the original batch files. Material-selection commit recovery uses its existing receipt; no new client fields.

Task 3 integration adds no conversation requirement. Native bridge retrieves this authenticated workspace identity itself and validates the service response; renderer does not choose the workspace or budget. Jev configured availability remains distinct from a live credential check.
