# Skill 调用状态

## 本地开发新增窄入口（2026-11-05）

| 可调用入口 | 已开放范围 | 未认证范围 |
| --- | --- | --- |
| qx-source-drafting | 来源文稿、精确金额、三类请求权要件、上诉/劳动裁决救济/管辖异议核查及条件日期参考 | 完整法律论证、实际法律截止日、可直接提交文书 |
| qx-employment-checklist | 解除与条款清单、来源情景、录用/竞业参数候选、明确同合同跨行/连续Word段落关联 | 跨文件或复杂表格身份推断、整个合同效力、实际应付认定 |
| qx-source-registers | 公司/合规/IP原文台账、限定公司文稿、日期线索跟踪、指定记录导出 | 公司决议效力、制度实质评价、实时权利状态 |

这三个入口使用已测试程序及受保护交付流程，不等于恢复五项完整专项 Skill。旧36项继续停用。Word模板功能沿用现有工具，不新增重复的泛化入口。

此表是工作台适配决策，不改变原始法律资料。停用条目不进入自动技能目录，原名称仅供迁移和查阅来源；不能加载旧原文绕过停用并声称执行了已停用流程。

用户明确要查阅历史模板时可把原文件作为参考资料说明，不能把教学、旧插件或未验证行为改名冒充当前实务能力。普通办案继续使用四项主业务，按需要加载仍可调用的专业技能。

