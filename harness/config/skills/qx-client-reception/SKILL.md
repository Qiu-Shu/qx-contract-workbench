---
name: qx-client-reception
description: >
  为律师接待客户、代拟当事人微信回复、补问材料和继续跟进。优先交付能直接转发的正文，
  并在需要持续办理时保存原话、更正、客户回复和内部底稿。普通闲聊不触发。
---

# 客户接待与跟进

先按本次用户意图调用 `mcp__qx_legal__get_workflow(name="reception")`；方法也在 [references/method.md](references/method.md)。普通短咨询不必建案或加载整个法律库。

- 用户需要回复客户时，先给可直接发送的正文。只要话术就只给话术；内部分析另列，不能混入正文。
- 持续接待或明确保存时自动使用案件记录：沿用本任务明确的 `case_id`，没有则根据已知事项创建题名清楚的工作案件，不额外要求用户先说编号。续接有同名歧义时才简短问明，不按全局“最近案件”猜归属。
- 原话、后续更正和跟进记录追加保存；客户正文与内部底稿分开记录。具体工具字段、材料绑定和导出范围见 [references/case-records.md](references/case-records.md)，需要保存或回读时才加载。
- 材料先由 `qx_materials` 导入、解析；已归案材料通过 `qx_legal` 的案件材料读取/搜索工具回读。收到文件不等于已核实内容。
- 转入完整合同审查、办案或庭审时加载对应 `qx-*` Skill。专项来访登记可按需加载 `legal-zh-clinic-client-intake`；律师函/索赔线索可用 `legal-zh-litigation-demand-intake`，其中机构模板和外部系统不代表本机已经配置。

方法来源及适配边界记录在 [references/sources.json](references/sources.json)。这是工作方法，不是私有法律知识包或现行法核验结果。
