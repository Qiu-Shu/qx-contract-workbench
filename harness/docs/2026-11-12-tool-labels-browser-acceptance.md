# 0.2.17 中文工具卡片浏览器验收

2026-11-12，最终候选解包资源的独立浏览器烟测 **5/5 通过，exit 0，页面错误 0**。本专项只新增 `tests/check_tool_labels_ui.py` 和本记录，没有修改产品代码或包内文件。

实际工作区：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目/harness`。

实际 payload：`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-final-extracted/application/resources/workbench`。

## 检查内容

复用既有隔离 Harness 宿主，以候选包内 Node 启动、包内模块系统导入真实 React 工具卡片，并通过公开 `apply` 入口取得 `ToolCallTree`；使用包内中文通用文案。测试没有变换、重写或替换工具卡片源码。

| 原协议工具 ID | 实际可见名称 | 展开与查看 |
| --- | --- | --- |
| `mcp__qx_materials__read_material` | 读取材料正文 | 输入、结果及原 call ID 通过 |
| `mcp__qx_legal__calculate_calendar_date` | 计算日期 | 同上 |
| `mcp__qx_knowledge__search_knowledge` | 检索知识库 | 同上 |
| `mcp__windows__Snapshot` | 读取当前桌面界面 | 同上 |
| `mcp__unknown__synthetic_probe` | 工具调用＋原始工具 ID | 未猜译；输入、结果及原 call ID 通过 |

每张卡片先核对收起状态，再点击展开参数与结果，随后点击“查看”。五条渲染路由的 `toolName` 和 `entryKey` 保留原 ID，五次查看回调保留原 `callId`；传入记录的名称、参数、结果前后完全相同。四个已知工具的收起标题不再重复英文协议 ID。截图已人工查看，五张卡片均可读。

## 实际运行与证据

证据根：`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112`。

- RED：旧 `candidate-extracted` 的实际包内卡片仍显示“工具调用 mcp__qx_materials__read_material”，中文名称断言失败，exit 1；日志 `logs/tool-labels-browser-red-3.log`，截图 `tool-labels-qa/1794469968451/tool-labels-failure.png`。此前一次模块观察接线超时及一次未接中文通用文案的准备日志保留，不计产品测试结果。
- GREEN：最终 payload 两次运行均为 5/5、exit 0。第二次仅扩大截图视口，完整证据为 `tool-labels-final-qa/1794470145304/tool-labels-report.json`、同目录 `tool-labels.png`，日志 `logs/tool-labels-browser-final-2.log`。
- 包内 `dsh-client-ui-tool/lib/client.js` 运行前后 SHA-256 均为 `1706a72a66e4c38f6d294ef534005fde6f3e6ffa4298504e71066a4966b6ed9d`。
- 最终报告 SHA-256：`ab3b129ec674fb753b4cbe70398dad35d6ebc8611db40f5893721592779d7f5e`；截图：`a10f8358acb9fe7c882825d068b54cddea8415aa98735ddd27ea1d105025e01c`。
- 最终脚本 SHA-256：`0b4af87bf39755ba1cbc4d134217bdb4cda0a7dc6e9405d7714a987259215534`。

复跑入口（从上述工作区执行；输出按时间戳新增目录）：

```powershell
. 'D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/acceptance-env.ps1'
$env:QX_TEST_APP='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-final-extracted/application/resources/workbench'
$env:QX_TEST_OUTPUT_ROOT='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/tool-labels-final-qa'
$env:PYTHONIOENCODING='utf-8'
& $env:QX_TEST_PYTHON tests/check_tool_labels_ui.py
```

测试始终设置 `PYTHONDONTWRITEBYTECODE=1`；浏览器关闭后终止本次宿主进程树。2026-11-12 15:55:59（Asia/Shanghai）复查烟测 Python/Node 启动器残留为 0；15:56:45 再查最终 payload 的 Node Web 宿主为 0。没有运行正式安装器，资料目录全部独立。

**边界：** 此处是最终包内真实卡片组件的浏览器渲染与交互验收；工具记录为合成数据，查看回调为测试收集器，没有实际执行所列文件、日期、知识库或桌面工具，没有调用真实模型，不证明模型调度、工具副作用或会话持久化。五个代表性浏览器用例也不等于逐个工具的完整业务验收；全面标签映射由独立单元测试负责。
