# D2g5c Standards review

Fixed point:421ffa5abf464c8e8c89a49ab02f7afa19246d8c; current working-tree scope:accounts.py,ingress.py,new generation_ingress.py and the two new generation-ingress test modules. Five-file SHA manifest, baseline hashes, standards-source hashes and actual case IDs are in standards-review.json.

## Findings

0 documented-standard violations;0 actionable smell findings. This is the Standards axis only. Spec is assigned separately. The reviewer authored the atomic test module, not the product implementation or root's main test module.

Sources:AGENTS.md,CONTRIBUTING.md,the actual D2g5c plan,Ponytail and existing module conventions. DTOs remain in domain.py; the change reuses the current SQLite transaction, canonical codec, domain receipts and persisted provenance. No dependency/schema/transport/UI or credential mechanism was introduced.

accounts.py:63-126 retains the existing legacy generation guard and extracts a reusable pure scope classifier. Direct membership/intake reads preserve the existing authorization model while avoiding the audit/rollback side effects of calling higher-level authorization helpers inside per-message classification. Existing compact naming and private helpers fit this module's conventions.

ingress.py:120-243 shares the existing parsing/dedup/journal/checkpoint pipeline rather than copying it. The added mode is private, default-false, and selected by the dedicated service; public legacy signatures retain their guard. Local imports handle the module relationship without initialization-time cycles. The transaction ownership and commit boundary remain explicit.

generation_ingress.py:13-103 is cohesive:validate native schema/provenance, classify targets, store fixed sidecars and expose the two dedicated operations. Helper boundaries add checks or domain meaning; none is an actionable middle-man abstraction. Repeated small identity checks protect distinct legacy/target boundaries and do not justify a broader authorization refactor. The supplied smell heuristics do not warrant speculative types, polymorphism, callbacks or a generalized ingress configuration.

The tests exercise real SQLite/service boundaries, recorded targets, commit failure, concurrency and restored copies. Fault injection observes actual SQL/commit behavior, with source integrity/state comparisons. No expected behavior is taken from a mocked service. Tooling-enforced formatting and broad task-integration claims were not duplicated as review findings.

## Actual verification evidence

Independent execution:15PASS,0FAIL/ERROR/SKIP,pytest21.11s,harness21.906s,exit0; twelve inputs stable, in independent-green.json/log/xml. Current three product files and atomic test still match those execution hashes. Independently read root-expanded.xml/log:37PASS,0FAIL/ERROR/SKIP,37.71s; not executed by this reviewer. The two module case-ID sets are disjoint, yielding52new distinct cases. Original independent module-missing1FAIL is retained separately, with its uncaptured RED-source SHA explicitly disclosed.

Broader related groups, publication, real-account/model behavior and WIN-PATH-02/native-crash issues are outside this Standards verdict. No additional tests, code changes, commits or other-chat operations were performed for the review.
