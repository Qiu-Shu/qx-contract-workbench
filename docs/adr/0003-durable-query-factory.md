# ADR 0003：查询短事务、发送授权与持久计费

日期：2026-10-03。状态：T08 本机虚构工程实现；真实供应商仍 BLOCKED_LIVE。承接 ADR 0002 的显式上下文原则，不引入全局数据库、依赖、DTO 或隐藏 caller commit。

## 决定与事务边界

`reserve_call`、批准、撤销、账单登记和 `reconcile` 均加入传入 Session；一个服务的全部写入使用 savepoint。调用者捕获服务错误后继续 commit 不会留下部分批准或部分核账。调用者 rollback 也回滚预留；预留本身绝不发送。

发送由 `execute_plan(..., database=Database, matter_id=...)` 显式拥有新建短 Session：A 重读后端计划、原子核余额/次数、预留并 commit；B 重读后端版本，持久化 dispatching 和私有 token hash 并 commit；关闭 Session 后进行供应商准备和网络操作；C 保存真实计费状态和不可变收据并 commit。SDK 的 initialize/list-tools、业务 call-tool 和等待期间均不持有 Session。发送前最后一次短事务核当前计划/主体/批准/schema/价格，消费一次性 `send_claim` 后才发 tools/call；token 只在后端调用栈中流转，不在 DTO、日志、前端或 QueryReceipt 中返回。

`FactoryQccTransport` 是唯一注册的本期发送 adapter；`execute_plan` 拒绝任意对象、子类、不同 Database 或不同 actor/session/matter。T07 的 `QccTransport` 保留原签名和原工程行为，仍适用于 T07 协议测试，不能跨 caller Session 承载本期非零价格执行。新 Factory 同样只支持 T07 受控 mock 和数字 loopback `/mcp` synthetic SDK；任何真实账户、endpoint、地区、数据政策、官方 schema、价格、许可都未获本期批准。

每页一个独立 key、预算预留、发送 claim 和收据；案级累计调用上限跨 plan、连接和重启。key 冻结案件、plan ID/version/hash、item、真实确认 party revision/hash、binding/approval/schema/endpoint/price、规范参数、页和固定 freshness window；不使用当前时钟生成重试新 key，不跨案共享结果。Q0 空 items 返回空收据、零工具调用，不要求付费预算。

## 未知、故障与账单

收到 success 或 failed 也不证明已知费用；未知发送或未知费用仍保预留和调用次数。只有受控开发价格/profile 可给出模拟确定费用；loopback SDK 只有已知成功/失败及已登记零价时可确认零费用，`state=unknown` 即使零价仍 sent_unknown。本期单位 `synthetic_credit`、价格单位 `synthetic_credit/call`；没有真实汇率、折扣、月封顶或真实收费结论。

正常发送前故障只能由匹配私有 token 的持久 `send_claim=false` 证明未发 tools/call 后取消；异常文字、provider 名称、客户端标志不能释放已消费 claim。预留后或发送标记后崩溃无此正常返回证明，重启不补发；显式 `recover_inflight(Database)` 将 dispatching 保守记为 sent_unknown。已有 reserved 而没有完成收据也拒绝自动发送。重复 completed/unknown 请求只读同一收据，不重发。

内部 continuation 以已持久 token/entry 保存收到的受保护 raw 和账本，即使发送者随后失权；C 之后重新核实际 Session、角色、成员和当前计划，失权调用者不会得到回执/raw。旧 Session 的 raw 读取也受 T07 案权限保护。

核账必须先登记本期明确 synthetic 的账单实际 bytes、SHA、line ID、entry ID、Decimal 金额和单位，再由真实后端律师成员批准该 line。自报 `BillingEvidence.approved_by` 或 SHA 不构成证据。同一账单可有多条合法行，同一行不可重复分配或矛盾覆盖；原始账单、批准、事件和旧收据均不可修改。确认后从预留转实际费用，不重复计扣；0 费用仍保已发调用数。超预留保真实金额、负余额和 incident，并阻断后续新调用。核账另追加收据费用版本，保留原 ProviderStatus、raw/hash/query_at，不能把 unknown 查询伪装成成功。

