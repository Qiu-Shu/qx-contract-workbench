# Task 1 implementation report

Workspace: `D:\Documents\ChatGPT\律所项目`. Branch: `codex/contract-review-v2`.

Commits: `580b8a6` (`feat: support unlimited DeepSeek grants and automatic defaults`), then `f885912` (`fix: restore saved automatic preference before reconfiguration`). Base: `9b2d801`.

Implementation and the review repair are committed. **The expanded Python group ended with exit 1: 469 passed / 3 failed in 619.54 seconds. All three failed test expectations were corrected and separately passed; the original group is not reported as an all-green run.** The parent independently re-reviewed `f885912` and confirmed SPEC/QUALITY PASS. No real model, Weixin, desktop UI, production profile, keys, or customer materials were accessed or used. No installation or publication was performed.

## Semantics and compatibility

- Every new desktop Main grant uses an explicit `max_total_usd: null`: ordinary, material, context and profile paths, plus the existing personal-Weixin automatic policy. Null means no monetary ceiling. Missing fields remain invalid. Jev DTOs, reservations, maximum budget and native validation stay finite and reject null.
- Existing positive Decimal Main budgets retain their caps. `budget_exceeded` is shared by native checks, reservation/enqueue, claim, additional rounds, archival integrity and the actual HTTP generation-capability caller. All reservations, call/round limits, expiry, ownership, config/basis hashes, usage and unknown fees remain recorded and checked.
- Unknown requests are never resent. A null budget does not turn an old unknown receipt into zero cost, and an unrelated new authorized intent may proceed while that original reservation remains recorded.
- Default automatic analysis is on for an available selected model/workspace. `model_auto_analysis: false` now records an explicit off; startup loading, backend restart, model changes and credential changes preserve the preference. Recovered workspaces retain their read-only block. Malformed/mismatched persisted scopes fail closed to false.
- Valid legacy desktop scope records with the two released input-size reservation amounts are recognized, and future Main grants use null. Existing finite ledger JSON is not rewritten; canonical policy bytes/hashes are tested unchanged. The old implementation represented both absent preference and an explicit off by an omitted field, so historical absence cannot identify an earlier off; per the approved default, absence becomes on. Explicit false is preserved.
- Existing JSON text storage accommodates null without a database schema change. A null-budget material output was included in the qxbak backup/restore tests. Older binaries that do not understand null cannot read these new Main-policy records; downgrade needs a compatible build. No old execution is reauthorized or migrated into a new grant.
- Main display is `DeepSeek V4.1 Flash`; provider API id remains `deepseek-flash`, and V4 Pro remains available. The setup cost disclosure states no fee cap; the old confirmation validators also accept/display null Main budgets without relaxing Jev validation.

## Actual verification

RED details, exact commands and limitations are recorded in `task-1-red-summary.md`. Additional raw HTTP RED log: `t1-http-red.log` (exit 1, 1 failed / 26 deselected, Decimal > None at capability). Initial Python RED: exit 1, 11 failed / 11 passed / 2 environment errors / 133 deselected. Initial Node RED: exit 1, 1 failed. The context environment error was the existing 40 GB disk gate on C:, resolved by choosing D: temporary directories rather than bypassing the gate.

| Command / scope | Actual result | Log |
| --- | --- | --- |
| Five initial integration files, same `-k` selection as RED, `--basetemp=.local/service-weixin-20261031/t1-pytest-green --tb=short` | exit 0; 24 passed / 133 deselected; 5 test-serialization warnings subsequently removed by using Decimal fixtures | `t1-python-green.log` |
| `node --test desktop/tests/*.test.cjs` (final committed product code) | exit 0; 412 passed | `t1-node-final.log` |
| `node --test scripts/test_assistant_generation_render.mjs` | exit 0; 21 passed | `t1-render.log` |
| `pytest -q tests/unit/test_main_unlimited_budget.py tests/integration/test_assistant_generation_routes.py -k 'unlimited or finite_policy or null_is_required or invalid_finite' --basetemp=.local/service-weixin-20261031/t1-small-final --tb=short` | exit 0; 9 passed / 26 deselected | `t1-small-final.log` |
| `pytest -q tests/integration/test_assistant_generation_routes.py --basetemp=.local/service-weixin-20261031/t1-http-fixed --tb=short` | exit 0; 27 passed | `t1-http-fixed.log` |
| `pytest -q tests/integration/test_assistant_rounds_runner.py tests/integration/test_native_judge_authorization.py -k 'bounded_two_round_run_completes or invalid_approval_limits' --basetemp=.local/service-weixin-20261031/t1-rounds-judge-final --tb=short` | exit 0; 13 passed / 60 deselected (includes null multi-round and rejected null Jev) | `t1-rounds-judge-final.log` |
| `pytest -q tests/integration/test_assistant_rounds_runner.py -k budget_exhaustion_between_rounds --basetemp=.local/service-weixin-20261031/t1-budget-boundary-final --tb=short` | exit 0; 1 passed / 19 deselected | `t1-budget-boundary-final.log` |
| `.venv/Scripts/python.exe -m cn_contract.cli schema --check` | exit 0; saved ReviewRun schema remains current; no schema generation change required | `t1-schema.log` |
| `.venv/Scripts/python.exe scripts/verify_defaults.py` | exit 0 | `t1-defaults.log` |
| `.venv/Scripts/python.exe scripts/verify_sources.py --mode development` | exit 0; 13 sources checked, all still NOT_PRODUCTION_APPROVED | `t1-sources.log` |
| `.venv/Scripts/python.exe scripts/verify_runtime_dependencies.py --mode development` | exit 0; native_build_verified=false; 0 network calls | `t1-runtime-dependencies.log` |
| `git diff --check`, `git diff --cached --check` before commit | exit 0 | tool output in this chat |

