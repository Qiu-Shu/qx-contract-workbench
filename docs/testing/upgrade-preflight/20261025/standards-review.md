# Native upgrade semantic preflight — Standards review

Fixed baseline: `3aa504524dd256dc2130605ee06604eb64432204`. Reviewed current `src/cn_contract/web/workspace_upgrade.py`, the actual native-upgrade preflight plan and the frozen new semantic-preflight test module. This reviewer wrote neither product code nor that test module. Spec is a separate agent's axis.

## Findings

**0 documented-standard violations; 0 actionable smell findings.** Standards sources: current AGENTS.md, CONTRIBUTING.md, Ponytail, code-review's smell baseline and existing native upgrade/backup conventions. Repository conventions override stylistic heuristics; tooling-enforced formatting is not duplicated here.

`workspace_upgrade.py:52–69`: the small private helper owns the native read lifecycle and reuses the existing complete backup-family validator. Its mode=ro URI uses the existing filename helper; no Database construction, initialization, storage flags or directory creation is introduced. Explicit BEGIN gives the multiple SELECTs one SQLite snapshot. The Session and Connection contexts unwind before finally disposes the engine, on both success and failure. It needs no configured Database/session info and starts no model/network/task operation. The fixed error hides data-bearing validation exceptions; existing marker I/O and DDL failure handling remains outside that normalization.

`pending_matches:96–103` retains hash/schema/integrity/FK/workspace checks and additionally validates the original-version saved history. `upgrade:123–128,152–164` checks the actual history before publication or pending-marker finalization, then checks each committed old schema again while its writer reservation excludes independent writes. The separate reader closes before DDL/commit. Valid marker/current-schema no-ops retain their existing behavior; older recognized schemas keep their family-specific skip rules.

Repeated calls protect different trust transitions rather than duplicate implementation. The helper adds transaction/resource/error responsibilities, so it is not a pass-through middle man. No speculative type, registry, new schema/DTO, generalized callback or repeated business-validation implementation is warranted.

The new tests use real synthetic native files, old schema reconstruction, original bytes and genuine row corruption with immutable DDL restored. Fault seams observe actual SQL read-only refusal, SQLite locking and marker/DDL boundaries. Expected service behavior is not replaced by mock return values. The narrow worker.lock snapshot exclusion is explained and its original bytes are checked separately.

## Actual verification evidence

Reviewer executed **two standalone synthetic probes**, exit **0**, harness **17.828s**; no pytest groups rerun. An independent WAL writer committed while the actual helper retained its original read snapshot. Success and injected-validator-failure paths both emitted engine-disposed/connection-close events; subsequent DBAPI use failed as closed. The failure sample's database bytes and all three captured product-input hashes stayed unchanged. Evidence: `.local/upgrade-preflight-20261025/independent-standards-probe.py`, `.log`, `.json` and `independent-standards-run.json`.

Read, not rerun: `.local/weixin-generation-dispatch-20261025/preflight-expanded-green-agent.xml/.txt`: **9 PASS, 0 failure/error/skip, 18.84s**. XML SHA256 `f2d54dd633422f46124bc63b12a7b68b67b35a353e5eb5b9b7872f0e9954ec19`; raw log SHA256 `2fdf6c0aaa98b0eb89bfeb06bba1e193706fc692191b9ec7064ea6d6648fee63`. These are the other agent's execution, not this reviewer's.

## Reviewed file manifest

| File | SHA256 |
|---|---|
| src/cn_contract/web/workspace_upgrade.py | `65b90d4e0e8b0b125f35ceb40c6b5ff7d68d959da710edf17551c014e5c73549` |
| tests/integration/test_workspace_upgrade_semantic_preflight.py | `e64865d68a33c7d9816940d4b5b442de0b3fa62a99b3f9935f60bd46fc98ac6f` |
| docs/plans/2026-10-25-native-upgrade-semantic-preflight.md | `215cebb79ff48ca05b294c8e7a225b765117b8f34339eb3494ef6117d28d7f22` |
| AGENTS.md | `e0fcf27d3a2b5aca6c09d5372c869a312dfc6dba558dcb67581ef9f5ffbe755f` |
| CONTRIBUTING.md | `5248771a8f16f535d9a8db2334ee54eb3e9c33c9f7c6469be5e2d88f49fc341a` |

Broader root regressions, release gates, installed build, real accounts/models and Git publication are **NOT_RUN by this reviewer**. This is record-level historical validation, not independent physical-original verification or a production-readiness verdict. No product/test/configuration/Git edits were made; only this report and owned local synthetic probe artifacts were written.
