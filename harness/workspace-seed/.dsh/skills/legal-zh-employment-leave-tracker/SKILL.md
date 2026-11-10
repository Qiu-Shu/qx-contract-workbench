---
name: legal-zh-employment-leave-tracker
description: >
  检查进行中的假期，获取截止日期预警和需要做出的决策。仅呈现
  需要采取行动的假期并说明原因——不是状态面板。建议每周运行，
  或每当律师需要知道哪些假期有即将到来的审批、证明或到期截止时使用。
argument-hint: "[无需参数——从假期登记册 leave-register.yaml 读取]"
---

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

- 原始完整文件：`legal-library/zh/employment-legal/skills/leave-tracker/SKILL.md`。英文对应版本（如存在）在 `legal-library/en/employment-legal/skills/leave-tracker/SKILL.md`。
- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。
- 调用同领域 `/employment-legal:<skill>` 时，实际名称为 `legal-zh-employment-<skill>`。其他领域映射见 `legal-library/skill-catalog.json`。

> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。


# /leave-tracker

检查所有有法定硬性截止日期的进行中假期，仅呈现需要决策或行动的项目。不是状态面板——告诉你需要做什么及为什么。

## 指令

1. 加载 `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/CLAUDE.md` → 管辖地表和假期管理部分。

2. 如果 `~/.claude/plugins/config/claude-for-legal-zh/employment-legal/leave-register.yaml` 不存在或无数据，提示律师上传假期电子表格或使用 `/employment-legal:log-leave` 添加条目。

3. 仅对需要行动的假期发出预警。无问题的假期每项一行总结。

4. 检查以下截止日期类型：

| 假期类型 | 关键截止日期 | 法律依据 |
|---|---|---|
| 医疗期 | 医疗期满日（按工作年限3-24个月） | 企业职工患病或非因工负伤医疗期规定 `[法条原文]` |
| 产假 | 产假期满日（98天基础 + 省/直辖市奖励假） | 女职工劳动保护特别规定 `[法条原文]` |
| 年休假 | 核实当年安排及跨1年度安排条件；生产/工作特点必要性、职工同意和实际计划待核，不把年末当作当然失效日 | 职工带薪年休假条例第5条 `[法条原文]` |
| 工伤假 | 停工留薪期满日（一般不超过12个月） | 工伤保险条例第33条 `[法条原文]` |
| 婚假 | 各省/直辖市人口与计划生育条例规定 | 省/直辖市规定 |

## 示例

```
/employment-legal:leave-tracker
```

建议每周运行——设置周一上午提醒调用 `/employment-legal:leave-tracker`。自动排期需要单独的集成（日历提醒、定时任务等）；Claude Code 不自行排期。
