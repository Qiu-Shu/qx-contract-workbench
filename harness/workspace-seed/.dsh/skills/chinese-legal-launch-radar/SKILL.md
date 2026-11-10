---
name: chinese-legal-launch-radar
description: "产品上线雷达：汇总上线准备、产品法律风险和整改事项"
---

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

# 产品上线雷达

先读取工作区中的 `legal-library/zh/managed-agent-cookbooks/launch-radar/README.md` 与 `legal-library/zh/managed-agent-cookbooks/launch-radar/agent.yaml`，随后只按需读取 `legal-library/zh/managed-agent-cookbooks/launch-radar/subagents/` 和 `steering-examples.json`。

复用其中完整工作流与输出格式，将 Claude 专用调用转换为 Harness 现有工具；原库提到的服务不代表已连接。仅用户要求监控或重复执行时才创建定时任务，仅获授权时开展并行工作。用户当前指令优先，缺少画像不自动启动完整问卷。

原入口：`legal-library/zh/.dsh/skills/chinese-legal-launch-radar/SKILL.md`。这是路径适配入口，未执行原库脚本。
