# C2b2b-A profile authorization kernel — development evidence

Date: 2026-10-23. Baseline: `60eb041536dc36dfd4133f0d09b909681146500c`.
Owned changes only: `src/cn_contract/assistant/providers/registry.py` and new `tests/integration/test_assistant_profile_authorization.py`.

Implemented full `MainProfileSendBasis` authorization keys via the existing `basis_digest`, max_calls=1 and callable-profile capability checks; profile submission/execution boundaries; and a lease wrapper passing the prepared request to the existing provider. The current profile basis builder regenerates actual current wire bytes and checks its full digest/byte length/configuration/template alongside the local save plan. Prepared DTO revalidation binds those bytes to the immutable wire. The dedicated preflight repeats current lease, policy, expiry, configuration and full content checks, independently repeated on return. Late valid candidates are removed while received usage/request identity survive. Ordinary/context/rounds paths reject profile permissions, including `granted_context_format`.

Profile preparation imports remain method-local; no new cold import chain for ordinary registry use. No DTO, schema, native/HTTP/runner/ledger/integrity-guard or installed-app changes. No commit or push by this subagent.

## Actual runs

All use repository `.venv/Scripts/python.exe`, independent synthetic identities/data, isolated SQLite where applicable, and `127.0.0.1` HTTP only.

- `red.log`: exit 1, **1 failed in 0.76s**. Valid behavioral RED: the new loopback happy path failed in registry.grant because the old implementation rejected MainProfileSendBasis; no remote operation.
- `green1.log`: exit 0, **1 passed in 0.75s** after implementation.
- `development-1.log` / `.xml`: exit 1, **56 passed / 1 failed in 2.35s**. The failure was test construction: MainContextSubmission omitted required `content`; product checks were not reached for that assertion. Fixed the fixture and preserved the original log.
- `development-2.log` / `.xml`: exit 0, **58 passed in 2.87s**, no warnings. Includes the corrected context fixture and the actual SQLite trusted-preparation-to-permission-to-loopback chain.
- `git diff --check -- src/cn_contract/assistant/providers/registry.py tests/integration/test_assistant_profile_authorization.py`: exit 0, no whitespace findings.

Final development command:

```text
.venv/Scripts/python.exe -u -m pytest tests/integration/test_assistant_profile_authorization.py -q --tb=short --basetemp=.local/profile-authorization-20261023/development-2-tmp --junitxml=.local/profile-authorization-20261023/development-2.xml
```

Coverage includes exact HTTP bytes, complete grant key vs content/wire key, single-call policy shape, missing provider capability, local save-plan variants, original draft identity/scope/composer/content/skill/attachments, bidirectional plain/context/rounds/profile isolation with shared workspace identities, actor/session/workspace/request ID/DTO/config mismatch, self-consistent forged wire, template changes, same-policy tombstones, idempotent same grant, revoke/regrant/configure/in-place config mutation/expiry, cross-event-loop refusal, transport checks during secret resolution, late received replies and an intentionally preflight-ignoring synthetic provider. No retry was observed: each permitted loopback case made exactly one POST; denied transport cases made zero.

Actual SQLite connection test uses C2b2a build_profile_basis, registry submission checks, service.save_message, C2b2a prepare_profile and execution/generate checks. The actual saved text is sent unchanged. The full database dump after save_message remains identical after prepare/generate; the run remains queued. This is not ledger consumption or archive saving.

## Remaining boundaries

max_calls=1 is a grant constraint, not persistent one-time consumption. Durable budget reservation, claim/settlement, real current-DB authorization at execution, handler saving and historical/restore activation remain subsequent work. New integrity guards and product entrypoints stay closed. Broader associated regression, independent review, four gates and publication belong to the root agent and are not claimed by this report.
