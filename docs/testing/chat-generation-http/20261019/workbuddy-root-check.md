# WorkBuddy 本轮复核及主代理核对

2026-10-19，产品提交 `eccea9a`。用户已明确允许 WorkBuddy 协助，并已重新打开专用会话。前段状态曾为 busy，存在旧任务缺少结束记录及活动 JSON 损坏；未取消、重试或手工清除。随后实际 `workbuddy_status` 返回 connected=true，才派发新的独立只读任务 `wb-151ff422094a`，不是重试旧任务。

任务限定只读 `assistant/task_manager.py`、`assistant/runner.py`、`assistant/providers/attempts.py`，不得写文件、运行命令、访问其他文件或联网。实际 start→wait 返回 completed、stop_reason=end_turn、error=null，只有 3 个获准 Read 和 3 个 completed Read 事件，未记录其他工具。原始回执保存在本机 `.local/chat-generation-http-20261019/workbuddy-review-completed.json`；[归档回执](workbuddy-review.json) 仅移除无关会话 ID、把文件路径改为仓库相对路径，报告正文和工具事件不变。

WorkBuddy 在限定范围内未找到两类可复现缺陷：提交前调度/历史补发、未发送预占与发送未知混淆。这是静态复核，不能计作运行测试、完整系统审计或真实模型连通。

主代理进一步核对其题设外前提：

- `persistence.py` 的 `Database.session` 在第181行显式 `BEGIN IMMEDIATE`。本轮同键并发测试与独立双事件循环探针已经通过，事务前提有源码及运行证据。
- `web/local_server.py:218` 起在 `_worker_lock(root)` 内、原工作器启动前调用 `recover_attempts`；恢复副本跳过写入。`test_assistant_model_startup.py` 和本片冻结 HTTP 重启链已经实测，不需因该静态报告重复运行。
- `assistant/model_schema.py:9` 明确 `run_id TEXT NOT NULL UNIQUE`，一 run 一 attempt 由 schema 约束。冻结后端同时核对实际 schema 版本、摘要及完整性。
- 容量 4 是应用实例内限制，不是未来集群并发额度。本机生产入口持有工作区 OS 锁，跨进程重复 claim 另由数据库状态/摘要守卫阻止；不能把本实现当作云端多实例调度器。
- `require_active`、权限、policy 和材料边界不在 WorkBuddy 三文件审阅范围，其依据仍是已执行的145项目标回归、独立Spec/Standards和源码检查，不借此次报告扩大结论。

两处措辞保留解释：`submit` 两步之间无 await 只说明同一事件循环没有协程让出，不等于数据库提交与内存调度具有原子持久性；进程崩溃窗口由启动封存处理。`sending/sent_unknown` 是已取得发送资格后的保守记账，不能证明供应商实际收到或必然收费；不能据此释放成明确未发送。

本轮无需据此改产品；当前无未关闭发现。后续能否继续调用须重新检查实时连接，不能把本回执长期当作在线状态。
