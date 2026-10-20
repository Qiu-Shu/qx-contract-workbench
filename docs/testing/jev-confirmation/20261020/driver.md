# CH-05D2 实际主入口验收脚本扩展

2026-10-20。仅修改测试脚本，未改产品或安装版，未运行 Electron / GUI / 模型请求。待主代理冻结输入后顺序执行。

## 修改范围

- `desktop/tests/model-approval-acceptance.py`：保留默认主模型流程与旧冻结位置参数；新增互斥 `--judge` / `--judge-closed`，以及更明确的 `--frozen PATH`。
- `desktop/tests/model-credentials-acceptance.cjs`：仍加载真实 `desktop/main.cjs`。只有测试 observer 的显式 `QX_PROBE_JUDGE_BUDGET=synthetic-judge-budget-v1` 才在 require cache 包装 `createModelSession`，仅对 kind=judge 注入十进制字符串 `0.02`；无此标记则不包装。生产 main 未增加预算或环境入口。增加 authorizeJudge/revokeJudge 的仅状态观察，不记录 payload/token/secret。
- `tests/helpers/inspect_native_control_records.py`：原默认单 Main/单 Judge 验收保持；新增只读 `--main-count 2`，按指定 run 查 Main 与 message，支持本轮两 Main、一 Judge 的精确完整 codec hash / policy / receipt / decision 对账。

## 三种本轮执行

从 `D:\Documents\ChatGPT\律所项目` 执行；每次 OUTPUT 必须是尚不存在的独立目录。

```powershell
.\.venv\Scripts\python.exe -X utf8 desktop/tests/model-approval-acceptance.py .local/jev-confirm-20261020/source-ui --judge
.\.venv\Scripts\python.exe -X utf8 desktop/tests/model-approval-acceptance.py .local/jev-confirm-20261020/default-closed-ui --judge-closed
.\.venv\Scripts\python.exe -X utf8 desktop/tests/model-approval-acceptance.py .local/jev-confirm-20261020/frozen-ui --judge --frozen .local/jev-request-20261020/frozen-backend/qx-backend/qx-backend.exe
```

源码两个模式均复用上一片 `synthetic_native_control_entry.py --judge MAIN/JUDGE` 的双精确回环端点装配和 httpx/httpx2 send tripwire。没有使用旧单端点 wrapper，避免它将合法辅助回环误挡。测试 observer 把第二端点与 tripwire 文件作为 test entry argv；冻结程序不接受这些测试入口与端点替换。

### source --judge

实际设置窗口保存/配置独立 Main/Judge 合成密钥。长中文原生确认初始默认取消、辅助未选；检查完整文字保持字面文本、100/150/200%应用缩放和窄窗口后取消，原草稿保留。继续既有“确认中草稿被更新”拒绝旧内容用例。

首次实际发送保持辅助未选：Main 回环一次、Judge 零次；刷新历史不重发。保存另一份独立文字并明确勾选辅助：精确回环顺序应是 Main（首轮）、Judge（第二轮）、Main（第二轮），总两 Main、一 Judge。原始两份消息仍完整；只读验证辅助与第二 Main 属于同一 run，完整 input hash 一致，预算预留 `0.02`、费用 unknown、建议 internal/unverified，刷新不重发。

### source --judge-closed

实际配置 Main 与 Judge，但不注入任何辅助预算。原生确认中辅助可见、默认不选且禁用，说明仍可继续主模型。执行主流程一次，辅助 private authorize 与 provider POST 都为零。此模式验证生产默认关闭行为，不等同于支持用户在产品里自行设定辅助预算。

### frozen --judge

复用 D1 冻结 Python 后端，启动真实当前 Electron 主入口与确认窗；test observer 仍只为测试注入合成预算。成功步骤只调用固定 `desktopAssistant.authorizeGeneration`，明确双选后应收到 Main/Judge 各一条实际私有 authorize 成功回执。随后从实际设置界面分别 disable Judge 与 Main。整个模式不提交 `/generations`，业务 message/run/attempt/receipt/output/decision 均应为零。

冻结路径没有供应商 loopback 注入，也没有全进程网络观测。因此此结果只能称“冻结后端的 UI→私有双授权与双停用已验证”，不能称冻结供应商执行成功或全进程外网请求零。脚本报告明确 `frozen_network_observation=not_instrumented`。

## 静态检查已运行

以下 exit 0：Python `py_compile`（driver 与只读 inspector）、Node `--check`（observer）、driver `--help`。这是语法/参数校验，不是 GUI 通过。所有 GUI 输出、截图和断言结果待实际运行生成。

## 保留的观测范围与产物

每次独立数据目录、主入口 bootstrap 状态、窗口隔离参数、浏览器请求清单、脚本错误、合成供应商精确计数、只读 DB 计数、源码前后摘要；截图包括长文初始/缩放、主模型单选、双选或冻结选择。凭据明文只存在测试常量与内存；脚本检查数据目录与子进程日志不含两份合成凭据。

本脚本不新测取消/切换/迟到 ACK 的所有 private IPC 排列，这些由对应固定 IPC/lease 单元回归覆盖；不替代最终审阅。未扩充生产 SDK、配置入口、运行库、后台队列或预算机制。
