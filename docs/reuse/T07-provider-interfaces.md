# T07 受控供应商接口与 T08 交接

2026-10-03。只有本机独立虚构开发范围；未取得 QCC 官方 schema、真实账户、许可、单价、地域/数据政策或生产批准。真实 endpoint、stdio、sse 均 `BLOCKED_LIVE`，不发送、不启动进程。T08 之前不存在可用的真实查询派发路径。没有 G05 CLI 双通道。

## 规格接口与后台可信引用

业务 DTO 继续全部使用 domain.py，没有新增/修改 DTO、schema 或 defaults。`qcc_registry.initialize_storage(Database)` 是启动时显式初始化；没有 global DB、业务隐藏 commit。服务加入调用者事务，技术 records 为 SQL trigger 保护的追加历史。

`discover_tools(config: ProviderConfig, *, actor, matter_id, db, secrets=None)` 返回实际 `ToolCatalog`。ProviderConfig 必须与当前数据库已登记的 endpoint 精确相等；查不到即零发送阻断。也接受后台不可变 endpoint ref，避免后阶段从客户端配置构造 endpoint。`register_endpoint` 只登记固定 mock；独立 `provision_synthetic_endpoint` 是不暴露于 HTTP 的可信本机测试初始化函数，只登记数字 `127.0.0.1:port/mcp`。SDK 传输另核完整 URL、只允许 POST，禁止重定向及代理环境。localhost、其他路径、userinfo、query、fragment 都拒绝。合成本机 SDK 使用 JSON response、stateless StreamableHTTP；不声称一般 SSE/生产 MCP 兼容。

`bind_capability(input: BindingInput, actor, *, db)` 按规格返回 disabled 的 `ToolBinding`，同时保存 immutable 技术 row。`binding_reference(pending, *, actor, db)` 返回其技术 ref；`bind_capability_record` 是需要 ref 的内部便捷入口。`approve_binding(ref, *, actor, db)` 另做实际服务端审批；客户端 approver/time 必须为空，schema、完整 input/output hash、provider、endpoint ref、当前价格/单位/快照 ID 必须逐一匹配。没有把自报字段当批准。

`QccTransport(endpoint_ref, *, actor, matter_id, db, secrets=None).invoke(binding, arguments, correlation_id)` 是 async，返回规格 `ProviderResult`；correlation_id 接受 UUID 或 UUID 字符串，拒绝自由文本。先核全部后台授权/绑定/价格，未知工具零 HTTP。调用前再次用安装版 SDK 发现实际工具，完整 schema 漂移写新 snapshot 并使旧 binding disabled，零业务 call。mock 也核当前静态目录变体。每操作不自动重发业务 call。

## 实际权限与后阶段读取

配置/目录/价格/绑定管理要求实际有效会话、数据库 admin role 和显式 server provisioned binding-manager grant；默认没有 grant。管理员因此没有案件材料读权限。可信初始化 `provision_binding_manager(user_id, db=...)` 只给实际 admin；`revoke_binding_manager` 追加撤销。技术批准不代表律师执业许可、现实账户或生产价格批准。

普通经办律师、复核律师、助理不能管理供应商配置，案内使用按实际成员/read 权限单独检查。后阶段服务调用：

|实际函数|用途与边界|
|---|---|
|`read_binding(ref, *, actor, db, matter_id=...)`|本案可用 ToolBinding；未传 matter_id 是管理入口。重新核 endpoint 创建人、binding 创建人、实际审批人的当前 admin/grant、当前目录 hash/价格。|
|`read_current_price(endpoint_ref, *, actor, db, matter_id=...)`|后台技术价格 ID、Decimal 字符串和明确单位；本期只能 synthetic_credit/call=0；没有真实价格。|
|`read_case_endpoint(ref, *, actor, matter_id, db)`|仅服务端内部 endpoint/ref projection；不作为前端 response，秘密值不会在此出现。|
|`read_approval(binding_ref, *, actor, db)`|管理入口读取实际追加审批记录、actor/time；不可从客户端捏造。|
|`read_raw(ref, *, actor, matter_id, db)`|当前有效案件成员才能读取受保护原始证据；跨案/失效会话拒绝。|

T08 应通过这些函数取得当前绑定/价格，再加 QueryPlan、真实预算 reserve/幂等 gateway。不要直接信任 BindingInput、ToolBinding 的 enabled 或 approved 字段，也不要把 party UUID 当企业查询编号。

## SDK 与证据边界

实际使用 mcp/mcp-types 2.2.0 和独立 httpx2 2.13.1，安装源码的两元 stream tuple、snake_case initialize/list_tools/call_tool、float seconds timeout。没有手写协议或复制旧 v1 SDK 模式。synthetic MCPServer 在测试内部 uvicorn thread 监听本机；不从配置启动 shell/subprocess。`tests/helpers/synthetic_qcc.py::sdk_server` 返回 config、真实 initialize/list/call/HTTP counts 和安装版 server，finally 关闭。

秘密由显式 `SecretStore` 的私有映射解析合成 opaque ref，不读取环境、文件、外部 secret 服务；配置/DB 只含 ref。已实测字面和 Unicode 转义反射。HTTP body 在 SDK 解码/日志前检查秘密的解码 key/value、重复 key、非有限数、1 MiB/32 深度/20k 节点；SDK 客户端日志按 ContextVar 固定化，不记录参数/body/异常链。未批准的真实秘密来源保留阻断。

原始证据包含 SDK result 的全部安全 content/structured 字段及实际 call HTTP JSON `wire_response`，保存在保护表，hash 对完整 canonical JSON 计算，**不是 wire bytes SHA**。SDK 自身或本地 schema 校验失败也保存已收到的安全响应；错误 code 另在 invoke metadata，不能覆写原始结果。guard 拒绝秘密反射/无法收到结果时，仅存固定 safe_error_summary，明确 raw_kind，不伪称收到原文。成功响应分页不足保留 SUCCESS 发送状态和 raw pages_complete/coverage_limit；这不允许下游断言企业无风险。未知发送/状态保留 SENT_UNKNOWN，mock 的账单证据仅合成固定 0 synthetic_credit。

raw 与 invoke metadata 在 savepoint 内原子保存；失败无半条写入。执行后授权失效仍保 server protected receipt，但不给失权调用者 raw；调用者应 catch 服务错误后选择 commit 保存历史。本机 SQLite caller rollback 会撤回记录，不保证外部真实账单持久性；未来付费 reserve/network 事务边界由 T08/T12 单独解决。
