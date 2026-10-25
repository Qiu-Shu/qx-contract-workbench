# D2g5c Spec review

Baseline: `421ffa5abf464c8e8c89a49ab02f7afa19246d8c`; review covers the frozen three product files and two new tests, including untracked files explicitly. User AGENTS.md is excluded. Standards is a separate review axis.

**Confirmed findings: 0.** No missing/partial runtime requirement, wrong behavior or scope expansion was confirmed in the reviewed implementation.

- Plan:7 requires “schema18精确门” and “旧record_synthetic_poll/accounts/dispatch的全账号暂停保持”. `generation_ingress._validate/record_generation_poll` enforce exact native schema18, actual account principal, recovery fence, account revocation and existing generations; legacy `_account`/`_mapping_reason` guards remain.
- Plan:9 requires “逐条分类使用纯读取” and “根旧版本不锁定新代scope”. `_scope_reason` performs current object ACL checks without denial audit/rollback; `_scope` separately checks root archive, root authority, root revocation and the complete current target snapshot.
- Plan:11 requires sidecars “同事务写入”, `after=True`, and cross-generation replies “整体VERSION_CONFLICT回滚”. Shared `_record_poll` preserves complete receipt hashing/global source dedup/checkpoint CAS; original nonzero accepted descriptors alone receive sidecars, and complete pre/post provenance validation rejects both reply directions before commit. The intentional whole-poll rejection is not a defect against this contract.
- Plan:13 requires “按descriptor sidecar的历史目标核当前权限” and fixed reads after restore/logical revoke/archive. `_readable` resolves the immutable historical target and checks its current root/object authority without redirecting to unrelated later targets; writes still require an active workspace and account. No dispatch, task creation, network, schema/DTO or HTTP/UI expansion appears.

T02/T12 policies were checked for backend ownership/current case access, immutable source/receipt handling, no sensitive denial body, and actual recovery isolation. Existing fixture-only data is synthetic. No claim is made that this limited slice satisfies all deployment requirements.

Evidence was **read, not rerun**: final root XML has 37 passing cases and independent atomic XML 15, giving **52 distinct new cases**; earlier 24-case GREEN is a subset, not additional cases. Product hashes match the independent runner's recorded after-hashes. Exact file and evidence SHA256 values are in `spec-review.json`.

Reviewer test execution: **NOT_RUN**. Related regression/release gates, final docs, push and memory closeout remain root responsibilities; installed release, real WeChat/models and production readiness are not verified here.


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


## Root final regression input manifest

Two distinct agents reviewed Spec and Standards separately. Root final groups are reported in verification-summary.json; broader root tests were not rerun by those reviewers.

- src/cn_contract/assistant/service.py: `b6e9c2c9825ede962be21c2385d0109b7712130405edbeed58a2b869d2c6baa0`
- src/cn_contract/domain.py: `f7b60f495e7805a8cc975e35b36595f38b31c1e1084d3856a2fe34261a1bc484`
- src/cn_contract/ops/backup.py: `98a3b95cb0b2a441ee3fc993296f682602b2d86b289621fe76e228779fe82914`
- src/cn_contract/ops/storage.py: `e24f24b955a579961b4cc20561e19f821f762b59230311d7a193c1f6328be4ef`
- src/cn_contract/ops/workspace_backup.py: `0cebe362b20104388e4ec1c084d5fdae82bbcbd18a42dd23efc0160c82afc1ad`
- src/cn_contract/persistence.py: `484ed202bd64e20f60d8223275d77d1db905d9b053e2f157db925988386c41b8`
- src/cn_contract/schema_migrations.py: `b6713c93db048d81bf1ec61c525b9950141f7de332a6163cb06cb960a89713e3`
- src/cn_contract/security.py: `d6457c56fc6a6889e0ac2848dc77b037b9806e125b2d3532a52275697662b7f2`
- src/cn_contract/storage_schema.py: `5078d534021c033ad8f36ee40b25b4056ffe279ae7de6fdfd6574d0f69d0ace1`
- src/cn_contract/weixin_inbox/__init__.py: `9ab4894319ed501c3a2292f74b13117a740b19979ad6ba0d5ef47c6a04036c62`
- src/cn_contract/weixin_inbox/accounts.py: `0ab2584d848a7af293970594d157743a5028b63a040481596d0f0dac51d85f13`
- src/cn_contract/weixin_inbox/conversation.py: `de25074489e652d20493850763559ea3fe36ca2ba35381cb0cfdba5ba752e96f`
- src/cn_contract/weixin_inbox/dispatch.py: `e991919b6d20de81f6bb9fbfbd1cfb171e30f15760b4d80bde144d15978a907f`
- src/cn_contract/weixin_inbox/dispatch_integrity.py: `bb21beeddfe56d9ff98919e43c24339c49cdb352b9a66568cc717ed1bb19c842`
- src/cn_contract/weixin_inbox/dispatch_schema.py: `998edb572830f2e2b421dc531b42af506edec0def2188fc065bf32ef1980aed1`
- src/cn_contract/weixin_inbox/generation_ingress.py: `2808b2d4d4e354a500cdfe73b706fb27a59be15c1533c13620c8fb24e9d0b0aa`
- src/cn_contract/weixin_inbox/generation_integrity.py: `1674aa1e9e0dcf2fd299406a8c29d121b5f81e245e2795eab96ce712d0ebd713`
- src/cn_contract/weixin_inbox/generation_preview.py: `369eff7d04fd3a39f992d1feab5983ea06575389f0c695110fb682180c820381`
- src/cn_contract/weixin_inbox/generation_schema.py: `63a84364a5286e6882dadd393162d93a74edae1cadf44acf74443ee337832d37`
- src/cn_contract/weixin_inbox/generations.py: `d1aed5228cd5bd748a0b44b87ef7e4eb88eb3adf5b85260b0fd199118bcd9314`
- src/cn_contract/weixin_inbox/grant_integrity.py: `cf8f4abf159d46a428b71196656ef56d4e89384372b099cd52db298b01d9af1f`
- src/cn_contract/weixin_inbox/grant_schema.py: `1dde13e8a4fa60846f28353329a48952a010df25109d3aab2d10b8d2217142a5`
- src/cn_contract/weixin_inbox/ingress.py: `4faebd87c657dd5d4ab6a26eac77fa3f78af2ef3a0163271aeb5fc6dd736b093`
- src/cn_contract/weixin_inbox/integrity.py: `57fd638d5b2d376fd8a31c5f2a16e60f63dd45cfddb34907e13693282892dc9e`
- src/cn_contract/weixin_inbox/provenance_integrity.py: `796f9de705f5fc35c4161e636b9b2eae1f3f27679c09f580e36ea9c59c90765e`
- src/cn_contract/weixin_inbox/provenance_schema.py: `60ef8b979a47408409aa573938266d9b48c053c8cd37956b2ac212704823c341`
- src/cn_contract/weixin_inbox/schema.py: `e194dc41c69c1b1e0103f8c17557715dbdc46ef95a4771427e07d1c10fcacdf0`
- src/cn_contract/weixin_offline.py: `d76e22e9f0780284134a441d9dc79f8794269632855ac76b217f25f41527022a`
