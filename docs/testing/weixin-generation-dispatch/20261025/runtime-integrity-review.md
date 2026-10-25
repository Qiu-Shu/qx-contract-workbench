# D2g5d runtime and integrity — independent cross-review

Baseline: `86daac9c6d13dae49dc30eac60113bda711625a9`. Reviewed the actual D2g5d plan, `generation_dispatch.py`, shared legacy `dispatch.py`, versioned `dispatch_integrity.py` and `generation_integrity.py`, plus their runtime/integrity test evidence. This reviewer authored the separate storage slice; **the storage implementation is excluded from this independent verdict**. No reviewed runtime/integrity product or test was edited here.

## Findings

**Final unresolved findings: 0. One confirmed defect was reproduced and closed.**

The initial dedicated query validated provenance through the generation validator only. With no generation rows, that parent validator returned early. A real legacy zero-target receipt whose time was moved to 2000 and whose hash was correctly recomputed was then returned successfully, although the exact v18 public dispatch validator rejected the same records. The independent synthetic probe recorded source hashes stable before/after and exited1. The runtime owner added explicit existing inbox/dispatch/grant validation, preserving valid legacy queries. The same probe now rejects the corrupt receipt; runtime tests include valid legacy receipt and both corrupt-time/checkpoint cases. This is a closed provenance-validation finding, not a reason to disable legitimate legacy queries.

Against the plan, new writes require exact native v19, current actual owner/principal/workspace, existing account generations, active non-restored state, root authority and exact current saved-target scope. Fixed queries/replays resolve the saved descriptor target rather than a later unrelated generation; read checks retain current case/intake/projection authority. Legacy public guards remain.

The shared delivery helper retains real TaskInbox collision/CAS/aggregation, receipt hashing and caller transaction ownership. No automatic freeze/model/network/send is added. Each `(root mapping,fixed binding)` stream keeps poll/ordinal prefix order; cursor intervals are compared only within a binding. Zero targets use the historical grant at receipt time. Root binding/conversation birth checks remain separate from later generation-target birth; receipt time covers poll/generation/event without requiring the wall-clock event time to follow the poll.

Only v19 enables nonzero receipts and removes the account-wide dispatch activity barrier. Frozen v17/v18 behavior remains explicit. Public v19 dispatch validates its core plus inbox/grants and the pure generation-chain helper; public generation validates dispatch before its private chain. This avoids public recursion while retaining scope/checkpoint/source/revocation parents. The final mapping-scope workspace check preserves the old condition as well as checking the effective target scope.

Repository standards/Ponytail review found no actionable duplication, speculative abstraction or other smell requiring an extra refactor. Private parameters in the shared helper serve the two actual legacy/dedicated callers.

## Actual evidence and limits

- Reviewer ran one independent **scenario** through RED and GREEN, not additional pytest cases: `independent-no-generation-query-red.log/.json` exit1 confirms the original defect; `...-green.log/.json` exit0 confirms its fix. The latest `...-green-final.log/.json` and `...-green-final-run.json` recheck the final conservative workspace-condition revision: **exit0, 2.032s**, all three captured runtime/validator hashes unchanged during execution. Repeated executions are not added as distinct coverage.
- Read, not rerun: `runtime-final.xml/.log` **29PASS**, pytest36.22s; `integrity-green.xml/.log` **11PASS**, pytest12.80s; root `atomic.xml` **8PASS**. Each XML has zero failure/error/skip. The runtime run captured dispatch validator `9879af95...` before the final conservative workspace-condition addition; this review checks the final `aa31cb8d...` source and final probe separately. Broader frozen root regressions belong to the root evidence, not this reviewer's execution.
- No real data/accounts/models/HTTP/paid/egress, installed release or whole-repository group was run. Archive/old-session/concurrency root tests were not repeated by this reviewer. WIN-PATH-02/native AV remain outside this verdict.

## Final reviewed SHA256

| Product file | SHA256 |
|---|---|
| generation_dispatch.py | `69e84f0d57f35b6c0098f5d89ebcc7511a387719d0865f94634913a75eecfa88` |
| dispatch.py | `a0d4dc1f99a6414e5696b69d6d07fc9e897038a6717586c10d6b85932619e2db` |
| dispatch_integrity.py | `aa31cb8d5e58fe3861264ffd1a585decce656816ebc69d13cff67c4f028eadcd` |
| generation_integrity.py | `95fde49967f4b61e9e7bc246606ee095941298afd553ebd23d0c02e68e2d3075` |

Full source/test/plan manifest: `runtime-integrity-review-manifest.json`. No new unresolved product finding was established after the final hashes were reviewed.
