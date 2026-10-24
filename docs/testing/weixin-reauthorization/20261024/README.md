# D2d 同目标显式重新授权实测（2026-10-24）

基线5142eaa，按[实施合同](../../../plans/2026-10-24-weixin-reauthorization-d2d.md)完成本机合成服务。原mapping、poll、descriptor与dispatch回执不改；新增授权不是微信远端身份认证，也不自动执行合同审查。

## 源码实现

新增第16版 `weixin-reauthorization-v1`，一张12字段不可变 `weixin_peer_scope_grants` 表，集中DTO为 `WeixinPeerRefreshInput` 和 `WeixinPeerScopeGrant`。授权链固定request、actor、revision、前scope哈希、新完整scope、账号checkpoint、理由、UTC与整条摘要；唯一mapping/revision及mapping/request，更新和删除均拒绝。

`accounts.refresh_synthetic_peer` 在BEGIN IMMEDIATE内复核实际principal、owner/workspace、首次撤权、restore fence、精确当前_snapshot、当前ACL/案件与会话归档；CAS前grant revision+scope hash后追加，commit后才返回。只允许原目标workspace/conversation/kind/ref/binding_revision不变的input/material版本单调刷新，至少一项增长；转案/重绑/跨目标继续409，不能用refresh复活撤销映射。同request同固定内容回读原grant，冲突不追加；`find_peer_scope_grant`支持未知结果查询和恢复副本读取，但仍需当前有效scope与权限。无授权时旧scope过期的查询先报VERSION_CONFLICT，未冒充案件权限已通过。

当前mapping guard及ingress预览使用有效授权；新grant只改变当前同目标投递许可。旧accepted原样可继续分发，旧blocked仍为previously_blocked。TaskInboxEventInput没有expected_scope字段；scope是本地预览及权限检查参数，原payload不是授权凭证。上传、解析、关联及事实确认仍沿旧受控材料能力和人工步骤，不因refresh自动冻结/调用模型。

grant UTC严格晚于本账号全部已提交活动，后续bind/poll/dispatch/revoke纳入grant→mapping→account的时间下界，UTC先解析再比较。历史校验独立验证规范UUID/JSON/DTO/hash、owner/actor、连续revision/前scope哈希、同目标、版本增长、严格时间/撤权及poll checkpoint分界，再按poll/dispatch时间选择当时授权，不能借用未来grant。允许旧pending在后续同目标授权后投递，不增加旧TaskInbox墙钟限制。历史链不重建所有当时ACL事实，也不提供远端认证。

bootstrap/catalog/migrations/native升级、六类旧assistant/task gate及base微信/dispatch完整性gate均接续。旧15版native/non-native共30组结构指纹不改；新grant非空只允许full native qxbak，两处fence增加weixin_reauthorization_enabled=false。

## 本轮实际验证

原始JUnit、门检查和独立notes在本机 `.local/weixin-reauthorization-20261024/`，不上传临时库/完整日志。`verification-summary.json`绑定18份最终产品源码与8份XML。独立按classname/name核得**26模块、925个不同Python用例最终通过**，重复/失败/错误/跳过均0；是分组回归，非单次全仓测试。

| 实际目标 | 最终XML | 结果 |
| --- | --- | --- |
| `tests/unit/test_weixin_reauthorization_dto.py tests/unit/test_weixin_causal_time.py tests/integration/test_weixin_reauthorization.py tests/integration/test_weixin_reauthorization_atomic.py` | `runtime-clock-final.xml` | exit0，70 passed，36.51s |
| `test_weixin_accounts.py test_weixin_inbox_ingress.py test_weixin_ingress_atomic.py test_weixin_dispatch.py test_weixin_dispatch_atomic.py`（integration） | `related-weixin-clock-final.xml` | exit0，108 passed，1 warning，102.27s |
| `tests/unit/test_domain.py tests/integration/test_task_drafts.py tests/integration/test_task_draft_routes.py` | `related-tasks.xml` | exit0，155 passed，55.55s |
| `tests/integration/test_weixin_reauthorization_schema.py` | `storage-schema-green.xml` | exit0，98 passed，49.08s |
| `test_weixin_dispatch_schema.py test_weixin_inbox_schema.py`（integration） | `storage-successors.xml` | exit0，175 passed，128.26s |
| 附件/模型wire/judge/法库/profile/任务来源损坏目标，精确命令见本机storage-notes | `storage-gates-one.xml` | exit0，41 passed，87.93s |
| `test_workspace_upgrade.py test_storage_schema_versions.py`（integration） | `storage-workspace.xml` | exit0，68 passed，101.87s |
| `test_weixin_reauthorization_integrity.py test_weixin_inbox_integrity.py test_weixin_dispatch_integrity.py`（integration） | `integrity-regression.xml` | exit0，210 passed，88.01s（已含66个新grant校验，不另加） |

