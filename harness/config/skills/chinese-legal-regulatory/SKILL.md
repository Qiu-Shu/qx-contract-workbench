---
name: chinese-legal-regulatory
description: "Use when the user needs Chinese legal work in the 监管合规 domain: 法规动态监控、监管简报、政策差异比对、合规差距、征求意见稿、监管政策重写、行政监管. This is a DeepSeek Harness (dsh) adapter for claude-for-legal-ZH/regulatory-legal; it routes natural-language requests to the original domain CLAUDE.md and skills/*/SKILL.md workflows."
---

# 监管合规 · Harness 工作区入口

<!-- source-bound-route-v6 -->
本案需要合规事项的原文台账及明确日期线索跟踪时，优先加载 `qx-source-registers`，按其范围和真实工具保存、导出。此入口不恢复旧停用工作流，也不代表完整领域审查通过；其他任务按实际可用能力处理，不能把通用自由记录当作同等来源保障。

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

根据用户任务选择最贴近的一个或少数几个技能，用 `skill` 工具加载完整正文；不要一次加载整个领域。

- `legal-zh-regulatory-cold-start-interview`（原工作流：`cold-start-interview`）
- `legal-zh-regulatory-customize`（原工作流：`customize`）
- `legal-zh-regulatory-gaps`（原工作流：`gaps`）
- `legal-zh-regulatory-matter-workspace`（原工作流：`matter-workspace`）
- `legal-zh-regulatory-policy-diff`（原工作流：`policy-diff`）
- `legal-zh-regulatory-reg-feed-watcher`（原工作流：`reg-feed-watcher`）

原适配器保存在 `legal-library/zh/.dsh/skills/chinese-legal-regulatory/SKILL.md`。本入口复用其领域路由，调整为工作区内路径与无冲突的技能名称；不修改用户全局配置。
