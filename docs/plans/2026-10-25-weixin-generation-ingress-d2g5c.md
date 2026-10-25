# D2g5c — schema18专用合成代际收件（2026-10-25）

基线421ffa5abf464c8e8c89a49ab02f7afa19246d8c，实际仓库D:/Documents/ChatGPT/律所项目。沿用当前无人值守实施/正常推送授权；用户已选择直接推进，复用既有设计和架构，不重新访谈。先TDD、最小实现、分组关联回归、独立Spec/Standards。仅独立合成数据；真实微信/模型/付费/外发均关闭。保留用户AGENTS未暂存改动。

## 设计及接口（本轮决定）

专用cn_contract.weixin_inbox.generation_ingress.record_generation_poll(actor, account_id, request:WeixinPollInput, raw_response:bytes, *, database)返回既有WeixinPollReceipt；find_generation_poll_receipt(actor, account_id, request_id, *, database)只查询固定回执。没有新增DTO、schema、依赖、HTTP/UI/transport或自动调用链。schema18精确门；写需本账号已有代际、当前真实principal/owner/workspace、非恢复/非撤销。旧record_synthetic_poll/accounts/dispatch的全账号暂停保持，不把新行为通过请求字段开关暴露。

在既有BEGIN IMMEDIATE中先核完整provenance及父链，再用poll CAS和当前latest目标生成原描述；scope/版本/权限/归档逐条分类使用纯读取，不捕获会中途rollback+审计commit的_owned/authorize。accounts.py仅提取可复用纯scope分类，旧_mapping_reason先行代际guard保持。根会话当前权限和归档核验，根旧版本不锁定新代scope；最新目标完整scope必须精确当前。其他peer仍按零代mapping/grant解释。

既有ingress.py提取事务内_record_poll，保留原raw限制/去重/receipt哈希/descriptor顺序/checkpoint CAS；private generation_aware固定由专用入口传入。接受的原始非零代descriptor和7字段sidecar同事务写入，duplicate/blocked/零代均无sidecar。源event namespace不改。时间after=True覆盖同钟/回拨，严格晚于全账号活动。提交前完整来源复验，正向或反向新变为已知的跨代reply均整体VERSION_CONFLICT回滚；不猜测改派或推进游标。

新固定query与精确重放按descriptor sidecar的历史目标核当前权限，根和该固定目标都核；后续无关目标的scope/ACL变化不替代原目标。恢复、逻辑撤销和会话归档后允许固定查询，案件归档/撤权仍拒绝。新写无实际分发/任务创建，现schema18拒绝后代dispatch，留下一片独立版本与运行接线。

## 文件及验证切片

- [x] 开工读当前状态/上轮证据/来源/Git，自动记忆与CodeGraph；远端0/0，仅用户AGENTS脏。
- [x] 根新tests/integration/test_weixin_generation_ingress.py先RED：两代真实公开收件/固定sidecar、逐条去重和零代peer、同钟、权限、旧guard、完整性与reply回滚。
- [x] 独立tests/integration/test_weixin_generation_ingress_atomic.py先RED：真实SQL/commit故障、丢ACK查询、双线程/新进程、qxbak恢复及撤权。代理仅拥有该新测试和.local证据。
- [x] 最小实现：src/cn_contract/weixin_inbox/accounts.py纯scope分类提取；ingress.py共用事务内pipeline；新generation_ingress.py专用授权/固定回执/sidecar/完整校验。
- [x] 新测试及旧ingress/accounts/generation/provenance/dispatch/backup/TaskDraft关联短组回归，Node/四门；唯一用例按JUnit键去重，各组前后SHA，所有实际失败保留。全仓单进程/真实微信/安装版等NOT_RUN，不关闭WIN-PATH-02/原生AV。
- [x] 冻结实现后并行独立Spec/Standards；更新README/TODO/TASK_STATUS和docs/testing/weixin-generation-ingress/20261025证据。
- [x] 54授权文件扫描和暂存字节核验，fetch正常commit/push产品71802a6，远端SHA/tree及5496条目一致；文档回执另正常推送。
- [ ] HumanLayer/Obsidian同脱敏摘要收尾，TencentDB Stop自动提炼；不指挥其他聊天/不恢复五分钟任务。同步失败保留自己pending如实报告。

实际最终关联34模块886不同Python全部PASS，52新增已包含；233Node/四门exit0。源输入83份跨组一致。独立Spec/Standards各0确认遗留。见[本片证据](../testing/weixin-generation-ingress/20261025/README.md)。

记忆收尾在本轮最终答复前执行，当前Git快照不预报成功；按本轮本机HumanLayer/Obsidian回执和最终答复核对，TencentDB待正常Stop自动提炼。
