# D1：官方微信协议离线预览实施计划

用户要求持续无人值守推进并每轮正常同步 GitHub。A—C 的合成合同任务已经完成；D1 是官方协议接入的首个可独立验证切片，不能称真实微信已接通。

本片使用 research 技能核验官方一手源码，使用 writing-plans、TDD 及独立审阅实施。沿现有分支继续，保留本轮开始已存在的 AGENTS.md 用户改动，不把它混入业务提交。

## 设计与边界

新增一个 Python 离线适配模块，接收独立合成的 getupdates 原始字节与桌面当前拥有的会话作用域，生成只读转换计划。复用严格 JSON、TaskInboxBatchInput、TaskMediaInput 及现有登录/归属检查；不修改 synthetic-only 存储约定、不调用 receive_batch、不创建业务记录或推进游标、不增加 HTTP、IPC、登录、轮询、下载、解密或发送入口。权限拒绝可能按现有 security.authorize 追加不可覆盖审计，不把这称为任务处理或游标消费。

上游事实以 `docs/research/2026-10-24-weixin-protocol-d.md` 的固定提交链接为准：bot account 与登录 user 不同；get_updates_buf 是账号级 opaque cursor，不能代替现有 binding 级整数游标；私聊范围按精确 from/to ID，不能复用上游空 allowFrom 放行；回复使用 ref_msg.svr_id，不能猜 generic reply_to。

只支持已完成的 USER 私聊消息中的 TEXT 与 FILE。首版 scope 只允许数据库当前真实主办/复核律师角色，不能相信调用方 Actor 自述角色。任何未知 peer/recipient、群聊、BOT、未完成/删除语义、未知 item 或歧义引用都会拒绝整份预览，不声称已消费上游游标。文件名与长度有本地边界，文件只生成 pending，不具备 attachment/hash/parse 权限。AES、CDN 查询参数/URL、context token 不进入输出；每个消息保留单向内容摘要以便后续查验。

## 接口与文件

业务 DTO 仅追加到 `src/cn_contract/domain.py`：

- `WeixinOfflineScope`：bot_account_id、sender_peer_id、owner_id、session_id、binding_id、expected_scope（ScopeSnapshot）、task_cursor（整数）与 upstream_cursor（原样 opaque 字符串）。不代表已认证微信身份。
- `WeixinOfflinePlan`：scope、response_sha256、next_upstream_cursor、batch（TaskInboxBatchInput 或 None）及 event_payload_hashes（event ID → 原消息摘要）。只读计划，不是 durable receipt。

新增 `src/cn_contract/weixin_offline.py`：

- `create_offline_scope(actor,binding_id,*,bot_account_id,sender_peer_id,upstream_cursor,db)`：检查当前登录/会话、工作区、owner、案件或接待权限、归档及恢复隔离；只读构造 scope。
- `translate_response(scope,raw_response,settings)`：纯协议转换；上游 before/after cursor 与 task_cursor 分离，非空 batch 只规划 expected_cursor/next_cursor=task_cursor/task_cursor+1，空轮询 batch=None。
- `preview_response(actor,scope,raw_response,*,db)`：重核当前 scope 和整数游标，再返回离线计划；不写入、不持久确认、不执行任务。
- `event_id(bot_account_id,sender_peer_id,message_id)`：基于精确身份三元组确定性摘要。uint64 接受规范十进制字符串或 Python JSON 精确整数，统一成十进制字符串；拒绝 bool、float 及越界，不经过 JS Number/浮点。引用同规则；该固定版本官方客户端源码及测试确实将 message_id 和 ref_msg.svr_id 作为同一作用域缓存键使用，不据此宣称服务端全局唯一保证。

## 实施任务与验收

- [x] 后端先写行为测试，观察缺失适配/DTO、身份/协议及资源边界的有效失败；实现最小模块和 DTO。原始 getupdates 以本地 256 KiB、100 消息、20 items/消息和既有文本/文件上限约束，注明是本地边界，不冒充微信服务上限。
- [x] 测试完整两种消息顺序、TEXT/FILE 合并、超大 uint64、原样 cursor、same ID 改内容摘要、同 ID 跨身份隔离、scoped reply、重复 ID/键、未知/缺失字段及 ret/errcode 错误。未知媒体或不完整消息不得静默漏掉后推进游标。
- [x] 集成测试实际 SQLite 当前 scope、owner/session/ACL/绑定变化/归档/恢复 fence，并断言所有业务表和 cursor 不变、网络调用为零。只在独立合成验证中显式把预览批次交给原 synthetic Inbox，证明 pending 阻断冻结及既有幂等；产品模块本身不提交。
- [x] 独立审阅、关联回归及四开发门，更新 TODO/TASK_STATUS/README、实际命令/数量与 NOT_RUN。
- [ ] 正常提交推送并回读远端 SHA/tree（实际同步以随后独立回执为准）；收尾按 AGENTS 完成本聊天脱敏 HumanLayer 增量与 Obsidian 记录；TencentDB 沿用 Stop 入队，不把全局健康当成本轮成功。

后续 D2 才建设可信身份绑定持久化、账号级 complete Inbox/checkpoint、撤权和备份兼容；必须让每个上游事件都有 durable accepted/blocked 结果后才能确认账号游标。真实凭据/账号/轮询、媒体下载解密、Outbox 发送及未知结果不重发、E 真实模型和安装包均 NOT_RUN。
