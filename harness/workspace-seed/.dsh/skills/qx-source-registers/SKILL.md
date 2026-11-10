---
name: qx-source-registers
description: 根据本案原文保存公司议事、合规事项或知识产权来源台账；可生成限定公司文稿、跟踪明确日期线索、按指定记录分别或合并导出Word，不判断公司决议效力、履行事实或当前权利有效状态。
---

# 来源台账与指定记录交付

同一案件的不同领域分别保存，不用一个领域的最后记录代替其他成果。只整理材料明确记载及待核项，不把未知扩大为否定事实。

先以明确 case_id 调用 get_case、read_case_material 回读本案已关联原件。每条引用使用真实 path、sha256、ordinal（填入chunk）和逐字quote，保留人物、议题、事件、日期口径、否定及条件。模型分类不是事实认定。

调用 `mcp__qx_legal__save_source_bound_register`，每个 `entries` 项包含 field 与 citation。程序把事实条目保存为原文，候选 field 分类单独记入未核验审计区，不将其反推为身份、法域、状态或事件。根据任务选择以下一种或多种独立调用：

| 范围 | 参数与边界 |
| --- | --- |
| 公司来源纪要 | domain="corporate"，document_type="minutes"，filename指定新文稿。逐议题保留已知票数、不同表态和签署资料状态；不生成未知表决结果。proposal仅用于用户已明确指定的股东会担保事项拟议案，不能用于其他议题或替用户选择有权机关；不等于完整股东决定或决议效力审查。 |
| 合规原文底稿 | domain="compliance"，不传document_type或filename；不把未提供回执写成未发送，不把没有批准记录写成未批准。明确日期跟踪可附tracking。 |
| 知识产权原文台账 | domain="ip"，不传document_type或filename；内部提交、官方申请、授权、证载期限和当前状态分别照录。不要传document_type="register"，该值不受支持。 |

合规 `tracking` 使用来源绑定的 as_of/as_of_entry 与 deadlines[{entry,date,year_basis}]。as_of_entry和entry均是本次entries的0起始索引，日期使用YYYY-MM-DD；年份来自原文用explicit，采用同年假设须用same_as_reference_assumption并保留假设。只比较自然日差，不把日期线索自动认定为法定期间，不调整工作日、节假日或送达规则；具体字段以实际schema为准。

同一领域的多个事项优先放在同一次entries中保存。当前交付保护按本案领域采用本轮最新保存结果，不能承诺同一领域多次保存的所有记录都在本次受保护交付内；需要分批时逐批明确完成范围。

保存成功后记录每次返回的 id，用 read_case_note 分页回读全文。合规与IP通过 `mcp__qx_legal__export_case(case_id, note_ids=[本次id], audience="internal")` 导出；公司已有path时直接交付文稿，内部底稿不得冒充公司正文。用户要合并时明确列出本轮选定的全部 note_ids，不能默认导出全案或选“最近一条”。

最终交付各自的 user_summary 和核验过的真实链接，分别标明完成范围。来源、记录或文件改变时不得复用旧成功回执；更正遵循明确授权与supersedes。工具缺失或失败则说明未完成，不用自由文本保存冒称来源台账成功。

摘录之外的同片段草案、主体范围、未完成或状态未知提示若由程序保留，应与正文一起核对，不把它们省略成已批准、已整改或已获权。日期应保留原文年份，不能截出月日后改按参考年计算；相邻提示与选中事项的关系仍须律师核实。

本方法不替代完整制度修订、AI合规评价、公司权限程序审查、知识产权权属判断、实时官方状态查询或续展缴费管理。没有实际检索时不声称已核验现行法或登记状态。
