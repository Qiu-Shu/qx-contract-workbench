# D2d：同目标 scope 的显式重新授权

基线5142eaa，沿现有分支；AGENTS.md用户改动保留。用户已授权无人值守实施/合成验收/正常推送；延续最小充分改动、TDD、独立复核。无真实微信、模型、下载/发送或新依赖/HTTP/IPC/UI。

## 范围与契约

只刷新同一映射身份五元组：workspace_id、conversation_id、scope_kind、scope_ref、binding_revision全部等于原mapping及前一grant；input_revision/materials_revision单调不减且至少一项增加。跨目标/转案/重绑需要未来generation方案，本片继续409。原mapping及所有旧receipt不改；撤销不可逆，恢复副本不可写。

domain.py追加WeixinPeerRefreshInput：request_id UUID、expected_grant_revision严格非负整数（0指原mapping）、expected_scope_sha256 SHA256（前一有效scope CAS）、expected_scope ScopeSnapshot（当前完整目标）、reason严格非空去首尾空白且最长200。

追加WeixinPeerScopeGrant frozen DTO：id/mapping_id/request_id/actor_id UUID；revision严格正整数；previous_scope_sha256 SHA256；scope ScopeSnapshot；scope_sha256 SHA256；checkpoint_revision严格非负整数；created_at UTC；reason同上；grant_sha256 SHA256。scope_sha256=SHA256(canonical_json(scope))，grant_sha256=SHA256(canonical_json(model_dump json exclude grant_sha256))。

追加第16版weixin-reauthorization-v1，冻结旧15版native/non-native的30组结构及指纹。一张12字段表weixin_peer_scope_grants：id TEXT PK NOT NULL，mapping_id TEXT FK weixin_peer_bindings，request_id TEXT，actor_id TEXT FK users，revision INTEGER typeof integer >0，previous_scope_sha256 TEXT，scope_json TEXT，scope_sha256 TEXT，checkpoint_revision INTEGER typeof integer >=0，created_at TEXT，reason TEXT，grant_sha256 TEXT；除id外各列NOT NULL；UNIQUE(mapping_id,revision)、UNIQUE(mapping_id,request_id)，UPDATE/DELETE一律拒绝。

accounts.refresh_synthetic_peer(actor,mapping_id,request,*,database)：独立BEGIN IMMEDIATE事务，复验当前principal、owner/workspace、account/peer撤权、恢复fence、同目标身份、完整当前scope与ACL/归档。CAS前一grant revision+scope hash；新revision=前一+1；在当前checkpoint下新增grant，commit后才返回。同request同内容/预期前序可回读固定grant，仍需当前授权；冲突拒绝，不创建新grant。find_peer_scope_grant(actor,mapping_id,request_id,*,database)仅查询固定结果，当前owner及该mapping有效scope权限仍核验，恢复副本可查不可refresh，未知结果只查询。

accounts._effective_scope(mapping,db,*,at=None)选择该mapping最新grant（历史at给出时只选created_at<=at）；无表的已知旧schema/无grant回退原scope。当前_mapping_reason及ingress预览使用有效scope，其他身份/ACL守卫保留。find原poll/dispatch在重新授权后可按当前权限查询；旧blocked永远previously_blocked，不重分类。旧accepted可在显式授权后继续同目标投递，不能跨目标使用。

grant.created_at=_activity_time(account,after=True)，严格晚于本账号所有既有活动；后续bind/poll/dispatch/revoke的_activity_time纳入grant表。运行与历史按同一个UTC生效边界选授权；不修改旧TaskInbox墙钟。不将本机因果时间当远端认证。

精确实现约束：BEGIN IMMEDIATE内重读的当前_snapshot必须等于新expected_scope；grant经mapping→account JOIN聚合时间上界，UTC用datetime解析比较，不作裸字符串比较。TaskInboxEventInput不含expected_scope字段；旧accepted payload保持原字节，当前有效grant只授权同目标投递，TaskDraft读取时仍重核当前会话/材料能力，不将预览scope参数误作payload中的授权凭证。

## 历史、升级和恢复

新增grant_integrity.py验证规范UUID/JSON/DTO/hash、actor=account owner、同目标五元组、连续revision/previous hash/版本单调、created_at严格晚于账号/映射和前一grant、checkpoint_revision等于grant时刻之前全部poll的最新next_revision；之后poll不得回到更早checkpoint或时间。grant晚于既有同账号dispatch，不能未来grant追溯解释旧记录；原mapping/当前conversation历史scope由既有_scope核查（允许当前后续版本）。检查grant与账户/映射首次撤权严格先后，不要求当前ACL尚有效。非空grant只允许完整native qxbak；全部旧family gate在16版继续执行。

base inbox/dispatch历史校验用各poll/dispatch created_at的有效scope，校验当时有效授权链及时间边界；当前权限不替代历史有效性。两代qxbak精确保留grant及旧记录；恢复fence新增weixin_reauthorization_enabled=false。新schema/bootstrap/migrations/native升级catalog和备份完整接续。

## 验收

先RED缺DTO/服务/schema/历史规则，再最小实现。合成覆盖：输入/材料分别增长；grant CAS/摘要/request幂等冲突；原mapping字节不变；同目标pending继续；blocked不复活；跨scope/binding/owner/session/ACL/归档/撤权/fence拒绝；同刻度/回拨有因果次序；并发/commit前故障/丢ACK查询/新进程；两代备份恢复及损坏归档拒绝；旧15版30指纹和旧family来源损坏门。

目标回归、四开发门、独立冻结复核后记录命令/退出码/数量和NOT_RUN，精确文件提交推送并核远端SHA/tree。真实微信/模型、E许可、浏览器/安装包/全仓均NOT_RUN；0.4.1、原生崩溃及WIN-PATH-02保持开放。按AGENTS完成HumanLayer/Obsidian/TencentDB收尾，不恢复五分钟轮询或指挥其他聊天。
