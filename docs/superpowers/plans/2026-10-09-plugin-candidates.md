# 插件候选提交 Implementation Plan

使用 writing-plans / executing-plans、Ponytail和既有插件更新流程，沿b8da6d7继续。

**Goal:** 在明确写入授权下，将当前虚构案的来源绑定建议保存为待律师处置候选。
**Architecture:** 复用15分钟选案、AssistedReviewInput、ReviewProposal不可变存储和现有处置/导出；不新增数据库表。增加可区分的插件来源收据，不能冒充人工候选或已验证模型推理。
**Tech Stack:** 既有FastAPI/SQLAlchemy/MCP及标准库；不增依赖。

## 设计约束

- 原选择默认只读；增加未勾选的“允许提交一轮候选”同意，后端严格布尔验证。客户端不能提交案件ID、授权主体、来源或模型证明。
- 新无参选案读取保留；新submit_selected_candidates(input)只收AssistedReviewInput。固定loopback POST，不自动重试、不调用远程模型。
- 后端核对当前授权、会话/角色/成员、事实与原件、来源及上下文。每个grant仅一轮；相同输入重放返回原收据，不再落库，不同输入拒绝。过期/撤权/重启后禁止重放；超时显示需去工作台核实。
- 写入完成保持awaiting_lawyer、人类决定为空；收据source=local_plugin_unverified，model_identity=UNVERIFIED。模型来源与推理不由客户端自证；后台供应商调用仍0。
- PDF危险文字、未核法源不能因插件输入变为已核；原手工录入、历史快照和导出来源提示保持可验证。
- 授权恢复/并发撤销/提交事务失败不可产生幽灵成功。缓存仅在数据库commit成功后发布，进程重启取消授权，不宣称跨重启重放可用。

## 实施步骤

- [x] API失败测试：默认拒绝写、显式授权成功、来源准确/待处置、重复/冲突、旧版本/撤权、原手工入口不可伪造来源。
- [x] domain.py收据/权限DTO，proposals.py构造及重验分支，case_bridge.py事务提交与同授权重放，审计动作。
- [x] case_client.py固定POST与offline_server.py有限写工具；0.1.5源包及绑定；界面显式同意、候选到达后的刷新说明。
- [x] 目标、旧手工/导出、插件回归，实际HTTP/STDIO与浏览器；独立审阅及实际修复复验。
- [x] 保存逐项命令/退出码/数量与宿主阻断，更新TASK_STATUS、Obsidian并提交；未验项目不标完成。
