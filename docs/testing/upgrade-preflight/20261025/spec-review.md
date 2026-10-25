# Independent Spec review — native upgrade semantic preflight

Baseline: `3aa504524dd256dc2130605ee06604eb64432204`. Reviewed current `src/cn_contract/web/workspace_upgrade.py`, plan `docs/plans/2026-10-25-native-upgrade-semantic-preflight.md`, the new nine-case test module and relevant existing validators. Reviewer authored only the new tests; the reviewer did **not** implement or change product code. Standards review belongs to a different agent. This review did not rerun tests or change product/tests/Git.

## Confirmed findings

**0 confirmed unresolved Spec findings.** No missing or partial runtime requirement, incorrect behavior or scope expansion was established for this prerequisite slice.

- Plan:9 requires “按其精确旧版本执行” and prohibits Database initialization, missing-table creation, original changes, audit writes and new account/model capabilities. `_validate_history` (product:52-69) opens the exact path with existing `sqlite_readonly_uri`, an explicit SQLite read transaction and a bound SQLAlchemy Session, then reuses the full existing `_file_references` chain. It never constructs Database or initializes schemas; final disposal and context exits close resources. The actual attempted UPDATE test receives SQLITE_READONLY and leaves source bytes fixed.
- Plan:14 requires rejection “在任何升级备份/回执/marker变更前” and coverage of the committed-DDL/unfinished-marker gap. `upgrade`:123-124 validates source semantics before these changes; `pending_matches`:96-103 retains existing exact schema/FK/identity/hash checks and also validates the saved before.db under its own old schema. The current pending database is independently validated first. Tests cover a damaged current database and a semantically bad backup with a recomputed matching outer hash.
- Plan:9 also requires “每步 DDL 的写锁内再次核验原版本”. Product:152-156 repeats validation after BEGIN IMMEDIATE and before statements. A real receipt-write seam injects a business-only change and verifies rejection before DDL; an independent SQLite writer is blocked with SQLITE_BUSY during the locked preflight.
- Plan:15 requires legal old history/originals/finished steps to survive and repeated upgrade to create no extra receipt. The positive service-created v17 history, registered synthetic original, existing rows/identity and idempotent current-version call pass. Current-version matching-marker no-op retains the previous behavior; this patch does not claim to add a general current-database health scan on every startup.
- Plan:21 explicitly leaves v19 delivery for later. The only product diff is this native-upgrade module; schema18, DTOs, dispatch/intake guards, installed release and real capabilities remain outside the implementation. The v17-to-v18 laundering proof uses a later **poll**, matching the actual version policy; post-generation dispatch remains invalid in both versions.

## Actual test evidence and failure accounting

The reviewer executed the owned module during test development, not again for this review:

1. Formal initial RED: **3 failed / 1 passed**, exit1, zero errors. Each negative fixture was rejected by its original v17 business validator, but unmodified native upgrade accepted it. The later-poll fixture additionally passed the intentionally broader v18 validator after that unsafe upgrade.
2. Initial five-case expansion: **8 passed / 1 failed**, exit1. The failure was test-fixture PermissionError when reading Windows worker.lock inside the held byte-range lock. It did not demonstrate a product semantic defect. Only that snapshot was adjusted to omit the unreadable locked file, with its original bytes checked separately outside the lock. The original log/XML remain preserved.
3. Final expanded execution: **9 passed**, exit0, **0 failures/errors/skips**, pytest 18.84s (JUnit suite18.779s). Evidence: `.local/weixin-generation-dispatch-20261025/preflight-expanded-green-agent.txt` and `.xml`. No earlier/subset cases are added to this count.

Exact reviewed SHA256:

- Product `src/cn_contract/web/workspace_upgrade.py`: `65b90d4e0e8b0b125f35ceb40c6b5ff7d68d959da710edf17551c014e5c73549`.
- Tests `tests/integration/test_workspace_upgrade_semantic_preflight.py`: `e64865d68a33c7d9816940d4b5b442de0b3fa62a99b3f9935f60bd46fc98ac6f`.
- Final log: `2fdf6c0aaa98b0eb89bfeb06bba1e193706fc692191b9ec7064ea6d6648fee63`.
- Final XML: `f2d54dd633422f46124bc63b12a7b68b67b35a353e5eb5b9b7872f0e9954ec19`.

Root related regression/development gates, final documentation/GitHub/memory closeout are pending separate evidence and are not claimed completed by this review. No v19 dispatcher, installed-release validation, real WeChat/model/paid/egress/signing work was performed. Whole-repository long-process/browser/installed/real-capability verification: NOT_RUN; WIN-PATH-02/native AV remain open.
