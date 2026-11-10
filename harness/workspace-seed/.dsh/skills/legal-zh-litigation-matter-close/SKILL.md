---
name: legal-zh-litigation-matter-close
description: >
  结案——捕获结果、最终敞口和反思教训，从活跃案件组合中归档但不删除记录。
  当用户需要结案、说"[案件]结束了"或需要记录和解、撤诉、判决、
  撤回或合并结果时使用。
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

- 原始完整文件：`legal-library/zh/litigation-legal/skills/matter-close/SKILL.md`。英文对应版本（如存在）在 `legal-library/en/litigation-legal/skills/matter-close/SKILL.md`。
- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。
- 调用同领域 `/litigation-legal:<skill>` 时，实际名称为 `legal-zh-litigation-<skill>`。其他领域映射见 `legal-library/skill-catalog.json`。

> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。


# /matter-close

1. 按以下工作流操作。
2. 确认代号和当前状态。
3. 捕获结果：结案类型（和解、撤诉、判决我方胜诉/败诉、撤回、合并）、日期、最终敞口/成本、反思教训。
4. 更新 `_log.yaml`：`status: closed`，添加 `closed: YYYY-MM-DD` 和 `outcome:` 字段。
5. 向 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/history.md` 追加最终条目。
6. 案件保留在 `_log.yaml` 和 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/` 中——不删除。`/portfolio-status` 从活跃汇总中过滤。

---

# 案件结案

## 目的

案件会结束。结果是案件组合生成的最有价值的数据点——它校准未来案件的风险框架。结案以结构化方式捕获结果，使记录有用，而不只是归档。

## 加载上下文

- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/_log.yaml` —— 找到对应行
- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/matter.md` —— 参考（登记时上下文）
- `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/history.md` —— 追加目标

**冲突门禁——不可绕过。** 结案前，检查 `_log.yaml` 中是否存在该案件代号。如果案件不在 `_log.yaml` 中，拒绝并路由：

> "我在案件日志中没有找到 [案件代号]。没有可结的案件——要么代号有误，要么该案件从未通过 `/litigation-legal:matter-intake` 登记。请先检查代号；如确实从未登记，则没有可更新的行，也没有可结案的文件结构。"

## 输入

代号（必填）。

## 结案内容

### 1. 结案类型

- `和解` —— 与对方达成和解，含金额、结构条款
- `撤诉` —— 对方撤回起诉/我方撤回起诉
- `判决我方胜诉` —— 在何阶段、上诉风险
- `判决我方败诉` —— 在何阶段、上诉状态、敞口已确定
- `撤回` —— 由对方撤回，附情况说明
- `合并` —— 并入其他案件（提供母案代号）
- `其他` —— 附说明

### 2. 结案日期

案件实际结束的日期（和解协议签署、裁定下达、撤诉立案）。

### 3. 最终敞口

- 公司实际成本（和解金额 + 律师费 + 禁令/结构性成本）
- vs. 登记时的初始敞口范围（我们的预判是否准确？）
- 计提准确性（如有计提）：账面 vs. 实际

### 4. 反思教训

两到三句话。我们哪些判断正确？哪些误判了？登记时本应更早标注什么？

这是未来律师会重读的部分。诚实。"误判了可能性——原告方比预期更激进"比"结果对我方有利"更有价值。

### 5. 文件关联提示

和解协议、终局裁定、撤诉裁定——如有路径。非必填。

## 写入

**在结案（产生后果的行为——案件被归档且停止主动追踪）之前：** 读取 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/CLAUDE.md` 中的 `## 使用者`。如果角色是**非律师**：

> 结案具有法律后果——它结束主动追踪，可能影响相关联的证据保全（如适用，另行运行 `/legal-hold --release`），并建立公司依赖的最终记录。您是否已与律师审查过此事？如已审查，继续。如未审查，以下是带去给律师的简要材料：
>
> [生成一页摘要：案件、结案类型和条款、最终敞口 vs. 初始、计提准确性、关联案件或上诉是否仍在进行、提前结案可能出错的事项、需要问律师的问题。]
>
> 如果您需要寻找律师：请联系当地律师协会或拨打 12348 法律援助热线获取推荐。

未收到明确确认之前，不写入结案字段或追加结案条目。

### 更新 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/_log.yaml`

```yaml
status: closed
closed: [YYYY-MM-DD]
outcome: [结案类型]
final_cost: [金额]
last_updated: [今天]   # 结案是最后的触及；记录它
```

保留所有既有字段。不删除日志行。

### 向 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/history.md` 追加最终条目

```markdown
## [YYYY-MM-DD] —— 案件结案：[结案类型]

**结果：** [叙述——发生了什么、以什么条件]
**最终成本：** [金额 + 如有结构条款]
**vs. 初始敞口：** [对比 matter.md 登记范围]
**计提准确性：** [如适用]

**反思教训：**
[2-3句话——诚实的回顾]

**关联文件：** [和解协议 / 终局裁定 / 等，如有提供]
```

### 触及 `~/.claude/plugins/config/claude-for-legal-zh/litigation-legal/matters/[slug]/matter.md`

在末尾添加结案块（不修改前面各节——它们是历史登记记录）：

```markdown
---

## 结案于 [YYYY-MM-DD]

[结果摘要，一段。指向最终历史条目获取详情。]
```

## 确认

写入前向用户展示完整的结案条目和 yaml 变更。

## 本技能不做什么

- 删除案件。已结案件保留在 `_log.yaml` 和磁盘中——它们是案件组合判断力的训练集。
- 重新立案。如已结案件重新出现（上诉、关联诉讼），开新案并在 `matter.md` 中引用已结案件。
- 总结用户未提及的教训。如用户跳过教训部分，留空而非编造。
