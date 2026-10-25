# D2g5a 按持久代际离线预览：实际证据

2026-10-25，基线 `074738034bdfb0f5231f003c9d12522793ee5928`。本片只有集中DTO与29行预览服务两个产品文件；复用D1协议解析和D2g持久历史/权限/事务。无schema、依赖、HTTP、UI或运行guard修改。账号收件/分发继续暂停，预览不是真实接通、持久收件或执行许可。

## 已实现与边界

|类别|本片核实内容|
|---|---|
|源码已实现|`preview_generation_response(actor, root_mapping_id, expected_head, raw_response, *, database)` 在一个BEGIN IMMEDIATE内核当前principal、根对象、完整历史、最新目标、完整scope和七字段head；返回固定synthetic/preview_only，零代取最后grant或mapping，非零只取最新generation。|
|源码已实现|输入head重新model_validate，防model_copy绕过；持久scope必须等于目标当前完整snapshot。owner/session、目标task cursor、账号opaque cursor均读当前数据库，调用原translate_response；不调用收件、任务、模型或网络。|
|已有测试证据|D2g1—4历史、head、页面与暂停guard证据保留；本轮只重跑下列实际相关集合，不累加历史总数。|
|本轮实际验证|14模块361个不同Python、15脚本233 Node、四开发门全部exit0；独立7个真实SQL竞争/权限/恢复/损坏/重开用例已包含在361内。真实qxbak恢复旧session401，重新登录仍409 BLOCKED_LIVE。|
|尚未实现|持久保存按代际收件/分发来源、运行解析和旧消息归属边界、可信微信身份/资格、下载/发送和E有限期模型授权。现有generation_integrity禁止代际后的poll/dispatch，本片保持该限制。|

入口在[`generation_preview.py`](../../../../src/cn_contract/weixin_inbox/generation_preview.py)，集中DTO `WeixinGenerationPreview` 在[`domain.py`](../../../../src/cn_contract/domain.py)。DTO只有mode/state/head/plan，要求head.scope与plan.scope.expected_scope一致；scope/CAS与当前权限仍由服务核验。冻结12个验证输入及完整命令见[verification-summary.json](verification-summary.json)。

这是**精确单peer的合成响应翻译**：混合peer整份拒绝；不证明远端认证、消息鲜度或持久去重，不把旧source/reply重新命名或改派，不确认上游游标。空响应可保留原opaque cursor，或仅提出下一个cursor假设，无task batch。文件只产生pending媒体元数据，密钥、CDN URL和context token被原codec丢弃。未来运行不能把preview当作绕过新权限/来源检查的令牌。

## 先失败与修正

- root初轮40 FAIL中，39个缺DTO/模块，1个fixture误把provision_user返回UUID当对象，后者不算有效功能RED；[原日志](root-red.log)、[JUnit](root-red.xml)。修正fixture并区分有/无游标空响应后，40项全部因缺DTO或模块失败，0 error，[有效RED](root-red-final.log)。实现后原40项全部通过，[首次GREEN](root-green.log)。
- 独立6项先因缺模块失败，[RED](independent-red.log)，随后6项通过；它们是最终独立7项的子集，不另加数量。
- 独立真实转案projection案件成员撤销时，预览正确403，业务不变，但原安全层追加1条authorization_denied。[原失败](independent-audit-red.log) 证实计划“所有失败均零审计”过度承诺。纠正计划/测试为：成功零业务/审计；拒绝零业务，保留既有安全拒绝审计。产品安全代码未改，最终精确核403及该审计字段/数量通过。
- 首次真实qxbak测试用恢复前session却期待恢复fence409，实际401；[原失败](root-restore.log)。源码 `workspace_backup.py` 本就撤销旧session，`assistant.service._current` 优先核身份。测试补显式重新登录，最终同时核旧session401、当前session409，产品未改，[通过](root-restore-final.log)。不降低guard或把第一次失败当成功。

## 最终根验证矩阵