| 停用入口 | 原因 | 一般业务去向（非专项替代认证） |
|---|---|---|
| legal-zh-ai-governance-ai-inventory | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题合同状态已分开，可用；新题将给定“供应商说它仅提供软件，工厂承担全部义务”误引为供应商“承担全部义务”，改变责任陈述主体。属重复事实归属失真，建议停用两类入口；不据此判断实际法律责任。 | qx-case-work |
| legal-zh-ai-governance-aia-generation | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题仍写“控制措施均未实施”“全面评估未启动”，材料只缺实施和评估状态信息；新题四栏与权限状态正确，但两套未同时过。重复未知转否定事实，建议停用。 | qx-case-work |
| legal-zh-ip-portfolio | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题在权利主张者栏填“甲公司（开发产品P）”，但甲开发产品/员工提交均不证明甲已经提出权利主张，重复把业务主体映射到权利身份。新题主要归属与期限核验可用，但商标受理回执事实过度待核、客户名单“无固定期限基础”仍宜保留待核。建议停用。 | qx-case-work |
| legal-zh-privacy-matter-workspace | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题评估状态改正为未知，却再次把甲公司填为委托客户，原材料没有委托关系；新题正确。实际评测输入会预载共享目标，不能单独归因原适配正文；组合入口仍重复事实身份错误，建议停用该专业别名，保留核心qx-case-work直接入口。 | qx-case-work |
| legal-zh-regulatory-comments | 原双题通过后，移除停用依赖的末次复核将没有提供决策记录写成“未提交、不提交、放弃均未发生”，把未知决策状态转为否定事实。新题正确，但两题未同时达标，停用此入口。 | qx-case-work |
| legal-zh-regulatory-gap-surfacer | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题制度摘要覆盖边界已改善。新题明确参考2026-11-04、K1期限2026-11-01且源记录open，却仍只报“是否逾期取决于期限来源，待核”，漏掉可从题干直接给出的“按源记录期限已过，实际履行待核”状态，削弱跟踪器核心排序用途。此项是过度待核造成的功能不足，不是错误断言实际未履行，也不是工具缺失；两轮未同时达标，建议停用并用核心事项跟踪替代。 | qx-case-work |
| legal-zh-regulatory-policy-redraft | 助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题已分离规则和选项；新题再次在候选正文加入处理前、变更更新与按保留期限保存，并把更新称“必要配套”，还把保存45天错误表述成“政策A第45天”。题干Q仅要求记录用途且仅授权该改动，重复扩写义务和混淆参数来源，建议停用。 | qx-case-work |
| chinese-legal-commercial | 邮件与履行证据已分开，但旧题未确认委托立场即定我方为甲方；题干只有甲采购乙，不能等同代理甲。第二轮仍有实质角色补事实，建议停用该总入口，以qx-contract-review明确立场入口替代。 | qx-contract-review |
| legal-zh-commercial-review | 原双题通过后，停用专项依赖并改接主业务的末次复核出现新实质错误：旧题未确认委托立场仍写我方（采购方）；新题限责条款错误引用付款第三款，且追加保密、知识产权例外，可能扩大我方责任。保留失败证据并停用此重复总入口，一般合同任务使用主业务。 | qx-contract-review |
| legal-zh-commercial-review-proposals | 新题没有法律来源，仍直接断言故意重大过失责任不能约定排除；后列法律效果待核不能撤销前文确定规则。与首轮未经核验法律效果同类错误重复，建议停用。 | qx-contract-review |
| legal-zh-commercial-saas-msa-review | 旧题价格误引已修复，但仍把仅摘要未提供数据退出条款写成合同均未约定，制造实质合同缺失。第二轮来源边界仍不可靠，建议停用专项入口，改由核心合同审查明确已读范围。 | qx-contract-review |
| legal-zh-corporate-board-minutes | 旧题E3只给董事会签到A/B，并未给其董事身份，E1仅给股东身份；本次仍将签到者直接确认为董事并宣称E3支持。此前虚构C/交割条件虽修复，公司记录身份事实仍越界，建议停用。 | qx-case-work |
| legal-zh-corporate-written-consent | 既定生效条件和未审议事实已修复，但旧题签署表把只见签到/股东身份的A/B直接当董事及签署人，尚缺董事名册与签署资格。第二轮仍生成未核公司身份，建议停用。 | qx-case-work |
| legal-zh-employment-hiring-review | 旧题服务期未核前提已改为问题；新题仍把竞业另签的单独书面约定作为确定要求，再附待核。未提供法源时预埋程序要求重复，建议停用自动录用专项。 | qx-case-work |
| legal-zh-employment-termination-review | 旧题再次预埋未取源补偿倍数，且写“新办公室启用日与解除无关联”，与上轮未核法律规则/缺关联推无关同类错误。新题守住不能抵消旧题实质失败，建议停用。 | qx-case-work |
| chinese-legal-law-student | 法考、课堂教学总入口不属于当前律所实务工作台，原入口会继续分派已停用教学技能。 | 四项主业务；原文仅作参考 |
| legal-zh-builder-hub-customize | 旧 Claude 插件中心的画像与版本管理混合，风格调整可能误改固定 SHA 或安装元数据。 | 四项主业务；原文仅作参考 |
| legal-zh-builder-hub-uninstall | 旧 Claude 卸载机制和安装来源尚未认证适用于本工作台，不能推定由本中心安装。 | 四项主业务；原文仅作参考 |
| legal-zh-clinic-draft | 助手逐项判读合成输入与输出，不是人工/律师认证。新场景把未知状态写成正在执行，并擅自改变说明书随设备提供的履行条件；内部说明不能补救对外正文。 | qx-case-work |
| legal-zh-clinic-plain-language-letters | 自身双题通过，但合并目标 legal-zh-clinic-status 复测未通过并停用，不能保留通向停用目标的入口。 | qx-case-work |
| legal-zh-clinic-semester-handoff | 学生离届、学期和导师分配是教学诊所制度，当前律所工作台没有该制度或名册。 | 四项主业务；原文仅作参考 |
| legal-zh-clinic-status | 助手逐项判读合成输入与输出，不是人工/律师认证。回归仍将未提供登记记录推成尚未登记，与该技能修复的状态边界相同。 | qx-case-work |
| legal-zh-criminal-matter-workspace | 助手逐项判读合成输入与输出，不是人工/律师认证。原ID问题修复，但新场景仍在工作区事实字段补造材料来源/形态。 | qx-case-work |
| legal-zh-law-student-bar-prep-questions | 法考试题生成属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-law-student-case-brief | 助手逐项判读合成输入与输出，不是人工/律师认证。更换为实务摘要后仍扩大假设规则或把材料缺失转为否定事实，教学旧模式也回流。 | qx-case-work |
| legal-zh-law-student-exam-forecast | 历年考题与考点预测属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-law-student-flashcards | 法条记忆卡片属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-law-student-outline-builder | 法学课程大纲属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-law-student-session | 专项教学练习属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-law-student-study-plan | 法考学习计划属于教学备考功能，当前律所实务工作台不支持其课程、训练与学习状态管理。 | 四项主业务；原文仅作参考 |
| legal-zh-litigation-brief-section-drafter | 助手逐项判读合成输入与输出，不是人工/律师认证。签收认定已修，但实质段落的来源说明仍补造表达媒介，不能当作忠实案卷摘要。 | qx-case-work |
| legal-zh-litigation-claim-chart | 助手逐项判读合成输入与输出，不是人工/律师认证。要件表核心的相反证据映射仍混淆不同性质事件，影响补证/论证方向。 | qx-case-work |
| legal-zh-litigation-demand-draft | 助手逐项判读合成输入与输出，不是人工/律师认证。现版仍在对外正文补造受函主体或已成立委托；内部待核不能补救正文的确定陈述。 | qx-case-work |
| legal-zh-litigation-demand-intake | 助手逐项判读合成输入与输出，不是人工/律师认证。授权分栏修复，但缺角色映射时仍按甲乙模板填定发收函方，核心登记不可靠。 | qx-case-work |
| legal-zh-litigation-privilege-log-review | 助手逐项判读合成输入与输出，不是人工/律师认证。程序提交状态仍被补造；新增默认争点过拟合旧题，无法泛化。停止继续加规则，建议停用该独立入口。 | qx-case-work |
| legal-zh-clinic-form-generation | 原91项之外的旧文书生成别名仅转发到已停用的clinic-draft；因目标停用同步关闭，未将它改名保留为另一条自动入口。 | qx-case-work |

## 合并与替代

| 原入口 | 去向或共享流程 |
|---|---|
| legal-zh-ai-governance-customize | legal-library/workbench/practice-context.md |
| legal-zh-ai-governance-matter-workspace | qx-case-work |
| legal-zh-ip-matter-workspace | qx-case-work |
| legal-zh-product-customize | legal-library/workbench/practice-context.md |
| legal-zh-product-matter-workspace | qx-case-work |
| legal-zh-regulatory-customize | legal-library/workbench/practice-context.md |
| legal-zh-regulatory-matter-workspace | qx-case-work |
| legal-zh-commercial-matter-workspace | qx-case-work |
| legal-zh-corporate-cold-start-interview | workspace/legal-library/workbench/practice-context.md |
| legal-zh-employment-matter-workspace | qx-case-work |
| legal-zh-litigation-matter-workspace | qx-case-work |
