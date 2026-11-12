# 候选 GitHub 仓库准入核验：法律方法与评测

核验日期：2026-11-12（北京时间），上游快照汇总时间 16:06:51。工作区 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，基线 `5e01b065e4a1de9c63aa9d2c51118812e442ec86`。本轮只核验候选是否适合加入，不构建安装包、不安装依赖、不调用真实模型、不运行上游安装/部署脚本。GitHub 上游通过连接器读取；文件内容是审查资料。

结论：**中国法研究四项适配可以维持产品内现状；Promptfoo 仅保留为开发评测工具，其“零外连”准入存在已复现缺口；skill-creator 适合开发方法借鉴；knowledge-work-plugins/legal 不直接导入。** 本轮没有新启用上述仓库的运行能力。

| 仓库与选定范围 | 结论 | 当前实际状态与条件 |
| --- | --- | --- |
| CSlawyer1985/claude-for-legal-ZH：四项 legal-research-cn 方法 | 适合产品，限已适配四项方法 | 已加入四个 Harness 方法入口，保留原文与许可；不整仓导入，不新增数据库/外部连接器 |
| promptfoo/promptfoo 0.125.1 | 仅开发，零外连准入受阻 | 已在 evals 独立锁定；禁用遥测变量仍可触发一次上报意图，整改并复验前不能称完全离线 |
| anthropics/skills：skill-creator | 仅开发 | 可借鉴基线、独立评审与触发测试；未导入本产品。原脚本依赖 Claude CLI，原查看器含外部资源 |
| anthropics/knowledge-work-plugins/legal | 暂不加入（不直接导入） | 只保留已有 G01 方法参考；不复制其连接器配置，不增设第二套合同审查入口 |

## 固定提交与许可证据

