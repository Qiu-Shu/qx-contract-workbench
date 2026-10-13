# Worker 修复独立复审

当前 `web/jobs.py:93–102` 只包住 `claim_next_job(database)`。其数据库会话在异常离开时回滚，之后才判断底层 `sqlite3.OperationalError` 与 `sqlite_errorcode & 255 == SQLITE_BUSY`，返回None复用现有轮询等待。其他错误重抛；已领取任务/外发/结果持久化不在重试范围。未见新增阻断。

独立实际结果：

- 原默认超时真实锁探针 + 正式新增worker锁/非BUSY目标：**3 passed，exit0，37.46秒，无警告**。默认15秒繁忙等待超时后继续轮询；持锁17.015秒、释放后worker_alive=true，HTTP上传202，任务completed，捕获线程异常0。
- 补充独立2探针 + 既有OS锁shutdown目标：**3 passed，exit0，3.49秒，无警告**。真实SQLite锁争用期间（仅测试连接busy_timeout=50ms）正常shutdown，线程已退出且工作区OS锁可重新获取；未知查询的每一次领取前注入BUSY，随后复用真实本机SDK场景执行、recover和同计划重入，外部模拟调用数始终1、sent_unknown保留。

新增审计脚本 `test_worker_extra_boundaries.py`；JUnit分别为 `worker-fixed-result.xml`、`worker-extra-result.xml`。初次RED的 `worker-result.xml` 保持不变。原真实锁探针再次执行时将固定输出 `worker-lock-observation.json` 更新为当前GREEN观测；初次RED详细值仍在原JUnit及 `worker-diagnosis.md`，不要把当前JSON误当首轮RED。

命令分别运行了原审计test_worker_lock.py与tests/integration/test_local_worker_contention.py；以及补充test_worker_extra_boundaries.py与tests/integration/test_local_workbench.py::test_shutdown_retains_lock_until_active_worker_finishes。均只使用独立虚构库，没有改src/tests，也没有运行完整套件。

审阅结论仅关闭已证实的领取锁超时导致线程退出问题；其他阶段异常的恢复策略、本次原始长事务的具体来源仍不在此最小补丁证明范围。
