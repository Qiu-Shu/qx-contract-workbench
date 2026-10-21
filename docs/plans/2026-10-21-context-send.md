# CH-06B2b2：资料辅助发送闭合切片执行计划

基线：`09db5f666305e2e048012b1d3655c742ed110c7b`（codex/contract-review-v2）。依据已复核的 [存储与接线设计](2026-10-20-context-send-storage.md) 与已完成的 B2b2a 适配基础。执行者：WorkBuddy（本机直接实施）。

## 本片范围（一次闭合后才启用应用发送）

1. **schema `assistant-context-v1`**：`assistant_model_attempts` 增加不可变 `input_format`（`plain-text-v1`/`library-context-v1`，旧行迁移为 plain）；新建有序关联表 `assistant_model_input_citations`（attempt_id+ordinal 主键、attempt_id+saved_citation_id 唯一、FK、禁止 UPDATE/DELETE）；替换 immutable input trigger 纳入 input_format。
2. **入口一致**：新 `assistant/context_schema.py`（ALTER 序列，新建库先 V1 后同 ALTER）；`storage_schema` 追加版本且 library rows 覆盖新后继；`schema_migrations`/`storage_bootstrap`/`model_schema.initialize_storage` 明确接受新结构、拒绝半迁移。
3. **登记与生命周期**：`attempts.py` 私有格式分派；`enqueue_context` 在同一 begin_nested 完成 message/run/attempt/来源关联/预算/reserved event；同一 request_id 幂等；claim/settle/read/history 按格式分派；上下文分支零 Jev 预留。
4. **原生一次许可**：`NativeModelControl.authorize_context` 服务端重建 manifest 核对 basis，策略 `allowed_content_sha256s=(manifest_sha256,)`、max_calls=1；registry grant/lease 显式区分两种 basis 类型；旧 V1 许可语义不变。
5. **归档恢复同一 seam**：`context_integrity.py` 纯校验（清单/关联/原引用哈希/同 scope/输出引用子集），`model_integrity` 按版本+格式分派；attachment/judge/library integrity 白名单加新版本；恢复 fence 复用 `recover_attempts`，不重建许可、不重发。
6. **应用入口**：`POST /api/assistant/conversations/{id}/context-generations` 经 `GenerationTasks.submit_context`；网页不能自选 input_format。律师选片 GUI 与桌面确认窗不在本片；真实供应商/账户不在本片。

## 验收（对应设计 1–10 组）

冻结 library-v1 fixture 升级逐条比对；bootstrap/upgrade/qxbak 三入口结构相等；旧 0d53fdf 代码拒绝新结构；ALTER/trigger/关联表中途失败原子回滚；格式与关联损坏矩阵在读取/claim/备份/恢复全拒；登记事务中途失败整体回滚；多状态 roundtrip（reserved/sending/received/拒绝含usage/failed_before_send/sent_unknown）；撤权/法库离线后旧合法上下文仍可备份、恢复只读不重发；迟到回复保留真实用量不采用；unknown 只读找回；混合 V1+context 工作区回归。

## 执行顺序

RED（新 schema/登记/完整性失败测试）→ schema 层 → domain DTO → 运行时 → 完整性 → 备份恢复 → 关联测试 + 四开发门 → 独立复核 → TODO/TASK_STATUS/README/证据 → 提交推送并核对远端 SHA。

## 边界

合成数据与 127.0.0.1 回环 HTTP；不调用真实账号；不重建安装器；旧 V1 编码/字节/权限语义不变并由固定样例对照证明；Jev 真实预算仍未配置。
