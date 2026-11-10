---
name: legal-zh-corporate-matter-workspace
description: >
  管理事项工作区——创建、列出、切换、关闭或分离活跃事项，使多客户执业者将一个
  客户的上下文与其他客户隔离。任何需要知道正在处理哪个事项的实质性技能均读取
  本技能。当用户说"新事项""切换事项""列出事项""关闭事项"或希望仅以实务级工作时使用。
argument-hint: "<new | list | switch | close | none> [简称]"
---

## 工作台执行边界

<!-- legal-quality-v1 -->
- 以当前请求、用户提供的材料和明确授权的当前事项为上下文；原库模板和占位符不是机构事实或授权。没有画像也先完成可做的分析，只补问关键缺口。
- 正文保留的 `~/.claude/...`、插件安装日志、MCP和slash command是原系统标识，不是本工作台可执行路径或已连接工具。不得据此读取全局画像、创建配置或运行原库脚本。实际读取和输出必须使用本次明确指定且已核实的路径；未指定保存位置时在对话中交付草稿。
- 仅当前任务明确要求持久化时写入该任务的授权位置。跨事项开关或原库设置不能替代跨案授权；不读取其他案件或复用其正文。
- 先核实当前运行时真实可用的工具，再执行检索、文件或外部服务操作。没有工具时交付可审查的方案/待核清单，不声称已查询、已发送、已安装或已完成。
- 只给假设规则或禁止联网时，结论限于这些规则和材料；其他法律义务列“待核”，不补造现行法结论。模型记忆不是已核验依据，`[法条原文]`仅在实际读到并校对来源和版本时使用。
- 明确区分材料事实、当事人陈述、假设、缺失事项和建议。无证据不把模板默认日期、主体属性、合规状态或程序保护填成事实。

- 原始完整文件：`legal-library/zh/corporate-legal/skills/matter-workspace/SKILL.md`。英文对应版本（如存在）在 `legal-library/en/corporate-legal/skills/matter-workspace/SKILL.md`。
- 本 bundle 已复制本技能资源，并合并该领域与仓库公共 `references/`；同名资源优先采用本技能版本。
- 调用同领域 `/corporate-legal:<skill>` 时，实际名称为 `legal-zh-corporate-<skill>`。其他领域映射见 `legal-library/skill-catalog.json`。

> 适配变更：工作台执行边界与已验证的质量问题在此副本修订；原始全文、来源和Apache-2.0许可证保留在legal-library/zh及en。修改SHA见docs/checks/skills-quality/legal-optimization-manifest.json。


# /matter-workspace

执业者跨多个客户和事项工作。事项工作区将一个客户或委托的上下文与其他客户隔离。本技能管理这些工作区。

## 子命令

