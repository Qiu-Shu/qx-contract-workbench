---
name: legal-zh-litigation-matter-workspace
description: "Use when the user invokes a legacy matter-workspace request."
---

<!-- workbench-skill-repair-v2 -->

# 诉讼案件工作区管理

兼容入口：调用 **qx-case-work** 处理本次明确案件的创建、读取和记录。按其真实工具能力执行；不再维护旧插件的活跃事项、全局 switch 或归档目录。

已有案件用明确 case_id；同名多案不猜，不因家属提供信息就把其列为委托人。家属身份、委托关系、律师授权分别记录。关联案件未知写“未知/本次不检索”，不能写“无”；跨案授权另行判断。

输出字段固定区分“用户拟定代号｜实际case_id｜建档状态”。例如demo-a只能填拟定代号；实际case_id未由已知记录或工具返回时填写“待创建后返回”，不以代号冒充。未执行建案时不填写建档日期或进行中状态。委托资料未提供写“签署状态未知/本次未提供”，不能填“未签”。仅收当前操作必需的最小字段，身份信息按需要用代称。下一步明确交给qx-case-work，不另造平行目录管理。

用户请求的列表、归档或切换只有实际工具支持且范围明确才执行；否则交付未执行的具体方案，不伪造已切换或已归档结果。

当前入口：[ qx-case-work ](../qx-case-work/SKILL.md)。

原始方法与许可出处：[原库只读参考](../../../legal-library/zh/litigation-legal/skills/matter-workspace/SKILL.md)。本工作台适配不修改原始库；参考中的旧插件指令不在此执行。
