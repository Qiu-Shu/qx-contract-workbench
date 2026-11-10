---
name: legal-zh-litigation-matter-briefing
description: >
  单个案件深度简报——当前姿态、变化之处、下个节点、
  待解决问题和风险重评估检查，适用于向法务负责人汇报或外部律师通话前准备。
  当用户说"简报[案件]"、"这个案件什么情况"或需要了解特定案件时使用。
argument-hint: "[代号]"
---

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

- 原始完整文件：`legal-library/zh/litigation-legal/skills/matter-briefing/SKILL.md`。英文对应版本（如存在）在 `legal-library/en/litigation-legal/skills/matter-briefing/SKILL.md`。
- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。
- 调用同领域 `/litigation-legal:<skill>` 时，实际名称为 `legal-zh-litigation-<skill>`。其他领域映射见 `legal-library/skill-catalog.json`。

> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。


# /matter-briefing

1. 加载 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/CLAUDE.md` → 风险校准 + 相关方。
2. 按以下工作流操作。
3. 读取 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/matter.md` + `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/history.md` + `_log.yaml` 中的日志行。
4. 生成简报：当前姿态、自上次更新以来的变化、下个节点、待解决问题、风险重评估检查（"`risk:` 字段是否仍反映实际情况？"）。
5. 标注陈旧度：如 `last_updated` > 30天，明确说明。

---

# 案件简报

## 目的

让律师在走向会议室的路上就能读完一个案件的情况。当前姿态、变化之处、下一步做什么、什么值得重新考虑。

## 加载上下文

- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/_log.yaml` —— 结构化行
- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/matter.md` —— 记述式登记
- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/history.md` —— 事件日志
- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/CLAUDE.md` —— 风险校准（使"风险：高"有具体含义，而非泛泛）

**冲突门禁——不可绕过。** 在生成简报前，检查 `_log.yaml` 中是否存在该案件代号。如果案件不在 `_log.yaml` 中，拒绝并路由：

> "我在案件日志中没有找到 [案件代号]。请先运行 `/litigation-legal:matter-intake`，以便冲突检索可以运行且案件工作空间建立。我不会为未登记的案件生成简报——冲突检索是门禁。"

## 输入

代号（必填）。如模糊或缺失，请用户从活跃案件列表中选取。

## 简报内容

```markdown
[工作成果标头——根据插件配置 ## 输出——因角色不同；见 `## 使用者`]

# [案件名称] —— 简报（截至[今天]）

**状态：** [状态 / 阶段]
**风险：** [评级]（[严重性] × [可能性]）
**重要性：** [类别]
**外聘律师：** [律所 —— 主办律师]
**最后更新：** [日期] [⚠️ 陈旧 >30天]
**利益冲突：** [状态 —— ⚠️ 如 `待定` 或 `未运行`]

---

## 一段话概要

[当前姿态。我们在做什么、为什么。如登记时记录了关键事实，请指名。]

## 近期变化

[history.md 中最近3-5条记录，最新在前。如历史记录较薄，说明。]

## 下一步

- **临近节点：** [next_deadline + 是什么节点]
- **即将到来的里程碑：** [matter.md 或近期历史记录中的任何日期事项]
- **待决定事项：** [matter.md 中标注的待解决问题]

## 敞口

[范围 + 自登记以来的任何变化。如已计提，当前计提金额 + 是否需要重新校准。]

## 内部负责人

[已纳入的人员；是否有人应该纳入但未被纳入]

## 风险重评估检查

*提示，非答案。*

- `risk: [评级]` 是否仍感觉正确，还是案件发生了变化？
- `materiality: [类别]` 是否仍然匹配？（新事实可能推动向计提或披露变化。）
- 案件是否需要补充新的相关方（如证据开示后信息安全负责人变得相关）？

## 待解决问题

[来自 matter.md 及历史记录中尚未解决的事项]

## 通话前备忘

[如用户指定了目的——"在外部律师通话前给我简报"——定制本节：应问的问题、应获取的决定、应提取的进展。如未指定目的，省略本节。]
```

## 陈旧度

如 `last_updated > 30天前`：在顶部标注并建议会议后运行 `/litigation-legal:matter-update [slug]` 以记录讨论内容。

## 语气

这不是营销文案。说已知的；标注不知的。如果案件历史记录薄且刚立案，简报就是短的——这是正确的。不要填充。

## 以下一步决策树收尾

以 CLAUDE.md `## 输出` 中的下一步决策树收尾。根据本技能刚产生的内容自定义选项——五个默认分支（起草X、上报、获取更多事实、观察等待、其他选择）是起点而非锁定项。决策树本身就是输出；由律师选择。

## 本技能不做什么

- 预测结果。风险评级是记录在案的判断，不是预测。
- 推荐策略。浮现问题；律师回答。
- 重新分流。如用户希望重新分流，通过 `/matter-update` 进行字段变更——本技能只读，不写。
