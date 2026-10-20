# CH-06B 持久引用与处理器回执：只读设计复核

基线：`4c303c541a6bfe08225642837ccda72fb761bcb2`；复核日期：2026-10-20。本文为设计建议，不是实现或测试通过记录。使用 CodeGraph 定位后核对现行源码与 v2.1 计划；只检索了相关本地 Obsidian 状态，未调用外部模型、真实法库、WorkBuddy 或网络，未运行产品回归。

## 建议本轮边界

完成一个“现有持久事件 → 固定本地法库调用 → 不可变引用快照及唯一回执”的深模块，并同时完成其 schema、升级、备份恢复与完整性校验。对外只提供受授权的执行与按服务器 ID 读取；不开放任意函数、工具名、根路径或引用 JSON 写入。继续复用 CH-06A 的适配器及前后权限检查，不改 HTTP、UI、主模型循环和草稿投影。

这个切片可用独立合成法库贯通 search → 保存 → 按 ID 原文复验 → 重放 → 备份恢复，下一片可直接由固定 runner 使用。不要只加引用表却把恢复兼容留到下一轮；也不要为完成回执一次加入整个注册表、runner 和自动建档。

## 最小接口与身份

- `execute_library_handler(actor, run_id, event_seq, request, database, adapter)`：内部入口，仅允许 `legal_library.search` / `legal_library.read_original`。`read_original` 的 request 只接受服务端保存的引用 ID，不能接收调用者编写的 `CitationRef`。查询仍用已有 `AssistantLibraryQuery`。固定 handler ID/version 由代码选取，不能作为客户端重试旋钮。
- `read_saved_citation(actor, saved_citation_id, db)`：读取历史快照，重新检查当前账号、工作区、对话及关联案件/接待权限；不要求历史 input/material revision 等于最新版本，不要求外部法库可用，也不执行新 handler。恢复只读副本可读历史，但不能借此恢复执行权。
- 私有的 `publish_in_session(db, prepared, result)`：在调用者控制的同一短事务/savepoint 中保存引用和成功回执；自己不能 commit。未来草稿处理器才能把业务写入和自身回执放入同一个事务，而不是调用一个已经提交回执的公共函数。无需现在添加任意回调或通用副作用参数。

持久引用的服务端 UUID 与已有 `CitationRef.citation_id` 内容摘要必须分开。内容摘要不含租户/对话权限，不能直接作为全局可读取地址。保存引用应绑定 conversation/run、产生它的 handler receipt、序号及 `ScopeSnapshot`；相同内容出现在两个对话仍分别授权。原文复验必须从已保存快照解析引用，拒绝跨对话/跨工作区引用。首片宜要求执行用引用属于当前 run，未来跨 run 引用只能显式重新绑定，不能偷偷套用旧来源。

## 事件与原子幂等：不可省略的约束

