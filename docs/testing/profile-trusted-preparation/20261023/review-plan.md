# CH-07C2b2a 可信数据库装配：独立计划复核

基线：2997d4602d842c6cab8e514a4c7340085910ad0c。
定位：数据库一致性读取，把C2a纯离线basis/prepare与当前受权数据库记录连接；不是模型执行资格检查，不授予许可、不登记attempt、不保存档案。registry/native/runner/HTTP及model_integrity中ASSISTANT_PROFILE_MODEL_NOT_ENABLED保持原样。本报告只读源码/规格；未跑测试、未操作真实资料或桌面；仅写本报告。

## 结论与最小接口

方案可行，没有因下述定位而产生的授权绕过。模块名assistant/profile_preparation_service.py清楚区分了providers/profile_preparation.py的纯函数，无须另建框架或DTO。

建议仅两个对外函数，使用caller-owned db；名称可按仓库风格调整：

- build_basis(actor, conversation_id, submission: AssistantMessageInput, config: MainModelConfig, db, *, project_intake=False) -> MainProfileSendBasis
- prepare_saved(actor, run_id, basis: MainProfileSendBasis, config: MainModelConfig, db) -> MainProfilePreparedInput

内部可共享一个读取当前conversation/profile/intake目标的私有函数；不需要新的Context/Permission/Run包装类型。新装配器不调用initialize_storage、save_message、save_profile、registry或任何provider；调用者分别管理事务和后续动作。返回值只证明读取时的数据库一致性，不能作为稍后直接发送/保存的令牌。

沿统筹最新选择：prepare_saved可读取未取消的queued或generating；不要求selected_provider为空或attempt不存在。这是可供登记及后续核验复用的读取，不代表可以claim、再次调用或获得预算。与此相应，不在本片新增执行资格策略。

## 预览装配的顺序

1. 深度重新验证输入DTO；actor身份与角色用数据库当前principal核验，不能信任actor.roles的旧快照。
2. service._owned(actor,cid,db)取得当前所有者、工作区、scope及投影接待权限；require_active(db)拒绝恢复隔离；service._expected拒绝归档、旧scope、旧composer。
3. submission.content与当前draft_input逐字相等且非空；requested_skill为空、提交attachment_ids为空；records.items(conversation,db)也必须为空。已上传但未选择附件无需全部拒绝；有选择但无法解析仍属于选择，必须拒绝。损坏/缺失当前材料快照不得视为空。
4. profile_store._profile(cid,db)取得最新可信档案或无档案的0基线。除该helper已有cid/workspace/revision/hash检查，还应核对已有profile的固定scope字段(workspace/conversation/scope_kind/scope_ref/binding_revision)与当前一致，且旧input/material revision不大于当前；对应profiles.merge_profile:119-124，避免提前准备注定不能保存的提案。
5. 接待目标与profile_store._commit:122保持同一选择规则：intake scope使用scope_ref，其他scope使用projection_intake_id。通过intake.read读取最新目标及修订，拒绝不存在/无权/已转案目标；即使project_intake=False也绑定目标和修订，因为现有提交仍保护人工接待内容。无目标时id与revision都为None，不预建空接待。
6. 调用已有纯build_basis，传实际读出的profile revision、接待目标/修订及可信caller明确的project_intake。project_intake默认False；模型不能决定此开关。config参数代表caller提供的配置快照，不伪称已核对运行registry。

## 已保存消息装配的顺序

1. 深度验证basis/config，按run_id读取service._owned_run和实际conversation；再次require_active、拒绝归档，继续核对当前scope、选择附件、profile与intake目标。
2. 显式要求run.actor_id及run.session_id分别等于当前actor；_owned_run本身只保证当前conversation可访问，并不保证这两项。run.request_id必须等于basis.request_id，未取消且状态属于queued/generating；其他状态拒绝。
3. 用run.message_id和run.conversation_id共同限制查询实际消息。要求角色user、消息id一致、消息source_revision等于run.scope.input_revision。不能接收调用者传入的伪造run/message视图；不能用会话最新消息替代绑定消息。
4. run.scope与当前conversation快照完全相同，并与basis.expected_scope只差input_revision+1。composer允许当前值大于或等于basis.expected_composer_revision+1；新增打字本身不改变已保存原话，不读取当前draft_input替换它。
5. 由实际原消息内容、basis.request_id、basis.expected_scope、basis.expected_composer_revision及空skill/附件重建原AssistantMessageInput；使用service.save_message相同的_digest字典（actor_id、实际workspace_id、实际conversation_id、request.model_dump(mode=json)），核对run.request_sha256。此步骤补足纯prepare所无的数据库来源绑定，不能只核对content SHA。
6. 从同一事务内重新读取的profile/intake状态重建完整basis，并要求与传入basis逐字段相等；配置、模板、wire、用途和保存计划均保持原值。不替换最新版本重试。project_intake只按原basis描述核验，不把其自洽解释为已经获得授权。
7. 复用service.get_run/实际AssistantMessageView进入纯prepare，固定composer_revision取已经过原request摘要证明的basis.expected_composer_revision+1。不要把当前更高composer传入纯prepare，也不要放宽C2a DTO的精确+1契约。