## 拒绝审计与 HTTP 接入

`authorize_query` 重读真实 Session/用户角色/案件成员；预算批准和付费执行限真实 handling/reviewing lawyer，本案 assistant 可读账本但不批准/执行，管理员管理 binding 不自动获得案件权限。拒绝只加入 caller 的固定 AuditEvent，reason 存 hash，不 commit caller；直接服务调用者若希望保留拒绝须捕获错误再 commit 该 caller 事务。一般 caller rollback 仍按其事务合同回滚。

gateway 和 Factory 的 `factory_transaction` 显式拥有自己的短事务，错误时先 rollback 该新 Session，再另开短事务保存固定拒绝审计；不回滚或 commit 任意外部 Session，也不抹此前已持久 ledger/raw。未知或他案 ledger ID 对公开 read-entry/read-receipt 返回同一 403，不暴露他案存在性。

T10 HTTP 路由必须调用 `authenticate_execution(Database, token, csrf, matter_id=...)`，它先关闭认证短事务，再核 CSRF 和付费角色并关闭授权短事务，然后 await gateway。不得使用跨 await 的 `yield get_db`；本期 CSRF 校验不调用 T02 会主动 rollback/commit 的 `deny` 路径。当前尚未新增 HTTP route。

## 实际接口

```python
queries.storage.initialize_storage(database: Database)
planner.create_query_plan(input: QueryPlanInput, actor, *, db, plan_id=None) -> QueryPlan
planner.read_plan(plan_id, actor, *, matter_id, db, require_approved=False) -> QueryPlan
planner.approve_case_budget(matter_id, actor, *, db, credits=None, max_calls=None,
                           expires_at=None, unit='synthetic_credit') -> UUID
planner.approve_query_scope(matter_id, party_id, purpose, scope, actor, *, db,
                           max_pages=1, extra_party_ids=(), relation_depth=0,
                           expires_at=None) -> UUID
planner.approve_plan(plan_id, expected_hash, actor, *, matter_id, db) -> QueryPlan
ledger.reserve_call(plan, item_id, actor, db, *, page=1) -> Reservation
ledger.read_budget(matter_id, actor, *, db) -> dict  # server technical projection
ledger.read_entry/read_receipt(entry_id, actor, *, db, matter_id=None)
ledger.register_bill_line(entry_id, raw: bytes, line_id, actor, *, db) -> UUID
ledger.approve_bill_line(line_ref, actor, *, db) -> BillingEvidence
ledger.reconcile(entry_id, evidence, actor, *, db, line_ref=None) -> BudgetEntry
ledger.recover_inflight(database: Database) -> None
gateway.authenticate_execution(database, token, csrf, *, matter_id) -> Actor
await gateway.execute_plan(plan_id, actor, transport=None, *, database, matter_id)
```

批准/撤销以及当前读取的实际签名以代码为准。DTO 无新增/修改；额外 `db`/Database/matter 和批准 refs 是 ADR 0002/本 ADR 的后端可信接点。需要非零价或故障模拟时仅 trusted 管理员开发服务 `register_synthetic_price` / 静态 `register_synthetic_behavior`；这些不存在 HTTP 入口，不表示供应商真实许可。

## 限制与证据

本机 SQLite BEGIN IMMEDIATE 单实例并发验证，不宣称分布式生产一致性。未来真实网络费用不能靠 caller rollback 消除账单，必须保留本 ADR 的持久 reserve/mark/settle 与受保护计费证据，并独立完成真实批准。结果归纳始终保虚构、来源范围、缺页/未知、许可和非无风险限制。原件、法律批准和正式签发不由费用批准改变。

实际失败/修复命令、目标 52 与必要受影响 78 的结果见 `docs/testing/T08.md`；独立审阅及父全套验证分别记录，不相互代替。
