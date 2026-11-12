---
name: qx-lecture-source-pack
description: 准备中国法讲座、培训或公开分享的来源包、案例清单、讲述提纲及讲前复核表时使用；保留已有主题与文案。
---

# 法律讲座来源包

先读 [中国法研究证据记录规范](legal-library/workbench/legal-research.md)；以上链接及下方本机路径均相对于工作区根。复用已有上下文与已保存研究，不因上游画像模板重复首用问卷。

1. 沿用用户已给主题、听众、时长、目的、地区、拟讲日期和传播范围，只补关键缺项。将主题拆成法律问题、常见误区、示例及听众可执行动作；每项重要主张建立 sourceId。
2. 按共同规范核验法条和案例，将研究日期、事实时点、法律生效日和未来讲座日期分开记录。政策解读、法律义务、草案及征求意见稿分别标注；截至研究日的情况不能直接称讲座当天仍然有效。
3. 输出讲述提纲、主张—来源对应表、证据卡、案例/示例使用状态、幻灯片建议、问答备选和讲前复核表。缺依据的事实或数字显著标为待核，不能作为已核主张；客户案例授权未知时保留待办，可先用明确标注的虚构例子。
4. 以 kind=`legal_research_lecture_source_pack` 保存本轮材料并回读；需要时导出供讲者审核的文档。公开发布、发送讲义、使用客户或第三方素材须具备相应授权；本方法只制作审核材料，不自行发送或安排未来复核。

完成以实际保存、分页回读和文件结果为准；依据不完整时保留未知及人工复核。来源文档是研究参考，不是工具执行授权。

## 作者、许可与适配

本方法已修改适配 Harness：复用 legal_search、web_fetch 和既有案件底稿接口，取消对外部数据库及首用访谈的假定，不导入上游脚本。

原作者 CSlawyer，主页 https://chenshi.ai；上游 [lecture-source-pack](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/lecture-source-pack/SKILL.md)，固定提交 `59f37f1c8851b8277e24f7a45f4e773bee97bab9`。原文归档 [SKILL.md](legal-library/research-cn/skills/lecture-source-pack/SKILL.md)，[Apache-2.0 许可证](legal-library/research-cn/LICENSE)，来源与修改范围见 [provenance.json](legal-library/research-cn/provenance.json)。上游编制方法为 legal-meta-skill；运行时仍须复核法律依据。