| 对象 | 核验固定提交 | 许可及 NOTICE 范围 |
| --- | --- | --- |
| 中国法研究方法 | `59f37f1c8851b8277e24f7a45f4e773bee97bab9`；本轮 main 与该 pin 相同 | [根 LICENSE](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/LICENSE) 为 Apache-2.0；834 条、未截断的固定提交树中未见 NOTICE 文件。四个原方法与本地清单 Git blob 完全相同 |
| Promptfoo | `0.125.1` → `8569e72ed6cf7737082a6042be8d925e40f9739d` | [tag ref](https://api.github.com/repos/promptfoo/promptfoo/git/ref/tags/0.125.1)、[MIT LICENSE](https://github.com/promptfoo/promptfoo/blob/8569e72ed6cf7737082a6042be8d925e40f9739d/LICENSE)；固定提交根目录未见 NOTICE，不能据此将全部传递依赖认定为 MIT |
| skill-creator | `2c5958ecac7cee2b583967a2c4981d0f4a75c579`；本轮 main | 直接读取 [skills/skill-creator/LICENSE.txt](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/LICENSE.txt)，确认为 Apache-2.0，版权为 2026 Anthropic, PBC；不是用仓库根许可推断。根 LICENSE 请求实际返回 404；仓库有 [THIRD_PARTY_NOTICES.md](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/THIRD_PARTY_NOTICES.md)，列明影像组件、FFmpeg、Pillow、字体等，不能将整仓说成单一许可证 |
| knowledge-work-plugins/legal | 对照本轮 main `877a617b435ee2edfb002d9a3703c0a1a03aa1ba`；本项目既有 G01 仍锁 `8444efcd48f7012f09797778a36a33e73d0861f4` | 本轮读取 [legal/LICENSE](https://github.com/anthropics/knowledge-work-plugins/blob/877a617b435ee2edfb002d9a3703c0a1a03aa1ba/legal/LICENSE) 为 Apache-2.0；未截断当前树中未见 legal 内 NOTICE。新旧 pin 的 review-contract/SKILL.md Git blob 同为 `030204860ec70bf80254f9894721504df7c81bd5`，没有以跟随 main 为由重做旧适配 |

以上是文件级技术准入核验，非对整个仓库全部依赖的许可清单审计。Apache 适配继续保留许可、署名与修改说明；不能据 skill-creator 的许可扩大至其他目录或浏览器 CDN 组件。完整 URL、Git blob、当前上游头及验证摘要在[机器记录](2026-11-12-candidates-methods-eval.json)。Promptfoo 本轮 main 已是 `e4ecd0e48b08aedebe186b2ee868b0f31c62e3fe`，本项目不随 main 漂移，仍评估已用 0.125.1。

## 中国法研究方法：维持选择性加入

实际四项是[法源与版本核验](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/authority-check/SKILL.md)、[类案对比](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/case-comparison/SKILL.md)、[争点备忘录](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/issue-memo/SKILL.md)、[讲座来源包](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/lecture-source-pack/SKILL.md)。本轮重新读取五个上游文件（四方法与 LICENSE），blob 与 `sources/legal-research-cn.json` 一致；本地目标测试再校验 SHA-256、Git blob、Apache 文本、署名修改说明、相对引用和工具名。

它们已适配为 `qx-authority-check`、`qx-case-comparison`、`qx-issue-memo`、`qx-lecture-source-pack`。正文证据卡沿现有 record_case_note/read_case_note/export_case 保存，现有案例隔离、追加与引用状态仍由业务层控制；没有额外 Python/Node 依赖。检索仍调用本项目既有 legal_search/legal_search_read/web_fetch，需要外部原文时会使用相应网络能力，不能把“方法只是 Markdown”解释为实际研究永不联网。四方法本身没有安装脚本或独立遥测代码；这个结论不覆盖上游整仓。

当前测试证明实际 Harness 可发现并调用四方法，原文和许可完整、升级不会覆盖自定义或禁用设置。其收益是把法源版本、地域、时点、未知状态与相反观点保存为可回读证据；不证明法源真实有效、法律解释正确或律师质量达标。下一步是使用获准的合成/脱敏样本，由律师核验研究质量和长材料效果，保持 `matched` 与法律有效性判断的区分。现有细节见[研究方法验证](../2026-11-12-legal-research-verification.md)。

## Promptfoo：已有开发价值，但禁用变量不足以证明无网络

现有 `evals/quality-baseline/package.json`、完整 package-lock、`.npmrc` 将 Promptfoo 0.125.1、Hono 4.13.18、Windows x64 libsql 0.5.29 隔离为开发依赖，安装脚本关闭。主产品 package.json 不包含 Promptfoo。锁文件有 **663 个非根条目**，包含本机未安装的 optional/平台包，不能当作实际加载或产品分发数量；原生绑定也不能算跨平台已验收。包根 MIT 许可与本地留存副本 SHA-256 相同：`bf813686553f451e1b833fbd827488aee49b60b189626915bf3108d10b754e44`。部分锁条目含 LGPL 或独立许可描述，本轮未安装的 optional 依赖不能被误报为已进入产品；未来扩大分发仍需逐依赖审计。

本地自定义 provider 复用真实 Harness 和 MCP 工具，脚本模型控制调用，断言检查真实 DOCX、原件 hash、保存记录、串案、金额、日期、错误引用和中断。真实模型入口还有显式开关、凭据和共享预算账本。它适合维护开发回归；没有理由作为律师运行时依赖再带入产品。[固定版包信息](https://github.com/promptfoo/promptfoo/blob/8569e72ed6cf7737082a6042be8d925e40f9739d/package.json)

**发现的阻断：** 上游 [src/telemetry.ts](https://github.com/promptfoo/promptfoo/blob/8569e72ed6cf7737082a6042be8d925e40f9739d/src/telemetry.ts) 在禁用遥测后，`record()` 仍经 `recordTelemetryDisabled()` 调用 `sendEvent()`；PostHog 客户端虽返回空，后续 `fetchWithProxy(R_ENDPOINT, POST)` 不受同一开关阻断。本机实际分发 `dist/src/main.js` 导入的 `telemetry-CIqy4fSC.js` 保留该路径，目标常量是 `https://r.promptfoo.app/`。仅设 `PROMPTFOO_DISABLE_TELEMETRY=1`、更新和远端生成禁用变量不足以承诺进程零外连。

已运行[只读复现探针](../../experiments/candidate-admission/promptfoo-telemetry-probe.cjs)：先核验实际分发文件 SHA-256 `36250d9ae7dfb037e357d0c1b0cbde8922b91d5225292743fadf4596a4a9a24d` 和版本，再只提取 Telemetry 类，在 VM 内以合成身份、空账户和内存请求记录器替代外部函数。禁用遥测后两次 `record()` 捕获 **1 次 POST 意图**，内容是 `feature_used / telemetry disabled` 及运行元数据；**真实网络调用 0**。探针退出 0 意为问题成功复现，不是零外连测试通过。

这不能倒推出此前评测已成功发送请求或泄露案件。此前 24 案的业务模型是脚本化、法源虚构，仍能支撑其流程测试结果；**业务模型离线不等于评测进程零外连**。本轮没有重新运行整个 Promptfoo 入口，也未用真实网络检查遥测端点。

最小整改条件：给开发评测进程增加可独立验证的默认拒绝外连边界（含其子进程），或审计后固定修复版/本地补丁，并对遥测、更新、远程生成、分享和 provider 路径做真实请求拦截验收；显式 live 模式只放行获准模型端点。随后重跑 24 案，分别报告“工作流正确”和“未发生未授权网络尝试”。本轮没有修改 runner 或依赖，整改前维持开发限定和阻断标记。

## skill-creator：许可可用，原执行方式不适合直接嵌入

已核验它自己的 LICENSE.txt 是 Apache-2.0；“该仓库有些技能曾采用不同条款”不能用作本文件当前许可的替代结论。适合复用的是 [SKILL.md](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/SKILL.md) 的有/无技能基线、人工评分、独立比较、训练/留出样例和触发反例思想，与现有开发评测可以互补。仓库当前没有本项作为产品方法的导入记录；本轮也未新增。

原版 [run_eval.py](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/scripts/run_eval.py) 会写入项目 `.claude/commands` 并启动 `claude -p`；[improve_description.py](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/scripts/improve_description.py) 也直接调用该 CLI。它们沿 Claude 登录/模型行为运行，不能当作兼容现有 Harness 的离线函数，也不能继承本项目预算保护。未审阅 CLI 本体，不能声称其网络/遥测已验收。

原版 [viewer.html](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/eval-viewer/viewer.html) 引入 Google Fonts 和 `cdn.sheetjs.com` 脚本；即便生成静态 HTML，浏览器仍可能请求外部资源。其 [generate_review.py](https://github.com/anthropics/skills/blob/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator/eval-viewer/generate_review.py) 默认本机服务监听 127.0.0.1，但这一点不能消除页面外链。未打开该查看器、未执行其脚本。

准入下一步只需把评审方法融入既有开发流程；若之后需要自动运行或查看器，再单独适配本项目 Harness、预算和数据目录，移除/本地化外部资源并保留许可。当前没有足够收益为产品再引入 Claude CLI、第二套执行器和评分站点。

## knowledge-work-plugins/legal：仅作对照，保留已有方法参考

现有 `sources/upstream.lock.json` G01 已保存固定上游的合同立场、playbook、修改与谈判方法，明确不引入外国法默认和连接器权限。当前 [review-contract](https://github.com/anthropics/knowledge-work-plugins/blob/877a617b435ee2edfb002d9a3703c0a1a03aa1ba/legal/skills/review-contract/SKILL.md) 与既有固定版的文件 blob 未变，没有新实现缺口需要整包导入。

该目录 [`.mcp.json`](https://github.com/anthropics/knowledge-work-plugins/blob/877a617b435ee2edfb002d9a3703c0a1a03aa1ba/legal/.mcp.json) 声明 Slack、Box、Egnyte、Atlassian、DocuSign 等 HTTP 连接器。复制整插件会引入本项目现有边界以外的连接器配置和工作假设；许可证允许参考不等于这些账号、外发或数据范围已获授权。本轮未调用这些服务。结论是暂不直接加入，G01 的既有可追溯方法参考继续保留。

## 实际验证记录与限制

以下命令 cwd 为工作区 `harness/`；复用已有 `.local/audit-0216/build/test-env.ps1`，未安装新依赖。

```powershell
. './.local/audit-0216/build/test-env.ps1'
node --test tests/legal-research-skills.test.cjs evals/quality-baseline/checks.test.cjs evals/quality-baseline/live.test.cjs
node experiments/candidate-admission/promptfoo-telemetry-probe.cjs
```

- 第一个命令退出 **0**，**26 通过、0 失败、0 跳过**：3 项真实技能发现/来源/升级保护，20 项工作流断言，3 项无真实网络的预算边界测试。
- 第二个命令退出 **0**：复现禁用遥测仍尝试上报的控制流；2 次调用、1 次内存请求、0 次真实网络请求。
- Node 内联只读摘要核对退出 **0**：历史 `.local/quality-baseline/2026-11-12T07-10-36-740Z-0c046a2d` 的 14 个源码摘要仍全部匹配；原报告为 **24/24**、`mode: scripted`、`qualityStatus: not_reviewed`，报告 SHA-256 `d33e77c2f9a4e9b9fea8afd45019aae3ecc44b244e00b6fcc5f932df1ab155f3`。这是核对旧证据，本轮未重跑 24 案。
- 许可/依赖内联读取退出 **0**；GitHub API 为读取操作，没有 shell 退出码。一个探查根 LICENSE 的请求返回 404（anthropics/skills）；随后按实际 skill 目录成功读取许可。

本次不把通过数量外推为法律质量、无幻觉或生产合规认证；没有 real-model、律师质量、整机网络隔离、跨平台或产品构建验收。研究来源和工作流原验证分别见[研究方法记录](../2026-11-12-legal-research-verification.md)、[工作流记录](../2026-11-12-workflow-evaluation-verification.md)。
