# Weixin task review — `934689a..2aef082`

## Spec Compliance

- **✅ Spec compliant for the fixed implementation.** `src/cn_contract/weixin_offline.py:196–200` accepts optional body-level `msg_id` strings, including empty/noncanonical/nonnumeric strings, while nonstrings still pass through the existing exact integer/uint64 validator. It adds no queue, model policy, receiver or new execution path.
- **✅ Identity and explicit references remain authoritative.** Envelope identity is still calculated from bot, peer and envelope `message_id` at `weixin_offline.py:94–96,159`; exact sender/recipient checks remain at `160–162`. Explicit `ref_msg.svr_id` and a present quoted `message_item.msg_id` remain strictly validated and compared at `114–126`. The new string exception does not apply to that quoted reference.
- **⚠️ Final verification pending, not a failed assertion.** At review time `task-weixin-report.md` still records the combined unit/runtime run as in progress. Its RED result is implementer-reported **3 failed / 9 passed**; final GREEN count and exit have not been supplied. No full test PASS is claimed here.
- **⚠️ Out of this diff.** Actual phone message values, root cause of the user's specific old blocked receipt, automatic-analysis UI activation and real connectivity remain unproved by this patch. The report explicitly distinguishes a source compatibility defect from a proven phone failure. No network was used to independently retrieve the referenced upstream TypeScript; its declared type is taken from the supplied requirement, not represented as independently fetched evidence.

## Strengths

- Minimal repair at the shared decode seam, with a comment explaining metadata versus server identity (`weixin_offline.py:196–200`). It preserves the legacy integer validation rather than accepting arbitrary nonstring values.
- New protocol tests assert the actual decoded batch is unchanged when only metadata changes, while the full-source payload digest changes; they also assert an invalid envelope ID still rejects (`tests/unit/test_weixin_offline_protocol.py:152–164`). The negative matrix covers null, booleans, float, containers and integer overflow/underflow (`167–172`).
- The runtime test is parameterized across numeric/empty/arbitrary item strings and automatic OFF/ON (`tests/integration/test_weixin_personal_runtime.py:453–455`). Its complete body checks real offline ingress/dispatch rows, one draft/event/dispatch receipt, provider-call counts, same-chat history and unchanged original blocked receipt rows (`477–524`). It does not equate a rendered control or a decoder-only stub with successful runtime dispatch.

## Quality and named-risk checks

1. **Risk: metadata becomes task identity or weakens replay checks.** The supplied diff cuts `_event` and the integration test mid-function, so their enclosing code was read at the fixed head; focused CodeGraph/source inspection located the identity and decode call. The unchanged ingress call site was checked specifically for identity and digest use: `src/cn_contract/weixin_inbox/ingress.py:96–107` derives source identity solely from envelope ID and bound peer; `121–140` hashes the full source message and handles prior descriptors before decoding. A changed metadata value under the same server identity remains an `event_conflict`; identical accepted replays stay duplicates and historical blocked descriptors remain blocked. No history rewrite is introduced.
2. **Risk: arbitrary string metadata bypasses size limits.** Checked the decoder bounds and actual ingress raw-response gate. `weixin_offline.py:177–178,215–216,227–228,244–245` retain the item, text, raw-byte and message limits; file size/name restrictions at `129–153` are untouched. Live ingress also checks `MAX_RAW_BYTES` before describing messages (`weixin_inbox/ingress.py:184–189`). The metadata gains no unbounded independent transport or persistence route.
3. **Risk: arbitrary IDs broaden explicit quote routing.** Checked `_reference` (`weixin_offline.py:114–126`) separately from the changed body item check. The exact uint64 reference consistency rule is unchanged. Existing envelope/reference malformed-ID and exact peer tests remain at `tests/unit/test_weixin_offline_protocol.py:305–337`; no quote or peer relaxation was added.
4. **Risk: automatic processing or outbound retries expand.** The diff contains no runtime/outbox policy change. The extended runtime fixture expects `int(automatic)` model calls even after replay and one outbound submission, with no downloads (`tests/integration/test_weixin_personal_runtime.py:501–531`). This meaningfully covers automatic OFF and normal replay. Unknown outbound recovery itself is unchanged and is not independently re-proved by this small diff; final suite evidence and root's existing unknown-send guard remain separate evidence.

## Issues

### Critical (Must Fix)

None found.

### Important (Should Fix)

None found.

### Minor (Nice to Have)

No actionable minor defect. The pending final test result is an evidence handoff item, not an invented code defect.

## Assessment

**Task quality: Approved at source-review level; final test gate pending.** The exception is restricted to optional item metadata, with identity, quotes, scope, replay and bounds preserved. The tests inspect decoded state and persisted runtime effects and include both automatic-policy modes.

Read the supplied fixed diff once, the requirement/report, the SDD task-reviewer template and only the focused enclosing functions/caller needed for the named risks above. No test was rerun, no original user data or actual account was opened, no network was issued, and no source/index change was made. Only this report and the authorized local project-memory summary were written. Later changes and another writer's WIP are outside this review.

### Final test evidence supplied after review

Root updated `task-weixin-report.md`: the same protocol/runtime command completed **267 passed in 245.51s, exit 0**, with no test failures or warnings. This closes the pending test-evidence item above; the result is root/implementer-supplied, not a reviewer rerun. The separate source-approval G01–G13 warnings are retained and are not production clearance. Actual phone connectivity and the original phone-message cause remain unverified. The later material-package UI failure is tracked in `review-final.md`, not attributed to this Weixin-only diff.