1. 去重键严格为 `(run_id, event_seq, handler_id, handler_version)`，并以复合外键绑定现有 `assistant_run_events(run_id, seq)`。事件必须已经持久且属于该 run；校验固定事件种类与规范化 payload，而不是“该序号存在就执行”。建议调用基于类型明确的 `tool.before` 事件；其 payload 固定工具、请求/输入摘要和来源上下文。既有 `message.accepted` 是原始消息身份，不应被任意查询输入反复复用。
2. 当前 service 已在 `save_message` 原子建立 run 与 `message.accepted(seq=1)`。若本片不负责产生 `tool.before`，必须明确唯一可信生产者合同，并在合成测试中按该合同写入固定事件；不提供任意 append-event HTTP 入口。后续 runner 持久化一次调用身份后重试沿用它，不能每次重试新建 event_seq。事件 seq 分配与插入同一短写事务，沿用 SQLite 写串行化/唯一约束，不用进程内锁冒充多用户隔离。
3. receipt 的 `payload_hash` 应覆盖 canonical tool request、run 的固定 scope、输入事件 payload/hash、固定 handler 版本及 `read_original` 的持久引用 ID/快照摘要。命中同键且同 hash 返回既有历史结果；同键不同 hash 固定冲突码。不得把新参数覆盖旧 receipt。
4. 调用前和返回后重新核验登录会话、角色、run.actor/session、conversation owner/workspace/案件权限、run 固定 scope 与当前 revision、归档/取消/终止状态及恢复 fence。`_owned_run` 本身没有核对当前 session 等于 run.session，也没有检查是否允许继续运行，不能只调用它就认为完整。可借鉴 `judge_attempts._request_for_run`，但不要引入 Jev/主模型费用与外发许可作为本地读取前提。
5. 外部法库文件读取期间不持有业务 DB 事务；完成后在短写事务重新核验上述条件，再一次性插入所有引用、receipt 及需要的结果事件。任何失败全部回滚，无孤儿引用、无“成功但未保存”。新写事务要使用新鲜读取，不能依赖此前 ORM 缓存的授权结果。
6. 两个并发相同调用可在入库前重复进行只读法库 I/O；唯一键保证业务效果只提交一次。明确这是提交幂等，不是物理 I/O 恰好一次。先前有成功 receipt 的重放不再调用 adapter。无需为本地无收费读取复制模型的 claim/sending/sent_unknown 队列；否则会增加崩溃恢复状态。
7. 保存回执不能再次产生 `message.accepted`、新 run 或模型调用。若本片执行多个工具调用，可按已持久 `tool.before` 身份计算每 run 的调用上限，失败也不能靠新序号无限重试；只统计成功 receipt 不能证明 CH-06 的 8 次工具上限。完整 4 轮响应预算属于后续 runner，不应在文档宣称本片已完成。

建议仅两个新表：`assistant_handler_receipts`（固定身份、规范输入/结果及其摘要、scope、时间，唯一复合键）和 `assistant_library_citations`（服务端 ID、产生 receipt、稳定序号、引用 JSON/摘要、历史 scope）。引用/result 中的 ID 清单必须严格互相对应；记录和回执使用不可变 update/delete 触发器。JSON 大小和单回执引用数有上限，沿用每页最多 8 条、每条最多 1200 字符。完整 DTO 仍只放 `domain.py`。

## 来源失效与证据范围

- 历史引用快照不是“当前来源仍在线”的证明。按 ID 读取历史不能为了保留显示而绕过当前访问权限，也不能因法库缺失把合法备份判损坏。
- 当前原文复验使用已有 adapter，对代际切换返回固定 `LIBRARY_GENERATION_STALE`；源缺失/损坏、引用不一致返回对应固定错误。保留旧引用，不改成新 generation，不按相同标题替换新版本，不写成功回执。需要长期保留复验失败时，可另存明确的失败/观测记录，不能把它叫已验证引用。
- receipt 重放给出当时的结果，不表示再次完成当前来源复验。另一次明确复验才产生新的观察；这一差别要体现在 DTO/方法名和将来的 UI。
- `source_match=record_quote_matched` 只证明当时当前记录与该段精确原文一致；`registered_source_sha256` 是入库源身份，未重新校验整份数 GB CSV。`support_status` / `applicability_status` 仍为 `unverified`。标题/元数据命中不等于引文支持法律结论。
- 恢复时只有保存的引用、版本、代际、原文片段及摘要；外部 F: 原始库/D: 索引没有进入工作台备份。不要加入外部源路径、aliases、raw_fields 或整个库目录作为 protected 文件引用。

## Schema、升级与备份必须一起做

现行 `CURRENT_VERSION` 是 `assistant-judge-v1`，不是计划早期描述的 assistant-v1。建议新增独立的 `assistant-library-v1`（命名可随实际计划确定），沿用现有追加式链。

| 位置 | 必须联动的内容 |
|---|---|
| `assistant/library_schema.py` | 固定 DDL、索引、外键、不可变触发器与精确 expected_objects；拒绝部分 schema |
| `storage_schema.py` | 固定保存当前 Judge v1 历史 baseline；更新版本链与各累计表族条件；避免以后改 current 定义导致历史 schema 漂移 |
| `storage_bootstrap.py`、`schema_migrations.py` | 新建库初始化顺序与隔离副本迁移步骤；未知/部分结构仍拒绝，失败 DDL 整体回滚 |
| `web/workspace_upgrade.py` | 已有通用逐版本备份、receipt/pending-marker 修复机制可复用；验证新版本链，不另写迁移器、不降级 schema |
| `assistant/library_integrity.py` → `ops/backup._file_references` | 同 schema 验证历史 receipt、event/run/scope/用户交叉关系、规范 JSON/摘要、结果与引用清单对应、边界/状态/版本；只验证存档内部完整性，不访问真实法库 |
| `attachment_integrity.py`、`model_integrity.py`、`judge_integrity.py` | 三处都有明确允许版本列表/判断，必须加入新版本，否则新库即使无新业务记录也会被备份校验拒绝 |
| `ops/workspace_backup.py` / 旧备份路径 | 继续复用 shared references validator；新引用没有文件清单扩展，但新记录需遵守旧 cnbak 不支持 assistant 数据的现有边界；新 qxbak 保存历史，新会话撤销及运行隔离保留 |

