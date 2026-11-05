---
name: qx-case-work
description: >
  整理诉讼或争议案件的时间线、证据、相反说法、缺口和待办，拟写可编辑文书，
  并通过明确案件ID连续保存材料版本和更正。用于实际办案整理，不替代合同专项审查或庭审角色演练。
---

# 案件整理与文书

调用 `mcp__qx_legal__get_workflow(name="case")`，或按需读 [references/method.md](references/method.md)。按用户目标组织成果，时间线、材料说法、推断与法律分析分清，不能把缺少材料当作反证。

- 正式办案请求包含成果留存：有明确 `case_id` 先 `get_case`；没有则根据已知事项自动创建题名清楚的工作案件，不另问编号或确认建档。长记录用 `read_case_note` 续读。普通解释不强制建案，续接同名多案不猜，不使用全局“最近案件”。
- 文件先由 `qx_materials` 导入解析，只有明确属于本案的文件才 `link_case_materials`；已归案内容用 `read_case_material/search_case_materials` 回读。
- 接待入口转办案只使用律师确认摘要及实际来源会话，保留每项陈述的归属；不自动搬入全聊天或内部策略，不凭来源会话、同名案件推断 `case_id`。材料只写“要求核账”而未写提出者时，主体待核，不补成“我方要求”。
- 每项事实按“来源原话→说话者/动作主体→可确定内容→未知内容”整理。别案题名里的“借款”不能补入本案摘要，转款陈述不确立借贷性质；“核账”不确立尚未付款。双方陈述有一致部分也仍保留陈述归属，不直接写“事实已确认”或未经核验认定诉讼自认、免证。
- 记录用 `record_case_note` 追加，更正通过 `supersedes` 关联原记录。引文用实际路径、逐字片段和工具位置，不让模型计算偏移。未匹配引文如实待核，不吞掉正文。
- 证据命题、三性与实务摘要按需加载 `qx-evidence-analysis`。只加载当前有关的方法。
- 来源绑定的条件文稿加载 `qx-source-drafting`；劳动解除条件清单及明确情景联合归档加载 `qx-employment-checklist`；公司/合规/IP原文台账加载 `qx-source-registers`。这些目标优先执行对应来源工具，不再用下述自由正文记录或通用Word生成替代并声称同等保障。完整法律论证及其他业务部分仍须单独说明完成范围。
- 具体技能按需要选：时间线用 `legal-zh-litigation-chronology`，阶段简报用 `legal-zh-litigation-matter-briefing`。无需同时加载。
- 用户要文书时交付连贯可编辑正文；内部引用说明另列。使用 `write_word_draft` 或 `export_case` 生成实际文件再展示，客户版与内部工作稿分开。

来源见 [references/sources.json](references/sources.json)。本机未迁移旧私有知识包；方法说明不等于已获得法律数据库或案件外部系统访问能力。
