# C2b2a trusted profile preparation — development evidence

Date: 2026-10-23. Baseline: `2997d4602d842c6cab8e514a4c7340085910ad0c`.
Scope: only the new `assistant/profile_preparation_service.py` and its new integration test file. No runtime entry, schema, migration, network, real data, commit or publication changes.

The service reads actual current principal/session, owned conversation, active-workspace state, selected materials, saved run/user message, profile revision and intake revision. It rebuilds the exact service submission digest and complete offline basis. Later typing can increase composer revision but cannot alter the prepared saved source. Existing profile binding and nonfuture source revisions are checked. Returned DTOs prove consistency only; they are not send/save permission.

Read-only boundary: this service performs no proactive business/model/profile writes. It deliberately retains the shared authorization helpers' flush behavior and denial audit transaction. It does not promise arbitrary caller sessions or permission failures leave the entire database unchanged.

## Actual development runs

All commands use the repository `.venv/Scripts/python.exe`, independent SQLite synthetic fixtures and isolated basetemp directories under this evidence directory.

- `red.log`: first behavioral test, exit 1, 1 failed in 1.36s; module absent. Valid RED before implementation.
- `green1.log`: same first test after implementation, exit 0, 1 passed in 1.29s.
- `development-1.log` / `.xml`: complete new-file first pass, exit 1, 46 passed / 1 failed / 1 warning in 22.77s. Failure was a fixture: attempting to redirect a run to another existing run's message hit SQLite UNIQUE before exercising the product. Corrected the synthetic corruption to move a message to another existing conversation. Original files were moved from `target.log` / `.xml` after process completion, preserving evidence for the root's separate final target run.
- `warning-red.log`: added explicit assertion that invalid config DTO cannot echo a private malformed field through serializer warnings; exit 1, 1 failed in 1.33s. Then added warning-free config revalidation in the new service.
- `development-2.log` / `.xml`: final new-file target, exit 0, **49 passed in 23.55s**, no warnings.

Final target command:

```text
.venv/Scripts/python.exe -u -m pytest tests/integration/test_assistant_profile_trusted_preparation.py -q --tb=short --basetemp=.local/profile-trusted-preparation-20261023/development-2-tmp --junitxml=.local/profile-trusted-preparation-20261023/development-2.xml
```

Coverage includes exact draft and persisted text, scope/composer, explicit skills/attachments, current selected materials, same-owner different session, revoked session/role/ownership/workspace, archives/restore fence, cancelled/completed runs, altered digest/request/scope/message, stale profile/intake baseline, converted intake, incompatible profile binding or future source, changed config, forged DTO validation, and preserved matter-denial audit without profile records.

Root owns the stable associated regression, four gates and independent review. Those results are not asserted here. Actual model calls, authorization grant issuance and fixed-handler persistence remain unimplemented in this slice.
