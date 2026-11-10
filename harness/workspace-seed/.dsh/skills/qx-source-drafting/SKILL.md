---
name: qx-source-drafting
description: 用于本案来源绑定的待审文稿、请求权要件和程序核查，含民事上诉、劳动裁决后救济、管辖异议的材料与条件期间审查；完整法律论证及提交仍须律师确认。
---

# 来源文稿

交付范围是原文事实、明确金额及有限字段形成的可编辑条件草稿。用户需要完整论证时明确尚需承办律师补充的部分，不把来源整理冒充全部诉讼工作已完成。

1. 使用当前明确的案件ID；没有时按已知事项建案，同名多案不猜。用 `mcp__qx_legal__get_case`、`read_case_material` 回读本案关联原件，记录实际返回的路径、sha256、ordinal及原句。引用中 `chunk` 填读取返回的 ordinal。聊天描述尚未登记为材料时说明来源缺口，不把模型新稿登记成原始证据。
2. 调用 `mcp__qx_legal__build_source_bound_litigation`。`document_type` 选 civil_complaint、civil_defense、representation、labor_arbitration、lawyer_letter、evidence_list、cross_examination；民事上诉和撤销劳动仲裁终局裁决来源草稿分别用 civil_appeal、labor_award_set_aside。`excerpts` 每项是 section（parties/requests/facts/sections）及 citation（path/quote/sha256/chunk）。保留陈述主体、否定、条件和相反内容，不截句改变含义。
3. 需要条件请求时提供 `brief`；当事人名称绑定原文，角色对应仍须核实。金额采用来源绑定的 `claim_amount` 或同次 `calculations` 的 `calculation_index`，不能同时给两者。计算项为 minuend 和 subtrahends，每项包含 citation 与原句完整金额 amount（带单位）。金额差额不等于已到期债权，不自行重算后写成应付结论。完整嵌套字段以本次工具实际 schema 为准。
4. 代理意见同时选入 requests 主张和 facts 依据/限制，并提供 brief；不能只留有利引文或丢掉冲突主张。检查返回的 missing_roles/missing_sections：只表示本次文稿未填，不说明材料或现实中不存在。原文已给拟角色时回读补入；拟出具律所不等于委托已成立。
   请求权审查可传 `claims`、`issues` 及 `legal_review.claims`，支持买卖价款、借款返还、不当得利和服务报酬四类待核路径，按同次请求索引关联支持与相反来源。服务报酬用basis="service_fee"，要件key为agreement/performance/due/balance/defenses，核服务范围、部分履行及验收争议，不误选买卖路径；具体合同类型及特别规则另核。程序路线可用民事一审、劳动仲裁、民事上诉、劳动裁决救济和管辖异议；字段枚举以工具 schema 为准，不造事实布尔值。
   上诉或劳动裁决救济可传 `legal_review.procedure.remedy`，分类、救济主体与收到日期均绑定原件；不明类型或主体用 unknown，不根据预计日期推截止日。模型选项只是待核分类，程序会阻断已识别冲突和特殊情形。输出日数与日期为条件算术参考，未处理休假日、送达效力、特殊期间等时不是法律届满日。
   civil_appeal、labor_award_set_aside 必须有对应 procedure.remedy 候选，同时选入 requests 具体请求和 facts 理由/限制原文。brief 仅填有来源的角色；上诉使用 appellant/appellee，撤销裁决使用 applicant/respondent；不套用 payment/return 或金额请求。程序分列原裁判、角色、请求和理由；案号、受理机关、具体请求范围与法定事由仍须补核。分支不明时只做内部程序核查，不更换文书类型绕过拒绝，也不称完整可提交文书。
   仅需程序核查时使用 procedure_review，不传 brief；原文明示同一裁决同时含终局及非终局事项时，remedy.decision_kind 可选 labor_mixed，仍须核同一裁决及救济主体。纯核查底稿不产生答辩或其他诉讼请求。
5. 交付实际 `user_summary`、正文 `path` 和 `internal_path`；内部稿标明仅核对、勿外发。`partial` 与 `conditional_draft` 均不是可直接提交文书。风险提示不代表客户已知悉、同意或授权。用户明确要看正文时只能采用返回的 body_text，不能改写成新的事实摘要。

同一案件同一轮同类型文稿的受保护交付采用最后一次生成结果；批量同类型多稿须分别办理并说明范围，不把中间稿都称作最终交付。

来源失配、版本变化或工具不可用时，说明实际未完成的部分；回读并修正原文引用后重试。不回退到自由生成器后声称仍有相同来源保障。生成文件不授权签署、发送或提交。
