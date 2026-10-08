# 持久本机入口独立审阅（2026-10-09）

最终结论：本次范围独立审阅通过，首轮2项P2已实际复验闭合，无新增未解决发现。工程验证不代表真实服务或生产通过。

范围：`src/cn_contract/web/local_server.py`、`demo_server.py` 的 worker 抽取，以及 `tests/integration/test_local_workbench.py`。不含插件 metadata 修复、工具配置、真实服务或真实材料。使用 Ponytail 与 CodeGraph 定位。所有探针使用隔离临时目录和虚构账户；未改变产品代码。

## 首轮审阅发现（历史记录；两项已在末节复验闭合）

### P2：重开已有工作区会自动初始化丢失/替换后的数据库

位置：`local_server.py:54–71`、`137–139`。`workspace.json` 只含固定策略/config，未绑定本工作区数据库身份；`_open_workspace` 仅要求 DB 路径是文件，随后 `_database` 调用带默认 schema 初始化的 `Database` 和 `initialize_storage`。因此已初始化目录的 DB 意外截断为零字节时，serve 接受它并创建新空库，掩盖原账户/案件丢失；替换为另一有效 SQLite 库也没有工作区身份核对。重开和 add-user 应先只读核验数据库身份/完整 schema，再以不初始化 schema 方式打开；新库创建仅允许 init 路径。

实际独立复现：`independent_probe.py`，初始化后把隔离测试 DB 写为空字节，保持 marker/protected。`build_local_app` 成功，账户数量0，DB被改写成393216字节。探针输出 `EMPTY_DATABASE_ACCEPTED True`。

### P2：退出超时释放工作区锁时，旧 worker 仍存活

位置：`local_server.py:149–156` 配合 `demo_server.py:49–52`。共享 lifespan 等待10秒后若线程仍活着就抛异常；外层工作区锁仍会退出并解锁，然后 dispose 数据库。此时底层工作线程并未停止，新的工作区实例可取得锁并执行 `recover_jobs`/取任务，破坏单 worker 与重启保全约束。锁和数据库生命周期需要覆盖 worker 的实际存活期；不能以“抛异常”代替确认任务停止。

实际独立复现：真实 Thread 执行受事件阻塞的虚构 run_next_job，超过实际10秒等待后退出抛 `worker still running; shutdown incomplete`。此时 `OLD_WORKER_ALIVE True`，同目录第二次 OS `_worker_lock` 成功，输出 `SECOND_LOCK_ACQUIRED_WHILE_OLD_WORKER_ALIVE True`。最后释放事件并 join，清理测试线程。

## 已核对行为

- init 只建单个 handling_lawyer，自定义账户，无默认公开账户；add-user 显式单角色，重名不重置密码。
- CLI getpass、非TTY拒绝、无 password 参数；解析错误不回显不认识的参数。
- 默认127.0.0.1:8767；无 host 参数；serve workers=1。
- init拒绝已有目录；目录限制项目.local子目录；祖先reparse及指定DB/marker/lock硬链接检查存在。
- create_app复用assisted_draft和固定12材料policy；真实模型/QCC/签发门未被放开。
- demo_server差异仅将现有worker代码抽出，无演示账户或模式行为改变。

## 实际执行证据

1. `.venv/Scripts/python.exe .audit-local/local-workbench-20261009/independent_probe.py`：exit0，2项缺陷已复现（上述四条布尔结果）。这不是产品通过结果。
2. `.venv/Scripts/python.exe -m pytest tests/integration/test_local_workbench.py -q --junitxml=.audit-local/local-workbench-20261009/independent-current-local.xml`：exit0，14 passed in 3.69s。包括父任务期间新增的后台解析/重启保全测试。
3. 早先并行执行 local_workbench + assisted_review：运行时父正在增加第14项测试，其第一版请求缺少既有 Idempotency-Key，因此观察到1F；父已修正测试请求。本项不列为产品缺陷。组合运行尚未结束，结束后补实际总数。

限制：未跑全套、未执行真实DeepSeek/QCC、未做法律样本验收或生产批准。没有以现有14通过抵销两个已复现边界问题。

## 组合回归实际结束补记

早先命令 `.venv/Scripts/python.exe -m pytest tests/integration/test_local_workbench.py tests/integration/test_assisted_review.py -q`：exit1，1 failed / 54 passed in 210.42s。唯一失败为新增 `test_document_worker_original_and_anchors_survive_restart` 第一版漏传既有 Idempotency-Key，上传得到422而非202；无产品源码变更，父已修测试且当前14项独立重跑全通过。41项 assisted_review 全部通过。不能将整次 exit1 改写为PASS，也不需重跑未修改的41项。


## 修复后独立复验（最终结论）

父实现已加入工作区UUID的DB/marker对应、只读 SQLite quick_check 与 schema 指纹检查；校验在会创建/注册schema的 `_database` 之前完成。新持久入口传入 `shutdown_timeout=None`，保持锁直到真实worker结束；旧demo默认10秒不变。

1. `.venv/Scripts/python.exe -m pytest tests/integration/test_local_workbench.py -q --junitxml=.audit-local/local-workbench-20261009/independent-fixed-local.xml`：exit0，18 passed in 5.49s。
2. `.venv/Scripts/python.exe .audit-local/local-workbench-20261009/independent_recheck.py`：exit0。原数据库探针扩展为3类异常×2入口共6项：空DB、缺web_http_writes表、换入另一工作区DB，对serve/build_local_app与add-user均拒绝，原DB字节不变。真实Thread阻塞保持10.5秒后再检查OS锁，得到WORKSPACE_IN_USE；释放阻塞后主lifespan正常结束、worker已不存活，随后可再次取得锁。
3. 原缺陷探针 `independent_probe.py` 保留为首轮证据，未改写历史失败。新的 `independent_recheck.py` 和 `independent-fixed-local.xml` 是最终修复后证据。

结论：两个已复现P2闭合；本次限定范围无新增未解决发现，独立审阅通过。41项assisted批次此前已通过，复验不重复；全套、真实DeepSeek/QCC与生产验收未运行。

实际限制：等待worker正常结束可能延长退出时间；强制终止进程属于异常退出，下一次启动由既有恢复路径处理。此限制已在源码注释说明，不再提前解锁假称清理完成。

## 最后便捷启动增量复核

仅复核 `local_server.py` 的start分支、`_prompt_password`和根目录`启动工作台.cmd`：无新增发现。首次仅在受控工作区不存在且TTY时读取用户名及两次getpass；已有目录直接进入既有安全打开路径，不重置账户，损坏/部分目录不会自动init；固定项目虚拟环境与loopback启动，无密码参数。独立运行 `.venv/Scripts/python.exe -m pytest tests/integration/test_local_workbench.py -q -k start_prompts --junitxml=.audit-local/local-workbench-20261009/independent-start.xml`，exit0，1 passed / 18 deselected in 1.28s；未重复整批，未交互双击cmd或真实供应商调用。
