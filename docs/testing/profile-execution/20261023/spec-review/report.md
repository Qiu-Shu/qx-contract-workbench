# CH-07C2b2b-B 独立 Spec 复核

结论：**0 项必须修复问题**；缺失、误实现和越界均未发现。本结论是本片有限审查，不是全面产品认证。

基线 `9a0d2df3767dc8252f1530be4f949583fd250af2`；以 `docs/plans/2026-10-23-profile-execution.md` 交付合同 1—7 为依据。审阅未提交的跟踪差异及新增 `profile_attempts.py`、`profile_model_integrity.py` 和相关测试，未把未接入的原生、HTTP、调度或界面能力列为缺陷。

- 合同 1—3：完整 basis 与持久 policy 身份、预算/claim、实际来源和当前保存基线重复核验；普通协议不能升级为档案协议；收到的费用与提案采纳分开。
- 合同 4—6：保存先于账本写入；显式 savepoint 处理鉴权审计整事务回滚；异常后重取存储、claim、current；固定请求 ID、handler 与事件同事务，blocked 不续发。
- 合同 7：保留共用费用/混合格式/来源校验；新增固定事件、output、handler、保存回执关联，并复用档案重放。空账本孤立记录仍先拒绝；已有 qxbak 路径进行完整性验收。

最终独立合成探针：**7 passed，exit 0，7.77 秒**。覆盖来源扩展后的输出大小、同会话两次独立批准整理、注册器重启后复用 policy ID、不同登录会话处理在途响应，以及事件大小写、额外档案事件、handler 时间倒置。使用实际合成 SQLite、registry、claim、codec、settle 和历史校验；未联网。

`inputs-before.json` 与 `input-stability.json` 核对 **19/19 输入前后不变**。执行命令、环境与基线见 `command.json`；实际退出码、JUnit、日志分别为 `exit-code.txt`、`results.xml`、`output.log`；跟踪差异见 `tracked-diff.txt`。

准备阶段的导入路径错误（exit 2）和探针误将 bytes 当作 str（exit 1）均保留于 `initial.*`、`first.*`，属于探针自身问题；修正后的预冻结单探针 1 pass 见 `second.*`。预冻结期间产品新增大小限制，故不声称最初 core 哈希稳定，也不将单探针与最终 7 项相加。

未重跑作者目标套件、父代理 23 文件关联/四门、真实恢复全流程、真实供应商或安装版。备份/恢复的跨模块调用与测试覆盖仅静态核对；最终集成及恢复实测以统筹证据为准。
