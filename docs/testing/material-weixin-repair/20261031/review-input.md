# Input-cap task independent review

SPEC: **PASS**. QUALITY: **Approved**. No Critical, Important or Minor findings.

Fixed scope: `32db1bb637c381a83fc02bfb4447d0981124ddb8..77464fed851f3bbb8d9b2d3cbb8273f24b1736fa`. Reviewed task-input-brief.md, task-input-report.md and the twelve-file task-input-diff.txt. This is a task gate, not a whole-branch/release review. I did not implement this input-cap change.

## SPEC

- Complete main-model request cap is **262144 bytes** in the backend DTO default and native configuration, with the pre-existing maximum unchanged: `src/cn_contract/domain.py:2889`, `desktop/model-session.cjs:21`. No codec truncation was added. New tests build the actual wire, preserve all 106 sources and all fictional 7133 characters, reject an explicit 65536-byte config and the complete 400-anchor selection over the new cap, and retain the schema maximum: `tests/unit/test_material_wire_capacity.py:39-59`.
- Native worst-case reservation derives input bytes, output tokens and prices from the same configuration with exact integer arithmetic: `desktop/model-session.cjs:27-33`; Python accounting remains Decimal-context independent: `tests/unit/test_assistant_model_contract.py:26-35`. Flash **0.0835584 USD** and Pro **0.36225024 USD** are authorization ceilings, not receipt costs. Config version, one-use lease and 120-second grant behavior were not relaxed.
- Only bounded JSON HTTP422 with the recognized `MATERIAL_INPUT_TOO_LARGE` value receives that fixed classification. Error text, correlation identifiers and other fields do not cross the native response boundary; unknown codes/status, malformed JSON and excessive error bodies stay generic: `desktop/model-approval.cjs:95-131`, `desktop/tests/material-approval.test.cjs:72-87`. Success-response bounds remain unchanged.
- The fixed code is retained by the native session and approval allowlists and reaches the material-action explanation: `desktop/model-session.cjs:9-10,246-249`, `desktop/model-approval.cjs:8-9,283-284`, `src/cn_contract/web/static/assistant-render.mjs:50`, `scripts/test_assistant_generation_render.mjs:260-273`. No truncation, automatic retry, coordinator change or extra capability was introduced.

## QUALITY

Strengths: one config drives the monetary ceiling; finite error-code classification avoids forwarding arbitrary local error text; the new capacity tests use real domain/codec behavior and assert complete contents rather than merely successful return. The change adds no dependency or parallel source of configuration.

Critical: none. Important: none. Minor: none. **Approved** for this fixed task scope.

## Focused checks outside diff

The diff context cuts off the larger call paths. I inspected only these named cross-layer risks:

1. **Raw text mistaken for complete wire / truncation:** `src/cn_contract/assistant/material_codec.py:37-44,52-57,75-85` serializes the complete request, compares UTF-8 JSON bytes against config and rebuilds the same source/config/system basis. No prefix selection or retry was found.
2. **Native/backend reservation disagreement:** `src/cn_contract/assistant/providers/policy.py:71-82` derives reservation from config bytes/output cap/rates with its own Decimal context, matching the new native calculation.
3. **Error lost before UI or failed preview proceeds to send:** `desktop/material-approval.cjs:11-23`, `desktop/model-approval.cjs:245-285`, `src/cn_contract/web/static/assistant-material-generation.mjs:49-63` retain the rejection and return before generation submission; `src/cn_contract/web/assistant_material_generation.py:85-98` emits the fixed HTTP422. This HTTP-preview failure does not traverse model-control's backend acknowledgement classifier.
4. **Larger main cap bypasses existing source/authority/other input boundaries:** `desktop/model-approval.cjs:142-170,253-273` retains ordinary text's 65536-byte limit, identity guard and two exact snapshots; `desktop/model-session.cjs:56,109-120,180-200` retains Jev65536, workspace/config/guard checks and one-use material authorization. `desktop/material-basis.cjs:22-41` already accepts bounded262144-byte material basis; `src/cn_contract/assistant/material_preparation.py:26-92` retains ownership, scope, material parse revision/hash and preview reassembly. No new source or session authority was added.

CodeGraph was used only to locate the material codec seam, without index initialization or synchronization. Source and tests were read-only. No actual contract, user profile, credential or external model/account was accessed; no source/index/HEAD mutation was made. Only this review report was written.

## Verification evidence and limits

- Inspected existing final `input-node-regression.log`: **186 passed, 0 failed/cancelled/skipped/todo**, 5343.3095ms. Inspected final `input-python-regression.log`: **60 passed**, 57.21s. Neither log contains warnings/tracebacks. These are implementer executions, not newly executed reviewer tests; overlapping earlier runs are not additive.
- No test was rerun: reading the changed code and the focused call paths raised no unresolved doubt requiring a new probe. The report's initial fixture-authoring failures are explicitly separated from meaningful RED evidence.
- Not verified here: packaged/install upgrade, running-process reconfiguration and actual Electron/model acceptance. Root owns those gates. An existing process configured at the previous cap needs reconfiguration/restart; this source approval does not establish release or legal-quality completion.