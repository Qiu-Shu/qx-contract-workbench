# CH-00A 公共边界抽离：本轮证据

2026-10-17，基线 `7b58b92865f0370687427d987fbc8fa42a96c205`。本轮完成已有存储初始化与HTTP请求校验的公共模块抽离；未新增对话表、模型调用或档案功能。所有运行使用独立合成目录，现有安装版与真实工作区未改动。

## 变化及兼容性

- `storage_bootstrap.py` 承接原12组存储初始化，顺序不变；备份结构检查、样本运行器和本机入口直接调用它。`web.app.initialize_storage` 保留同一函数导出。备份计算不再导入主应用、Web业务服务或PDF引擎。
- `web/request_context.py` 承接原5个请求函数；选案桥、法库、恢复、接待、草稿确认改为直接引用。五个函数与原源码逐字一致；原app名称保留为同一函数对象。PDF页面继续使用现有参数注入。
- `web/app.py` 净减少65行。此数只表示职责移出，不表示总代码量、安装包或内存减少。已有FastAPI Depends接口语义不同，保持原状，未强行合并。
- 数据库原始结构摘要和备份规范化摘要分别保持 `2c622bf427fb9ac8c93329862b0fb4acfc45cf7d07349e82800ee51090167ba0`、`cf9282bd4d8b60df107ba98a72c6c116435c3b553294ad135027e1f9e1bf26f4`。两种算法保持原义，未把结构校验改成仅相信归档自报值。

## 实际验证

| 检查 | 结果 |
|---|---|
| 存储、旧升级、完整备份、恢复、材料边界、PDF按需加载 | 69 passed，127.52秒，exit 0 |
| 请求、认证、API控制、选案桥、接待、法库、草稿确认、恢复路由 | 99 passed，320.61秒，exit 0 |
| 两组按JUnit身份去重 | 167个不同用例，0失败/错误/跳过；1个恢复用例重合 |
| 新冻结后端 | PyInstaller完成，exit 0；源码新模块实际打入独立候选 |
| 冻结EXE合成验证 | 5组通过，exit 0：初始化登录/同源与页面、重启、口令备份、隔离恢复、恢复登录/只读页/拒写 |
| schema、defaults、来源与依赖开发检查 | 四项exit 0；原生产审批限制保留 |
| 独立Spec／Standards审查 | 各0问题；静态审查未冒称运行验收 |

数值、日志摘要和精确用例去重见 [summary.json](summary.json)。原日志/JUnit、冻结产物与合成资料均留在 `.local/chat-first-boundaries-20261017/`。本轮未重复全仓库回归；首批轻量化的1,905个用例结果属于前一提交，不冒称覆盖本次后续改动。未生成或替换安装程序。

存储目标命令（现有项目Python，`-X utf8 -m pytest`）：`tests/integration/test_storage_bootstrap.py tests/integration/test_workspace_upgrade.py tests/integration/test_workspace_backup.py tests/integration/test_backup_restore.py tests/integration/test_local_material_boundaries.py tests/integration/test_assisted_backup.py tests/integration/test_document_lazy_loading.py -q --tb=short --junitxml=.local/chat-first-boundaries-20261017/storage-targeted.xml`。请求命令见 [request-review.md](request-review.md)。冻结构建沿用 `desktop/backend.spec` 和 `.local/desktop-tools/python-build`，使用独立dist/work目录；协议探针改编自现有 `tests/integration/test_desktop_runtime.py`，真实执行新EXE。

## 失败与限制

两个新增隔离测试先各出现一次有效RED：旧备份校验／旧路由导入会加载主应用；抽离后通过。初次一次性原始schema取样脚本在Windows释放临时SQLite文件时遗漏关闭连接，改用 `closing` 后取得改动前摘要；没有修改生产存储来迁就脚本。

冻结探针首轮错误预期恢复副本的 `/workspace` 返回200，实际按现有规则303转向 `/recovery`。核对恢复中间件与既有用例后，只修正探针，补查恢复页200和写入409。首轮日志保留为 `frozen-smoke-first-failure.log`；不是产品故障修复，也不是把失败删除后宣称全程通过。

下一步是 [CH-01迁移复核记录](../../../plans/chat-first-schema-migration-notes.md) 中的固定受支持版本、有序迁移和旧qxbak/cnbak兼容，再增加对话存储。当前只完成CH-00A的公共模块切片，接待业务对Web服务的既有依赖、其余路由拆分与更广泛能力包隔离仍待后续。
