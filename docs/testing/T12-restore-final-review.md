# T12 independent restore final review

At the sealed source, **54 / 54 actual probes pass**, all commands exit 0. Common 200 source/config/rule/profile/prompt/schema/test/fixture/lock inputs remain identical before and after the sequential actual runs; the author 623-file freeze is independently recomputed with zero drift.

| Probe group | Actual denominator | Actual seconds | Result |
| --- | ---: | ---: | --- |
| Original format/path/auth/disk oracles | 15 | included below | PASS |
| Added fault after a restored original becomes read-only | 1 | included below | PASS |
| Combined disk/path/auth/format | 16 | 6.046 | PASS |
| Raw-schema and authenticated malformed archive | 14 | 3.953 | PASS |
| Actual raw/service restoration | 24 | 5.953 | PASS |

The outer same-source run exits 0 in 19.141 seconds. All three helper source drift counts are zero. Evidence paths are actual-f1/result.json, raw-f1/result.json, rich-f1/result.json, final-result.json and the before/after common snapshots.

Actual restoration preserves full raw schema, 38 physical tables, integrity and FK validity, unchanged source DB rows, and all historical rows/payloads except five explicitly allowlisted security delta tables. It revokes every old session, blocks both queued and running jobs, retains the durable fence after a new Database instance, rejects old-token/new-patch/current-bundle/download/direct-T08 operations, and records mock factory dispatch count zero. Unknown cost remains exactly 15 used, 5 remaining, one call, with BUDGET_EXCEEDED rather than a generic fence being the tested reserve outcome.

With the old source store temporarily unavailable, the actual original, four export files, and a nonempty independently applied patch are read from the new root and match source bytes/hashes. Whole-paragraph accept/reject equivalence is independently parsed from OOXML. This is a structural check; native Word is NOT_RUN.

Three actual materialization failures each inject once, including after read-only file creation, and leave no nested database/staging/published root. Source DB hardlink and actual reparse/symlink inputs are rejected before archive creation. Raw dropped/changed trigger, dropped/extra table and FK corruption are rejected without repairing their bytes; matching archive hash/table evidence is deliberately re-signed so the intended raw boundary is exercised. Bad logical reference, record hash, encrypted ZIP and unsupported ZIP method 99 are controlled rejections.

History remains intact. Five actual strict-format RED cases precede the sole writer's fixes and same-oracle closure. Auxiliary failures remain separately documented: wrong import name (no restore), exact exception-name oracle error, owned 255-character path preventing a requested disk injection, and initial builder with zero applied patch result records. An empty loop is not accepted as patch restoration proof. current-actual.json retains the original histories and counts; no old evidence was refreshed to a later source.

No business/tests/config/status/Git/Vault writes, installs, real network/provider requests, browser, native Word, production account/key generation, or secret search occurred. Public fixed fictional key bytes were used and never logged. Real OS isolation, domestic approved deployment/TLS, legal gold, real source/account/data policy approvals and live smoke remain NOT_RUN or BLOCKED; this review does not claim full OS sandbox or production completion.

The original PREPARATION report and seal remain byte-identical. The root's full suite/release CLI/Git operations and other reviewer network/secrets/readiness work are separate evidence, not counted in these 54.