|组|不同用例|退出码|实际证据|
|---|---:|---:|---|
|新DTO13＋主集成30＋独立atomic7|50|0|[日志](root-new.log)、[JUnit](root-new.xml)、[命令/散列](root-new.json)|
|原离线codec123＋当前权限预览12|135|0|[日志](root-protocol.log)、[JUnit](root-protocol.xml)、[命令/散列](root-protocol.json)|
|generation输入/服务/atomic/backup|100|0|[日志](root-generation-service.log)、[JUnit](root-generation-service.xml)、[命令/散列](root-generation-service.json)|
|head DTO/service/routes/atomic＋旧运行guards|76|0|[日志](root-head-guards.log)、[JUnit](root-head-guards.xml)、[命令/散列](root-head-guards.json)|
|现有15个assistant Node脚本|233|0|[TAP](node-all.log)、[命令/散列](node-all.json)|

Python的(classname,name)去重361、14模块，0失败/错误/跳过；独立7和先前GREEN/边界/恢复重跑不再累加。所有最终组、Node与四门12个输入SHA前后相同。新测试为[`unit`](../../../../tests/unit/test_weixin_generation_preview_view.py)、[`主集成`](../../../../tests/integration/test_weixin_generation_preview.py)、[`独立atomic`](../../../../tests/integration/test_weixin_generation_preview_atomic.py)。

覆盖零/一/二代、最后grant变化使旧head失效、完整scope三revision增长、当前角色/session/root/target归档与撤权、owner/workspace篡改、真实projection案件ACL、安全拒绝审计、两类当前cursor、空响应、坏JSON/重复键/混合peer/重复消息、旧source/reply和媒体秘密剔除；成功snapshot业务/审计无变化，拒绝业务无变化且仅保留既有安全审计。socket.connect/create_connection在成功预览中被替换为失败哨兵；没有provider调用。fixture本来包含历史TaskDraft/dispatch，不声称整库任务行数为0。

独立实际SQLite锁顺序验证：预览先锁得到完整旧快照，随后新代追加；追加先锁则旧head预览409。撤权先锁则预览STATE_CONFLICT，不返回raw候选；历史损坏VERSION_CONFLICT，重开Database后仍可做无写预览。真实ingress仍STATE_CONFLICT、旧dispatch/refresh暂停回归通过；没有解除运行guard。

## 范围计数对账与复核

本轮361 = 新50＋协议135＋服务100＋head/guard76，是当前选择的回归集合，**不是累计或全仓总数**。前两片JUnit集合已实际对账：[比较结果](test-scope-comparison.json)。D2g3的298与D2g4的229共有198例；D2g4未选旧服务100而选前端页面31，故298−100＋31=229；Node192＋新leaf41=233。只是读取旧证据作集合比较，没有把历史测试宣称为本轮重跑。

同一独立审查者分别完成Spec/Standards两轴，0确认遗留；[原始报告](independent-review.json)、[复核说明](review.md)。独立最终7/7 exit0，[日志](independent-final.log)、[JUnit](independent-final.xml)；产品两源及独立测试散列稳定。计划的审计措辞在复核期间纠正，报告单独说明文档变化，不声称全部输入都没变。root读取所有diff并复跑该7项、其余主验证和四门。本轮WorkBuddy NOT_RUN。

四开发检查exit0：[schema](schema.log)、[defaults](defaults.log)、[sources](sources.log)、[dependencies](dependencies.log)。13项来源仍NOT_PRODUCTION_APPROVED；55运行包＋1构建包，native_build_verified=false，network_calls=0。本片不新增浏览器/HTTP/UI路径，浏览器和安装版 **NOT_RUN**；不复述上轮浏览器通过为本轮结果。

全仓单进程、真实微信/模型/合同、付费、签发、自动外发、新安装包均 **NOT_RUN**。完整历史校验和写锁仍有开销，未作性能基准；真实qxbak通过不证明既有WIN-PATH-02或原生访问冲突修复，两项保持 **OPEN**。安装版0.4.1未更新；下一片先解决持久消息代际来源与完整性，再接实际合成接收/分发，真实服务继续关闭。
