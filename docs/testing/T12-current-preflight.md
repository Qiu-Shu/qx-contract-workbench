# T12 当前只读预检

PLANNING_ONLY / NOT_RUN，2026-10-03T08:47:39.490082+00:00。当前 T11 正在实施，本预检不并发 T12 业务。只有文本/AST/hash读取，71输入前后漂移0；实际 collector 退出0。备份、恢复、AEAD、key生成、OS/ACL/防火墙/TLS设置、部署更改、账户、测试、浏览器、Word、联网、原生库导入均0。

与旧 T12-preflight 的 T06时点相比，T07固定SDK本机模拟、T08持久账本、T09实际受限修订/制品、T10中文页面/任务已具备。根节点 T10 工程709项及四类普通浏览器结果是历史阶段证据，完整浏览器网络捕获仍NOT_RUN；此处未重跑也不将其作为T12恢复PASS。T11/84/gold仍待各自实际结果。

|范围|可复用现有入口|T12未满足条件|
|---|---|---|
|独立用户/密码/会话/对象鉴权|T02实际认证及T10后端cookie/CSRF接入，可复用；`src/cn_contract/security.py::login`, `src/cn_contract/security.py::authenticate`, `src/cn_contract/security.py::authorize`, `src/cn_contract/security.py::verify_csrf`|生产身份系统、批准host与HTTPS/TLS部署尚未实施；非T12实际执行证据|
|通用出站URL/地域/数据类型批准门|T07 fixed synthetic loopback精确endpoint/POST/redirect拒绝与T10 worker外发限制可复用；`src/cn_contract/providers/qcc_registry.py::allowed_synthetic_endpoint`, `src/cn_contract/providers/mcp_client.py::_GuardedTransport`, `src/cn_contract/web/jobs.py::run_next_job`|check_egress及生产DNS地址绑定/每跳核验、批准地域与数据策略NOT_IMPLEMENTED；.cn/HTTPS不能自证数据境内|
|工作进程CPU/内存/时长与OS无任意外网|T10单线程本机demo生命周期；T03未读对象/安全ZIP局部门；`src/cn_contract/web/demo_server.py::serve`|独立受限解析工作进程、ACL/AppContainer/WFP/资源限制未部署；线程和Python URL门不是OS沙箱|
|secret/sensitive Git候选与制品扫描|T07受保护secret引用/固定异常与T09 audience字节门；`src/cn_contract/providers/mcp_client.py::SecretStore`, `src/cn_contract/exports/storage.py::checked_bytes`|staged/发布范围/日志/metadata统一扫描、独立虚构canary与误报/人工复核协议NOT_IMPLEMENTED；不能扫描全机私人库|
|一致SQLite与文件快照维护屏障|T02 Database显式短事务/BEGIN IMMEDIATE、回滚原件清理与不可变存储；`src/cn_contract/persistence.py::Database`, `src/cn_contract/persistence.py::read_original`, `src/cn_contract/exports/storage.py::store_bytes`|SQLite backup调用、worker/写者维护屏障、WAL一致快照与DB引用文件manifest尚未实现；主db复制不能证明一致恢复|
|标准AEAD加密备份与key引用|正式依赖含cryptography；唯一BackupConfig/BackupReport DTO已定义；`src/cn_contract/domain.py::BackupConfig`, `src/cn_contract/domain.py::BackupReport`|backup_and_verify、批准key resolver、归档格式/随机nonce/认证manifest/私有暂存与key独立保管NOT_IMPLEMENTED；当前不生成key、不调用AEAD|
|新目录恢复与路径/大小/认证边界|T02安全原件读、T09生成文件reparse/hash门可复用为窄边界参考；`src/cn_contract/persistence.py::read_original`, `src/cn_contract/exports/storage.py::redirected`|恢复新UUID目录、归档大小/路径名单/大小写冲突/ADS/设备名/hardlink与TOCTOU控制均无实际恢复实现|
|恢复schema/trigger/FK/服务状态/hash对账|各阶段显式initialize_storage、不可变快照和当前读门可复用；`src/cn_contract/persistence.py::Database`, `src/cn_contract/authorities/storage.py::initialize_storage`, `src/cn_contract/rules/storage.py::initialize_storage`, `src/cn_contract/exports/storage.py::load_run`|恢复前原始SQLite schema/trigger SQL验证、全部行与文件对账、调用恢复后的实际服务尚未实现；create_all自动补表不能掩盖缺失|
|unknown预算/次数保持和worker不重发|T08 recover_inflight/read_budget，T10 running job转blocked；已有重启工程证据；`src/cn_contract/queries/ledger.py::read_budget`, `src/cn_contract/queries/ledger.py::recover_inflight`, `src/cn_contract/web/jobs.py::recover_jobs`, `src/cn_contract/web/jobs.py::claim_next_job`|合法旧backup发送高水位、外部可信恢复checkpoint/fence、恢复queued隔离和新DB账本核验未实现；现claim_next_job可领取queued不能冒充恢复禁发|
|恢复会话/批准安全启动delta|实际Session.revoked、revoke_session/current授权及T09制品读取可复用；`src/cn_contract/security.py::revoke_session`, `src/cn_contract/persistence.py::read_approval`, `src/cn_contract/exports/storage.py::checked_bytes`|restore后全部会话撤销、当前ops批准独立于archive、旧正式批准隔离与历史不覆盖尚无实际服务|
|删除、保留及备份到期策略|BackupConfig.retention_days只是类型字段；原件/审计不可变可复用；`src/cn_contract/domain.py::BackupConfig`|律所数据政策与供应商许可、原件/派生/索引/缓存/备份删除联动未实施；不预设法定天数|
|真实发布证据manifest与生产门|source/runtime独立development/release门和ReadinessDecision DTO已存在；`scripts/verify_sources.py::verify_manifest`, `scripts/verify_runtime_dependencies.py::verify_manifest`, `src/cn_contract/domain.py::ReleaseManifest`, `src/cn_contract/domain.py::ReadinessDecision`|build_release_manifest、实际部署/恢复/84/gold/规则批准集成未实现；现source9/runtime59非0仍阻断，不填approved_by或漂亮JSON造GO|
|单机单实例/回滚/关闭外查运维|T10本机demo显式单worker启动关闭和QCC-off workflow实际完成；`src/cn_contract/web/demo_server.py::build_demo`, `src/cn_contract/web/demo_server.py::serve`|SECURITY_RUNBOOK/OPERATIONS_RUNBOOK、批准生产配置、HTTPS/国内host、真实回滚和恢复演练尚未执行|

