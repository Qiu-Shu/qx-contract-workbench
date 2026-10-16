# CH-01 首个存储切片与旧备份兼容

2026-10-17，基线 `00c12b780a08db26da4937859837fd53b045af46`。沿已有工程实施，无新运行依赖。仅使用独立合成材料；没有处理真实案件或资料库，没有启用模型或外查。

## 本轮实现

- 增加独立 assistant 模块：四张固定表保存对话、原话、运行和事件；业务 DTO 仍在 domain.py。服务不反向导入 Web，不在事务内访问模型或处理文件。
- 创建、读取、草稿保存、发送登记和运行读取逐次核验当前会话、角色、所有者及关联接待／案件权限。发送保存原话和来源版本，不认定事实。相同请求重放只产生一次运行；并发第二次发送明确返回忙碌。发送登记只得到 queued，尚无执行器。
- 草稿编辑与已发送输入分别计版本。原话和事件有数据库不可改约束；请求失败不会留下半条消息。
- 固定 pre-intake、intake-v1、assistant-v1 三种已知结构。旧参考来自已核对的冻结 0.4.1 结构，不从当前初始化器倒推。原生完整 schema 与备份规范化 schema 分别验证。
- 已有工作区先只读识别，再有序升级。每一步保留独立数据库快照、回执和中断恢复依据；已有当前版本不再执行隐式建表。未知结构即使 marker 自洽也拒绝。
- 旧 qxbak／cnbak 先验证旧档案字节、表内容／结构、文件与引用，才升级隔离恢复目录。原档案和源工作区不改。恢复撤销旧会话，将未完成对话任务标为 blocked 并追加恢复事件，禁止服务写入。

四表是批准规格的首个实际消费切片；其余表随附件、调用、档案等任务以新版本增加，不建立空占位表。当前新服务针对处理／复核律师；未开放助理或纯管理员对话操作。

## 实际验证

| 检查 | 结果 |
|---|---|
| 最终联合目标回归 | **293 passed，197.28 秒，exit 0**；0失败、错误、跳过 |
| 服务作者目标 | 49助手＋111原有领域＝160通过，exit 0；已包含在最终293中，不相加 |
| 迁移作者目标 | 24通过，exit 0；已包含在最终293中 |
| 新备份兼容与隔离 | 10通过，包含两代旧库×两格式、当前两类任务恢复、密文损坏和迁移失败；已包含在293中 |
| Windows冻结后端 | 沿用固定PyInstaller构建成功，exit 0 |
| 实际新EXE协议探针 | **8组通过，exit 0**，详见下表与摘要 |
| schema/defaults/来源/依赖开发检查 | 四项exit 0；报告schema仅增加ASSISTANT_BUSY枚举 |
| Spec／Standards独立源码审阅 | 各0确认问题；未把静态复核当运行验收 |
| WorkBuddy | 本轮实际连接并完成限定文件只读复核，建议经主代理核对；见review.md |

冻结程序实际完成：旧 pre-intake 备份恢复至 assistant-v1；恢复登录／原件回查／拒写；原生两步升级及两份快照；重启不重复升级；已有排队对话不自动执行；当前备份恢复后任务阻断、原话与事件保留；当前恢复副本只读核对；全新工作区初始化及登录／同源校验。

探针通过真实服务构造合成排队记录，然后由新 EXE 完成备份、恢复与隔离；不是声称已存在聊天 HTTP 入口。使用中文带空格测试路径；没有覆盖另一 Windows 用户或系统 DPI。原安装 0.4.1 未替换，本轮没有生成安装器。

最终目标命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_assistant_backup.py tests/integration/test_workspace_backup.py tests/integration/test_backup_restore.py tests/integration/test_assisted_backup.py tests/integration/test_local_material_boundaries.py tests/integration/test_local_workbench.py tests/integration/test_local_worker_contention.py tests/integration/test_desktop_runtime.py tests/integration/test_storage_bootstrap.py tests/integration/test_storage_schema_versions.py tests/integration/test_workspace_upgrade.py tests/integration/test_assistant_storage.py tests/unit/test_domain.py -q --tb=short --junitxml=.local/chat-storage-20261017/integration-final.xml
```

构建沿用 `desktop/backend.spec`，独立dist为 `.local/chat-storage-20261017/backend`，work为同目录build；构建模块来自 `.local/desktop-tools/python-build`。探针保留在 `.local/chat-storage-20261017/frozen_probe.py`，以仓库根为PYTHONPATH运行。日志／JUnit／候选均保存在该.local目录；可追溯摘要见[summary.json](summary.json)。作者实现与命令见[storage-report.md](storage-report.md)、[migration-report.md](migration-report.md)。

## 失败记录与限制

旧备份初轮4项全部失败，实际原因是新增表后旧库被当前唯一结构拒绝；兼容升级后全部通过。原生3项有效失败分别暴露未知／缺触发器但marker自洽的结构仍获准，以及已有库重新执行DDL。服务并发1项有效失败为第二请求返回版本冲突而非已约定忙碌，修正后通过。缺新模块导致的导入／fixture错误另记，不充作34项已证明业务失败。

备份关联首轮24通过1失败：未知结构现提前被入口拒绝，旧测试仍只接受含SCHEMA的错误码；核对路径后更新为精确WORKSPACE_DATABASE_MISMATCH，未削弱拒绝。最终293包含复验。首次联合命令误写不存在的test_local_server.py，0测试／exit4；改为实际test_local_workbench.py后执行。冻结探针先遗漏测试辅助模块的PYTHONPATH，随后误将既有列表接口当items对象；均修正探针，原日志保留，没有更改产品接口迁就探针。

本轮未重跑全仓库回归；前一阶段1905项属于旧提交，不能当成本次结果。没有对话首页、聊天HTTP／SSE、执行器、附件、主模型／Jev、自动档案投影或新安装器。完整CH-01及后续CH任务仍在推进，代码可调用不等于产品入口已接线。下步先接薄HTTP／任务与恢复边界，再按既定依赖推进首页与建案前附件；网络、解析和流式响应不得占SQLite写事务。
