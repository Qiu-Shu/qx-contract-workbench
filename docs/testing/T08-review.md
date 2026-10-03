# T08 独立账本与流程审阅

状态：ENGINEERING_REVIEW_COMPLETE，仅本机独立虚构账本/流程工程审阅。审阅者没有写T08业务、正式测试、锁、状态或作者文档；只写 `.audit-local/t08-accounting-review/` 与本文。此前reviewer只有设计/NOT_RUN，本次继承独立PASS为0。真实QCC仍BLOCKED_LIVE；许可、真实价格/schema/账户、地域/数据政策与真实律师批准缺失，生产批准null。工程通过不表示真实供应商、法律或生产验收。

本次应用 requesting-code-review、verification-before-completion 的证据指导；父任务禁止再派代理，故由本独立审阅者直接读实际planner/ledger/gateway/storage、FactoryQccTransport、三正式目标/helper和T08-detail/preflight，再写自己的真实服务探针。所有数据和预算批准身份均为明确虚构，仅0/5/15/20/25等模拟积分，无真实扣费或材料。

冻结代码上实际完成三组命令，均exit0、0失败/错误/跳过，日志没有warnings：

|独立执行组|实际通过|pytest报告耗时|证据|
|---|---:|---|---|
|三正式目标 test_query_plan / test_budget_concurrency / test_query_recovery|52|33.15s|final-target.xml / .log|
|本审阅 test_accounting.py|58|37.68s|final-independent.xml / .log|
|必要auth / matter_access / party / qcc_binding / mcp_transport回归|78|19.78s|final-affected.xml / .log|

完整实际argv/UTC/exit/数量在 `commands.json` 与 `final-runs.json`，脚本为 `run_final.py`。三组结果为不同测试分母，不加总称84项验收或法律准确率。未运行whole/CLI/demo/Word/UI/真实QCC；受影响MCP测试及专门Factory探针只运行127.0.0.1合成SDK server，均实际停止本机测试服务，无外部网络、安装、postinstall、系统变更或commit。使用项目既有Python/pytest及库，未额外加载Word/native helper。

独立实际发现与闭合：

|缺陷|真实独立RED|原probe复验/最终闭合|
|---|---|---|
|批准budget/scope/plan/bill在内部insert+flush后失败，caller捕获再commit仍留实际批准|adapted.xml exit1，4 failed/24 passed；expanded.xml仍4个同类失败|服务savepoint后approval-fixed.xml exit0，4 passed；撤销同模式revoke-atomic.xml 3 passed；最终58全部通过|
|B案有效成员读取A案已有账本ID与不存在ID分别403/409，泄露跨案存在性|cross-case-adapted.xml exit1，1 failed/43 deselected|case-bound lookup与统一403后closure-expanded.xml exit0，9 passed；最终原probe通过|
|未注册transport早期BLOCKED_LIVE在factory事务外，拒绝未留审计|transport-denial-red.xml exit1，1 failed/55 deselected，0dispatch/0ledger正确|校验纳入初始短factory事务后transport-denial-fixed.xml exit0，原1 passed；最终通过|

另有作者自行发现“账本已对账但当前receipt billing仍unknown”的真实RED，不冒称本审阅发现。本审阅独立closure探针验证：追加新的receipt版本更新费用/计费状态，保原provider status/raw/query_at及未知送达/范围限制，旧payload不变，再execute不会重发。账单确认不能伪造成功送达或内容无风险。

保留辅助错误原证据：initial.xml为22 passed/6失败，6个是probe缺DTO必填pages/authorization_id或Party两步登记/确认适配，不计业务RED；expanded.xml为38 passed/5失败，其中1个是mock_catalog别名patch适配，另4个是真实批准P2；pagination.xml修正alias后1 passed，实际6页/6持久call成立。cross-case-red.xml是http_status字段误用和一个set序列化warning，修正status_code/frozenset后cross-case-adapted.xml才是1个真实业务RED。旧XML全部保留，不能以路径/收集/适配错误包装功能缺陷。

58项独立覆盖实际两线程/独立连接20余额两笔15仅一笔发送、并发同键与完成后不重发、网络等待期间独立新Database短写；4种未知计费profile保预留/次数、新Database恢复0重发、3个持久阶段崩溃；零费多plan/重启仍6次、价格/版本/主体变化0发送、实际session/角色/成员和批准者角色/成员撤销；默认1页、精确purpose/scope/过期边界、授权6页每页不同key计次与不完整范围限制；实际账单批准、多合法行、重复幂等、冲突不覆盖、re-hash/单位/float拒绝、25实际超额保负5与incident、对账内部失败原子、独立Decimal精度；callback结束前失权不返材料但留raw/receipt与安全拒绝审计，HTTP token/CSRF短事务交接，5项SQL历史不可变触发器，批准/撤销/预留捕获内部失败后commit无半写。

父任务补充的Factory边界也实际独立检验：真实已安装SDK本机server→T08 reserve/marker/network/settle；每server callback读取已durable dispatching/send_claimed并完成独立SQLite短写，证明Factory网络过程未持写Session。重用同Factory两plan两tool call，各invoke记录dispatch_count=1；另同实例先成功后before_send当前增量0，第二条cancelled_before_send且旧calls1/used5保持。factory-sdk-reuse.xml窄跑2 passed，最终58包含这两条；没有移植T07旧QccTransport PASS当Factory PASS。

源证据：作者freeze清单SHA `39eb67deedee2380c4d365d9b68a9bca8f28f5d75978cc4d618b741e28339721`，12 owned实际bytes/hash初查与终查均12/12匹配；初查在正式目标运行期间，运行前33项源/测试/fixture快照独立保存，前后33/33 SHA一致。作者freeze中的业务/测试10项也都属于该运行前后快照；另两作者docs终查与冻结预期一致。T06原provenance及四DOCX也在33快照中，未修改。数据证据hash不是批准引用，源码冻结不代替生产批准。

没有剩余已知未闭合P2。边界：验证范围是单实例SQLite、本机合成MCP、合成价格与本项目明确身份；不宣称多节点会计一致性、官方工具封顶/关联主体计费规则、完整历史风险或真实QCC许可。当前mock缺供应商精确总页/历史来源日期时保留明确未知/不完整限制，不编造“1/10页”或已核清风险。OCR、T09原生Word视觉、T10完整UI、T11双律师gold及T12OS/备份/release验收仍各自后续任务。本审阅未写业务/正式测试/锁/状态/Vault，父节点统一全套、项目状态与commit/memory。
