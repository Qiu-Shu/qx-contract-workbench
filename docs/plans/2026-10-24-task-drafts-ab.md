# 持久合同任务 A＋B 实施记录

目标：把多次消息和附件持久收集为同一合同任务，在材料清单确认后复用现有案件、事实确认及 Mock 审查形成内部结果。

授权：2026-10-24 用户批准落地实施及无人值守，允许 WorkBuddy 协助。沿 `codex/contract-review-v2` 继续，起点 `f9e6bf45e78a58ff094fa21b8dcc47fd465fb227`。本次实施 A＋B；C（PDF 桥接）、D（真实微信）、E（真实模型和限期授权）保持后续阶段。

技术：现有 Python/FastAPI、SQLite、原生 JavaScript 和 Electron；无新增第三方依赖。业务 DTO 仅定义在 `domain.py`。

约束：独立合成数据验证，不连接真实微信、不调用真实模型、不自动确认事实、不正式签发或向第三人发送。保留当前会话归属、案件授权、不可覆盖原件、审计和备份恢复隔离。

## 分工与接口

1. 核心 `task_drafts/schema.py`、`service.py` 和 domain DTO：事务 Inbox、游标、事件去重、持续草稿、明确归属、暂停/取消/恢复、材料冻结 CAS。收集不得创建 assistant run。
2. 存储：追加 `task-drafts-v1`，保持旧 schema 指纹；备份完整性与恢复禁重放；检验迁移历史及篡改拒绝。
3. 桥接 `task_drafts/bridge.py`：冻结材料复制为目标空案件的不可变文档版本，复用 `candidate_parse`，停在待事实确认；用户完成现有事实确认后复用 `services.review` 的 Mock 路径。当前阶段同步有界本地执行，业务结果与执行映射在同一数据库事务保存。
4. HTTP/桌面：独立模拟合同任务卡片、两种消息/附件到达顺序、明确主合同和目标案件、任务控制、材料清单及事实/结果导航；统一工作区任务投影。

核心接口：`create_binding`、`receive_batch`、`list_drafts`、`read_draft`、`update_draft`、`freeze_draft`、`read_execution`、`advance_execution`。桥接接口：`prepare_execution(actor,id,value,db)`、`review_execution(actor,id,value,db)`。

## 验证次序与审阅关注点

- 每个实质模块先执行有效失败测试，再实现最小通过实现，记录命令、退出码和实际数量。
- 独立检查事件幂等与篡改冲突、断电后重新打开、游标提交顺序、多附件完整性、越权显式关联拒绝、旧材料清单确认失败、冻结后补充隔离、取消/恢复与不重复执行。
- 桥接验证原件哈希一致、跨案件/会话拒绝、合成白名单、事实未确认阻断、同执行重复调用不生成第二次审查、撤权后拒绝读取/执行。
- 存储验证旧 schema 升级、损坏备份拒绝、恢复后的执行隔离；HTTP 验证登录/CSRF/归属与桌面真实调用链。
- 目标回归后独立审查并修复，再更新 TODO、TASK_STATUS 和实际证据；前一实施轮按当时边界留在工作区；用户随后明确要求GitHub同步，现正常提交并核验远端，不声称真实入口或法律质量已经验收。

## 当前执行账本

- 基线工作区干净，远端核对无分叉。
- WorkBuddy 已完成只读复核，原生 ACP 回执核实请求及实际模型均为 Kimi-K3 (`kimi-k3-2`)；用户随后授权其写代码，独立浏览器脚本扩展交由其实现并由 Codex 实测。
- 核心、存储、桥接和界面实现已落盘；最终实际结果见 [验收汇总](../testing/task-drafts/20261024/README.md)，本计划不代替执行证据。
- 真实微信/产品模型、PDF 桥接、安装器及生产迁移均 NOT_RUN。
