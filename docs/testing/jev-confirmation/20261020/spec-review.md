# CH-05D2 independent Spec review

Reviewer: `/root/jev_request_spec_review` · 2026-10-20. Base `a1ecd7e7d06112e228719586e4d35fe65a906036`; no commits beyond that base at initial review. Reviewed the working-tree production desktop diff and new tests against `docs/plans/2026-10-20-jev-confirmation.md` and approved handoff §§3–5. Used CodeGraph for assembly/call boundaries, then read current source directly.

## Spec

Production implementation: no unresolved finding identified.

- `judgeBudget` is a trusted constructor input, defaults to null, and is absent from the production `main.cjs` assembly. Settings and renderer messages cannot supply it. The test observer's explicit synthetic injection is outside `build.files`; it is not a production environment-variable switch.
- The existing confirmation window independently identifies TypeSafe, purpose, the same complete text and a separate decimal program reservation. Auxiliary starts unchecked, unavailable auxiliary remains disabled, and declining it preserves permitted Main. No supplier-price guarantee, automatic fact confirmation, new provider or business skill dispatch was added.
- Details, decision and sender/state validation remain strict. New details permit only false cancellation or exact `{main:true,judge:boolean}`; unavailable auxiliary cannot be selected. Old four-field/boolean compatibility remains. A fixed isolated file window, blocked navigation/network, literal textContent, default cancel focus, bounded lifetime and late-state cleanup remain in place.
- Main authorization succeeds first; auxiliary is authorized only on its explicit choice and independent captured version/budget. Before/after reads recheck full text hash, revisions, materials and session. Both leases remain open for the final asynchronous identity check. Known auxiliary refusal may skip auxiliary; uncertain ACK stops the captured backend. Late cancellation/replacement revokes owned grants. If outer validation fails after the inner lease has closed successfully, the captured backend is stopped, not its replacement.
- No Python protocol/schema/permission expansion was found in this slice. The complete-text lease and original backend hash enforcement remain D1 responsibilities. This is a confirmation UI engineering slice; real account/price/budget prerequisites are not satisfied by the synthetic constructor input.

The new and amended tests were read for these boundaries; this reviewer did not execute tests, build, run GUI, call real providers, or change product files. Execution numbers must come from the parent-owned actual reports.

## Driver follow-up

Final driver and author notes reviewed. Source `--judge` asserts Main-only first, then an independently selected second text with Jev→Main, exact hash/accounting and no reload resend. `--judge-closed` configures both services but injects no budget and asserts no auxiliary authorization or POST. Frozen mode invokes the real fixed native approval UI only, then disables both services without submitting generations; it does not test frozen provider execution.

Two overly broad report labels and an unmeasured zero-call field were corrected before execution: reports now say real-model execution was not requested, limit source observations to the exact loopback/tripwire scope, and describe frozen absence of generation submission. Frozen full-process networking remains uninstrumented. Test injection is not production activation. No GUI was run by this reviewer; parent execution will determine actual counts and pass/fail.

Final Spec result: 0 unresolved findings. Production, test and plan hashes below were rechecked when sealing this report.

## Reviewed file SHA-256

| File | SHA-256 |
| --- | --- |
| desktop/main.cjs | 887012c43b1fa92139198a0d06c16ce17e4b7d88f10765332fb064389e93565d |
| desktop/model-session.cjs | 288d57e9aa8855deed52ff58bd08c0243a0ab70c09ad3c5cb647685ae469ee02 |
| desktop/model-approval.cjs | 2539492323344e0ea0e6656f2ee11013606d4802d09dc47f729f4f32338dc6c4 |
| desktop/model-approval-window.cjs | 5e5eb085514e262e7ae3db19866ebfe5b02b83ede51b741df37b53378ec24b41 |
| desktop/model-approval-preload.cjs | 5cc2b68fcea434a57f7d339bd5341a88dee35a6c308d2fda13b4f6d7bc194203 |
| desktop/model-approval.html | 40d96c90cc36d5706430b2b577fe8ff2527439682da9af58ba088a673df4d5ce |
| desktop/model-approval.css | 7c89030daa26ef62a6965cc41626f1d3e3e6a301659b47568b74cc56774c254b |
| desktop/model-approval.js | 9c1e072a011a37ed1446adc29354eb5e33db4a4c49b58cdf685f1e855ae5598d |
| desktop/package.json | 387d06b2db84d356181ec6558fddb70d8b0414cc96854979e48635e404e611bc |
| desktop/tests/judge-approval-session.test.cjs | 5bb29b9b0085fea0ca8636b97d2af9563a5dba17f62bdb1a4e928a0046c698e5 |
| desktop/tests/model-approval.test.cjs | c996c5ef6fb24fc0b012031e3c70352fcc522e0471473ebe31be492c8094520f |
| desktop/tests/model-approval-window.test.cjs | 674eae012c1f476145bd359d6bfe920dea071ab953abae2618d1754b8c434be2 |
| desktop/tests/judge-settings-core.test.cjs | 4b136253ee93b5eb83cc4d8fc2f6384e0364f20019178383d566dc946f6a9494 |
| docs/plans/2026-10-20-jev-confirmation.md | 51e8a032df8772390ffe9391d99603449e272257e3345ef7e7b779e8a0abc530 |
| desktop/tests/model-approval-acceptance.py | a26792ab61ec1a48ffcaf325209177927777af4660466a158d924f2aa3304cc1 |
| desktop/tests/model-credentials-acceptance.cjs | 348069cc23d7c8b28634cb117566525fcdb85acd3f6a8ea417ec603d13881086 |
| tests/helpers/inspect_native_control_records.py | dadb74839cba59638eed9206a80dbee938471abcb234e32b15a14e397f45b613 |
