# CH-05D1 native Jev authorization evidence

Base: `27f224c6568fcfdd4c16f49c6533cf9741dbb464`. Final target: **83 passed**, exit 0, 27.825 seconds; six recorded input hashes stable. No commit/build, no real materials/keys or remote model request.

## Implemented contract

`NativeJudgeControl(runtime, provider_factory=None, *, database=None)` adds `authorize` and `revoke`; missing DB rejects both. DTOs are only in `domain.py`. ACK contains only fixed `status` (`authorized`, `existing`, `revoked`). The budget is an independent positive exact JudgeUSD; reserved=max_total and max_calls=1.

The service authenticates and reads the actual saved draft, verifies the current config version, full scope/composer/hash and attachment absence, then predicts only input_revision+1 and computes the existing codec full-input hash. An existing run requires exact historical request identity/scope/content/digest and never grants new permission. Old requests retain digest+authorization UUID tombstones without full content/provider/secret.

Before every new grant, any reserved/sending auxiliary attempt in the workspace blocks replacement, including after expiration/revoke/reconfigure. Otherwise a matching settled auxiliary, a matching terminal Main run with no auxiliary, or an expired unconsumed grant releases the slot. The grant/tombstone is published only after the DB context commits successfully. Revocation authenticates and only clears the current actor/session grant.

## Actual verification

| Evidence prefix | Exit | Tests | Failures | Seconds | Inputs stable |
|---|---:|---:|---:|---:|---|
| approval-red | 1 | 1 | 1 | 2.635 | True |
| approval-green | 0 | 1 | 0 | 1.547 | True |
| slot-boundaries-initial | 1 | 7 | 1 | 3.821 | True |
| slot-boundaries-green | 0 | 7 | 0 | 3.670 | True |
| authorization-boundaries | 0 | 26 | 0 | 13.927 | True |
| authorization-validation | 0 | 50 | 0 | 24.975 | True |
| target-final | 0 | 81 | 0 | 22.754 | True |
| publication-red | 1 | 2 | 2 | 2.074 | True |
| publication-green | 0 | 2 | 0 | 1.882 | True |
| publication-final | 0 | 83 | 0 | 27.825 | True |

Exact commands, UTC times, JUnit counts and before/after input hashes are retained in each prefix's `.json`; raw output is in `.log`/`.xml` with `.exit`. `diff-check` exit 0.

The initial RED confirms the missing DB-enabled authorization API. The first slot regression exposed the incorrect `canceled` spelling; the implementation now uses `cancelled` and verifies the historical full JudgeRequest hash. Independent Standards review exposed a post-publication snapshot expiry gap. The formal `publication-red` reproduces renewal and the missing UUID return. `JudgeRuntime.grant` now completes validation, allocates and publishes a UUID, and returns it (including idempotent existing grant); native immediately records that UUID without another snapshot. `publication-green` and final targets confirm the fix. Existing callers that ignore the return remain compatible.

Final coverage includes current/historical identity, strict DTO limits, permissions/logout/restore/attachments, same-request idempotency, expiry and ABA, cross-session revoke and pending attempts, all auxiliary terminal releases, DB commit fault, bound event loop, provider collection, zero provider calls, and no secret/session token in stored rows.

## Final source hashes

- `src/cn_contract/domain.py`: `48a1c300bb9e48befdc74103af0819262192a689c56a4b4f464b9e33905dd667`
- `src/cn_contract/assistant/native_judge_control.py`: `c1bf0a6ada4a2c97dd27d6800082e37f77b7c68f9347f5ea2b6243065ae6a003`
- `src/cn_contract/assistant/providers/judge_policy.py`: `3e068fed410189352858584a9da6634bea308acf40142cdb0e6b8b0e92016601`
- `tests/integration/test_native_judge_authorization.py`: `9f763b171d02bc5310abc289ef73abcc43f3c0b7c53f46e56b273f62804c40c6`

## Limits and handoff

This slice does not expose a real paid entry or assert a vendor fee cap. It retains the existing single slot, registry, ledger and queue boundaries. Parent owns the private protocol/entry and the other agent owns the optional task stage. Main authorization, historical schema and HTTP were not changed here. Parent should use its independent review and pipeline/native acceptance evidence for the overall CH-05D1 conclusion.
