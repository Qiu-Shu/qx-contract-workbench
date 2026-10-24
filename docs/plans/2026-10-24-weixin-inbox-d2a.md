# D2a：合成微信收件存储底座

目标：在现有工作区 SQLite 中加入 credential-free、synthetic-only 的账号、精确 peer 映射、完整 poll 回执和逐条结果结构，闭合 schema/迁移/完整性/恢复契约。此片不增加生产收件方法或任务分发，不把直接 SQL 合成夹具称为已接通微信。

现有 D1 保持只读。D2a 沿用主数据库、既有版本化 additive DDL、不可变记录与 qxbak；不增加 sidecar、凭据、网络、HTTP、IPC、依赖或模型。SQLite 本身未加密；既有 qxbak 加密不能冒称运行库加密。用户已有 AGENTS.md 修改保留，不纳入本片 Git。

## 版本和表

追加 `weixin-inbox-v1`，保留 13 个前驱 schema 的 native/non-native 原始与规范化摘要。四表由 `weixin_inbox/schema.py` 定义，已有 task-drafts-v1 DDL 不改。

1. `weixin_accounts`：id、workspace_id、owner_id(users FK)、bot_account_id、mode='synthetic'、initial_cursor、checkpoint_revision>=0、upstream_cursor、created_at；revoked_at/revoked_by/revoke_reason 全空或全有。UNIQUE(workspace_id,bot_account_id)。身份与初始游标不可变，不可删除；checkpoint 只允许 revision 恰加一；撤权只能从无到有一次。
2. `weixin_peer_bindings`：id、account_id FK、sender_peer_id、task_binding_id FK、scope_json、scope_sha256、created_at、同上撤权三字段。UNIQUE(account_id,sender_peer_id)、UNIQUE(task_binding_id)。身份/快照不可变，不可删除；本片无隐式重新激活。
3. `weixin_poll_receipts`：id、account_id FK、request_id、request_sha256、response_sha256、expected_revision、next_revision=expected+1、expected_cursor、next_cursor、descriptor_count(0..100)、receipt_sha256、created_at。UNIQUE(account_id,request_id)、UNIQUE(account_id,next_revision)，全部不可变。
4. `weixin_inbox_descriptors`：id、poll_id FK、ordinal(1..100)、sender_peer_id、upstream_message_id、source_event_id、source_sha256、status、reason、mapping_id FK、prior_descriptor_id 自身 FK、payload_json。UNIQUE(poll_id,ordinal)，全部不可变。

descriptor status 仅 `accepted_pending_dispatch`、`blocked`、`duplicate`。前三个 source identity 字段全有或全空；ID 为规范 uint64 十进制字符串，source_event_id 依 D1 精确 bot/peer/id 生成。accepted 必须有 mapping/来源及标准化 TaskInboxEventInput，reason/prior 为空。blocked 必须 reason、payload 为空；conflict 可指向此前相同来源。duplicate 必须 prior，payload 为空且不得直接分发。固定 reason：sender_unbound、binding_revoked、scope_stale、scope_denied、recipient_mismatch、message_unsupported、message_invalid、event_conflict、previously_blocked、replayed。

完整消息/响应只留 SHA256，不留原始 JSON、AES、CDN URL/参数、context token 或桌面 session。仅 accepted payload 可保留经过 D1 标准化的文字和 pending DOCX/PDF；原件/hash/parse 权限仍不存在。历史 blocked 不因后续授权自动复活。

## DTO、完整性和恢复

DTO 仅追加 `domain.py`：WeixinAccountSnapshot、WeixinPeerBindingSnapshot、WeixinInboxDescriptor、WeixinPollReceipt。poll receipt 包含完整有序 descriptors 和 receipt_sha256；摘要取 canonical_json(model_dump(mode='json',exclude={'receipt_sha256'}))。域校验本身不代表真实账号认证。

`weixin_inbox/integrity.py:validate_weixin_records(db,*,allow_inbox=False)`：已知旧结构无本片表时接受空历史，未知结构必须拒绝；新结构逐表完整性重核。非空历史只允许完整工作区 qxbak（allow_inbox=True），普通局部备份明确拒绝。校验账号 workspace/owner、mapping 到 task binding/会话归属及 scope hash；快照为历史授权，不要求当前 ACL 仍有效，不放开运行时当前权限。

校验 poll revision 从 1 连续、expected/next opaque 游标链、账号当前 checkpoint 等于末条（无历史时 revision0/current=initial）；每个 poll ordinal 连续且数量相等，payload canonical、hash/来源命名空间、mapping 归属匹配。accepted payload 只允许 D1 能输出的安全 TEXT/pending DOCX/PDF，不含任务 UUID/start_new 或文件能力；重复/冲突只能指向同账号、同来源的更早原始 descriptor，不能循环或让 blocked 自动变 accepted。

保持现有所有模型、附件、辅助、法库、档案和任务校验在后继结构下继续生效。bootstrap、storage_schema、schema_migrations、两种备份/恢复及版本 feature gates 同片闭合；恢复仍依 require_active 栅栏，不能重放收件。

## 验收与分工

- Storage 代理：新 schema、版本/三条升级通道、旧完整性 gate、backup 接入、新 schema/migration 测试。不得改旧冻结摘要。
- Integrity 代理：新 integrity、独立合成历史夹具及篡改测试。不得新增业务入口。
- 根代理：确认 DTO/完整回执 hash 契约，qxbak 完成历史往返、定向回归/四门、独立复核、状态/证据、每轮 GitHub 及三端收尾；DTO 实际由 Integrity 代理同片实现。

先行为 RED 再实现，原始失败/退出码与数量保留。新建=升级=expected schema；所有前驱升级、失败 DDL 原子回滚、未知结构拒绝；带数据 poll/blocked/duplicate/revoked 映射归档恢复精确保留，恢复不得产生业务动作。需要以相应旧模块真实损坏测试证明 gate 仍有效，不能只对新表测试。

D2b 后续才实现持有短事务并在 commit 后返回的 record_synthetic_poll：先完整收件结果，再 checkpoint CAS；分类失败不能经既有 security.deny 的 rollback/commit 意外提交半批。此问题留明确接缝，不在 D2a 假装实现。真实认证、网络、账号 token、下载/解密、Outbox、真实模型及新安装包 NOT_RUN。
