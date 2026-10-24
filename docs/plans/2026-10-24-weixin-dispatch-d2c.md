# D2c：合成收件至共享 TaskInbox 的受控分发

基线0bea6a2；沿当前分支保留AGENTS脏改。用户已授权无人值守实现、合成验证及正常推送。继续ponyTail最小充分改动/先失败测试/独立复核；不增加依赖、transport、HTTP/IPC/UI，不连接真实微信、模型或发送。

## 新回执与schema

追加第15版 `weixin-dispatch-v1`，旧14版native/non-native原始/规范指纹全部保留。`weixin_inbox/dispatch_schema.py` 一张不可变表 `weixin_dispatch_receipts`：

`id TEXT PRIMARY KEY NOT NULL; descriptor_id TEXT NOT NULL UNIQUE REFERENCES weixin_inbox_descriptors(id); account_id TEXT NOT NULL REFERENCES weixin_accounts(id); mapping_id TEXT NOT NULL REFERENCES weixin_peer_bindings(id); actor_id TEXT NOT NULL REFERENCES users(id); task_binding_id TEXT NOT NULL REFERENCES task_channel_bindings(id); task_event_id TEXT NOT NULL UNIQUE REFERENCES task_inbox_events(id); source_event_id TEXT NOT NULL; payload_sha256 TEXT NOT NULL; expected_task_cursor INTEGER NOT NULL (exact int>=0); next_task_cursor INTEGER NOT NULL (exact int=expected+1); created_at TEXT NOT NULL; receipt_sha256 TEXT NOT NULL`，UPDATE/DELETE一律拒绝。事件、映射、回执不可覆盖。

唯一新DTO在domain.py末尾 `WeixinDispatchReceipt`，字段同表（UUID/UTC/严格cursor/SHA/canonical wx1 namespace），receipt_sha256=SHA256(canonical_json(model_dump(mode='json',exclude={'receipt_sha256'})))。不包含动态task_id/draft state；这是固定接收回执，不保证自动完成草稿关联。

storage/bootstrap/migrations/native升级/两种备份同片闭合。旧6类完整性gate及weixin_inbox/integrity的硬编码版本必须接续，不能静默跳过旧history；旧weixin-inbox-v1 DDL不改。ops backup新增validator hook、两处fence添加weixin_dispatch_enabled=false。

## 运行服务

`weixin_inbox/dispatch.py`：`dispatch_synthetic_descriptor(actor,descriptor_id,*,database)->WeixinDispatchReceipt`；`find_dispatch_receipt(actor,descriptor_id,*,database)->receipt|None`。调用accounts._transaction持有独立BEGIN IMMEDIATE直到commit；实际principal/账号owner/workspace与current mapping全scope/ACL/撤权/归档先核对，写入口fence先核对，读在恢复可只读但仍检查当前权限。输入仅descriptor UUID，所有account/mapping/binding/payload从已持久descriptor重建，不接受调用方目标或内容。

只有accepted_pending_dispatch且带精确mapping的原始descriptor可分发，blocked/duplicate拒绝，未知/跨owner拒绝。同mapping必须按poll.next_revision、ordinal顺序分发accepted前缀；存在更早尚无receipt的accepted时VERSION_CONFLICT，不影响其他peer。已有receipt在current guard后回读固定结果，不调用receive_batch或推进cursor。find查询无业务写。与已存task inbox事件同source但无dispatch receipt视为冲突，不能伪造/收养桌面事件为微信分发；匹配receipt时重核持久关联hash。

取该mapping唯一synthetic task_binding当前整数cursor，用TaskInboxBatchInput(expected=cursor,next=cursor+1,events=(原canonical payload,))调用既有task_drafts.service.receive_batch，随后插入dispatch receipt。二者同事务commit后返回，任何异常不捕获为继续处理，全部业务rollback；旧授权拒绝可能单独提交拒绝审计，不得称绝对零DB写，但不得有半个task事件/草稿/cursor/dispatch receipt。服务不批量捕获permission错误，也不调用freeze/bridge/model。pending DOCX/PDF仍无原件/解析，不能冻结。

保留现有聚合：两种指令/附件顺序进入同草稿；歧义/容量满则event durable待分配；已知回复在同binding内关联，未知引用待分配；冻结后有效引用为补充草稿；纯文字的暂停/取消/继续沿既有受权消息语义，文件内容不被解释。固定receipt只证明收到，不承诺所有事件都已有task_id或已完成审查。

实测后的时钟裁定：固定UTC时钟反例证明分发/撤权同刻度会误拒合法归档。accounts新增_activity_time，在同事务内只聚合本账号时间元数据；撤权时间严格晚于已提交活动（必要时+1µs），绑定/poll/dispatch遵守已提交UTC下界，权限撤销本身立即生效。TaskInbox既有wall时间不改；历史校验要求receipt不早于poll/mapping/event，不额外要求event>=poll，因跨peer逻辑floor可稍晚于旧TaskInbox时钟。当前鉴权、来源碰撞拒绝、receipt hash及当时撤权的严格检查全部保留；时间不是远端认证或精确外部时钟证明。

## 历史校验

`weixin_inbox/dispatch_integrity.py:validate_dispatch_records(db,*,allow_dispatch=False)->[]`。已知旧schema缺表接受，未知schema失败；非空仅full qxbak，局部拒绝。逐条DTO/receipt hash、canonical UUID、source wx1、账号owner=actor、mapping/account/peer/task_binding/conversation/workspace、descriptor属于该poll/account且accepted、source与payload hash精确匹配TaskInbox不可变原event、receipt创建时间>=poll/mapping/task_event时间、且未在当时账号或mapping撤权后分发；task cursor current>=next，expected/next在同binding按时间不重叠，允许桌面批次造成gap。accepted分发在各mapping的原收件顺序必须为前缀。不能要求恢复时current ACL/scope仍有效，不能固定动态草稿关联。旧task/base weixin validator继续负责其历史本体。

## 分工/验收

- Storage代理：dispatch_schema、catalog/bootstrap/migrations/所有旧gate/backup hook/fence及new schema tests、必要旧测试fixture successor适配；不改旧冻结摘要。函数hook名固定如上。
- Integrity代理：dispatch_integrity及独立合成/实际服务来源完整性篡改tests；不改domain/schema/runtime。
- Root：DTO、dispatch.py与先失败服务测试、真实qxbak/故障/并发/未知回执、新进程恢复、四门、独立审阅/状态/推送/三端收尾。

RED/GREEN命令/退出码/数量留.local/weixin-dispatch-20261024，不把setup错误或中途通过累计成最终通过。schema需全前驱升级/原子rollback/native marker/unknown拒绝；旧任务、模型、base weixin损坏在后继版仍拒绝。运行验收用public D2b建账号/poll、实际dispatcher→共享TaskDraft与UI已有读取服务；两个顺序、待分配、引用/暂停、current权限、撤权、幂等、顺序、碰撞和恢复写拒绝；SQL及commit故障无半批、commit后丢ACK可find、新进程/并发/真实qxbak。真实微信/合同/模型、下载发送、E有限期许可、安装包及全仓/Node/浏览器NOT_RUN；原生崩溃和WIN-PATH-02开放。
