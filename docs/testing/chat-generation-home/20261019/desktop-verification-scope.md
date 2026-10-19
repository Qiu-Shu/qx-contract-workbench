# 首页生成：冻结后端与实际开发 Electron 验证

2026-10-19。此目录只含独立合成测试与本机验证产物，不是安装器、安装版更新或真实模型批准。

最终证据是 `desktop-final-summary.json`、`frozen-backend-home-report.json`、`electron-default-verified/report.json`、`electron-synthetic-verified/report.json`。EXE 4 组、默认 Electron 4 组、合成 Electron 5 组分别通过；这些是不同环境的验收分组，不合并冒称 13 个不同单元回归用例。最终三个探针实际退出码均 0。根代理的 Python/Node 回归另计。

冻结构建实际执行 `.local/chat-generation-home-20261019/frozen_build_verified.ps1`，内部调用已安装的 PyInstaller 和真实 `desktop/backend.spec`，完整参数、退出码、开始/结束时间见 `frozen-build-verified-command.json`。构建前后 205 份明确输入一致，摘要 `b31bb2d3f69fb74c5f5151acbd01a262f7d1079660e999be9bac115645a94208`。日志保留 4 条 WARNING（tzdata、pysqlite2、MySQLdb、psycopg2 隐式导入不可用），不宣称零警告。产物目录 `frozen-backend-verified/qx-backend` 为 547 文件、96,189,838 字节；EXE SHA-256 为 `17e6bb2241caaa10335546ffda42c062c242392654d679fab570b1f6d37eb9af`。

最终探针命令（均在实际项目根目录运行）：

```powershell
.venv/Scripts/python.exe -X utf8 .local/chat-generation-home-20261019/frozen_backend_home_probe.py
.venv/Scripts/python.exe -X utf8 .local/chat-generation-home-20261019/electron_home_probe.py default .local/chat-generation-home-20261019/electron-default-verified
.venv/Scripts/python.exe -X utf8 .local/chat-generation-home-20261019/electron_home_probe.py synthetic .local/chat-generation-home-20261019/electron-synthetic-verified
```

Electron 输出目录必须是新目录，复验需换新目录名。实际 Electron 命令和绝对路径在各 `report.json` 的 `command` 字段；脚本使用已有 Electron 44.8.0，不联网安装。Playwright 只通过绑定 `127.0.0.1` 的 CDP 驱动实际应用创建的窗口。

`electron_probe_bootstrap.cjs` 直接 require 实际 `desktop/main.cjs`，不替换 BrowserWindow、session、preload 或窗口安全策略。Backend 子类只观察 ready/退出；default 模式保留实际 `python -m cn_contract.desktop_entry`。验证观察到 `nodeIntegration=false`、`contextIsolation=true`、`sandbox=true`、`webSecurity=true`；renderer 不可访问 Node，也不能从首页调用仅设置页获准的账户建立接口。

synthetic 模式只把开发 Backend 的入口换为本目录 `electron_synthetic_entry.py`。该测试入口先在 Python 内替换 `build_local_app` 装配，再调用真实 `desktop_entry.main`；stdin 协议、真实应用、真实适配器与生命周期均保留。可信运行时只批准一个固定合成文本摘要、回环假供应商及有限预算。生产源码与默认 `runtime=None` 未被改为启用状态。最终合成 Electron 恰好 1 次上游 POST、1 消息、1 attempt、1 receipt、1 内部待核候选；刷新只读回历史，不重复 POST；真实供应商调用为 0。

新冻结 EXE 验证登录、首页、四份新静态模块字节一致、默认生成拒绝且草稿保留、历史端点的当前归属校验，以及旧 `/messages` 仅登记不生成模型 attempt。最终数据库为 1 条旧消息、0 attempts/receipts/outputs；完整性与 schema 标记一致。关闭父管道后实际 EXE exit 0，监听端口释放。

实际 Electron 经原设置页建立合成账户、登录首页、保存和显示结果、刷新历史，再关闭原窗口，应用与其自有后端均正常 exit 0、端口释放。候选滚动后以矩形和 `elementFromPoint` 核对未被 sticky 输入区遮挡，原文引用与费用提示可见；截图在 `electron-synthetic-verified/electron-candidate-visible.png`。18 份桌面/首页验证输入前后及两种 Electron 模式一致，并与当前源码及相关冻结输入比对无差异。

历史说明：`electron-default-initial` 的断言误以为新 Electron 的 `getLastWebPreferences()` 会返回 preload 路径；`electron-synthetic-initial` 使用错误 CSS selector。仅修测试 harness 后通过，原日志保留，不能计为产品红灯。`frozen-backend-final` 是根代理最后修复刷新入口前的中间构建，未做最终验收；`*-second` 和 `*-visual` 为较早验证，最终只认 `*-verified` 与上述冻结报告。

未修改、构建或替换安装器及安装版 0.4.1；未使用真实工作区、真实客户材料、真实模型端点或凭据；未执行发布、推送或完整 Python/Node 回归。
