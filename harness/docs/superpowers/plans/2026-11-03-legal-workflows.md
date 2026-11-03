# 四能力落地 Implementation Plan

> 实施方式：superpowers:subagent-driven-development；用户已明确“开始落地”，直接实施，不增加业务审批或重复设计确认。

**Goal:** 在现有单输入框、本人微信和Harness会话上，接回合同/接待方法、案件材料归属与连续记录、五阶段庭审演练。

**Architecture:** 现有材料MCP保持；新增本机 `qx_legal` MCP复用MaterialStore、SQLite与旧工作方法。业务正文始终自然语言，记录失败不丢弃已生成回答。四个本地Skill负责按需编排，无新增首页按钮。MiroFish仅研究真实代码并借鉴适合的角色/记录机制，不安装其云端模拟栈。

**Tech Stack:** 现有Python 3.12/MCP/SQLite/python-docx、Harness 0.2.2-alpha.2。

**Spec:** 本文及用户上一轮认可的迁移顺序；旧GitHub四能力评估、`config/workspace-AGENTS.md` 的客户回复要求。

## Global Constraints

- 只修改新项目；旧仓源码、数据库、私人知识原件保持，不伪称缺失私有包已恢复。
- 保留其他会话新增的网页/桌面/文案Skill与运行配置。当前开发分支 `codex/local-harness-20261102`；新目录是本机独立部署，无旧代码覆盖或自动推送。
- 案件/材料/来源通过显式ID绑定；没有全局“最近案件”自动落档。普通短回复不强制建案。
- 记录追加、更正关联，不覆盖用户原话与旧成果。引用失败为待核提示，不因回答字段/篇幅拒收整段文字。
- 合成数据验证；运行验证不操作真实工作会话或微信外发，不读取真实案件。
- 无新依赖、无自动发布。模型上下文压缩通过Harness现有机制；业务记录在本机，可回读。

## Tasks

- [x] A 案件基础：`bridge/business_store.py` + focused tests。CaseStore(MaterialStore)；create/list/get/link_materials/add_note/read_material/search，显式case_id、不可变记录、材料版本与逐字引用反馈。
- [x] B 方法迁移：`bridge/workflows.py`、`config/skills/qx-client-reception`、`qx-contract-review`、`qx-case-work`；旧方法来源、摘要和适配说明；自然语言交付，不带旧JSON拒收协议。
- [x] C 庭审：`bridge/hearing.py`、`config/skills/qx-mock-hearing`；复用旧阶段/角色顺序，逐发言记录、重开回读、材料变更提示与可追溯续接；不宣称裁判预测。
- [x] D 接线：`bridge/business_server.py`注册工具；增量挂载qx_legal；同步四Skill及AGENTS路由到运行workspace，保留原扩展。
- [x] E 验证：真实MCP临时工作区测试；真实Harness虚构接待/合同/办案/庭审操作与重开回读。记录实际工具、输出、失败及限度。
- [x] F MiroFish：固定上游版本，记录许可原文、云依赖与可借鉴机制，给出本机采用结论。

## Review Focus

- 同名案件不自动合并；新会话不得按最近时间猜归属。
- 补件/更正保留旧记录，原文件变化能被发现。
- 未匹配引文不得标成核实，但不吞掉正文。
- 客户正文与内部底稿分别保存及输出。
- 回合重试不重复追加；程序中断不把未执行的阶段标成完成。

## Coordination ledger

|任务对|共享接口/文件|决定|
|A/D|CaseStore公开方法|A先报告实际签名；D只写MCP薄封装，不改存储模块|
|B/D|Skill工具名、workflow函数|统一qx_legal前缀；四业务入口由D补最终工具签名|
|A/C|MaterialStore.db与case_id|同SQLite事务；C用CaseStore读关联资料，不自行列全部材料|
|C/F|角色/记忆思路|F提供研究，不复制第三方实现；C保留旧五阶段兼容|
|A/B/C|文件归属|每代理独占模块与测试；根只做集成、庭审与文档|
|D/现有扩展|AGENTS、profile|增量编辑；不覆盖用户已增加的浏览器/桌面Skill和团队配置|

Ruling：现有独立D盘运行目录直接增量实施，避免复制当前用户workspace；模块在临时workspace验证后再挂载。现有Git尚无提交，不为本次工作创建依赖秘密/真实材料的初始提交。
