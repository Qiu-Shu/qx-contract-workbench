1. **Original explicit-readiness reproductions — ADDRESSED.** The two original combined hold messages now remain held; supported positive start/completion phrases release the hold, and Jev wait cannot override that explicit release (`src/cn_contract/weixin_inbox/service_routing.py:8`–`:28`; `service_records.py:98`–`:100`; `service_runtime.py:274`). The added parameterized regression exercises the original negative instruction and subsequent positive release against opposite Jev suggestions (`tests/integration/test_weixin_service_runtime.py:14`). However, the new positive substring matching introduces another P1 negative-readiness defect below; readiness is therefore not ready for acceptance overall.

2. **“新事项” clarification losing original materials — ADDRESSED.** Bare new-matter answers are attached to the existing `clarify` batch before normal new-business splitting (`src/cn_contract/weixin_inbox/service_records.py:82`–`:86`). The regression uses two genuinely completed matters, retains the original ambiguous file batch, and checks three events in that same batch after the answer (`tests/integration/test_weixin_service_runtime.py:42`). The corrected RED log fails on expected Main count 3 versus actual 2, rather than the discarded empty-conversation fixture.

3. **Crash after committed material selection — ADDRESSED.** The retry looks up the prior operation, requires current materials revision to equal its committed revision, and reconstructs only the pre-selection materials revision (`src/cn_contract/weixin_inbox/service_runtime.py:424`–`:435`). It still calls the unchanged `attachments.select_materials`; that method checks the original operation kind and whole-request digest through `_same` (`src/cn_contract/assistant/attachments.py:312`–`:320`, already inspected in the original review). Other scope fields and selected items remain in that hash, so this repair does not bypass the old receipt validation. The fault-injection test executes the real committed selection before raising, retries twice, and verifies exactly one Main call and one link (`tests/integration/test_weixin_service_runtime.py:69`).

4. **Missing-original integrity acceptance — ADDRESSED.** The validator now compares exact declared `(event_id, media_id)` pairs with persisted media rows, then retains the prior byte-hash validation (`src/cn_contract/weixin_inbox/service_records.py:161`–`:168`). Missing and surplus rows cannot pass merely because existing row hashes match. The original corruption probe, including restoring the exact trigger SQL, is covered by the new rejection test (`tests/integration/test_weixin_service_runtime.py:92`).

## New breakage in the fix diff

### Important [P1]: Negative start/completion phrases release a held batch

`src/cn_contract/weixin_inbox/service_routing.py:13`–`:15` treats any occurrence of `可以开始` or `发送完毕` as `collecting`. The preceding negative list does not recognize **“现在还不可以开始”** or **“尚未发送完毕”**. Both therefore return `collecting`, although they explicitly withhold readiness.

Focused synthetic confirmation: ingest the original explicit hold instruction plus a real synthetic file, advance to verify no execution, then send **“现在还不可以开始”**. The batch moves to **completed** and makes **one Main call**. This regression is introduced by the new positive substring matching: the former control path did not interpret this phrase as a release.

Fix negative or conditional start/completion semantics before accepting a positive substring. Preserve the latest explicit event precedence, and apply the same interpretation to collection and Jev readiness precedence. Add narrow regressions for these negative phrases alongside the supported positive release cases. Do not weaken material-readiness or receipt checks to solve this.

## Out-of-scope observations

None. The unchanged material-readiness checks still precede execution, and this fix does not remove those guards. No new review of unchanged subsystems was conducted.

## Checks and evidence

- Read only the supplied `a426461..82e0e7b` fix package, appended repair report, and exact regression log tails. Did not read the updated full Task 2 package, run git, mutate product source, or repeat suites.
- Confirmed final log output: **113 passed in 75.42s**. Its report identifies the exact covering command and exit 0. The **344 passed** run is correctly qualified as overlapping repairs and is not used as frozen-HEAD evidence.
- Ran one new inline synthetic probe command, exit **0**, **3.59s**: two direct control checks and one complete held-to-negative-start scenario. The direct checks both returned `collecting`; the runtime scenario completed with Main calls=1. All materials, credentials, transport and Main responses were synthetic; no user profile or live network was accessed. Temporary workspace removed; only this report retained.

## Verdict

**Fix round: Findings remain open.** All four original concrete reproductions are addressed, but the fix introduces the P1 negative-readiness regression above. This must be repaired before Task 2 is approved.
