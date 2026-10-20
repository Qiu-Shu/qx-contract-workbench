# CH-05D1 independent Spec review

Reviewer: `/root/jev_request_spec_review` · 2026-10-20 · read-only product review.

Base: `27f224c6568fcfdd4c16f49c6533cf9741dbb464`. `git log BASE..HEAD --oneline` is empty; the reviewed change is the working tree against BASE, including the new untracked tests/helpers. Sources: `docs/plans/2026-10-20-jev-request-backend.md` and approved `docs/plans/2026-10-20-jev-native-handoff.md` §§3–4. CodeGraph located the actual assembly/call sites; current source and diff were read directly.

## Spec

No blocking implementation finding. Verified statically:

- Independent backend approval reads the actual owned draft, authenticates the current session, predicts only input_revision+1, uses the full JudgeRequest/config/template codec hash, and publishes its grant/tombstone after the database context commits. Historical existing requests cannot gain a fresh execution grant. Changes, revocation and configuration replacement do not revive an old intent.
- A persisted reserved/sending auxiliary attempt prevents a replacement grant even after expiry, revoke or reconfigure. Revoke checks the policy-owning session. Main authority is not Jev authority.
- A single task reserves both ledgers before dispatch, captures the original Main lease, executes the auxiliary runner then that Main runner, and clears both unsent reservations. Expected optional failures are caught only at configuration/permission/wire-size/budget checks; stored DTO and transaction failures propagate. No extra deadline or task manager was added.
- A new explicit private-pipe capability gates authorize/revoke; no renderer authorization IPC or HTTP route was added. D1 correctly leaves the confirmation UI, real price/budget adoption and real vendor execution to later work.
- The driver distinguishes source loopback execution (Jev then Main, same run, full input hash, unknown cost and unverified decision) from frozen authorization/revoke/disable/restart rejection only. Its read-only inspector asserts the claimed ledger relationships. Network observations are explicitly limited; this review did not execute those probes or treat their code as proof of a passing run.

Documentation alignment item resolved: the execution plan now states that expiry can free the slot when no unfinished Jev attempt remains, including an old Main run with no auxiliary attempt. This agrees with the one-time reservation rule: historical Main runs never gain auxiliary work later.

Follow-up review: the Standards review's publication/expiry issue was fixed by returning the fixed authorization identity from `JudgeRuntime.grant`, then storing that identity in the native tombstone without a second time-sensitive snapshot. No post-publication validation can now omit that tombstone. The two added regressions cover expiry immediately after publication and stable grant identity/revoke replacement. This reviewer read the correction/tests; it does not claim to have executed them.

Final Spec result: 0 unresolved findings, no scope creep identified. No UI or real-vendor completion is claimed.

No tests, GUI runs, builds, real provider calls, commits, or pushes were performed by this reviewer. Parent-owned execution evidence remains separate.

## Reviewed file SHA-256

Hash snapshot includes the implementation and probe files; recheck after author completion and any further edits.

| File | SHA-256 |
|---|---|
| src/cn_contract/domain.py | 48a1c300bb9e48befdc74103af0819262192a689c56a4b4f464b9e33905dd667 |
| src/cn_contract/assistant/native_judge_control.py | c1bf0a6ada4a2c97dd27d6800082e37f77b7c68f9347f5ea2b6243065ae6a003 |
| src/cn_contract/assistant/providers/judge_policy.py | 3e068fed410189352858584a9da6634bea308acf40142cdb0e6b8b0e92016601 |
| src/cn_contract/assistant/providers/judge_attempts.py | 007aacd4c21772be95b4fc5479f46a05d07380afeafe8b34c12f137216e1504c |
| src/cn_contract/assistant/task_manager.py | 699c3a6e850737d1c898a0a89521bf80a673b2b912ef126a2e24c6a131aae032 |
| src/cn_contract/desktop_control.py | 0987b5e9774f34bc9ece6b6499aaf3962eb08db360772f7b141c10a46ef4a7df |
| src/cn_contract/desktop_entry.py | bb5f21014427156e2b8d3f3d9b693cec97a7b1761206aa0775f02cd6eecf1291 |
| src/cn_contract/web/assistant_generation.py | 30d4e99881e920f84391621008a3053dbe273938c73bf1dab1b79f9f04d5fe30 |
| src/cn_contract/web/app.py | 039f8a079fc0686b745dcc18e7416e9b90a2475b31f81192f42aae42b265aa1d |
| src/cn_contract/web/local_server.py | d1b127e3307e482784ddc879c647b08536eef8b7dea4eee56e8287d3c7da9958 |
| desktop/model-control.cjs | 629daf1da2323966f6210c3d37f12627717b6de57298d5d9c10fbd6a8103534a |
| desktop/backend.cjs | 38941f3a9893182cbefeacef82b0eb8b4e838bf2abf2a6694bb58f68d25b8779 |
| desktop/tests/model-control-acceptance.cjs | 896e06616cc41459c45f576cdb24c7dddaa922499311b599171d3b969f620505 |
| tests/helpers/synthetic_native_control_entry.py | 2e0a0bc8fddb3c55d3ce449e4420c6891f8d9bc191a6ca1f3af77426bbc61cc6 |
| tests/helpers/inspect_native_control_records.py | acb4e0a4a5d6ce4c6a0c191fc6a8e0d076aba7425a90dd98fb7817618142ad3c |
| tests/integration/test_native_judge_authorization.py | 9f763b171d02bc5310abc289ef73abcc43f3c0b7c53f46e56b273f62804c40c6 |
| tests/integration/test_assistant_judge_stage.py | 977d0510021e9bd9dc89381f3215d0ec28ceff1d943aa105bf8d1216375d3681 |
| desktop/tests/judge-authorization-control.test.cjs | 544ffcc4cebf1364af00bacab5851a41ef1da5ac02f3de488eb54ce14bf4840e |
| tests/unit/test_judge_authorization_protocol.py | c34e10fdfb5d96fb2581549400e593f1df3ba0ac5be229daed09c47be700060f |
| tests/unit/test_desktop_control_protocol.py | cd560fc25e016990fe6eae74c7723e11ab0ce7cb75ba9794a04b17eb73136072 |
| docs/plans/2026-10-20-jev-request-backend.md | 09349751107c737fa60ef7447a4a65c824e8ffb10b8afea08f0422d61842d3fd |
