# C2b2b 下一执行切片：独立设计复核

基线 `9a0d2df3767dc8252f1530be4f949583fd250af2`。只读核对当前 attempt、runner、profile存储及完整性源码；未改产品、未运行测试、未触及真实库或模型。

## 结论与模块边界

可按统筹方案实施：既有 `assistant_model_attempts/receipts/outputs`、预算、claim、恢复和单次runner保持唯一；新增 `providers/profile_attempts.py` 放档案格式的登记、当前数据库校验及保存专有逻辑，公共 `attempts.py` 只增加明确格式分派。以函数内导入避免新冷启动链，不增通用钩子框架或第二队列。

需要一片闭合持久登记→claim→同次响应→费用/输出→固定保存回执→历史/恢复语义，才移除 `model_integrity:455-461` 的新格式拒绝。native/HTTP生成入口可继续未接；内部通过不宣称律师端自动存档可用。

## 必须提前固定的接口契约

1. `enqueue_profile(actor,cid,message,basis,db,runtime)`：调用C2b2a从真实草稿重建basis，再由registry核验完整用途；使用共用 `_budget`/reservation，限定profile格式、round_no=1、policy.max_calls=1。一个事务内 `save_message`、按保存后实际记录 `prepare_profile`、登记attempt及原有model.reserved。没有attempt的旧普通消息不能通过重试补开模型资格。原request_id相同仅返回同一持久attempt；改目的/计划/配置/策略摘要或错格式拒绝，不能重新预留或发送。应在复用 `_replay` 时显式区分profile；当前 `context=False` 不足以区分plain/profile。
2. 共享 `_input`、`_wire`、`read_attempt` 和runner增加明确profile分支，不让MainProfileRequest落入普通MainRequest或MainReply转换。`domain.py` 增加显式MainProfileOutputView/MainProfileAttemptView，保留候选profile_patch；`MainGenerationHistoryItem.attempt` 也须支持该类型。旧DTO及V1输出保持原样，不靠隐式基类序列化。
3. `profile_attempts.current(...)`：在claim和settle使用C2b2a核验实际actor/session、run/request/message摘要、固定scope、空选择、最新profile/intake基线，持久prepared须与可信重建逐字段相等，再核对当前registry目的许可和保存的policy/config摘要。继续使用同一claim token与发送前状态CAS，不另建锁/次数计数。保存后新增草稿允许，scope版本不变。
4. 纯 `validate_candidate` 放现有profile_preparation模块，settle与历史复用：深验MainProfileCandidate、空citations、patch scope/base、只引用当前保存的user message、quote字符区间/原文/SHA/source_revision、unverified与允许origin、contact不推断、material仅needed。不要信任替身provider自动满足codec；不要接受document/其他消息引用或manual_edits。
5. 采用统筹的保守语义：**claim/settle时完整保存基线变化、撤权、取消或scope失效→弃候选，仅保存已发生费用，不建output/handler。** 只有candidate通过当时完整current检查后，具体保存操作发生冲突/故障，才可保留output并记录blocked handler。这样不会把旧许可刷新到新版本。

## 原子保存与拒绝审计：不能只依赖savepoint

`profile_store._commit:112-185` 可复用，外部 `save_profile:188` 会自行开多个session，不适合在模型结算事务中调用。当前文字片只需从同一db读取run绑定user message构造ProfileSourceSnapshot，不能把输入DTO当已读数据库来源，也无需引入附件I/O。来源及纯候选校验应在写入前完成。

**重要事务风险：** `_commit` 会重新调用 `_writable`/intake权限，`security.deny:111-125` 会rollback整个调用方事务，再单独commit拒绝审计。`db.begin_nested()`不能把这个全事务动作限制在savepoint。如果先插费用/output/response.ready，再简单catch保存异常后继续插blocked，会引用已经回滚的行，甚至丢掉费用。

最小可行做法有两种，统筹需固定一种并给故障测试：

- 优先在所有当前权限/来源检查后，先在受控savepoint尝试 `_commit`，成功后在**同一个外层事务**写费用、output、response.ready、handler和终态事件；任何关联写失败，外层整体回滚，不能留下孤立档案。物理插入先后不等于提前提交，handler在引用行全部存在后落库即可。
- 若沿用 `save_after_output`，异常必须在savepoint上下文之外捕获，重新取得有效事务、require_active、重取sending行及claim，再检查current；判断先前费用/output/event是否仍存在。审计rollback后必须从真实存活状态重建，不能沿用旧事件seq/output ID假装已保存。

