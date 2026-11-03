---
name: qx-contract-review
description: >
  从用户立场审查合同、附件、补充协议或补件，核对条件、原文数字及相反材料，
  给出可编辑的替换条款与备选方案。仅答一个条款问题时按该范围处理，不强制整份审查。
---

# 合同审查

调用 `mcp__qx_legal__get_workflow(name="contract")` 获取本机方法，或读取 [references/method.md](references/method.md)。先按用户要求审查，信息缺口不成为整段回答拒收理由。

- 明确我方立场、目的和已读范围；不能从甲乙方或旧模型回答猜角色。区分未约定、未提供材料与未证明履行。
- 正式合同审查本身包含成果留存。已有明确 `case_id` 就回读；没有则根据已知合同自动创建题名清楚的工作案件，不另问编号或确认建档。只解释一个短条款可直接答；续接同名多案时才问清归属。
- `qx_materials` 负责导入/解析，`qx_legal.read_case_material/search_case_materials` 负责已归案材料回读；按分页读到本次结论所需的原文、条件和例外。
- 具体议题及 NDA、供应/SaaS、DPA 分工见 [references/specializations.md](references/specializations.md)，按合同实质需要选择，不一次加载所有专项 Skill。
- **合同修改默认批注模式**：先 `inspect_word_document` 定位，调用 `write_review_word` 不传mode或传 `comments`；正文保留，理由和建议文本写入批注。只有用户明确要求带修订痕迹改正文时才用 `tracked_changes`，不要仅凭“修改合同”切换。
- 正式意见书用 `write_contract_opinion` 生成同内容的HTML阅读版与Word版，再 `present`。采用“结论 → 已确认事实与待核实事项 → 风险表 → 必要法律判断 → 谈判条款 → 补件 → 材料范围”的顺序；章节按事项增减，不凑问题数量。排版和判断质量见本机方法。

来源记录见 [references/sources.json](references/sources.json)。旧私有知识包未恢复；原方法中的审批人、阈值和外部系统不是已配置事实。
