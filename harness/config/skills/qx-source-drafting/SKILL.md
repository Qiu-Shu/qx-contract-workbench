---
name: qx-source-drafting
description: 用本案原始材料形成来源绑定的待审文稿，包括起诉、答辩、代理意见、劳动仲裁、律师函及证据说明；适合要求逐字来源、确定性金额核算和正文/内部稿分开的任务，不承担完整法律论证或提交认证。
---

# 来源文稿

交付范围是原文事实、明确金额及有限字段形成的可编辑条件草稿。用户需要完整论证时明确尚需承办律师补充的部分，不把来源整理冒充全部诉讼工作已完成。

1. 使用当前明确的案件ID；没有时按已知事项建案，同名多案不猜。用 `mcp__qx_legal__get_case`、`read_case_material` 回读本案关联原件，记录实际返回的路径、sha256、ordinal及原句。引用中 `chunk` 填读取返回的 ordinal。聊天描述尚未登记为材料时说明来源缺口，不把模型新稿登记成原始证据。
2. 调用 `mcp__qx_legal__build_source_bound_litigation`。`document_type` 选 civil_complaint、civil_defense、representation、labor_arbitration、lawyer_letter、evidence_list 或 cross_examination。`excerpts` 每项是 section（parties/requests/facts/sections）及 citation（path/quote/sha256/chunk）。保留陈述主体、否定、条件和相反内容，不截句改变含义。
3. 需要条件请求时提供 `brief`；当事人名称绑定原文，角色对应仍须核实。金额采用来源绑定的 `claim_amount` 或同次 `calculations` 的 `calculation_index`，不能同时给两者。计算项为 minuend 和 subtrahends，每项包含 citation 与原句完整金额 amount（带单位）。金额差额不等于已到期债权，不自行重算后写成应付结论。完整嵌套字段以本次工具实际 schema 为准。
4. 代理意见同时选入 requests 主张和 facts 依据/限制，并提供 brief；不能只留有利引文或丢掉冲突主张。检查返回的 missing_roles/missing_sections：只表示本次文稿未填，不说明材料或现实中不存在。原文已给拟角色时回读补入；拟出具律所不等于委托已成立。
5. 交付实际 `user_summary`、正文 `path` 和 `internal_path`；内部稿标明仅核对、勿外发。`partial` 与 `conditional_draft` 均不是可直接提交文书。风险提示不代表客户已知悉、同意或授权。用户明确要看正文时只能采用返回的 body_text，不能改写成新的事实摘要。

同一案件同一轮同类型文稿的受保护交付采用最后一次生成结果；批量同类型多稿须分别办理并说明范围，不把中间稿都称作最终交付。

来源失配、版本变化或工具不可用时，说明实际未完成的部分；回读并修正原文引用后重试。不回退到自由生成器后声称仍有相同来源保障。生成文件不授权签署、发送或提交。
