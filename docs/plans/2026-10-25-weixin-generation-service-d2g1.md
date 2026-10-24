# D2g1：显式代际追加与固定查询服务

基线37654fa，实际目录 `D:/Documents/ChatGPT/律所项目`，沿当前分支无人值守实施、正常推送，AGENTS用户改动保持。沿用ponytail/TDD/独立复核和上轮存储设计，不重复访谈；本合同是本轮技术裁决，不扩展真实账号或模型授权。

目标：把D2f的直接SQL合成记录提升为当前桌面身份下的事务服务，明确授权新目标、完整CAS、持久固定记录与未知结果查询。本片不解释新代际为可执行收件授权，账号级暂停保持；不增加schema、HTTP、页面、传输、机器人、下载/发送或产品模型。

## 方案与接口

直接放宽暂停会使旧accepted/TaskDraft指向错误目标，故本片只追加不可变记录。复用schema17、_transaction的BEGIN IMMEDIATE、实际principal/owner/workspace/对象权限、因果时间、DTO/hash和完整历史validator，不另建队列、许可表或依赖。下一片再接运行时分代及明确页面操作。

集中 `WeixinPeerGenerationInput` 八字段：request_id；expected_generation严格非负整数；expected_previous_generation_sha256（仅expected_generation=0时None）；expected_previous_scope_sha256；expected_checkpoint_revision严格非负整数；task_binding_id；expected_scope完整ScopeSnapshot；reason复用已有有界校验。额外actor/account/workspace权限字段拒绝，model_copy输入重新校验。

`weixin_inbox/generations.py`：

- `append_synthetic_generation(actor, root_mapping_id, request, *, database) -> WeixinPeerGeneration`。
- `find_peer_generation(actor, root_mapping_id, request_id, *, database) -> WeixinPeerGeneration | None`。

两入口均先在数据库重建实际principal/root账号归属和当前workspace，精确验证schema17，读取完整规范代际并检查历史损坏，失败使用VERSION_CONFLICT/409，不自动修复或升级，不暴露来源正文。没有代际时public validator本身早返，故首条INSERT后完整post-validator仍必须成功才能提交。

## 追加事务

1. 重新校验输入；独立BEGIN IMMEDIATE中重建principal，require_active。账号用active=False读取以允许追加后代，但明确拒绝账号/root逻辑撤权，不能借此恢复收件。
2. 原root对话、前一代目标（如有）和新目标均用_owned/_active_targets核当前对象权限、owner/workspace及案件/接待转案状态，POST不允许会话归档。原root材料版本可变化，不把原授权scope改成当前scope。
3. 新target task binding必须已存在、synthetic且CID精确对应expected_scope，完整expected_scope必须等于当前_snapshot。不能root或任何前代CID，不能占用任何原mapping/任何generation的binding。调用者不能创建目标或替换owner。
4. expected_generation/previous_generation_hash/previous_scope_hash/account checkpoint精确CAS。零代际prevscope取D2d有效scope；否则取前代scope/hash。checkpoint使poll先提交时旧请求409；追加先提交时后续poll仍被既有暂停拒绝。
5. _activity_time(after=True)的floor包括新target binding/对话及所选user source_revision/material snapshot时间，回拨时仍在全部账号活动及目标来源之后。只INSERT一个规范完整generation，checkpoint保存当前账号值；不改任何旧payload/grant/游标/任务，不调模型/worker。
6. INSERT后复验完整历史再commit。所有可能触发_owned/authorize拒绝审计的权限检查必须在INSERT前结束；post校验不能再次调用会独立rollback/commit的ACL拒绝路径。

已有同root/request时，按固定记录的generation-1/prev hashes/checkpoint/目标binding/完整scope/reason还原八字段，完整输入相同且当前principal/active/对象权限/固定目标当前snapshot仍准确才返原记录。不能用当前latest代际CAS否定已提交旧request，也不能把该记录自己的binding当新占用。不同输入409；不新增记录。未知结果只查询，不自动重发。

## 查询语义

find不调用require_active，不要求历史scope仍等于当前snapshot，恢复副本、逻辑撤权及会话归档后可查询固定metadata。实际root及所查记录目标当前owner/workspace、对象ACL和_active_targets仍必须成立，案件归档或成员撤销不因旧记录获得访问。记录不存在时在root当前权限下返回None。成功查询不新增业务记录、游标、任务或审计；与现有D2e一致，拒绝路径可沿既有权限机制独立保存审计，不声明拒绝绝对零写入。

## 验收步骤与文件

- [x] domain.py八字段DTO、generations.py两入口，先RED再最小实现；缺接口与行为边界失败分类保留，作者最终84通过。
- [x] 独立atomic模块验证SQL/commit前回滚、commit后丢ACK只find、新Database/进程、同CAS竞争、poll竞争；结果与完整旧表字节/计数核对。
- [x] 独立backup模块用真实服务生成两代再qxbak往返，find可读且追加BLOCKED_LIVE；旧历史精确保留，恢复无自动执行。独立最终16通过。
- [x] 根代理12模块310不同Python、192 Node和四开发门通过，独立冻结复核完成；只累计最终不同case，所有中间失败分类保留，[实测](../testing/weixin-generation-service/20261025/README.md)。
- [ ] 更新README/TODO/TASK_STATUS和实际证据，扫描仅授权源码/文档/独立合成数据，fetch后正常commit/push并核远端SHA/树；本轮三端记忆按AGENTS收尾。

审查重点：旧request重放与latest CAS分离；跨对象ACL和归档/转案；首条及后代完整历史校验；INSERT后独立审计提交风险；目标真实来源/回拨时间；恢复find只读且业务guard不解除。仅domain.py与新generations.py为产品修改，测试辅助文件独立。全仓、安装版、真实微信/模型/合同/付费/签发/外发NOT_RUN；0.4.1、原生长进程崩溃和WIN-PATH-02保持开放。本片不重试漂绿上轮浏览器WinError5，不称其已修。
