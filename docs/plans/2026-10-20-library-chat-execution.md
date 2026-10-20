# CH-06B2a：对话中的本机检索与持久引用

基线 `13f53bf986fb672834d2952c0276b52ea41b3d9c`，2026-10-20。沿 v2.1 与 B2 接线准备执行，用户已授权无人值守、独立代理、WorkBuddy 复核及正常 GitHub 同步。此文先定义实施合同，完成证据另记，不能将计划当成功能。

## 最小完整切片

- 明确选择 `legal_research`，输入最多 200 字关键词，发送只查询本机库。固定 `AssistantLibraryQuery(text=content,limit=5)`；不解释自然语言、不接收路径、不将文字或命中发送给主模型/Jev。其他技能与普通文字生成保持原行为。附件存在时明确拒绝本片检索，不默默忽略。
- 新 POST `/api/assistant/conversations/{id}/researches` 接收既有 `AssistantMessageInput`，只接受 `requested_skill=legal_research`。新 message/run 和唯一初始 `tool.before` 在同一短事务提交，然后纳入同一个 `GenerationTasks._tasks`。既有 `/messages` 只是保存，不能被升级为执行；旧 request_id 没有本片初始事件则拒绝接管。同 request_id 相同请求读回，不重新执行；不同内容冲突。
- 本片一个 run 执行一次 B1 `legal_library.search`，调用身份由服务器生成。法库 I/O 在短事务外固定线程执行；发布重验权限、会话、范围、草稿版本、取消和恢复栅栏。shutdown 必须封存且等待正在运行的本地工作，不能释放容量后仍让旧线程写入。失败只保留固定错误码，绝不自动重试。
- 成功查询（含空命中、not_ready、not_configured、timeout）保存回执并终结 run；UI 分别说明这些状态，不冒充成功检索到资料。没有模型 attempt/output/Jev 记录。模型配置为空时仍装配同一生命周期管理器。
- 新 GET `/api/assistant/conversations/{id}/researches/by-request/{request_id}`、`/api/assistant/conversations/{id}/research-history?message_id=...`、`/api/assistant/library-citations/{id}` 仅读已保存数据。历史查询最多 50 个消息，每 run 最多 8 回执；只返回用户有权访问且属于该对话的消息。当前和历史作用域分别校验，较新的输入版本不使合法历史失效。恢复副本可读历史、不可执行。不得在 GET 或刷新中读当前法库。
- HTTP 研究视图 `{run: AssistantRunSummary, receipts: LibraryHandlerReceiptView[]}`；历史视图 `{scope: ScopeSnapshot, items: [{message_id, research: 研究视图}]}`。引用读取复用 `SavedLibraryCitation`。所有业务 DTO 只在 domain.py，业务服务与薄路由分开。
- UI 保持当前工作台样式。复用草稿保存、request 未知找回、切换 epoch、取消与刷新机制，独立本机检索控制器及引用面板，禁止复制整份生成控制器。点击技能不发送/清空；关键词提示不偷偷塞入一句自然语言指令。Enter/Shift+Enter/中文 IME 原行为不变。
- 命中卡显示标题、待核对、查看已保存片段；面板显示片段、位置、来源版本/索引代际、保存时间，明确历史快照不是全文或当前法规效力确认。使用 textContent；切换/撤权/关闭立即清除，迟到响应不渲染，键盘可开关且焦点恢复。已有材料面板与新引用面板互斥。

## 分工与验证

1. 服务：短事务登记、可信初始事件、无 I/O 历史读取、线程执行与终结；安全/幂等/取消/离线历史/旧保存不接管/备份恢复反例先失败后通过。
2. 统筹：同一 manager 的 admission/close、薄 HTTP、可信本地库装配、恢复白名单；无模型配置执行、CSRF/越权/响应丢失找回/0 模型与 Jev 请求/旧模型回归。
3. 前端：明确入口、结果与引用面板、状态文案；Node 状态反例及真实本机浏览器合成闭环，窄窗口/大字号/键盘/迟到隔离。
4. 合并后独立 Spec/Standards 审查；WorkBuddy 限定文件只读复核，结论独立核对。适当目标回归与必要全套，记录输入摘要、实际退出码及数量。同步 README/TODO/TASK_STATUS、证据及执行记录，扫描后正常推送现有分支，核对远端 SHA。

本片不改 DDL、不安装依赖、不扫描真实 F: 法库、不运行真实模型、不更改已安装 0.4.1，也不声称多轮 runner、自动分流、阿里云或整体包体性能已完成。
