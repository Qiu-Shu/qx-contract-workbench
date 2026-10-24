# D2b：合成账号、精确映射与原子完整收件

沿用 D2a 版本/四表/DTO；不改 DDL、依赖、HTTP/IPC/UI，不连接微信或模型。用户已授权无人值守增量实施及正常推送；沿当前分支保留 AGENTS 未提交改动。复用 ponytail、先失败测试与独立审阅，不重复需求访谈。

## 接口和事务

业务输入只追加 domain.py：WeixinAccountCreateInput(bot_account_id, initial_cursor='')、WeixinPeerBindInput(sender_peer_id, task_binding_id, expected_scope)、WeixinRevokeInput(reason非空白<=200)、WeixinPollInput(request_id,expected_revision,expected_cursor)。拒绝额外/非严格类型；DTO在服务边界重新验证，不信任model_copy。

`weixin_inbox/accounts.py` 公共方法均 `(..., *, database)`，自己创建 Session，`BEGIN IMMEDIATE`→校验→写入→commit→返回；不接受调用方尚有业务写入的 Session。create_synthetic_account(actor,request) / read_synthetic_account(actor,account_id)；bind_synthetic_peer(actor,account_id,request)；read_synthetic_peer(actor,mapping_id)；revoke_synthetic_account(actor,account_id,request) / revoke_synthetic_peer(actor,mapping_id,request)。读可用于恢复核对，写必须require_active。真实 principal由数据库session/user重建，仅律师，owner/workspace由服务填，mode固定synthetic；bot/peer字符串不代表远端认证。创建重放只接受同owner/相同初始游标，绑定重放只接受同精确peer/task_binding/完整scope；撤权不反转，不隐式重绑。撤权重复同原因回读固定原时间/actor，不同原因冲突。

内部共享 `_transaction(database)`、`_account(actor,id,db,*,active=True)`、`_mapping_reason(current,account,mapping,db)`。_account返回(accountDTO,currentActor)。_mapping_reason返回None或固定reason，**只读、不audit、不rollback/commit**；复用_current、_principal和现有security._ACTIONS/read策略及MembershipRow，检查task binding→会话同owner/workspace、archive、精确scope、matter ACL、intake owner和转案ACL、projection intake；revoked->binding_revoked，快照修订变化->scope_stale，权限/归属失败->scope_denied。映射历史不可改，过期映射明确阻断；刷新/重新绑定留后续显式设计。

实施裁定：新增收件属于新增业务工作，直接案件、接待转案和投影接待关联的案件均须存在且非 archived；归档归 scope_denied。既有只读 authorize 行为不改。Database 自带 engine begin listener 已是 BEGIN IMMEDIATE，共享_transaction复用该机制，不重复执行 BEGIN。

`weixin_inbox/ingress.py`：record_synthetic_poll(actor,account_id,request,raw_response,*,database)->WeixinPollReceipt；find_poll_receipt(actor,account_id,request_id,*,database)->receipt|None。调用共享事务，在任何写入前重建当前principal/account与fence，锁持有到commit。账号撤权拒绝新增；同request_id且请求摘要/响应SHA都相同则返回原receipt（不看旧expected revision是否已推进），不同则VERSION_CONFLICT。新请求expected revision/cursor必须精确匹配。请求SHA取canonical_json输入DTO的SHA，responseSHA取原始bytes。

lookup/重放仍核验当前身份、账号owner；有accepted内容时逐个要求_mapping_reason=None，防止撤权/换案后借旧回执读取旧文本。find在恢复fence可只读；record即使重放也拒写入口。未找到返回None；查询不推进任何游标。

## poll和逐条分类

复用D1 strict_json/字段常量/_event，无新的协议依赖。bytes有界、重复JSON键/错误envelope/非零ret或errcode/非法cursor/超过100条均整批拒绝无checkpoint。缺get_updates_buf沿用旧opaque cursor；明确成功而缺msgs视为空poll。允许单账号poll混合精确peer，每条都持久记录ordinal和sourceSHA，空poll也留完整回执并revision+1。

可用source身份为规范sender_peer、无损uint64 ID、D1 event_id(bot,peer,id)的完整三元组；无法识别则三字段全空，blocked message_invalid，不保存raw。每条先查同来源更早原始descriptor（含本poll更早项）：同hash已accepted→duplicate/replayed；同hash已blocked→blocked/previously_blocked；不同hash→blocked/event_conflict，均指向原始行且无payload。身份未重复时精确recipient错误→recipient_mismatch、未知peer→sender_unbound、当前mapping失败→对应reason；D1不支持→message_unsupported，其他格式错误→message_invalid。有效事件仅accepted_pending_dispatch，安全TEXT/pending DOCX/PDF，绝不调用receive_batch/模型/下载。以前blocked不会因后来授权复活。

先在内存完成描述和完整回执hash，再同一事务insert poll+所有descriptors，最后UPDATE account WHERE revision/cursor CAS；任何SQL/commit故障整批rollback。current ACL分类不得调用security.deny。当前事务BEGIN IMMEDIATE阻止并发权限或cursor写入穿透检查。固定本地数量/字节界限不冒充上游限额。不承诺远端认证、业务exactly-once或生产完成。

## 分工与验收

- Root：输入DTO及RED单元、端到端故障/恢复/幂发测试、证据/四门/独立复核、正常GitHub与三端收尾。
- Accounts代理：accounts.py+tests/integration/test_weixin_accounts.py，先RED再最小实现；不得改domain/ingress/DDL。
- Ingress代理：ingress.py+tests/integration/test_weixin_inbox_ingress.py，先RED再实现；等待共享_accounts契约，不改domain/accounts/DDL。
- 独立复核与已核实Kimi-K3只读反例审查；不把实施前建议当最终实测。

验收必须涵盖实际服务创建→混合peer含坏消息→完整回执/checkpoint同commit→新Session/进程找回；同请求重放、冲突、并发CAS、同poll重复/冲突/blocked后授权、空poll；过期/伪造/禁用session角色、跨owner/workspace、case撤权/转案/归档/scope变更、账号/peer撤权；写入中与commit失败没有半批，查询恢复无重发；真实qxbak服务历史往返和恢复拒写。每项实际命令/退出码/数量保留。NOT_RUN：真实微信/合同/产品模型、下载发送、有限期许可、新安装包、全仓回归。原生崩溃与WIN-PATH-02继续开放。