## 必须拒绝或明确保留的情况

- 会话失效、用户被停用/失去律师角色、跨所有者/工作区、matter权限被撤；projection intake转案后即使conversation scope没变，也按当前权限拒绝。
- 恢复副本、归档会话、binding/input/material版本变化；scope不变但原basis所指profile或intake版本变化同样拒绝。
- 另一有效session尝试装配旧session的run；run/request/message交叉关联、原文/角色/source_revision/request摘要改变。
- 错误用途/模板/handler、非空点选技能/提交附件/当前选择附件、非成对接待版本、损坏profile摘要或当前材料快照；错误不输出原文、联系方式或配置秘密。
- 保留既有ServiceError语义；DTO/存储解码错误归一为有界失败，不能吞错并返回空来源。_owned含flush，既有授权拒绝可能记审计，因此只承诺本模块不主动业务写入，不声称所有拒绝零审计。
- 准备过程中无await、外部文件读取或网络；正常使用现有BEGIN IMMEDIATE事务语义。若调用方在其后释放事务，再claim/settle必须重新核验，不能把本次结果长期缓存当授权。

## 目标验收建议

1. 真实合成DB正常链：保存草稿→build_basis→既有save_message→prepare_saved，结果与纯prepare/C1 wire逐字节一致；全部业务表准备前后不变，provider调用0。
2. 无profile/无intake、已有profile、intake scope及projection intake四种目标；project_intake=False仍绑定现有目标，True不创建接待。
3. 当前draft变化仅在预览阶段拒绝旧submission；保存后composer-only上升并新打字仍可读取原run，原wire不变；随后input/material/binding变化全部拒绝。
4. 同用户不同session、过期/revoked session、角色/权限撤回、跨conversation/message、归档和恢复fence，覆盖当前拒绝；保留可能的拒绝审计。
5. 旧profile基线增加、profile绑定不符/未来版本/摘要损坏、接待人工修订、接待已转案/目标更换，都拒绝旧basis，不暗中刷新。
6. 篡改run.request_sha256及其actor/session/request_id/message_id、user role/source_revision/content；同content但不同原scope/composer也不能通过。
7. queued/generating未取消正例；cancel_requested或其他终态拒绝。已有主模型元数据不因此被本读取器认定为执行许可。
8. 先有上传附件但当前选择为空可通过；选择非空、选择快照缺失/损坏拒绝；无任何附件正文读取或外发。
9. 准备反复读取不新增message/run/event/attempt/output/profile/intake/handler；现有profile-text新记录完整性封闭guard及registry/native拒绝测试继续通过。
10. caller rollback/异常后模块未擅自commit；成功读取与下一步写入可共用同一db，不通过另开session绕开事务。

## 主要源码依据

- assistant/providers/profile_preparation.py:25、42：纯basis/prepare已有严格类型与配置/模板核验。
- domain.py:4068、4098：保存意图与保存前后版本/完整wire约束。
- assistant/service.py:20、61、80、225、277：当前身份/权限、版本、真实原提交摘要及_owned_run限制。
- assistant/attachment_records.py:40：当前选择快照；不等于上传清单。
- assistant/profile_store.py:45、112：档案摘要、接待目标/修订及原子提交已有规则。
- assistant/profiles.py:119：历史profile固定scope及版本上界。
- intake/service.py:55、ops/storage.py:45：接待当前记录及恢复fence。

以上为实现契约建议，不宣称装配器已实现或验证通过；等待实际源码冻结后独立复核。未重开需求访谈、未重复既有协议和完整套件。
