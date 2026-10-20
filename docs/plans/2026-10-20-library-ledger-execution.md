# CH-06B1 执行合同：持久引用、固定回执与完整恢复

2026-10-20从641a6e82575ec7366ed3aea49214f2655b03c33c接续；fetch 0/0、干净，无活动验证/导入。沿[设计复核](2026-10-20-library-ledger.md)，不重做已验内存/CH06A。WorkBuddy初检无活动端点；用户随后告知可用，本轮重新检查连接成功，提交独立只读schema复核，不重派上一超时任务；结果以阶段证据为准。用户已授权现有分支、并行子代理和GitHub同步，仍仅使用独立合成材料。

## 本片固定接口

内部 `begin_library_call(actor, run_id, call_id, request, database)` 是唯一固定tool.before生产者，返回run_id/event_seq/payload。call_id为受信runner保留的UUID；相同身份/相同请求返回原事件，不同请求拒绝。每run最多8个不同调用事件，失败或未完成也占该逻辑身份；4轮主模型预算及HTTP/UI另属B2，不在本片宣称完成。

每个新call采样当时的composer_revision；该事件在composer变化后不得执行或重放。既有run不存不可变的起始composer，因此允许同一仍有效run以新call_id采样新composer；scope/input等仍须匹配。此约束按调用生效，不伪造整个run的固定composer。

`execute_library_handler(actor, run_id, event_seq, database, adapter)` 从持久事件读取请求，不再接受第二份可被调换的request。先查当前权限及执行状态，已完成则返回原回执并标replayed，不读外部法库；未完成复用CH06A工具服务，释放业务DB后读取，再在短写事务重新核验并保存。并发只保证提交幂等，不承诺物理只读I/O恰好一次。

`read_saved_citation(actor, saved_citation_id, db)` 是历史读取，只查当前账户/工作区/对话和历史作用域权限，不要求原登录session仍有效、当前revision等于历史或法库在线。返回当时快照，不暗示当前来源复验。本片不接HTTP/UI，不接受模型生成的CitationRef当服务端凭证。

短写入口在自有新session首先取得连接，由现有Database的begin hook发出BEGIN IMMEDIATE，串行分配事件序号/最终提交；不重复手动BEGIN，也不在文件I/O期间占事务。私有 `_publish_in_session` 不commit，使用savepoint，使后续草稿+回执可复用同事务。失败不留半组引用或成功回执，不产生新message/run/model任务。实现初验暴露重复手动BEGIN导致嵌套事务错误，已据既有引擎合同调整；失败记录保留。

## 共享数据合同（业务DTO仅domain.py）

- `LibraryHandlerRequest`: tool（既有两个字面量）；query仅search使用；saved_citation_id仅read_original使用，互斥、严格重验。
- `LibraryHandlerEvent`: call_id UUID、handler_id=tool、handler_version字面量`1`、request、scope、expected_composer_revision、citation_sha256（仅read_original，为既有持久引用JSON摘要）。固定event_type=`tool.before`，audience=`internal`，payload为该DTO规范JSON。
- `LibraryHandlerCall`: run_id、event_seq、payload（上述event）。
- `LibraryHandlerResult`: result（既有AssistantLibraryToolResult）、citation_ids（最多8个不同UUID，数量等于result中引用数）。
- `LibraryHandlerReceiptView`: id、run_id、event_seq、handler_id、handler_version、request、scope、result（LibraryHandlerResult）、created_at。
- `LibraryHandlerExecution`: receipt、replayed布尔；不是重新核验来源的声明。
- `SavedLibraryCitation`: id、receipt_id、run_id、scope、citation（CitationRef）、created_at。

新增`assistant-library-v1`，仅两张不可变表：

1. `assistant_handler_receipts`: id主键；run_id关联runs；event_seq>0；handler_id固定两工具；handler_version=`1`；payload_sha256、request_json、result_json、result_sha256、scope_json、created_at均NOT NULL。唯一(run_id,event_seq,handler_id,handler_version)，复合FK(run_id,event_seq)指向run_events。request_json≤8192、scope_json≤4096、result_json≤262144字符。payload_sha256是完整规范event JSON摘要（含scope/版本及来源引用摘要）；result_json存LibraryHandlerResult。
2. `assistant_library_citations`: id主键；receipt_id关联receipts；ordinal≥0且<8；citation_json≤32768、citation_sha256、created_at；唯一(receipt_id,ordinal)。run/scope由receipt关联取得，不重复储存。read_original成功也保存本次复验得到的新引用UUID，不能覆盖原快照。所有字段均不可UPDATE/DELETE。

共享纯编码/核对函数放`assistant/library_records.py`：encoded(model)规范JSON、sha(str)、model(kind,raw)严格JSON且规范字节相同、result_citations(result)取有序CitationRef元组；receipt_view(row)解析展示。此模块不访问法库、不查当前授权，供执行与存档完整性复用，避免另写序列化规则。

## 实施分工与验收

- schema代理：新DDL、固定Judge历史baseline、storage_schema/bootstrap/migrations及对应迁移测试；旧测试对current版本的期望同步更新，不放宽历史schema。
- service代理：上述DTO/records、独立library_handlers执行模块和合成测试；授权、事件身份、原子重放、并发、取消/撤权/版本变化、错误固定化。
- backup代理：library_integrity及ops/backup接线，既有三验证器新版本允许范围、升级/备份/恢复与篡改拒绝测试；不访问外部法库验证历史快照。
- 父代理：契约整合、独立双轴复核、稳定输入目标/必要广回归、命令/退出码/实际数量、文档/本地提交/正常推送与远端核验。测试包含pilot时显式设置已存在隔离DuckDB解释器。

历史完整性核对所有tool.before事件及所有回执/引用：同run/scope/actor/session/message/规范payload与摘要，事件顺序/唯一call_id/最多8个，read_original引用必须来自同run更早回执，原引用摘要匹配；结果引用清单与表行逐条一致，无孤儿。存档只检查内部历史关联和单调revision，不要求旧session当前有效、外部源可用或运行仍active。旧cnbak含新记录仍按既有assistant数据政策拒绝；qxbak保留历史并撤销会话/隔离运行，不重发。

历史binding允许小于当前revision；等于当前时才要求当前scope相同，较旧历史仍核对当时目标存在。保存read_original回执时必须与服务器已保存来源快照及摘要一致。旧版本schema也不得隐藏本片tool事件。以上均由反例验证后收紧，避免正常重绑定阻断备份或非法历史被遗漏。

实施状态：本片已实现并完成完整源码回归，3222项通过、0跳过，0失败/错误，exit0；473份输入前后稳定。独立Spec发现并关闭内容身份遗漏，生成/持久编解码共用纯摘要算法；Standards无待修问题。WorkBuddy完成指定4文件只读复核，统筹另外核实其意见。实际命令、失败记录与限制见[阶段证据](../testing/library-ledger/20261020/README.md)；HTTP/UI、完整4轮模型、自动档案和安装交付仍待后片。
