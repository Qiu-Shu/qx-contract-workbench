# C2b2b-B shared ledger/runner development evidence

Date 2026-10-23; baseline `9a0d2df3767dc8252f1530be4f949583fd250af2`.

Owned files: `domain.py`, `assistant/providers/attempts.py`, `assistant/runner.py`, and new `tests/integration/test_assistant_profile_execution.py`. `providers/history.py` required no change. Root separately owns profile_attempts/profile_preparation; an independent agent owns integrity changes. No native/HTTP/task manager/schema changes, no real material, external model, installed app, commit or push by this agent.

## Implemented

- Profile output/attempt DTO subclasses preserve full patch and explicit input format. History includes the new type after the existing legacy alternatives, and resolves its forward references.
- Public attempts add explicit lazy profile enqueue/current/settle dispatch, decode profile prepared input, rebuild actual profile wire, return profile DTOs, and prevent plain replay from retrieving a profile attempt. `_event` returns its already-persisted sequence for the fixed handler.
- Runner explicitly sends profile prepared input through generate_profile and retains MainProfileReply during normal/timeout/cancellation settlement. Network awaits continue outside DB sessions.

## Actual runs and findings

All commands used the repository `.venv/Scripts/python.exe`, independent synthetic SQLite workspaces, synthetic credentials and local `127.0.0.1` HTTP only.

- `red.log`: exit 1; 1 failed in 1.64s. Valid initial RED: actual workspace/registry test failed because enqueue_profile did not exist, before HTTP.
- `history-red.log`: exit 1; 1 failed in 1.07s. A profile-first union incorrectly redecoded plain reserved history as profile. This was an implementation bug detected by a behavioral compatibility test.
- `history-green.log`: exit 0; 1 passed in 0.99s. Existing alternatives remain first; all three DTO types roundtrip without format drift.
- `green1.log`/`.xml`: exit 1; 5 passed, 2 failed, 22 deselected in 4.78s. One failure was an inadequate fixture (principal_amount alone does not project into intake); corrected the happy-path response to include an actual sourced consultation. The second was a real product bug: security.deny inside the root settle nested transaction context prevented its audit write after rollback. Root fixed this with explicit savepoint lifecycle; original RED retained.
- `green2.log`/`.xml`: exit 0; 30 passed, 3 deselected in 17.90s. Save-failure tests deliberately excluded while root repaired the transaction boundary.
- `green3.log`/`.xml`: exit 0; **34 passed in 19.80s**, no warnings. Includes real denial audit persistence, durable session revocation after rollback, and all final ledger failure cases caught by the caller before normal outer commit.
- `git diff --check` on owned product/test files: exit 0, no findings.

Final development command:

```text
.venv/Scripts/python.exe -u -m pytest tests/integration/test_assistant_profile_execution.py -q --tb=short --basetemp=.local/profile-execution-20261023/development-ledger/green3-tmp --junitxml=.local/profile-execution-20261023/development-ledger/green3.xml
```

## Observed coverage

Actual SQLite → complete registry grant → enqueue/claim → local HTTP → fee/output/profile/intake/handler → history serialization, one POST and idempotent repeated retrieval; legacy messages/attempts cannot upgrade, plain replay cannot retrieve profile, changed save intent/body/policy cannot replay. Insufficient budget leaves the complete DB dump unchanged. Cancel/revoke/crash recovery never sends old attempts and uses unsent/unknown accounting correctly. Concurrent execution claims only once; an independent connection edits the next draft while HTTP waits. In-flight source/binding/cancel/profile/session/intake/grant changes retain received usage while discarding candidate/handler. Task cancellation and actual timeout do not retry. Invalid model source/citation/usage keeps cost without archive.

Saved/unchanged/blocked handler paths are exercised. Actual security.deny preserves its audit; durable revocation after rollback rechecks current access and keeps only fees. Failures at fee/output/handler insert roll back profile, intake, receipt and response event even when the caller catches the SQL exception inside its session and then commits normally.

## Limits

This report is not the root's final associated regression, integrity/restore verification or independent review. New internal execution is not an enabled native/HTTP/UI entrypoint or real-provider acceptance. Overall publication and project status belong to the root agent.
