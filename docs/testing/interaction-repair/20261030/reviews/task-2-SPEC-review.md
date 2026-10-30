# Task 2 — independent SPEC review

Current SPEC result: **PASS after `c739c7b`; the original P1 is closed.** Original fixed range `88bb75e..aed6d57`; reviewed task brief/report and `git show aed6d57` once, then focused current-source followups. Follow-up reviewed only `aed6d57..c739c7b` and its targeted evidence. No product/test edits or broad suite reruns. The separate QUALITY picker/autosave finding is outside this SPEC closure and remains with its assigned reviewer.

## Correction acceptance — `c739c7b`

The composer now captures the initial textarea value and edit revision before awaiting upload; input/composition events advance the revision. It stops a files-only send after upload, rejects text dispatch when revision/value/composition changes, and leaves the field editable. The entry callback also compares the captured text with controller state immediately before dispatch. The new inline notice tells the user to send the retained text again. This directly closes the boundary identified below without disabling editing or changing upload/unknown-request semantics.

Read the recorded RED/GREEN logs as well as the three-file correction diff: the four deferred-upload cases (files-only new typing, text+file replacement, edit then undo, and IME start) fail on the old product modules, with 25 tests / 21 pass / 4 fail; the focused material/transport/entry GREEN records 40 pass / 0 fail. Each edited-input case retains text and sends only after another explicit Enter. The report records exits 1 and 0 respectively. These are existing evidence inspected by this reviewer, not rerun results, and overlap prior renderer counts. No new actionable SPEC finding in this correction.

## Original finding — resolved by `c739c7b`

**[P1] Preserve the send intent across asynchronous attachment upload** — `src/cn_contract/web/static/assistant.mjs:146–147` (with `assistant-composer.mjs:6`).

The brief requires: “then sends nonempty current text only on successful uploads, **or ends after files-only upload**,” and preserves user-controlled sends. The new composer awaits `beforeSend()` and only then invokes `onSend`, which reads the mutable `controller.state.text`. The textarea remains editable during upload (`assistant-render.mjs:199`). Starting with an empty composer, selecting a file and pressing Enter therefore also sends any next-message text entered while the file uploads, without a second send action. Likewise, an initial file+text send can use replacement text entered during upload instead of the text associated with the click. `controller.send` snapshots only when it is finally invoked, so its own edit checks do not protect this earlier boundary.

Capture the send intent at the original Enter/click boundary. Files-only intent must stop after upload; when intended message text changes during upload, retain it and require another send action (or use the established equivalent edit/version guard). Add a deferred-upload regression for both empty-to-new-text and changed existing text. Do not freeze or silently discard new typing.

## Focused reproduction

Ran one read-only `node --input-type=module` probe importing the actual shipped `bindComposer`, with a deferred `beforeSend` and the product's same mutable-text `onSend` expression. Pressed Enter at empty text, delivered a normal input event while upload was pending, then resolved successful upload. **Exit 0**, observed `newTextSentWithoutAnotherEnter=true` and the newly typed text in the send callback. This proves the changed async boundary; no model/network/user-data access occurred. Source inspection confirms normal controller sends save/snapshot the late text, rather than reject edits made before invocation.

## Remaining scope and evidence

No additional actionable Spec issue found in configured-scope popup removal, separate Judge exclusion, fresh-chat/paused Weixin flow, local upload policy, IME/Shift+Enter/overlap guards or queue/navigation protection. Reported native 401/renderer 452 tests and Python 195 passed + 13 disk-budget setup errors followed by D: 14 passed were read, not rerun; overlapping counts are correctly distinguished. They do not cover the finding above. Actual packaged UI, external Weixin connectivity and post-Task2 provider checks remain root-owned gates, not claimed passed here. Task3 product work remains paused pending root's GO and a repaired Task2 baseline.
