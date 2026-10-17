# 首页的消息分页与任务找回

基线cfc380123feec043f7affb2829758761e59eb3bb，沿现有分支实施已批准v2.1及首页readiness中的两个读取前提。现有2,042项全量及冻结6组为上一提交证据，不重称本轮测试。只用独立合成库，不触碰安装版、法库或真实材料。

## 接口决定

- 新增`read_conversation_page(actor, identifier, db, *, before=None, limit=50)`。在当前身份、归属和关联对象权限下，读取同一对话最多`limit+1`条，limit范围1—50。数据库按现有不可变消息的rowid倒序取近页，返回页内按原顺序排列；对外游标为最旧已返回消息的UUID，仅有更旧记录时返回`next_before`。每次游标重新核对同一对话、解析实际rowid，不采用offset或下载全文后切片。新消息追加不会挤动旧页；相同时间/版本不合并。沿用现有排序，不暴露rowid。
- DTO仍只在domain.py：`AssistantMessagePageQuery(before, limit)`；`AssistantRunSummary(id, message_id, request_id, request_sha256, scope, state, requested_skill, cancel_requested, created_at, last_event_seq)`；`AssistantConversationPageView`扩展旧ConversationView，包含有上限messages、`next_before`和`latest_run`。latest_run按持久插入顺序取最近一条，任何状态都原样呈现，不解释为应自动续跑；其事件只取MAX(seq)，不加载全部事件正文。
- 新增`find_run(actor, conversation_id, request_id, db)`返回当前有权对话中该request_id的摘要，或None；只读不存在不等于对端请求从未发生。客户端如需重放必须保持原幂等键及完整原请求。
- 旧`read_conversation`和`get_run`保持行为，供既有服务／备份消费者兼容。`create_conversation`和`save_draft`新增可选`page_size=None`，默认保持旧返回，HTTP明确传50走新分页响应；参数在任何写入之前验证，不能写完再因分页参数报错。这样首页自动存草稿不会重新下载整个历史。仅引入这个有实际消费者的兼容参数，不建立通用响应框架。
- 当前GET `/api/assistant/conversations/{identifier}`使用分页视图，接受before/limit。新增GET `/api/assistant/conversations/{identifier}/runs/by-request/{request_id}`精确查询运行摘要，未找到返回200/null。POST创建与PUT草稿改用有界响应。其他写入/运行/SSE接口保持。恢复中间件仅为这个精确GET路径增加只读放行；服务仍独立核验权限。

无新表、索引、迁移、worker、模型或前端。分页为消息读取上限，不声称数据库耗时恒定；保留旧服务完整读取能力也不等于所有旧接口均已轻量化。

排序保证限于现有不可变记录与SQLite Backup文件备份／恢复路径。对外UUID每次重新解析，客户端不保存内部rowid数值；这不能保证未来逻辑导出／重建／跨库迁移后的插入顺序。[SQLite官方说明](https://www.sqlite.org/lang_vacuum.html)也明确，未声明INTEGER PRIMARY KEY的表经VACUUM可能改变rowid。当前产品未使用VACUUM或逻辑重建；若以后增加这些维护路径，应先引入并迁移显式持久顺序、验证旧游标与最近任务选择，不把本次文件备份实测泛化到阿里云迁移。

## 验证与分工

服务实现者只改assistant/service.py、domain.py和新增服务测试；主代理负责HTTP/recovery及HTTP验证、记录。独立Spec/Standards复核后本地提交。

- 有效RED先复现缺接口；用101条独立合成消息验证三页、顺序/无重复遗漏、空页、页界限、外案/不存在游标、追加后旧页稳定、相同日期/版本、未读取页外正文。
- 当前/撤销用户与案件权限、错工作区、只读恢复仍拒绝不应有的访问；通过真实保存并重开服务找回queued/cancelled/blocked任务与原request_id，未找到时不写入。事件摘要不加载正文，GET不创建消息、事件或新任务。
- HTTP检验版本字段、分页参数、认证、跨用户、重复请求找回、恢复精确路由和创建/草稿有界响应；与已有存储/控制/HTTP/迁移/备份相关测试一起回归。旧全量2042不重复计数。
- 最终候选冻结后端在独立中文目录实际完成多页、重启找回、重复请求身份不变、备份恢复只读找回；此检查不是安装器或首页验收。
- 仅在新变更影响的目标与关联验证、独立复核、实际冻结检查通过后记录结果。本次窄读取切片以这些关联测试为验收；完整回归留新首页集成稳定后的阶段关口，避免每个小接口重复上一批半小时全套。
