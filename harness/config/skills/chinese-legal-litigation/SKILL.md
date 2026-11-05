---
name: chinese-legal-litigation
description: "Use when the user needs Chinese legal work in the 诉讼仲裁 domain: 案件登记、诉讼仲裁、律师函、要件分析、大事记、证据三性、庭前准备、保全、传票、法律文书. This is a DeepSeek Harness (dsh) adapter for claude-for-legal-ZH/litigation-legal; it routes natural-language requests to the original domain CLAUDE.md and skills/*/SKILL.md workflows."
---

# 诉讼与仲裁 · Harness 工作区入口

<!-- source-bound-route-v6 -->
本案需要诉讼、仲裁、律师函或证据说明的来源绑定待审文稿时，优先加载 `qx-source-drafting`，按其范围和真实工具保存、导出。此入口不恢复旧停用工作流，也不代表完整领域审查通过；其他任务按实际可用能力处理，不能把通用自由记录当作同等来源保障。

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

根据用户任务选择最贴近的一个或少数几个技能，用 `skill` 工具加载完整正文；不要一次加载整个领域。

- `legal-zh-litigation-chronology`（原工作流：`chronology`）
- `legal-zh-litigation-cold-start-interview`（原工作流：`cold-start-interview`）
- `legal-zh-litigation-customize`（原工作流：`customize`）
- `legal-zh-litigation-demand-received`（原工作流：`demand-received`）
- `legal-zh-litigation-deposition-prep`（原工作流：`deposition-prep`）
- `legal-zh-litigation-legal-hold`（原工作流：`legal-hold`）
- `legal-zh-litigation-matter-briefing`（原工作流：`matter-briefing`）
- `legal-zh-litigation-matter-close`（原工作流：`matter-close`）
- `legal-zh-litigation-matter-intake`（原工作流：`matter-intake`）
- `legal-zh-litigation-matter-update`（原工作流：`matter-update`）
- `legal-zh-litigation-matter-workspace`（原工作流：`matter-workspace`）
- `legal-zh-litigation-oc-status`（原工作流：`oc-status`）
- `legal-zh-litigation-portfolio-status`（原工作流：`portfolio-status`）
- `legal-zh-litigation-subpoena-triage`（原工作流：`subpoena-triage`）

原适配器保存在 `legal-library/zh/.dsh/skills/chinese-legal-litigation/SKILL.md`。本入口复用其领域路由，调整为工作区内路径与无冲突的技能名称；不修改用户全局配置。
