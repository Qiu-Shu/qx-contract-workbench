# WIN-PATH-02 与模型就绪调查（2026-10-24）

本次为 macOS 源码调查及独立虚构数据验证。没有修改备份、模型或其他生产源码，没有提交、清理既有改动、访问真实案件、读取密钥值、调用付费模型或改动远端服务器。当前工作树原有改动与其他并行工作的文件均保留。

## 结论

**WIN-PATH-02 保持开放，根因未定。** 当前源码的成功恢复路径没有找到可以直接证明的本进程资源泄漏；macOS 探针证实最终发布前相关连接和句柄关闭，不能证明 Windows 上的历史拒绝已经消失。没有增加重试、改变文件守卫或将 macOS 成功写成 Windows 修复。

**真实模型尚未获得本次就绪或真实调用验收。** 本地普通 HTTP 启动和可信桌面启动的装配入口不同；仅设置环境变量不能使现有普通后端接入模型。当前实现固定使用 DeepSeek 的 OpenAI Chat Completions 格式，不是任意兼容服务的通用连接器。

## 历史失败与成功路径的资源所有权

原始证据：`docs/testing/profile-persistence/20261023/target.log` 第 56–65 行。失败用例是 `tests/integration/test_assistant_attachment_backup.py::test_long_parent_paths_create_restore_and_rebackup[long]`，第一次恢复在 `workspace_backup.py:369` 将 `.qx-restore-*/workspace` 重命名到同一恢复父目录中的 UUID 目录时报 `PermissionError [WinError 5]`。调用已通过解包、迁移、隔离、数据库验证和文件摘要检查，发布未完成。既有独立 Windows 复跑通过的记录位于 `docs/testing/intake-decoupling/20261023/README.md:37`，不构成修复证据。

读取的源码责任链：

- `workspace_backup._validate_database` 使用 `closing(sqlite3.connect(...))`；`_references` 在 `finally` 中 `database.engine.dispose()`。
- `_unpack` 的 ZipFile、各个成员读写流已在返回前退出上下文；`_reader` 的文件流亦有上下文。
- `workspace_backup.restore_workspace_backup` 在 `with _worker_lock(root): upgrade(root)` 退出后执行 `_fence`；`local_server._worker_lock` 在退出时解锁，外层文件上下文随后关闭。`workspace_upgrade.upgrade` 的 SQLite 连接由 `closing` 关闭。
- `_fence` 在 `finally` dispose 引擎；最终 `_validate_database` 与 `_file` 校验结束后才调用目录 rename。
- 本地 HTTP 运行时的 worker 生命周期持有锁，退出时等待线程结束并 dispose 引擎；恢复维护路径没有启动该 worker。源工作区活跃锁会阻断备份。

新增 `backup_resource_probe.py` 在两条路径上拦截实际最终目录 rename，追踪 sqlite3 及 SQLAlchemy 的 DBAPI 连接关闭、worker 锁持有，并用本机 `lsof -a -p <pid> -Fn` 查询待发布恢复目录的本进程句柄：

|路径|已关闭 SQLite 连接|仍持有 worker 锁|恢复目录打开句柄|结果|
|---|---:|---:|---:|---|
|正常最终发布|5|0|0|发布一个隔离副本|
|注入 PermissionError|5|0|0|只尝试一次；自有 stage 清理；没有发布副本|

两条路径均核对源文件与加密归档摘要保持、无关 sentinel 保持。此探针不枚举 Windows 其他进程句柄，也不模拟 Windows 共享删除权限或杀软、索引器、ACL，因此不能排除这些候选，更不能认定其中之一是根因。只读文件属性、长路径、外部占用和权限目前均没有因果证据。

下一次可区分根因的验证必须在 Windows：对上述**同一个用例**定向运行，捕获最终目录重命名前后的路径、进程、原始 Win32 错误及失败时的目录/子文件句柄占用；同时记录 worker 退出和 SQLite 连接关闭。可用 Windows Process Monitor 的路径过滤追踪重命名结果与其他进程访问，失败时辅以句柄快照。没有必要重跑历史 49 分钟全套来代替这一证据。当前机器没有提供 Windows 运行环境，因此未执行此项。

## 聚焦验证及运行器问题

|验证|实际结果|日志|
|---|---|---|
|新增资源释放及最终发布拒绝探针|2 passed / 0 failed / 0 skipped，11.78 秒|`backup-resource-probe.log`|
|既有完整本地备份文件、历史长路径附件用例、合同长路径备份文件|21 passed / 0 failed / 0 skipped，15.87 秒|`backup-targeted-regression-final.log`|
|桌面模型设置、会话、凭据、桥接四文件|69 passed / 0 failed / 0 cancelled / 0 skipped，201.22 毫秒|`model-readiness-node-canonical-temp.log`|

23 个 Python 项是两个探针加 21 个既有用例。此前单独运行的模型会话/桥接 22 项包含在 69 项中，不累计。

保留两类无效或失败运行记录：