无论哪一种：权限再次失效时只落费用，不保留新候选；普通保存失败但重新current仍有效时，整个档案/接待子操作回滚，output、blocked handler和费用同次落库。数据库不可写时不能宣称费用已持久，应沿sending→恢复sent_unknown的保守状态；不自动重发供应商。不得为了方便改全局deny行为或在处理中私自commit。

## 固定事件、回执与恢复的共同合同

- 事件 `response.ready` 固定绑定attempt_id/output_id/basis_sha256/handler_id=profile.save/handler_version=1，成功或失败事件绑定相同event_seq和结果；model.finished继续旧结构。事件内容、顺序和字段名必须由三个作者先固定，不能各自推断。
- handler去重沿现有 `(run_id,event_seq,profile.save,1)`，并遵守attempt/output唯一约束。ProfileCommitInput.request_id应由该固定处理身份确定性产生；manual_edits固定空，project_intake/目标/修订只取批准basis。applied/unchanged必须关联具体profile_receipt，blocked只允许version_conflict/save_failed且无profile_receipt；blocked是终态，不换事件/版本/请求ID刷新旧许可重试。
- applied与unchanged按profile_changed或projection_changed确定；空patch也可形成无变化回执，不虚构新revision或空接待。保留原merge_profile对人工锁、冲突、未知和来源的处理。
- 同一成功事务包含档案、接待、投影/档案回执、模型output、固定handler和成功事件；故障注入覆盖每个写入位置。费用以MainReceipt沿用收到usage、未知、未发送三态；供应商实际使用量超出预留仍记真实回执，不截断或改0。
- 恢复仍复用recover_attempts：reserved→failed_before_send，sending→sent_unknown，run→interrupted，绝不重新发送或补跑档案保存。成功/blocked保存结果都已原子落库，不需要第二个恢复队列。

## 完整性闭合不能只删guard

保留旧 `_validate` 的全账本共用检查，profile在明确schema下增加格式分支及独立 `profile_model_integrity.py`。不能把profile行筛出去后仅各自验证，漏掉同policy总次数/摘要、同run混格式轮次、model_runs集合、孤立receipt/output/citation以及原model事件链。

profile历史至少验证：持久prepared完整重建、原request摘要、会话属于用户、历史scope/source/material快照、唯一完整basis策略键和单次round；候选采用同一纯validate_candidate；固定output→response.ready→handler→profile_receipt与后续profile事件一一对应。profile_commit请求必须等于候选patch及原basis本地计划，manual_edits为空，确定性request_id一致；handler的basis摘要及created_at关系明确。成功历史继续运行已有profile_integrity全量merge重放，不绕过人工历史；blocked不能伪造成功receipt或偷偷增加profile/intake修订。

**在空账本早退之前**检查所有孤立handler、response.ready/profile相关事件。每个采用的profile output恰有一个处理回执；无output的未发送/未知/弃候选不得带handler。缺一个成功handler不能被当“以后补保存”，多一个blocked/成功事件也不能通过。历史检验使用记录当时的基线、资料和授权关系，不要求现时session仍有效，避免撤权后无法备份合法历史。

qxbak允许完整profile模型历史；不支持模型历史的cnbak路径仍拒绝。原所有附件、模型、Jev、法库、档案验证入口继续运行；旧所有schema与旧有效数据保持可读。原封闭guard只在这些校验、恢复和故障回滚全部就绪后替换，不能提前放行。

## 并行分工与验收重点

- **统筹**：profile_attempts.py、纯candidate校验、必要profile_store/source内部事务接口；先固定函数签名、事件payload、request_id和handler结果规则。
- **执行作者**：attempts/runner/domain分派、history DTO接纳、登记/预算/claim/settle集成测试；复用既有恢复实现。
- **完整性作者**：model_integrity的窄分派、profile_model_integrity跨表重放、归档与故障测试；不同时改执行作者的attempts或统筹的profile_store。

必须同步的三点：settle异常与deny全事务回滚语义、事件/回执精确结构和状态映射、新DTO序列化及profile完整性分派。三者未对齐前不得移除guard或启动新持久执行。

重点合成验收：登记幂等/旧消息不升级/预算与并发单claim；同次响应回答和方法提案；部分写入故障全回滚；保存冲突与权限审计分别保费用；重放不重复档案/接待；sent_unknown/recovery无二次HTTP；恢复副本禁止执行；旧plain/context/rounds和既有档案历史继续通过。native/HTTP无需本片开放，真实材料/费用和活动桌面不参与。
