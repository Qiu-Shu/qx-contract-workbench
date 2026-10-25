# D2g5d atomic and historical-test compatibility review

Baseline: `86daac9c6d13dae49dc30eac60113bda711625a9`.
Workspace: `D:/Documents/ChatGPT/律所项目`.
Review scope: the parent-authored new atomic test module and all ten existing integration-test diffs against the baseline. Read-only review; no product/test/Git changes or test reruns in this review.

Reviewer disclosure: I authored the separate generation-dispatch runtime and its runtime tests. I also authored the original semantic-preflight tests in the preceding turn. I did **not** author the parent’s atomic module or this turn’s compatibility edits, including the new preflight compatibility hunks. This report reviews those other-author changes, and is not an independent review of my own runtime implementation.

## Findings

**0 confirmed unresolved findings in the reviewed scope.** The compatibility changes restore exact historical fixtures and retain their rejection oracles; they do not relax historical fingerprints or silently replace historical behavior with v19 behavior.

- The old predecessor builders remove the new index and, where required, successor provenance sidecar before asserting the exact old schema. Dropping the dispatch table removes its index implicitly. The explicit schema assertions remain in place. This repairs fixture construction after fresh bootstrap advanced to v19.
- `test_weixin_provenance_schema.py:20,71,109` uses `CURRENT` for tests whose contract is “upgrade to latest” or “fresh equals upgraded.” Historical `TARGET` and frozen fingerprint/DDL checks remain historical. `test_weixin_generation_schema.py` now walks `VERSIONS[16:]`, covering every later native transition rather than skipping v18 when `CURRENT` becomes v19.
- `test_weixin_provenance_schema.py:202–215` pins its native crash-window fixture to the historical v17→v18 transition. `test_workspace_upgrade_semantic_preflight.py:130–145` pins only the marker-gap setup to the same first transition and asserts its exact v18 schema. The post-receipt corruption injection targets that actual first upgrade receipt (`:197–205`). The positive preflight test still reaches the real current version. Semantic validation, disk/original/marker/backup invariants and error oracles were not removed.
- `test_weixin_generation_integrity.py:175–208` explicitly reconstructs v17 for the no-later-poll rule and v18 for the global dispatch barrier. Those old adverse cases still require rejection. This correctly distinguishes the plan’s v19-only causality change from frozen v17/v18 semantics (plan lines 7, 10 and 18).

## Atomic and recovery coverage

The eight parent-authored cases use actual SQLite/session boundaries: SQL cursor or receipt failure and commit failure (`test_weixin_generation_dispatch_atomic.py:37`, three cases); two real competing dispatch threads (`:62`, two cases); append-versus-delivery race with a fixed old target (`:83`); another Python process finding the committed receipt without replay (`:94`); and two actual qxbak round trips with an independent synthetic DOCX original (`:120`). The rollback checks compare all tracked table state and permit a successful retry. The thread test accepts the legitimate serialization conflict only with an explicit subsequent retry and verifies final cursor slots. Restore checks require fresh login, exact original bytes and fixed receipt, inactive capability fences, blocked delivery and unchanged state/archive/source files.

These tests substantiate the plan’s synthetic transaction/recovery boundary (lines 9, 11 and 17), not a real account/model/transport or production end-to-end claim. The conservative new-write boundary remains covered by the separate runtime cases: native v19 plus generation-bearing account, current principal/role, account/peer revocation, root and fixed-target ACL, archive, exact saved target scope, restore fence, and fixed target rather than latest. The compatibility edits do not bypass these conditions. Replay/find deliberately have their separately specified current-ACL read behavior; requiring them to satisfy new-write scope equality would change the approved contract.

## Evidence read, not rerun

All paths below are relative to `.local/weixin-generation-dispatch-v19-20261025/`.

| Evidence | Actual recorded result | Interpretation |
|---|---|---|
| `atomic.log`, `atomic.xml` | 8 PASS, 0 failures/errors/skips; 19.87 s | Parent execution of the eight new cases. |
| `compat-before.log`, `compat-before.xml` | 3 FAIL, 1 PASS, 1 ERROR | Exact predecessor fixtures retained successor index/table after v19 bootstrap. These were fixture-construction failures, not evidence of a product fix. |
| `compat-after.log`, `compat-after.xml` | 5 PASS; 6.76 s | Parent reran the affected compatibility set. |
| `compat-extra.log`, `compat-extra.xml` | 153 PASS; 104.68 s | Parent ran full generation-service, generation-integrity and semantic-preflight modules. |

The sets overlap; this review makes no distinct-total claim by adding them. Parent’s final 12 short groups were still pending at review time. This reviewer’s new execution: **NOT_RUN**. Full repository suite, real accounts/models/paid calls/egress, Windows path/native crash acceptance: **NOT_RUN** in this review.

Per parent’s coordination report, WorkBuddy metadata identified `kimi-k3-2`, but the requested Bash operation was denied by its bridge and the task cancelled with `retry_safe=false`. No WorkBuddy report/code was adopted; it is not counted as an independent review and was not retried.

## Reviewed input SHA256

| File under `tests/integration/` | SHA256 |
|---|---|
| `test_weixin_generation_dispatch_atomic.py` | `9300224e85d6d6b95231674ec82908e1ff9d068b3c7ec36b5a4cfa382d5f79c5` |
| `test_weixin_dispatch_schema.py` | `23831dacd67ea32950a952e705bcd3ff82ca7dbe7d46d9ed5d37a3e61bd635ea` |
| `test_weixin_generation_ingress.py` | `c45a882e74da7e4cb09cc47a7d20325441d08429ce00821b8762a4e6a18f0a6e` |
| `test_weixin_generation_integrity.py` | `45c08b5b8d63887f2dda357d762477c6ef08e3a07eef770f5ea25630d479393c` |
| `test_weixin_generation_schema.py` | `5020869ae34a127f3eb8fe13d6631e4cfdc3948fc7037d536877d11d3cf20723` |
| `test_weixin_generation_service.py` | `985a7c530854dbdbbdd94f8a6c8cda1c6cecc37495744150bad32eb91deb84f8` |
| `test_weixin_inbox_schema.py` | `79e01d9e1045781e54de43046f438abcef71273b4ed00c911560f0077f608427` |
| `test_weixin_provenance.py` | `839f918986414f94db4dee9b891550688e79e7ea7ef4cf086c8361ca0cac7b80` |
| `test_weixin_provenance_schema.py` | `5532e71e8f9efeef13ed5f85825b9ebca0eeb1897f625bb7aa163a92204a8dea` |
| `test_weixin_reauthorization_schema.py` | `3a80431bb09089ddec7e91bcbdcf641c8f0cd15722577bb57f3fcdfeb72e5a09` |
| `test_workspace_upgrade_semantic_preflight.py` | `8501d0a411d05842589d9f06217477c859285f525d48b974e990e0633d353995` |