1. `backup-targeted-regression.log`：首轮遗漏创建嵌套 basetemp 的父目录，21 个 setup error，未进入产品逻辑。创建该父目录后用另一个新 basetemp 完成上表回归。
2. `model-readiness-node.log`：系统默认 `/var/folders` 临时路径经过符号链接祖先，触发现有目录守卫；40 pass / 14 fail / 15 cancelled。没有改源码或关闭守卫；指定物理路径 `TMPDIR=/private/tmp` 后同四文件 69 项通过。首轮不能作为 Windows 产品回归，也不能隐藏为全部一遍通过。

运行命令：

```sh
/tmp/qx-audit-20261024-venv/bin/python -m pytest -q -s docs/testing/conversation-maintenance/20261024/backup_resource_probe.py --basetemp=/private/tmp/qx-backup-resource-20261024
mkdir -p /private/tmp/qx-backup-regression-20261024
TMPDIR=/private/tmp /tmp/qx-audit-20261024-venv/bin/python -m pytest -q tests/integration/test_workspace_backup.py tests/integration/test_assistant_attachment_backup.py::test_long_parent_paths_create_restore_and_rebackup tests/integration/test_contract_long_path_backup.py --basetemp=/private/tmp/qx-backup-regression-20261024/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
TMPDIR=/private/tmp node --test desktop/tests/model-settings.test.cjs desktop/tests/model-session.test.cjs desktop/tests/model-credentials.test.cjs desktop/tests/model-bridge.test.cjs
```

足够长的 ASCII basetemp 保持既有中文长路径夹具的单个组件不超过 macOS 字节长度限制；不更改测试定义。日志是本机合成结果，不等于 Windows、Electron、安装包或法律效果验收。

## 模型配置合同与本地存在性

仅检查当前调查 shell 的存在布尔，不输出值：`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`JEV_API_KEY`、`TYPESAFE_API_KEY`、`MODEL_PROVIDER_REF` 均为 false。仅检查本仓库固定相关路径的文件存在性：`.env`、`.env.local`、`.env.production`、`.local/workbench/workspace.json`、`.local/model-credentials/deepseek.bin`、`.local/model-credentials/typesafe.bin` 均不存在；`config/defaults.json` 存在。

这些结果只描述**当前 shell 和上述仓库路径**，不能推断其他进程、macOS 用户目录、Windows 机器或远端服务器没有凭据。没有搜索这些位置，也没有打开任何凭据文件内容。

源码事实：

- `.env.example` 明示应用不自动加载此文件；`config.py` 从固定 defaults JSON 加载，模型默认固定 mock。
- `local_server.build_local_app(..., assistant_model_runtime=None, assistant_judge_runtime=None)` 默认不注入真实模型运行时；`local_server` 普通服务启动没有创建模型 registry/control。
- `desktop_entry.py:101–111` 才创建 `MainModelRegistry`、`JudgeRuntime`，装配 `NativeModelControl` 和私有父子管道。桌面配置成功仍不自动授予发送权，发送授权有用途、内容、会话及预算边界。
- `domain.MainModelConfig` 只允许 provider=`deepseek`、protocol=`deepseek-chat-json-v1`，model 为 `deepseek-flash` 或 `deepseek-v4-pro`。
- `assistant/providers/deepseek_transport.py:13` 固定 `https://api.deepseek.com/chat/completions`，Bearer 认证，不从环境选择端点，外部调用关闭环境代理、重定向和自动重试。合成回环入口只能由可信测试显式构造。
- `desktop/model-credentials.cjs:48–55` 的实际 OS 加密持久化要求 `platform === 'win32'` 和可用异步 safeStorage；macOS 不能据当前实现宣称桌面密钥保存可用。

2026-10-24 查询的官方资料：[DeepSeek 首次调用](https://api-docs.deepseek.com/)、[模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)、[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。官方当前继续支持现有两个模型 ID、`/chat/completions` 和 `thinking: {type: 'disabled'}`；桌面两模型的保守 peak/cache-miss 输入输出单价也与页面一致，因此未发现这些字段的协议漂移。官方另列 Anthropic 兼容 base URL 为 `/anthropic`，不能把 Anthropic 格式或其他服务商地址直接接入当前固定 Chat Completions transport。OpenAI 格式兼容不等于凭据跨供应商兼容，也不等于普通服务器已经装配模型。

真实联调前的具体缺口是：确定实际运行入口、选定受支持供应商/格式及模型、从授权托管位置提供凭据、通过可信控制面完成运行时装配与单次发送授权，然后仅以虚构材料作一次受预算限制的端到端联调。本调查没有执行以上配置或调用，不能将 69 个合成测试称为真实模型成功。

## 随后主任务联调更新

本文件的配置存在性调查完成后，用户通过隐藏输入另行提供临时密钥。主任务随后完成一次真实DeepSeek独立虚构内容请求，结果见[联调回执](live-smoke.json)与[本次汇总](README.md)。这不改写本调查阶段真实调用0的事实，也不表示普通服务或Windows安装版已更新。
