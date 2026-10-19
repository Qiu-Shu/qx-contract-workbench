# CH-04B 独立计划审核

日期：2026-10-19；仓库 `D:\Documents\ChatGPT\律所项目`；只读基线 `ffe1897`。对照 `docs/plans/2026-10-17-main-model-http-readiness.md`、本轮 `2026-10-19-generation-http-execution.md`、已批准 v2.1（并发/事务/权限边界）和现有源码。未修改产品或正式测试，未读取真实 key、调用外部模型或派发 WorkBuddy。

已自动检索 Obsidian 与 TencentDB 项目状态；前者与 CH-04A 阶段证据一致，后者归纳中的待核验表述仅作参考。CodeGraph 定位后核对了实际 lifespan、数据库事务、执行器与 HTTP 认证实现。较早的已结束全套与冻结检查不重复运行。

## Spec / Security 结论

整体接口方向符合已批准分批实施：复用单次 claim、预算和费用回执；独立 generation HTTP；默认无可信 runtime；旧 `/messages`、历史 queued/reserved 及读取不取得执行资格；明确技能未接通时拒绝；仅内部待核文字及已获准来源；Jev/首页消费/真实配置另行交付。没有必要增加用户设计审批或扩大本片范围。

当前没有要求推翻路线的设计阻断。已向根代理即时指出以下三个实现必须验证的时序，并留待新代码独立审核关闭，不能据本计划审核称功能通过：

1. **真实原生 lifespan 组合。** 基线 `attach_job_worker` 直接覆盖 `app.router.lifespan_context` 且退出时释放数据库；简单在 create_app 中先包装 generation 会被覆盖。执行文档已明确修复组合。必须实际验证 OS worker lock 与历史恢复在外层，generation 任务关闭及留账先于 worker/数据库释放，最后才释放工作区锁。仅 create_app 的 TestClient 成功不能替代 build_local_app。
2. **提交、调度与关停准入。** “本进程新登记”判定须与 enqueue 同处 BEGIN IMMEDIATE，不得事务外判不存在。数据库成功提交后才创建任务；创建任务失败须封存确定未发送的 attempt。close 先关闭准入，随后等待已注册任务；同请求重放只读取，不因无内存任务而重新调度。固定并发上限已写入计划；超限要在新消息/预算预占之前拒绝，同时保留已有请求的只读找回。
3. **取消尚未执行第一步的任务。** asyncio Task 在首次运行前被 cancel 时，`execute_attempt` 的捕获取消分支完全不会进入。仅 cancel+gather 不能释放未 claim 预占。需要明确处理该已登记而未发送窗口，或用可证明保持正确账本语义的等效方式；不能误记已发、重发，或让取消任务永久占住预算。另需确保后台异常被消费且不向日志回显材料/凭据，拒权仍只保存允许的非正文回执。

## 代码审阅接续范围

- 仅当前身份/归属下返回 capability、attempt 与 by-request；能力 GET 不调用 resolver 或供应商，不暴露政策、允许摘要或配置秘密。
- POST 在读取正文前、登记时各核验认证/同源/CSRF；恢复 fence、材料限制、技能限制、预算由服务端再次核验。
- 快速 202 与模型等待分离；延迟回环期间草稿写入、取消和只读查询可继续。
- 重复/旧 attempt、创建任务失败、发送前取消、发送中关闭、撤权、跨循环及满容量时序按实际代码选择独立反例。
- 本报告是计划审核，不是新增测试、真实模型连通或安装版完成证明。新代码尚在分工实施；待其稳定后记录实际残余问题或关闭结果。
