# CH-07C3 frontend sending subtask

Scope: modified only assistant-generation.mjs, assistant-state.mjs and new scripts/test_assistant_profile_generation.mjs. No commit/push, real model, real material or installed app operations.

The existing generation controller now selects profile mode only when the dedicated native bridge and both profile API methods exist. Ordinary eligible text saves the draft, obtains a server profile basis, asks for native confirmation, and submits the actual flat MainProfileSubmission DTO (AssistantMessageInput plus project_intake=true). The native choice contains conversation_id plus the four MainProfileSelection fields. No message/basis wrapper is accepted by the actual backend DTO.

Existing plain clients retain their path. Profile errors never retry through plain generation. Selected skills/materials/attachments/citations and active/awaiting-input runs block profile sends. Editing, retyping, changing skill or citation and then resetting, refreshing a changed scope/composer, switching, closing and revocation invalidate pending confirmation. The same generation pending/request/history machinery handles recovery. Native status=existing only reads the request and never POSTs. Unknown POST outcomes retain the request ID. Registration must return input_format=profile-text-v1. History passes through server attempt objects and never infers a profile save receipt.

Verification:
- red.log: node --test scripts/test_assistant_profile_generation.mjs; exit 1, 47 tests, 9 passed / 38 failed / 0 cancelled / 0 skipped. Failing behavior was absent profile dispatch and guard paths. One invalid-preview test initially assigned null to a nullable intake revision; it was corrected to 0 before GREEN (fixture correction, not a product failure).
- green-first.log: exit 0, all 47 tests passed.
- target.log: first adjacent run exit 0, 59 top-level tests; its nonexistent test_assistant_context.mjs input was silently unmatched by Node, so it did NOT cover context tests. The final command corrects this.
- target-final.log: node --test scripts/test_assistant_profile_generation.mjs scripts/test_assistant_generation_state.mjs scripts/test_assistant_state.mjs scripts/test_assistant_context_selection.mjs scripts/test_assistant_material_state.mjs scripts/test_assistant_generation_entry.mjs; exit 0, all 73 top-level tests passed, 0 failed/cancelled/skipped. Breakdown: 50 profile tests, 11 context tests, 9 entry tests and 3 whole-script containers. Those containers internally report 36 generation groups, 28 state checks and 4 attachment groups; do not add those counts to 73 as independent cases.
- git diff --check for owned inputs passed.

The final 3 supplemental profile tests exercise existing registration readback, rejection of a plain attempt for a profile request, and preview network failure without fallback. They were added after the initial RED/GREEN; they are not claimed as RED evidence.

Limits: browser/Electron/backend real-process acceptance and independent review belong to root. This subtask did not run Python, freeze/build/install, contact models, or assert legal correctness. No new dependency, new send button or second queue was added.