三个公开目标接口check_egress/backup_and_verify/build_release_manifest在实际应用/scripts AST中均不存在，只有领域DTO/计划。表中的函数为未来窄复用候选，不证明T12能力。现有claim_next_job可领queued、recover_jobs只隔离running；真实恢复必须先保持provider off并隔离恢复队列，不能自动使用demo启动路径后声称零重放。

正式cryptography锁定50.0.2，生产批准仍null。本轮未import其原生模块、实例化AEAD、生成/解封key或读账户引用。应沿旧计划使用标准认证加密和批准key resolver，而实际安全归档/私有暂存/独立key保管仍未实现。SQLite一致快照只保证数据库，需维护屏障与DB引用文件清单共同固定截点；文件存在/可解密不足以恢复验收。

合法旧备份的AEAD认证不能证明最新发送/撤销状态：T08unknown持有量与账单高水位、当前恢复批准和外发fence必须独立于archive核验。新Database恢复后需实际服务重算余额、拒绝超额、核全部原件/制品及旧批失效、0发送，原库不覆盖。恢复Session必须撤销并重新授权，历史批准/审计不改写。

T10历史source发布9/runtime发布59阻断分别保留；本轮未重新执行发布门或改变审批。真实地域/HTTPS/host、OS资源和无任意外网、数据保留政策、规则/法律gold/账户及许可均不能由DTO字符串、URL标签或hash相等替代批准。未来发布manifest应绑定实际证据而生产mode缺门非0；开发制品明确虚构/mock限制。

本轮未创建.env、deployment配置、账户或keys；未运行备份/恢复或T12测试。未来应新增虚构canary与新受控目录恢复测试、记录真正argv/UTC/exit/count/hash并独立审阅。当前路径存在性和入口列表详见忽略目录current-preflight.json，所有13个建议条目NOT_RUN。首次自有collector误写runtime门函数名，实际exit1的读取断言诊断及原helper保留在collector-first-diagnostic.json/prepare-first.py；按实际AST符号verify_manifest修正后exit0，未执行生产门，非功能RED。
