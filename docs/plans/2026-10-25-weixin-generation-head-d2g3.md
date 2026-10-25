# D2g3 最新代际只读快照实施计划

> 执行沿既有 implementing/TDD 流程逐项进行；用户已授权无人值守实施与正常GitHub同步，无需重复需求访谈。

**Goal:** 桌面调用方无需读数据库即可获得下一次显式追加所需的准确代际、前驱摘要与checkpoint CAS。

**Architecture:** 集中七字段 `WeixinGenerationHeadView`，`generations.read_peer_generation_head` 在一个既有 BEGIN IMMEDIATE 事务中重核当前root、完整历史和最新目标权限并构造投影；conversation按根CID包装，HTTP仅增加精确GET head。schema17和账号暂停guard保持。

**Tech Stack:** 现有Python/FastAPI/Pydantic/SQLite，不加依赖或前端框架。

**Spec:** 接续[既有D2g1合同](2026-10-25-weixin-generation-service-d2g1.md)、[D2g2合同](2026-10-25-weixin-generation-http-d2g2.md)及TODO所列最新CAS head；基线dee54ea。

## 契约与边界

DTO精确 `mode=synthetic`、`state=history_only`、`generation`、`generation_sha256`、`scope`、`scope_sha256`、`checkpoint_revision`。generation为严格非负整数，零代 iff generation_sha256为null；scope摘要必须准确。完整record摘要仍是opaque凭据，不从删减投影重算。不返回账号/bot/peer/actor/root/taskbinding/自由reason，也不提供can_append或当前授权承诺。未绑定根CID返回null，不虚构零代/游标。

`read_peer_generation_head(actor,root_mapping_id,*,database)` 复用 `_root(active=False)`、`_history` 和最新 `_target(active=False)`，全部读取及DTO构造在 `accounts._transaction` 内。零代scope/hash取D2d有效最后grant或原mapping，非当前对话snapshot；非零取最后generation。checkpoint与代际来自同一受锁快照。成功读取不写业务或审计；拒绝可记既有权限审计。

根和最新目标当前owner/workspace、角色/成员、案件/接待转案/projection归属及_active_targets仍核。会话归档、账号/root逻辑撤权、恢复副本仅允许读固定历史，不豁免当前对象ACL。无需因非最新历史目标失去权限误挡最新head；历史校验仍完整。较旧head用于新request追加409，客户端不能据读头绕过最终写事务/CAS或自动重试。

GET `/api/assistant/conversations/{cid}/weixin-authorization/generations/head` 复用身份/同源检查并重新调用服务。只增加精确恢复GET白名单，所有写/邻近路径不放开。原D2g2测试中head被禁用的旧断言精确替换为head/或head/x，其余保护不变。

## 步骤与验收

- [x] 新增集中DTO、service/HTTP合成失败测试；根46/独立11有效RED，首次同名收集错误单列，不算产品RED。
- [x] 最小实现四产品文件：domain、generations、conversation、web/weixin_authorization；不接UI/按代际运行。
- [x] HTTP head→POST两代、scope来源/当前ACL/隐私/恢复；实际head/append与head/poll双向SQLite竞争、旧CAS、新Database、坏历史/schema均验。根14模块298不同Python、192 Node与四门通过；独立Spec完成，root Standards核查完成，第二独立Standards因宿主thread limit/WorkBuddy Bash拒绝NOT_RUN，不称双独立。见[实测](../testing/weixin-generation-head/20261025/README.md)。
- [x] 更新状态和实测证据，52授权文件扫描通过；fetch后正常提交推送d6627de至codex/contract-review-v2，远端SHA/tree及5,197条目一致；保留用户AGENTS改动，[回执](../testing/weixin-generation-head/20261025/github-sync.md)。

按AGENTS在最终答复前完成HumanLayer回读、Obsidian记录；TencentDB使用已加载Stop自动入队，仅有全局状态时不声称本轮保存成功。浏览器UI/安装版/全仓/真实微信与模型合同/付费签发外发均NOT_RUN；原生崩溃和WIN-PATH-02保持OPEN。后续再接明确桌面操作及按代际历史生效边界。
