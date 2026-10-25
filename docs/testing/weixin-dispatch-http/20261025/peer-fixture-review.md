# Peer fixture correction for HTTP service validation

The existing `accounts.bind_synthetic_peer` uses `_account(active=True)`, which correctly rejects new peer binding after an account has generation history. The first combined service run reached this guard while arranging the same-account foreign-peer negative test. This was a fixture order error; no product guard or expected HTTP denial is relaxed.

Only two test functions change in this correction:

- `setup(chat, *, other_peer=False)`: optionally create and bind the second peer before the first root generation is appended, then return that mapping.
- `test_cid_cannot_choose_another_peer_or_account_descriptor`: request the prebound second peer for the same-account case. The independent-account case still creates its account, binds its peer, appends a generation, and only then records a synthetic poll. The 403 assertions and no-mutation assertions remain intact.

The first combined service run was **61 PASS / 3 FAIL** and is not final acceptance: its HTTP test input drifted while three ACL fixtures were changed from immutable owner corruption to the existing `deny_projected_case` current-ACL helper. The separate peer fixture order issue described here is now corrected. The full combined service group must be rerun on the frozen final files; this correction itself does not claim a fresh test result. The original failed-run evidence is retained by the root runner.

AST comparison against `http-test-before-peer-fixture.py` confirms that only the two functions above changed; all other functions, including the 403 assertions, are unchanged by this peer correction. No product file is modified in this correction.

Before SHA256: `0b4f53f5422f4cc52c680c8f45cafa838495ea39991b70c2b63a5d7106b664d7`

Final frozen test SHA256: `d8e09461b24d37ad531fde82373098522783994b152307e34bc77a30285a6d78`

## Root ACL denial audit oracle correction

The complete post-peer run was **63 PASS / 1 FAIL** with stable source inputs. The remaining root ACL test assumed that all tables, including `audit_events`, must remain unchanged. Existing `security.deny` (security.py:111-126) intentionally rolls back business work and separately commits one `authorization_denied` audit. The root HTTP authorization path correctly retains this existing behavior. No product change is needed.

Only `test_get_uses_current_root_and_fixed_target_acl_without_latest_substitution` changes in this correction, plus standard-library `hashlib`/`json` imports. Root denial must preserve the exact old audit-row prefix, append exactly one row, and keep every other table unchanged. The audit payload is parsed, its stored `reason_sha256` is verified against `CROSS_MATTER_DENIED` (raw reason must remain absent), then that verified reason is reconstructed only for strict `d.AuditEvent` validation. The test checks action, actor, correlation ID against the 403 response, empty before/after hashes, target matter/entity, and consistency with the stored row header. Fixed-target and later-target branches still require the entire state to remain unchanged.

The test file before this change is retained as `http-test-before-audit-oracle.py`. No tests were rerun by the author for this correction; the root will rerun the entire 64-case service group. No product files were modified; the three reviewed root product hashes match the cross-review manifest.

Before audit-oracle SHA256: `d8e09461b24d37ad531fde82373098522783994b152307e34bc77a30285a6d78`

Final frozen HTTP test SHA256: `0337d1cbbc0a8d0c811e855c5b70c1be6f60e2b8ea56520350a4d931185effe7`
