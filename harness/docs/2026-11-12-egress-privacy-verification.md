# 评测外连控制与脱敏误遮修复

2026-11-12，按用户“OK落地”，完成已确认的前两项：[实施范围](2026-11-12-egress-privacy-plan.md)。实际工作树 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，基线 `54c8e3b0f5b47952f611a15f1559faa00d0b736f`。**源码修复与本轮验证完成，未构建安装包、安装新版、下载依赖、调用真实模型或推送发布。** restic、Presidio、Docling 接入仍是后续事项。

## 评测入口的实际改变

`npm run eval:workflow` 在启动 Promptfoo 前加载本地策略。默认拒绝 Node 的 fetch、TCP/TLS（也覆盖 HTTP/HTTP2/WebSocket）、DNS、UDP、Worker 及任意子进程；仅允许已配置 Python 启动固定 relay。relay 启动两个 MCP 服务及材料解析器时，也会经过同一 Python 启动保护，拒绝其他命令和网络审计事件。Windows asyncio 内部创建本机 socketpair 的路径保留，未开放通用 loopback 网络。

每次拒绝写入该轮 `network.jsonl`。即使依赖把异常捕获后继续，入口会读取审计并返回失败；缺审计、固定适配未生效、缺 Node/Python 防护记录、默认模式出现模型请求同样失败。原本的脚本模型、真实 MCP、文件与保存断言继续运行。

显式 live 模式仍需原有开关、密钥和共享预算。在适配器完成预算预留之后，只允许 `https://api.deepseek.com/chat/completions` 的 POST，重定向强制拒绝，Python 子进程仍不允许模型联网。独立审阅以假传输验证预算结算与端点控制，真实模型请求为 0；未把该模拟验收称为真实 API 联调。

固定 Promptfoo 0.125.1 的两处内存适配均先验证原始字节 SHA-256，替换位置必须唯一；未修改 node_modules 或锁文件：

| 固定文件 | 原始 SHA-256 | 适配 |
| --- | --- | --- |
| `telemetry-CIqy4fSC.js` | `36250d9ae7dfb037e357d0c1b0cbde8922b91d5225292743fadf4596a4a9a24d` | 遥测关闭时直接返回，不再生成“关闭遥测”事件 |
| `main.js` | `df6d75a365d37d01d948afc48434bcd18e28f466f82552c00dfeb3878a60e4bd` | 先检查可选配置是否存在，再加载 TS；已存在配置仍沿原逻辑读取 |

依赖升级后摘要不符会停止评测，必须重新审阅适配。原始缺口的[候选报告](research/2026-11-12-candidates-methods-eval.md)作为历史证据保留；本轮没有反推历史请求实际发送成功。

这里是固定、受审计开发依赖的语言运行时保护，不是操作系统网络沙箱。不能拿它运行任意不可信脚本、原生扩展或借此声称全机器零网络；直接启动上游 CLI 也不在此入口保护内。审计不记录请求正文、密钥或完整 URL。

## 脱敏修复

共用 `_generic_organization` 原来能排除单独的“学校”“医院”，不能排除并列的“学校和医院”。现在仅当并列项**全部**是通用类别时才跳过，支持“和、与、及、以及、或”；具体机构名称仍会遮盖。该共用判断同时影响新候选及旧字典的启用判断，因此旧误判不会继续遮盖新上传文本；旧映射本身没有删除，历史恢复信息保留。

新增公开上传边界用例覆盖普通/深度模式、五种并列词、具体学校/医院和联系人；要求 `2026年12月31日`、`12000元`、`12.5%` 保留，并检查旧字典场景。原件保持、手工复核、模式切换、自定义词及可逆恢复由现有回归覆盖。没有引入模型、词库或替换识敏引擎；不声称解决所有无标签姓名/OCR 漏识。

## 失败与修复证据

- HTTP 接收器先完成一次合成正向控制，确认接收器有效；保护缺失时第二次请求实际到达，测试失败。修复后请求被拒绝，接收计数不再增加。
- 脱敏新用例修复前实际失败于“学校和医院”被遮盖；初次因未设置 `QX_LEGACY_ROOT` 导致的收集错误另存，不计为行为失败。正确环境下的 RED 与修复后的 GREEN 均保留。
- 子进程接线先发现 Windows 审计接收字符串命令行，以及材料服务还会启动独立 reader。已按实际受控调用适配并保护 reader，没有放开任意 Python 运行。
- 首轮完整评测业务 **24/24**，但有 **2 次被拒绝的 tsx 父进程命名管道 IPC**，入口实际 **exit 1**。只读调用栈确认它们不是互联网请求，原因是探查不存在的 TS 配置时提前加载 tsx。前移存在性检查后再次运行，最终业务与网络审计均通过。首轮报告未覆盖，也未记成通过。

## 最终实际验证

所有原始日志保存在 `D:/CodexChecks/AI-Shixiong-egress-privacy-20261112`。使用已有 `harness/.local/audit-0216/build/test-env.ps1` 与 D 盘临时目录。下表各组独立列出，目标测试与全量存在重叠，不相加宣传数量。

| 命令/范围 | 实际结果 |
| --- | --- |
| `node --test .../network.test.cjs .../live.test.cjs` | 6 通过，0 跳过，exit 0；涵盖 12 种 Node 拒绝操作、4 种 Python 拒绝操作、受保护的本地事件循环、真实加载固定遥测模块、模拟预算 |
| `pytest bridge/test_privacy_modes.py bridge/test_privacy_review.py` | 19 通过，exit 0；先 RED 后 GREEN |
| `node evals/quality-baseline/run.cjs` 最终轮 | **24/24，0 failed，0 errors，exit 0**；102 秒；业务模型 scripted，法律质量 `not_reviewed` |
| 最终轮网络审计 | **122 个受保护进程（1 Node + 121 Python）；拒绝尝试 0，模型请求 0；两处适配生效** |
| `npm test` | **Node 429 通过/2 既有跳过；Python 464 通过/1 既有跳过，36 子测试通过；入口 exit 0** |
| `pytest bridge/test_privacy.py` | **44 通过，exit 0**；Windows 文档、PDF/图像与恢复相关保护 |
| 独立 Standards / Spec 审阅 | 两轴均无未解决阻断项；Spec 另实测 TLS、HTTP2、WebSocket、假模型传输及配置探查 4 路径；已补入子包默认网络测试并更新 README |

最终评测目录为 `harness/.local/quality-baseline/2026-11-12T08-54-24-702Z-876ae4b1`；失败首轮为 `2026-11-12T08-50-10-281Z-4ce94fed`。两轮各有 manifest、Promptfoo 结果与网络审计。原始依赖字节、最终 18 个评测执行输入摘要、最终修复文件、日志与独审证据的复查清单见[结构化证据](checks/egress-privacy-20261112.json)。

尚未进行：真实模型/律师法律质量验收、全机器网络隔离、跨机测试、restic 产品接入、Presidio/Docling 新试点、安装包构建及正式安装。下一项可按既定计划推进本地备份的数据范围与统一停写，不把本轮两处修复扩大称为整个审核计划完成。
