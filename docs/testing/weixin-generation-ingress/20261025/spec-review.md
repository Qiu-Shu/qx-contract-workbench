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