All abbreviated pytest commands use `.venv/Scripts/python.exe -m pytest`. Results overlap and must not be added into a fictitious distinct-test total.

The expanded group command (completed; exact original result retained) is:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/integration/test_assistant_generation.py tests/integration/test_assistant_generation_routes.py tests/integration/test_assistant_material_generation.py tests/integration/test_assistant_material_routes.py tests/integration/test_native_model_control.py tests/integration/test_native_context_control.py tests/integration/test_native_profile_control.py tests/integration/test_assistant_profile_execution.py tests/integration/test_assistant_model_backup.py tests/integration/test_assistant_context_send.py tests/integration/test_assistant_rounds_runner.py tests/integration/test_model_registry.py tests/integration/test_native_judge_authorization.py tests/integration/test_weixin_personal_runtime.py --basetemp=.local/service-weixin-20261031/t1-pytest-full --tb=short
```

Log: `t1-python-full.log`. **Exit 1: 469 passed / 3 failed, 619.54 seconds (10m19s)**. This run collected earlier test versions; all three failures were the already identified test differences. The new HTTP test initially expected 200 instead of the actual accepted 202 (fixed, final entire HTTP file 27/27 passed); two pre-existing cap tests still assumed the old 65,536-byte default while the baseline MainModelConfig already defaults to 262,144. The Unicode test now explicitly configures 65,536 and rebinds the policy config hash; the between-rounds test uses actual config input/output caps and an exact one-round reservation (final targeted boundary 1/1 passed). Both repaired tests have passed, without changing product caps or validation. These fixture differences are not described as product regressions. New null-budget double-round and null-Jev rejection cases were added after this group's collection and separately passed in the 13-case group. The final unchanged/patched cases have segmented validation; no complete rerun of the whole 474-case final integration collection is claimed.

## Files and remaining work

Exact own file list: `task-1-files.json`; committed stat and full `-U10` diff: `task-1-review-package.md`. There are 44 own code/test files. Shared `docs/TASK_STATUS.md` (the original 4-line WIP), design/plan documents and unrelated untracked evidence remain uncommitted and unstaged.

The parent independently reviewed `580b8a6` and found one P2 preference lifecycle bug (review: `task-1-review.md`). Its repair is committed separately as `f885912`; the parent re-ran the original probe with exit 0 and confirmed **SPEC/QUALITY PASS**. The expanded Python group has ended and its exact result is recorded above; its processes were confirmed absent at 2026-10-31 11:03:47. Task 2 global service-desk Weixin architecture remains untouched; only its existing policy accepts null. This is engineering validation, not installation, live channel or legal-quality acceptance.

## Independent review repair

The P2 was confirmed: after a synthetic credential replacement the runtime is deliberately unconfigured, and returning/reopening settings does not restart that backend. `reset()` defaulted the checkbox to on while the prior status projection omitted the persisted false for an unconfigured runtime. Thus an ordinary reconfiguration could silently turn analysis back on.

Before changing product code, three tests reproduced the page reopen, IPC projection and native lifecycle failures. Exact RED command:

```powershell
node --test --test-name-pattern='explicit off survives credential|projects the explicit off|credential replacement and settings reopen' desktop/tests/model-settings.test.cjs desktop/tests/model-session.test.cjs desktop/tests/model-settings-navigation.test.cjs
```

Exit 1, **3 failed / 0 passed**, raw log `t1-review-red.log`. The page test includes configured off → replace synthetic credential → ready → reopen unconfigured settings → configure, and verifies the configure payload remains false.

The existing main-process settings wrapper now reads the persisted preference even for an unconfigured runtime. The settings IPC preserves that boolean; the actual settings renderer uses it. No second preference store or new persistent field was introduced, and default-on remains the fallback only when no preference exists.

Targeted final GREEN command:

```powershell
node --test desktop/tests/model-settings.test.cjs desktop/tests/model-session.test.cjs desktop/tests/model-settings-navigation.test.cjs desktop/tests/model-bridge.test.cjs desktop/tests/judge-settings-core.test.cjs desktop/tests/judge-settings-ui.test.cjs
```

Exit 0, **93 passed**, raw log `t1-review-green.log`. Includes three new regression tests, previous default/restart/model-switch/credential tests, bridges and independent Jev settings. Only the affected suites were rerun after review; the earlier 412-desktop suite is evidence for `580b8a6`, not a claim of a new complete run on `f885912`.

After the repair, schema check and working/staged diff checks exited 0 (`t1-review-schema.log` plus this chat's tool outputs). Six own files were committed; the shared status WIP and unrelated docs remain unstaged. Scoped complete diff: `task-1-review-fix-package.md` (`580b8a6..f885912`, log/stat/U10).
