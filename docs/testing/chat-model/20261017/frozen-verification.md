> 原始记录位于本仓 `.local/chat-model-20261017`；下文原始脚本、日志和未复制的页面文件路径均相对该目录。此处仅保存可提交摘要。

# CH-04A Windows 冻结验证

日期：2026-10-17。工作区：`D:\Documents\ChatGPT\律所项目`。

**结果：事件序列完整性修复后的最终私有 backend 构建及独立冻结合成 probe 均通过。** 正式 0.4.1 应用未安装、替换或更新；主界面没有因此开启真实模型。本轮没有读取用户密钥或连接外部模型。

## 构建输入与工具

- 复用 `desktop/backend.spec` 的真实后端入口、资产清单、隐藏导入与排除规则；构建环境为项目 `.venv` 加 `.local/desktop-tools/python-build` 中既有 PyInstaller 6.22.3。
- 辅助 spec 仅将原 spec 的入口替换为本目录 `frozen_model_probe.py`，名称改为 `qx-model-probe`；不改变任何产品源码、正式测试、依赖或桌面安装配置。
- 收到事件序列修复后的再次全源码冻结通知，执行 `frozen_build.ps1`。201 项明确构建输入的构建前/后及运行后文件摘要完全相同，集合 SHA256：`144012e66c2f03e68c46613d925a6282cd7ec54b2ab1535c3ff6badc1e2a9444`。完整映射见 `frozen-source-before.json` / `frozen-source-after.json` / `frozen-source-verified.json`。
- 事件修复之前实际通过的构建、完整产物、验证报告、合成工作区与输入清单已复制到 `frozen-before-event-sequence-fix`，明确标注仅覆盖旧快照，未混入本次最终结论。
- 最早一次构建在得知两个产品补丁尚未汇合后主动停止，日志保存为 `frozen-backend-interrupted-before-freeze.log/.exit`，退出码 -1；没有计为通过。最终构建使用新的 `*-final` 目录。
- 最终两个 PyInstaller 进程退出码均为 0。构建日志各有 `tzdata`、`pysqlite2`、`MySQLdb`、`psycopg2` 隐藏导入提示；本轮实际 SQLite/UTC 运行路径未因此失败。提示和完整依赖分析均保留，不能称构建零警告。

## 实际运行结果

| 验证对象 | 实际结果 |
|---|---|
| 新冻结 `qx-backend.exe` | 使用新的中文合成工作区，通过 stdin 配置启动；ready 用时 1.432 秒；登录页、未授权拒绝、真实登录、session 与 assistant 首页 HTTP 检查通过 |
| 后端结构 | 新库精确识别为 `assistant-model-v1`；三张 model 表存在且均为空；marker 摘要、SQLite quick_check 与 foreign_key_check 通过 |
| 后端退出 | 关闭父进程 stdin 后正常退出，exit 0、stderr 0 字节，端口关闭；未遗留本轮后端进程 |
| 独立冻结辅助程序 | `sys.frozen=True`；实际从其 `_internal/httpx2` 加载 httpx2 2.13.1，显式注入合成政策与假凭据；唯一网络目标为自己监听的 `127.0.0.1` |
| 完整受控主链 | `enqueue_generation → execute_attempt → read_attempt` 完成一次真实 loopback HTTP POST；request 实际 UTF-8 为 1024 字节，持久 wire 摘要与收到的字节摘要一致 |
| 输出与费用 | 正文通过结构与来源核验；应用保存 internal/model_generated/unverified；usage=42 tokens，按合成费率估算 0.0000234 USD；不称供应商账单 |
| 重放 | 同 attempt 再执行、同 request 再登记及读取返回同一结果；HTTP POST 总数仍为 1；attempt/receipt/output/message/run 各 1 条 |
| 辅助退出 | exit 0，stderr 0 字节，未遗留本轮辅助进程。默认 Settings 的模型提供者仍为 mock |

独立辅助程序证明新增模块与 httpx2 在冻结环境中的受控合成链可用，**不代表正式安装版已装配模型或真实供应商连通**。本轮未运行全部 pytest；最终完整回归由根代理另行记录。

## 包体

均为 PyInstaller 目录包，不含 Electron 安装包。

| 产物 | 文件数 | 目录总量 | 主 EXE |
|---|---:|---:|---:|
| 真实 backend | 546 | 96,153,813 bytes / 91.699 MiB | 15,513,211 bytes / 14.795 MiB |
| 独立合成 helper | 546 | 96,141,085 bytes / 91.687 MiB | 15,500,483 bytes / 14.782 MiB |

backend EXE SHA256：`62d019a884c76d556c2a29ca99484540bc1a86bd572ee08985ef01ecd7759148`。

helper EXE SHA256：`2eb9bcc6e35f20b657c82924c1c3e35403086cb4555a27a1859ed24c5c6399ef`。

## 可复核入口

- `frozen-summary.json`：全部产物、字节数、摘要及运行退出码。
- `frozen-backend-smoke.json` 与 `.stdout.log/.stderr.log/.exit`：真实后端。
- `冻结 合成模型回执 840f66e6/report.json` 与 `frozen-model-helper-run.stdout.log/.stderr.log/.exit`：辅助冻结调用。
- `frozen-backend-final-build.log/.exit`、`frozen-model-helper-build.log/.exit`：两次最终构建。
- `frozen_build.ps1`、`verify_frozen_runs.py`、`frozen_backend_smoke.py`、`frozen_model_probe.py`：仅在本目录保存的验证脚本。

所有工作区和生成物均位于本任务 `.local/chat-model-20261017` 内，使用独立虚构文字与假凭据。未运行用户真实材料。