归档校验不可要求历史登录 session 当前仍有效、scope input/material revision 等于当前或外部来源现在可用；应验证历史关联和单调 revision，并由读取/执行时另查当前授权。否则正常追加聊天、退出登录、恢复副本都会被误判损坏。成功回执均为终态时不需要新恢复 worker；若实现引入中间态，则恢复 fence/进程重启恢复也必须同片完成，不能悬置。

## 最小充分验证集合（建议，未运行）

1. 独立合成法库：真实 search 保存后按服务器 ID 回读；查询引用 JSON 伪造、不同对话 ID、不同 scope、非本 run 事件均拒绝。
2. 同事件/版本/请求重放完全一致且 adapter 不再调用；不同 payload 冲突；并发重复最终仅一 receipt、一组引用；在写第一条引用/写 receipt 前后故障注入均无半成品。
3. I/O 中失效/取消/变更材料或输入/权限撤销/恢复 fence：没有成功 receipt。历史 read 不受正常新增输入 revision 阻断，当前重新执行受到阻断。
4. generation 切换、源缺失、源被改：旧快照保存且未伪装当前可用；合法引用所在 CSV 的其他行变化不被夸大为整件已核验；支持性/适用性始终待核。
5. 所有历史 schema（native 与非 native）迁到新 current、固定 Judge baseline 摘要、重复迁移、缺触发器/多表拒绝和中途失败回滚；延续已有 `test_assistant_judge_schema.py`、`test_storage_schema_versions.py` 模式。
6. 旧 qxbak/cnbak 依现有政策恢复后有新空表；含新引用的 qxbak 往返保留引用/receipt/event，外部法库不在目标机仍可读历史且显示来源未复验。篡改 JSON/hash/跨 run 引用/orphan receipt 被拦。失败恢复不发布目标且不改旧 archive/source bytes。复用 `test_assistant_judge_upgrade_backup.py`、`test_assistant_model_backup.py`、`test_workspace_backup.py` 的真实隔离路径。

## 主要复用证据

- `assistant/service.py`：`_owned/_expected/_owned_run/save_message/read_events/quarantine_runs`。
- `assistant/tools/service.py`、`assistant/tools/library.py`：现成受范围约束的只读执行与原文再核。
- `assistant/schema.py`、`model_schema.py`、`judge_schema.py`：固定结构、事件身份、不可变记录。
- `assistant/providers/attempts.py`、`judge_attempts.py`：run/session/当前 scope 检查、同事务事件与历史输出模式。
- `assistant/attachment_integrity.py`、`model_integrity.py`、`judge_integrity.py`；`ops/backup.py`、`ops/workspace_backup.py`、`ops/storage.py`：存档内部证明、只读恢复 fence 与 protected 文件边界。
- `storage_schema.py`、`storage_bootstrap.py`、`schema_migrations.py`、`web/workspace_upgrade.py`：精确识别、版本链、旧库升级与失败恢复。
- v2.1 §7.1、§9.4/9.5、表定义、升级/恢复边界、CH-06/CH-09。相关 Obsidian 最新记录确认 CH-06A 已完成；其历史测试数量未作为本轮测试结果。

复核结论：该切片边界成立。最高风险是“来源复验与历史快照混为一谈”“schema 新增但旧完整性验证器拒绝新版本”“现成 _owned_run 被误当完整执行授权”及“回执先提交造成未来草稿原子性死端”。建议在正式实施计划先写清上述四点，产品与备份兼容一起验收。
