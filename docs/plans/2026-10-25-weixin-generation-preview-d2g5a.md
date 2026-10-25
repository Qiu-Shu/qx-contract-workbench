# D2g5a 按持久代际离线预览 Implementation Plan

> **For agentic workers:** 使用已授权执行与TDD逐项实施；独立代理仅负责自己的测试文件和复核。保留用户AGENTS改动。

**Goal:** 在现有收件仍暂停时，以当前身份和持久代际生成零写入的合成协议预览，为后续运行解析建立边界。

**Architecture:** 在既有accounts._transaction中复用generations._root/_history/_target，完整比较调用方expected_head与实际持久head，另核持久scope等于目标当前完整snapshot。仅调用现有weixin_offline.translate_response；不调用收件/任务写接口，不调用另开事务的read_head。

**Tech Stack:** 现有Python/Pydantic/SQLAlchemy/SQLite/pytest，无依赖、schema、HTTP/UI变更。

**Spec:** sources/specification-v2.0.md安全/权限/独立虚构材料约束；D2g1—4的持久代际和暂停契约。用户明确无人值守推进、常规推送的授权优先，复用既有方案，不重复访谈。

## 全局约束与选择

当前generation_integrity禁止代际之后再有poll/dispatch活动，持久descriptor/dispatch也未保存新代际绑定来源，因此本片不删除或弱化account._has_generations暂停guard。直接开启运行会使当前存档/恢复来源校验失真；本片只提供当前目标的合成假设预览。真实微信身份/资格、下载/发送、模型/付费、恢复解锁均不在范围。

接口：`generation_preview.preview_generation_response(actor, root_mapping_id, expected_head: WeixinGenerationHeadView, raw_response: bytes, *, database) -> WeixinGenerationPreview`。

输入复用现有完整七字段history_only head作只读前置条件并重新model_validate，避免重复定义相近输入。新DTO仅在domain.py：`WeixinGenerationPreview(mode='synthetic', state='preview_only', head: WeixinGenerationHeadView, plan: WeixinOfflinePlan)`；验证head.scope与plan.scope.expected_scope一致。此DTO不是授权令牌、持久Inbox、去重结论或游标回执，不能凭它跳过运行时权限/来源校验。

零代使用最后grant或根mapping的持久scope和根binding，非零只选最新generation持久scope/binding。根和目标当前ACL、归档、revocation、恢复fence都要核；完整scope等于目标当前snapshot后才翻译。owner/session、task_cursor/account_cursor全部来自事务内当前记录；空poll不凭空推进任务游标。整份预览精确匹配本根peer，混合或其他peer整份拒绝，不称账号级分发。全局source_event_id不加generation，历史/reply来源不被重写。

## Review Focus

- expected_head晚于/早于持久链、checkpoint或零代grant变化必须拒绝，不能把旧head当当前授权。
- 根/目标当前角色、session、案件/接待转案及projection权限变化、归档和恢复均阻断预览，不披露目标内容。
- SQLite锁取得之前发生追加/撤权时必须读到新状态；锁取得之后不能把多个时点的head/游标拼接。
- 协议解析错误、混合peer、文件媒体密钥与上下文token不得变为运行能力或持久原始材料；source/reply不跨代重新命名。
- 成功和空poll零业务/审计写入；拒绝不得写业务，但保留既有security.deny拒绝审计。不触发socket、模型、任务或旧poll/dispatch恢复。独立实际403反例已纠正原“所有失败均零审计”的过度承诺，安全代码不改。

## 一个可验证切片

**Files:** domain.py集中新增一个DTO；新增weixin_inbox/generation_preview.py；unit DTO、主功能集成和独立atomic各一文件。其余产品文件保持。

- [x] 先写unit/主集成和独立竞争/恢复测试；实跑RED，缺模块和实际行为失败分开记录。
- [x] 最小实现事务内持久目标解析与现codec预览，跑新增GREEN和相关回归；不扩权限/运行guard。
- [x] 独立复核当前冻结产品与测试，根复验独立产物，记录实际数量/退出码、源散列和NOT_RUN。
- [x] 对比D2g3/D2g4计数的不同测试集合，避免共享记忆误认为数量回退；只解释实际范围，不重做已完成工作。
- [x] 更新状态/实测证据，扫描授权文本，fetch后正常commit/push并核远端SHA/tree；按当前AGENTS三端收尾。

最终361不同Python、233 Node、四开发门exit0；50新例含独立7且不重复累加，原恢复session预期错误和原审计计划错误均保留。产品自首次实现后未改；[证据](../testing/weixin-generation-preview/20261025/README.md)。

产品6c0b26a及证据已正常推送并核远端SHA/tree/5,297条目一致；[回执](../testing/weixin-generation-preview/20261025/github-sync.md)。用户AGENTS未提交。
