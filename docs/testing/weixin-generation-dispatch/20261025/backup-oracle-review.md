# Fresh-v19 backup rejection oracle review

Independent read-only diagnosis against baseline `86daac9c6d13dae49dc30eac60113bda711625a9`, workspace `D:/Documents/ChatGPT/律所项目`. This diagnosis did not modify product/tests/Git or execute tests; only this local review note was written at the parent’s request.

## Conclusion

Agree with the minimal test-only adjustment in `tests/integration/test_weixin_generation_backup.py::test_rehashed_hostile_generation_archive_is_rejected_without_publication`: change the two exact error-message expectations, at the create boundary (line 139) and restore boundary (line 148 in the reviewed source), from `WEIXIN_GENERATION_INTEGRITY` to `WEIXIN_DISPATCH_INTEGRITY`. Add a brief comment explaining the v19 first rejecting parent boundary. Do not widen the regex or change product error handling.

`ops/backup.py:182` invokes public dispatch validation before generation validation at line 184. For exact v19, `weixin_inbox/dispatch_integrity.py:158–171` additionally validates the pure generation parent chain and wraps that failure as `WEIXIN_DISPATCH_INTEGRITY`. Thus a rehashed invalid generation is rejected earlier at the complete dispatch parent boundary. It has not become valid.

The original test’s safety intent remains: recomputing hashes cannot allow an invalid generation to be backed up or published by restore. Keep all three damage payloads (`previous_scope`, `checkpoint`, `root_target`), chain rehashing, refusal to create an archive, zero destination publication and unchanged original/archive assertions intact. Do not downgrade the fixture to v18 merely to retain an old first-error name; that would remove coverage of the current fresh-v19 backup entry.

The direct public generation validator retains its own `WEIXIN_GENERATION_INTEGRITY` wrapper (`generation_integrity.py:121–131`). Its independent adverse cases (`test_weixin_generation_integrity.py:140–217`) already cover the relevant previous-scope, checkpoint and root-target defects. Those exact GEN assertions must remain unchanged.

## Actual evidence and required verification

Read `.local/weixin-generation-dispatch-v19-20261025/final-provenance.raw.log`: **105 PASS / 3 FAIL**, 123.70 seconds. All three failures are regex mismatches after the real backup creation path rejected with `WEIXIN_DISPATCH_INTEGRITY`.

All three cases currently stop at **create**. Their later hostile-archive construction and **restore** rejection assertions were therefore **NOT_RUN** in that execution. After the two oracle changes, rerun the entire final-provenance association group to verify both stages and all publication/file invariants. This read-only diagnosis is not a new passing test result.

## Additional dispatch fixture diagnosis: new UNIQUE constraint

Read `final-integrity.raw.log`: **230 PASS / 2 FAIL**, 160.88 seconds. In `test_weixin_dispatch_integrity.py::test_coherent_receipt_rehash_cannot_hide_broken_historical_provenance[binding/overlap]`, both failures occur while constructing hostile data, before receipt rehashing and before the validator assertion. The actual v19 unique index correctly rejects duplicate `(task_binding_id, expected_task_cursor)` pairs: changing the first receipt to the other peer's binding at line 216 collides with that peer's cursor-zero receipt; changing the second same-binding receipt to cursor zero at line 271 collides with the first receipt.

The parent's proposed minimal adjustment is valid: only inside these two adverse cases, drop `weixin_dispatch_binding_cursor` and immediately assert that the complete actual schema identifies as exact native `weixin-target-provenance-v1` (v18), then retain the original coherent-rehash and exact `WEIXIN_DISPATCH_INTEGRITY` validator rejection. The v19 schema differs by this one index, so this constructs a recognized historical archive rather than an unknown weakened v19 schema. Leave other damage cases on fresh v19, and do not weaken shared `corrupt`/`rehash_receipt` helpers, historical fingerprints or the product. Actual v19 duplicate-slot SQL rejection and refusal to migrate existing duplicate slots have independent schema cases (`test_weixin_generation_dispatch_schema.py:156,173`).

A smaller alternative preserves more fresh-v19 coverage for **binding**: the same branch already deletes the other peer's receipt for `task_event` damage to prevent its older UNIQUE from obscuring provenance checks. Extend that condition to `damage in ('task_event', 'binding')`. The target still names a real, wrong task binding, while the task event remains on the original binding; the provenance mismatch and final validator oracle are unchanged. Only **overlap** then needs the exact-v18 fixture. This alternative is recommended, but either locally scoped approach preserves the original historical-safety intention.

The two failing executions did **not** exercise their intended validator rejection. After the chosen fixture-only adjustment, rerun the complete final-integrity group; retain the failed logs and disclose the changed test-file hash separately from frozen product hashes. No test/product/Git modification or test execution was performed for this additional diagnosis; only this local note was appended.
