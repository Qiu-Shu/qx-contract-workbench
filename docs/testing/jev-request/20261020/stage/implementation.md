# CH-05D1 optional Jev stage author evidence

Base: `27f224c`; only synthetic fixtures and local random-port HTTP were used.

## Implementation

- `src/cn_contract/assistant/task_manager.py`: optional exact `JudgeRuntime`, reserve on the same main transaction, original fixed main lease after one optional judge await, one existing task, and both unsent reservation types released by the existing callback.
- `src/cn_contract/assistant/providers/judge_attempts.py`: default reservation behavior retained; `optional=True` degrades only at explicit in-memory configuration/permission checks, input wire-size validation and actual budget comparison. Stored DTO/identity validation, `_budget`, write and readback failures remain exceptions.
- `src/cn_contract/web/assistant_generation.py`, `app.py`, `local_server.py`: optional runtime forwarding only; no HTTP permission/credential route.
- `tests/integration/test_assistant_judge_stage.py`: 36 new tests, including one actual synthetic loopback POST, one existing HTTP generation route, rollback/storage-error discrimination, admission-time expiry, cancellation, replay, receipt retention and no transaction across the optional wait.
- No dependency, schema, queue, registry, dispatch or UI additions. Native authorization and desktop assembly belong to the parent/other author.

## Actual executions

| Evidence | Command | Exit | Actual result |
| --- | --- | --- | --- |
| `red.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_judge_stage.py -q` | 1 | 5 failed: missing `judge_runtime` argument, no collection errors |
| `initial-green.log` | same | 0 | initial 5 passed in 8.87 seconds |
| `expanded.log` | same | 1 | 28 passed, one test fixture attribute typo (`protected_root`) fixed to real `storage_root` |
| `green.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_judge_stage.py tests/integration/test_assistant_task_manager.py tests/integration/test_assistant_generation_routes.py -q` | 0 | 84 passed in 36.90 seconds, including all final 31 new tests |
| `startup.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_model_startup.py -q` | 0 | 5 passed in 6.68 seconds |
| `expiry-red.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_judge_stage.py -q -k expiring` | 1 | 1 failed, 31 deselected: first snapshot passes, policy then expires and old second snapshot incorrectly rolled back main |
| `expiry-green.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_judge_stage.py -q` | 0 | intermediate 34 passed in 13.95 seconds |
| `final-green.log` | `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_judge_stage.py tests/integration/test_judge_attempts.py tests/integration/test_assistant_task_manager.py tests/integration/test_assistant_generation_routes.py tests/integration/test_assistant_model_startup.py -q` | 0 | final 157 passed in 78.92 seconds, including final 36 new tests and default old judge reserve regressions |

Counts in earlier runs overlap the final target run; do not sum them. `git diff --check` for owned source and test paths exited 0.

No build, install, commit, push, public network request, actual account credentials or real materials were used by this author. Independent review and final integrated source/frozen evidence remain parent tasks.

## Expiry finding resolved before freezing

The first implementation had a narrow admission-time expiry window in which the second runtime snapshot rejected Main. A failing regression reproduced it; the final implementation removes the duplicate pure precheck and places optional refusal inside the existing reserve function at precise trusted runtime calls. Expiry between configuration and permission validation skips Jev; expiry after its snapshot is sealed by the existing execution claim as not sent. Both continue permitted Main. Corrupt final readback and transaction rollback remain whole-submission failures. Final target evidence covers these distinctions; no known expiry limitation is being deferred.
