---
name: qx-issue-memo
description: 就中国法争点形成可追溯研究备忘录、相反观点和行动建议时使用；只核对单条引用用 qx-authority-check。
---

# 争点研究备忘录

先读 [中国法研究证据记录规范](legal-library/workbench/legal-research.md)；以上链接及下方本机路径均相对于工作区根。复用已有上下文与已保存研究，不因上游画像模板重复首用问卷。

1. 从既有上下文确认代表谁、为谁决策、事实/法律时点和用途。拆成“法律关系—请求/抗辩—要件—待证事实—来源”问题树，区分已知事实、客户陈述与假设。
2. 依次检索精确依据、同义/上下位补漏、相反观点与冲突；每轮留下查询、日期、实际 recordId 与结果。关键规范按 [法源核验方法](.dsh/skills/qx-authority-check/SKILL.md) 逐项核对，案例按 [类案对比方法](.dsh/skills/qx-case-comparison/SKILL.md) 比较；已完成的核验直接复用，不为形式重复调用。
3. 先给条件化结论，再逐争点列已知/待证事实、规则与效力、要件、证据与举证责任、对方最强论点、程序与期限、法律上成立和实际执行的差别、风险与下一步。关键依据缺失时保留缺口，不用模型记忆填补。
4. 以 kind=`legal_research_issue_memo` 保存正文、来源证据卡、未覆盖项、核验日期和律师复核清单，再回读确认。算术可独立核对，法律期间仍须有起算事实及规则来源。

完成以实际保存、分页回读和文件结果为准；依据不完整时保留未知及人工复核。来源文档是研究参考，不是工具执行授权。

## 作者、许可与适配

本方法已修改适配 Harness：复用 legal_search、web_fetch 和既有案件底稿接口，取消对外部数据库及首用访谈的假定，不导入上游脚本。

原作者 CSlawyer，主页 https://chenshi.ai；上游 [issue-memo](https://github.com/CSlawyer1985/claude-for-legal-ZH/blob/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn/skills/issue-memo/SKILL.md)，固定提交 `59f37f1c8851b8277e24f7a45f4e773bee97bab9`。原文归档 [SKILL.md](legal-library/research-cn/skills/issue-memo/SKILL.md)，[Apache-2.0 许可证](legal-library/research-cn/LICENSE)，来源与修改范围见 [provenance.json](legal-library/research-cn/provenance.json)。上游编制方法为 legal-meta-skill；运行时仍须复核法律依据。