- `/corporate-legal:matter-workspace new <简称>` — 创建新事项工作区，运行简短的信息采集，写入 `matter.md`
- `/corporate-legal:matter-workspace list` — 列出事项及其状态和活跃标识
- `/corporate-legal:matter-workspace switch <简称>` — 设置活跃事项
- `/corporate-legal:matter-workspace close <简称>` — 归档事项（移至 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/matters/_archived/`，绝不删除）
- `/corporate-legal:matter-workspace none` — 脱离任何活跃事项，仅以实务级工作

## 指令

1. 读取 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/CLAUDE.md` ——确认 `## 事项工作区` 部分已填充。如果 `Enabled` 为 `✗`，告知用户："事项工作区已关闭——你的配置为企业法务，仅服务一家公司，因此插件自动在实务级上下文下工作。如果你实际为多家客户工作，重新运行 `/corporate-legal:cold-start-interview --redo` 并选择私人执业设置。否则，你完全不需要 `/matter-workspace`。"不要报错——对于企业法务用户，关闭状态是预期状态。
2. 使用以下工作流。
3. 按 `$ARGUMENTS` 的第一个 token 分发：
   - `new` → 运行信息采集访谈，写入 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/matters/<简称>/matter.md`，初始化 `history.md` 和 `notes.md`。
   - `list` → 枚举 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/matters/*/matter.md`，打印表格，标记活跃事项。
   - `switch` → 更新实务级 CLAUDE.md 中的 `活跃事项：` 行。
   - `close` → 将 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/matters/<简称>/` 移至 `~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/matters/_archived/<简称>/`，在 `history.md` 中记录关闭日期。
   - `none` → 将 `活跃事项：` 设置为 `无 — 仅实务级上下文`。
4. 展示变更内容并在写入前与用户确认。

## 注意事项

- 除非实务级 CLAUDE.md 中 `跨事项上下文` 为 `开`，技能绝不跨事项读取。
- 归档不是删除——已关闭事项保留可读，用于保留/利益冲突目的。
- 简称为小写字母加连字符。如简称跨已归档和活跃事项重复使用，已归档版本保留在 `_archived/<简称>/` 下。

---

多客户执业者（私人执业——个人执业、小型律所、大型律所）跨大量事项工作。一个事项的上下文不得泄露到另一个。本技能是使这一隔离成立的薄文件管理层。

**默认状态是关闭。** 企业法务用户从不看到此项——他们仅以实务级运行。事项工作区在冷启动时为私人执业用户开启，或通过编辑实务级 CLAUDE.md 中的 `## 事项工作区` 开启。如果 `Enabled` 为 `✗`，本技能不运行；`/corporate-legal:matter-workspace` 解释关闭状态并建议对实际需要事项隔离的用户运行 `/corporate-legal:cold-start-interview --redo`。

## 存储布局

所有事项数据位于：

```
~/.claude/plugins/config/claude-for-legal-zh/corporate-legal/
├── CLAUDE.md                       # 实务级实务画像
└── matters/
    ├── <简称>/
    │   ├── matter.md               # 客户、对方当事人、事项类型、关键事实、覆盖规则
    │   ├── history.md              # 事件、决策、草稿、审查的带日期的日志
    │   ├── notes.md                # 自由格式的工作笔记
    │   └── outputs/                # 本事项目的技能输出（可选子文件夹）
    └── _archived/
        └── <简称>/                 # 已关闭事项 — 可读但不活跃
```

简称为小写字母加连字符。示例：`acme-msa-2026`、`zenith-renewal`、`vendor-xyz-nda`。

## 活跃事项在实务 CLAUDE.md 中

实务级 CLAUDE.md 中 `## 事项工作区` 下的 `活跃事项：` 行是单一真实来源。切换事项编辑该行。无独立的状态文件。

## 子命令逻辑

### `new <简称>`

1. 确认简称在 `matters/<简称>/` 或 `matters/_archived/<简称>/` 中尚未存在。如已重复使用，请用户选择不同的简称。
2. 运行信息采集访谈：
   - **客户**（我们代表的当事方，或企业法务场景中的内部业务单元）
   - **对方当事人**（另一方——可能有多个）
   - **事项类型**（读取插件的实务画像获取典型类别；对公司业务插件：并购买方/并购卖方/融资/董事会事项/主体重组/整合项目/其他）
   - **保密等级**（标准/较高/清洁团队——较高在跨事项设置中提示额外注意）
   - **关键事实**（2-5句：本事项目是什么、利益方有谁、利害关系何在）
   - **对实务合同手册的事项特定覆盖**（例如"客户要求24个月责任上限而非12个月"，"对方当事人是战略合作伙伴——保持维护关系口吻"）
   - **关联事项**（任何关联事项的简称）
3. 使用以下模板写入 `matters/<简称>/matter.md`。
4. 在 `matters/<简称>/history.md` 中初始化一条"已创建"条目。
5. 创建一个空的 `matters/<简称>/notes.md`。
6. **不**自动切换到新事项。询问："要现在切换到 `<简称>` 吗？（`/corporate-legal:matter-workspace switch <简称>`）"

