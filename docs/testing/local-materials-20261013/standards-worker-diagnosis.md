# Worker 锁争用诊断（只读）

## 结论与证据

确认为既有可用性缺口：`web/demo_server.py:41` 无异常防护；`web/jobs.py:91` 的 `claim_next_job` 在其 try 块外。领取通过 `ops.storage.quarantined` 取得连接，`persistence.py:181` 发出 BEGIN IMMEDIATE。SQLite 15秒繁忙等待耗尽后，OperationalError穿透到线程顶层；主HTTP进程仍运行，worker不重启。8101956中的worker循环相同，非本轮新引入。

独立虚构库真实故障注入，仅在首次claim前加事件屏障以确定竞争顺序，没有修改SQLite超时或mock数据库错误。第二SQLite连接持写锁，实际等待16.453秒后捕获线程OperationalError。释放锁后上传HTTP202，2秒后任务仍queued，worker_alive=false。测试1 failed，exit1，20.32秒。

命令：`.venv/Scripts/python.exe -m pytest .audit-local/local-materials-20261013/standards-review/test_worker_lock.py -q --tb=short --basetemp=.audit-local/local-materials-20261013/standards-review/worker-tmp --junitxml=.audit-local/local-materials-20261013/standards-review/worker-result.xml`

结果：`worker-lock-observation.json`；此探针捕获threading.excepthook并把异常写入虚构审计，测试用worker存活和实际任务进展断言变红。没有抑制产品异常或改产品文件。

## 最小修复建议

在`claim_next_job`的完整数据库事务外围（包括commit）识别`sqlalchemy.exc.OperationalError`底层为`sqlite3.OperationalError`且SQLite错误码为SQLITE_BUSY。事务上下文先回滚，再返回None，使用既有stop.wait(.2)继续领取。若包含SQLITE_LOCKED，需显式定义同样仅限未成功领取阶段；可按错误码低8位识别扩展BUSY，不做字符串宽匹配。

不要对整个run_next_job重试，不自动重放已领取或外部查询任务；非锁错误应继续暴露。仅延长busy_timeout不能消除线程永久退出。

## 必要回归

1. 本探针：真实锁超过busy_timeout，解锁后worker仍存活、新上传由queued到completed；测试可将专属测试连接busy_timeout缩短加快反馈，至少保留本次默认15秒证据。
2. 领取前注入非BUSY OperationalError，必须继续抛出，避免把schema/corruption等误作空队列。
3. 繁忙重试中关闭lifespan，stop等待能中断、OS锁仍待worker退出后释放；已有shutdown生命周期测试应保留通过。
4. 关联query任务的未知扣费/不自动重发测试保持通过；此补丁只重试尚未取得任务的领取阶段。

本轮两次warning的具体持锁请求尚未单独定位；目前证明了相同BEGIN IMMEDIATE超时→线程永久停止路径，未声称已定位每次日志的长事务来源。完整套件由父会话进行，本诊断未运行。