root命令统一 `.venv/Scripts/python.exe -B -X utf8 -m pytest <目标> -q --tb=short --junitxml=.local/weixin-reauthorization-20261024/<回执>`。storage/integrity代理的实际Python前缀、basetemp和目标节点以本机 `storage-notes.md`、`integrity-notes.md`为准；它们的原始XML、日志及退出回执已保留。108组的1 warning来自既有有意forged model_copy序列化输入，未称warning0。

四开发门在最终时间修复后均exit0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`，前缀同root命令。13来源仍NOT_PRODUCTION_APPROVED；依赖55 runtime+1 build、native_build_verified=false、network_calls=0。4份gate文本和JSON记录精确命令/退出码。

实际public合成服务覆盖输入/材料分别增长、CAS/request冲突/原mapping逐行不变、旧pending接续/blocked不复活、真实case成员撤除/案件归档/转换intake及projection所有权拒绝、session/role/撤权/fence。SQL grant INSERT与commit前故障全回滚；实际commit后丢ACK可find；双Session同request只追加一次、不同request前序CAS只有一个胜出；新Python进程可回读。

实际独立合成DOCX先经受控本地上传/解析使旧mapping失效，显式refresh后旧pending才能投递，经人工关联后保持collecting且无blocker，task executions/assistant runs/review runs均0。两代真实qxbak逐行保留7张来源/任务表，恢复可find但refresh（含同请求重放）阻断；备份样例上述3类执行表也均0，源全部文件字节不变。两类认证加密有效但grant内部损坏的归档拒绝恢复发布；不把所有历史ACL事实视为可由备份重建。

## 失败与独立复核

有效RED：缺DTO22 failed、缺服务1 failed、新schema缺失1 failed、旧model gate漏后继版1 failed；grant缺module31 failed，补schema后规则33 failed/33 passed；入口先查mapping再验principal反例1 failed→GREEN；UTC格式排序4 failed/4 passed→8 GREEN。grant夹具曾错误跳升checkpoint（31 passed/35 errors及单项setup error），不算产品RED。atomic首轮9 passed/2 failed是测试误写ready状态及旧表名，改为现有collecting/ops_restore_fences后11过；扩展权限测试首轮54 passed/4 failed是误判stale查询分类优先级，补“有/无已生效grant”两组断言后纳入最终70项。中间通过数不累计。

独立Codex reviewer发现 `_activity_time` 的SQL MAX字符串比较遗漏合法空格分隔UTC表示；root先RED后改为取本账号全部非空活动时间、逐个解析UTC后max。原独立探针和8用例复验通过，最终旧微信108与新运行70随后重跑。reviewer复核最终18源码/8XML SHA，重算925身份/26模块，确认无剩余可证实缺陷；未重复运行四门或全仓。

WorkBuddy任务 `wb-bg-ec1e40bf7055` 经桥接核实actual `kimi-k3-2`，完成实施中的只读设计复核、未跑测试。其当前scope精确核验/账号级grant JOIN/UTC比较建议已核对实现并明确进计划；“旧payload内嵌expected_scope”推断经DTO和_event源码核对不成立，未盲采纳。后续实际源码复核 `wb-bg-8ac4056489fc` 约600秒后failed、无完整答复，未计为通过；已读取桥接历史并仅释放本任务worker，不重发prompt。最终冻结代码与文档由独立Codex reviewer复核，静态建议不称实测。

| 最终关键源码 | SHA256 |
| --- | --- |
| `domain.py` | `18d2982039a1778381dc56335f6141b42b9eb469999c5e0b73b5a4cd52895da9` |
| `weixin_inbox/accounts.py` | `83bb64085c127783ac55a69f77ad25b308fb9b497fa60793585d3628b0476224` |
| `weixin_inbox/ingress.py` | `b94faa85fdf9145d8d86a60272543176efc597ac5cc41776410160bbcf116f06` |
| `weixin_inbox/grant_integrity.py` | `0c816b70a141d6bc0a5ced95bb127c07f187347706ffdddeaf64d757cc5d5a83` |
| `weixin_inbox/grant_schema.py` | `1dde13e8a4fa60846f28353329a48952a010df25109d3aab2d10b8d2217142a5` |

## 尚未实现与NOT_RUN

跨目标/转案/binding revision变化的显式generation与可信transport入口仍需设计，当前不放宽。运行scope refresh没有新增UI/HTTP/IPC入口。真实官方微信资格/账号认证/轮询、机器人、下载解密、发送/Outbox、真实合同外发、产品真实模型/付费、E有限期模型许可、新安装包、全仓/Node/浏览器均未实施或NOT_RUN。安装版0.4.1、既有原生长进程崩溃与WIN-PATH-02开放；运行SQLite未加密，qxbak加密不等于运行库加密。