### `list`

枚举 `matters/*/matter.md`。读取每份文件的前置信息或前几行以提取状态。打印表格：

| 简称 | 客户 | 事项类型 | 状态 | 创建日期 | 活跃 |
|---|---|---|---|---|---|

用 `*` 标记当前活跃事项。如有已归档事项，在单独的"已归档"标题下列出 `_archived/*`。

### `switch <简称>`

1. 确认 `matters/<简称>/matter.md` 存在。如不存在，提供 `/corporate-legal:matter-workspace new <简称>`。
2. 编辑实务级 CLAUDE.md 中的 `活跃事项：` 行为 `活跃事项：<简称>`。
3. 向用户展示 matter.md 摘要以便确认在正确的事项上。

### `close <简称>`

1. 确认 `matters/<简称>/` 存在。
2. 在 `matters/<简称>/history.md` 中追加一条带当日日期的"已关闭"条目。
3. 将 `matters/<简称>/` 移至 `matters/_archived/<简称>/`。
4. 如果已关闭事项是活跃事项，将 `活跃事项：` 设置为 `无 — 仅实务级上下文`。

### `none`

将实务级 CLAUDE.md 中的 `活跃事项：` 设置为 `无 — 仅实务级上下文`。与用户确认。

## `matter.md` 模板

```markdown
[工作成果页眉 — 按插件配置 ## 输出规范 — 因角色而异；参见实务级 CLAUDE.md 中的 `## 使用者`]

# 事项：[客户] — [简述]

**简称：**[简称]
**创建日期：**[YYYY-MM-DD]
**状态：**活跃
**保密等级：**[标准 / 较高 / 清洁团队]

---

## 当事方

**客户：**[名称]
**对方当事人：**[名称]

## 事项类型

[并购买方/并购卖方/融资/董事会事项/主体重组/整合项目/其他 ——附一行理由]

## 关键事实

[2-5句。本事项目是什么。利益方有谁。利害关系何在。与默认合同手册有何不同。]

## 事项特定覆盖

*偏离实务级合同手册且仅适用于本事项目的任何内容。*

- [例如："责任上限：客户要求24个月，而非内部标准12个月。"]
- [例如："口吻：维护关系——对方当事人是战略合作伙伴。"]
- [例如："适用法律：必须为香港法，而非中国大陆法。"]

## 关联事项

- [简称 ——一行说明为何关联]

## 保密说明

[如为较高或清洁团队，说明原因。谁可以查看事项文件。即使全局开启，跨事项上下文是否允许。]
```

## `history.md` 初始化

```markdown
# 历史记录：[客户] — [简述]

仅追加的事件日志。最新排在最前。

---

## [YYYY-MM-DD] — 事项创建

信息采集完成。简称：`[简称]`。状态：活跃。
[任何超出 matter.md 值得保留的初始上下文——例如"为回应[对方当事人]发来的主协议草案而创建。"]
```

## 跨事项上下文

实务级 CLAUDE.md 有一个 `跨事项上下文：` 标志。当其为 `关`（默认值）时，在事项 A 中工作的技能**绝不**读取任何其他 B 的 `matters/B/` 中的文件。句号。这是该设置存在所保障的保密性。

当其为 `开` 时，技能仅在用户明确要求时才可跨事项文件夹读取文件（例如"比较我们过去五个供应商事项在责任上限上的立场"）。即使为 `开`，默认也仅加载活跃事项，除非用户要求跨事项视角。

## 本技能不做什么

- **不运行利益冲突检查。** 利益冲突是执业者/律所的工作；信息采集记录用户声明的内容。
- **不强制执行保留政策。** 关闭归档事项；不删除。保留政策超出范围。
- **不自动路由输出。** 实质性技能决定写入何处；本技能告诉它*哪个文件夹*是活跃的，而非放入什么。
- **不决定跨事项是否合适。** 它读取标志并遵守。
