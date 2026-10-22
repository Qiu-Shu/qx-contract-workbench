# CH-07B 本地档案保存闭环

基线 `2b72c9a02a25607761705811550323fa9fcfce00`；沿用 v2.1、CH-07A 纯合并与 CH-07B1 来源读取。只用独立合成数据。当前无人值守授权覆盖本片，不另起工程或请求重复批准。

## 实施合同

- `ProfileCommitInput`：request_id、patch、expected_intake_id/revision（同时空或同时有值）、manual_edits（最多12个唯一字段）、project_intake（默认false）。客户端/模型不能提供 owner、确认者或已核实状态。
- `save_profile(actor, request, *, database)` 先检查同请求回执，再通过既有来源读取入口核对原件；短写事务重新核对当前授权、归档/恢复、scope、profile与intake修订。内部savepoint包含全部写入，外层捕获异常也不留下半份记录。
- 当前目标接待为 scope=intake 的 scope_ref，否则为已有 projection_intake_id；请求须精确匹配当前目标与修订。禁止任意链接别人的接待、跨conversation竞争时静默重基线、已转案接待继续改写。
- 合并复用merge_profile；上次投影回执指向的IntakeDraft作为基线，当前接待作为人工保护比较来源；无基线既有字段整字段保护。业务字段仍只有现有intake版本链，不另造CRM。
- 一次成功保存包含profile新修订（确有变化时）、已有intake.create/save（确有投影变化时）、首次projection链接和不可变回执。回执本身是独立的内部profile.saved/profile.unchanged事件，**不往已有模型run事件机器追加不兼容事件**。每请求一个有序回执；同request同摘要重放原回执，不同摘要拒绝；语义无变化不加profile/intake修订。
- 客户回复/内部意见保持独立；每次投影记录consultation_origin，旧手工版本继续标原话，自动摘要标接待摘要并链接来源会话。人工编辑仍未自动核实，原件及旧修订不可覆盖。
- 提供当前/指定历史/按request找回的本机接口与显式编辑提交；GET不运行模型。恢复副本只允许历史读取，拒绝提交；此片不接自动模型提炼/新首页档案面板。

## 持久结构与离线验证

新增版本 `assistant-profiles-v1`，保留全部历史schema原样。两张append-only表：

1. `assistant_profile_revisions`：conversation_id、revision>0（复合主键）、profile_json（<=2097152字符）、profile_sha256、created_at。
2. `assistant_profile_receipts`：conversation_id、sequence>0（复合主键）、request_id（同conversation唯一）、request_json（<=2097152）、request_sha256、profile_revision可空（空代表0）、profile_changed 0/1、intake_id/revision/hash可空三元组、projection_changed 0/1、consultation_origin='user'或'profile_summary'、event_type='profile.saved'或'profile.unchanged'、audience恒internal、actor_id、session_id、created_at。复合外键关联profile修订和intake修订，用户/会话/对话外键。changed或projection_changed为真则saved，否则unchanged。receipt保存不可变请求，不保存整套重复来源原件。

离线validator按每conversation sequence重放全部请求。用历史消息和当时材料快照重建来源，不检查当前登录是否有效，不读取外部文件或当前选片；复用纯合并并检查profile结果、投影baseline/current历史修订、摘要/变化标志/引用/时间/owner/session归属以及没有孤立修订。原件字节完整性沿用已有附件与qxbak检查。新schema初始化、所有旧版本迁移、完整性、qxbak备份与只读恢复一起闭合。

## 验证与协作

主代理负责DTO、保存/读取服务、HTTP与接待摘要标识及集成测试；迁移子代理负责schema、初始化、版本门和迁移测试；完整性子代理负责历史重放验证、备份接线与故障矩阵。共享文件domain.py由主代理独占。

验证包括有效失败记录；原子失败注入/并发幂等/撤权与过期/人工保护/同名不合并/受众隔离；旧schema完整迁移；篡改与完整备份/只读恢复；相应回归与4开发门。独立复核后记录实际命令、数量、退出码，更新协作文档并正常推送核对远端。不得把本片称为真实模型、安装器或法律质量验收。
