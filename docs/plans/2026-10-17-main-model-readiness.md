# CH-04 首片接线准备（只读结论，未实施）

核对日期：2026-10-17。仓库：`D:\Documents\ChatGPT\律所项目`。读取时 HEAD：`00b106c4306f96d685a43b797765b7bb9ad3e4b3`；本文核对包含 CH-03A 工作树实现（随本阶段提交保存），不能只用当时 HEAD 代表本次源码。依据 `docs/plans/chat-first-architecture-v2.1.md` 第 6.5、8、CH-04 节；已用 CodeGraph 定位后核对当前源码。本只读核对未改产品、测试或 desktop 文件；原回归 94872 后因路径别名修复主动中止，最终回归 31938 已通过，详见 CH-03A 证据；本计划核对本身未运行新增测试、读取凭据或调用真实模型。

## 1. 可以直接复用的边界

| 当前源码 | 实际可复用内容 | 不能推定已具备的能力 |
|---|---|---|
| `assistant/service.py:20–84,225–284` | 当前 session/角色、conversation owner、workspace、接待与案件成员权限；作用域版本；消息与 run 同事务；同 request_id 重放和一个活动 run 的限制 | `save_message` 仅登记 queued；没有 worker 或模型执行。旧 queued 不代表曾批准外发，不能在启用 worker 后批量自动补发 |
| `assistant/schema.py:28–60` | run 已保存 actor_id、session_id、不可变 scope_snapshot；provider/model/budget 预留列；事件单调 seq 和活动 run 唯一索引 | 没有 `assistant_model_attempts`、外发许可、配置版本或持久输入清单；仅有一段 budget_json 不形成扣费账本 |
| `assistant/service.py:304–323,348–363`；`web/assistant.py:29–64,137–147` | 取消请求、历史事件重读、短事务 SSE、恢复 run 隔离 | 未来 worker 仍须在发出前和提交前重查权限/取消/fence；现有 SSE 不是供应商流解析器 |
| `assistant/attachment_records.py:15–83`；`attachments.py::read_parse/read_excerpt` | 当前归属、不可变材料选择版本、具体解析版本、原件摘要、anchor 与 quote_sha256 | 当前材料策略 `domain.py:2669` 为 `external_processing=False`；本机处理同意不能变成云模型许可，读到原文也不等于允许发送 |
| `queries/ledger.py:14–65,109–180,183–190`；`providers/qcc_mcp.py:123–219` | 原子预占、幂等摘要、单次发送 claim、已发送未知占用预算、发出前失败证明、撤权后的受限费用回执落库、重启不重发；网络前后各开短事务 | 账本强依赖 matter/plan/item、QCC credits 与 synthetic receipt，不可直接给建案前聊天塞假案件或把 USD 当积分；适合借算法和故障测试，不复制它的 DTO/业务授权 |
| `review/model_adapter.py::strict_json`；`review/deepseek_codec.py` | 严格 JSON 重复键/深度/大小/非有限数拒绝、最小输入投影、返回身份/截断/usage 一致性检查、Decimal 精确计价的测试思想 | offline codec 绑定合同 `ModelRequest/ReviewContext`、三种 operation、合成金额和离线模型 ID；不能直接改掉 OFFLINE 字符串做聊天适配。旧 `require_provider` 的精确 MockProvider 白名单保持 |
| `config.py::Settings/canonical_json`；`persistence.py:161–207` | 冻结 extra-forbid 配置、可重算配置摘要、Decimal 序列化；显式 Database，短 session | 默认模型严格是 mock；没有主模型供应商设置或主模型凭据存储。SQLite 所有事务 BEGIN IMMEDIATE，await/慢响应绝不能在 session 内 |
| `providers/mcp_client.py:1–76,159–175` | 已有 httpx2 异步调用先例、trust_env=False、禁止跳转、外层截止时间、日志隔离和响应边界校验 | 这是合成 MCP loopback 专用客户端，不能放宽其端点/协议来充当主模型。可借配置方式；主模型用自己的窄适配器 |
| `ops/storage.py:36–47`；`storage_schema.py`、`schema_migrations.py`、`storage_bootstrap.py` | 持久恢复 fence、精确结构版本链、原生升级和独立恢复副本迁移 | 增加 attempt 表必须同步结构识别和迁移；仅 create_all 会破坏旧备份验证 |

补充：确有 `domain.py::EgressPolicy` 和 `ops/egress.py::check_egress`，但后者只接受已注册的合成 HTTP 127.0.0.1 MCP 端点，模块明确写生产地域/DNS/隔离未批准。因此“已有通用云模型外发策略”不成立；保留其旧语义，在 assistant 边界新增接收方授权。

`ops/secrets.py` 是发布候选密钥扫描器，不是密钥存储。此次限定源码检索未找到已接入主模型的 Windows 凭据管理器；不据此断言用户机器没有其他配置。后续从受信装配注入凭据 resolver；缺配置明确不可用，不扫描用户目录找 key。

## 2. 建议首片只闭合这一条链

同源请求登记 run → 短事务准备一份不可变输入与当前许可 → 原子预占 attempt → 事务外调用当前明确选定的一家供应商 → 记录回执/usage → 短事务重新核权并比较版本 → 保存已验证的内部候选和事件。首片可先完整接收有界结构化响应，再发已验证成果；不必同时实现供应商 token 流、工具循环、Jev、自动档案和合同签发。

输入仅取明确选择的消息与获准来源卡，绑定 workspace/conversation/binding/input/materials 版本及配置、模板、输出契约摘要。source 卡绑定 attachment/parse_revision/anchor/quote_sha256；未完成外发许可的本地附件继续拒绝外发。对首片合成测试可使用受信注入的独立合成文本与明确模拟授权，不能让 renderer 的 `synthetic:true` 自证安全。

调用前必须提交 `sending` 与一次性 claim，再执行 HTTP；数据库与网络不能原子提交，故崩溃落在 claim 与发出之间也保守记 `sent_unknown`。原 request_id/attempt 重放不得再发；重启、SSE 重连、刷新、恢复备份都不派生新调用。已有历史 queued 需显式执行资格/版本门，不能因升级自动消费。

响应收到与结果可采用分别记录：HTTP/JSON/结构验证失败仍可能计费；usage 缺失保持 null/unknown。取消、撤权或输入变化后，不向当前界面出流、不写当前成果；通过仅限该已 claim attempt 的内部结算通道保存可用回执与费用，不给该通道读其他材料或改当前档案的权限。恢复 fence 后不启 worker、不补发；归档中的未知费用保持历史未知。

## 3. 最小文件切面（拟新增/拟调整，不是已经修改）

| 文件 | 首片职责 |
|---|---|
| `src/cn_contract/domain.py` | 集中新增 MainRequest、ProviderEvent、配置/外发决策、ModelAttempt/usage DTO；成本可空、Decimal+单位、费用状态与结果采用分开；不复用必须有 cost 的旧 ModelUsage |
| `assistant/providers/main.py` | 聊天专用窄接口和第一家适配；固定受信端点、供应商专属参数、输入/响应上限、显式超时、无自动 POST 重试；无凭据返回未配置。第二家随后遵守同一内部契约，不能自动切换接收方 |
| `assistant/providers/policy.py` | 当前身份、恢复 fence、接收方/材料类别/预算/配置版本与 payload manifest 的唯一外发决策；接收方权限来自受信配置，模型和 HTTP body 不批准自身 |
| `assistant/providers/attempts.py` | reserve/claim/receipt/recovery 的短事务与 CAS；同一实际调用一条 attempt，未知状态保留预算；本地 request_id 与供应商 request_id 分开 |
| `assistant/model_schema.py`（名称可依实现调整） | 独立追加模型表/索引/不可变输入约束，不改旧 assistant-v1 和 attachments-v1 基线 |
| `assistant/runner.py` | 管理 prepare/await/commit 三阶段、当前 session 核验、版本及取消检查、有限并发/队列；供应商等待在 DB session 之外，不把这些逻辑堆进 app.py |
| `storage_schema.py`、`schema_migrations.py`、`storage_bootstrap.py` | 增加精确下一版本及初始化；现有旧基线只读保留，原生升级公共算法继续复用 |
| `assistant/service.py::quarantine_runs` 和必要的启动装配 | 增加 attempt 启动/恢复隔离与不重发语义；HTTP/原生装配仅传受信配置和 runner，不扫描历史 queued 自动付费 |
| `pyproject.toml`、实际依赖 lock/notice（有变更时） | 固定生产传输依赖。`httpx==0.28.1` 当前仅 test extra；工程另有 mcp 带入的 httpx2，优先验证该已有栈能否复用，不能同时无理由加入多套 vendor SDK。需要直接声明时同步 lock/冻结验证 |

前端不在这个接线准备中提前解锁：当前 `AssistantSkillView.state` 固定 not_connected、catalog.generation_enabled 固定 False，页面发送 disabled，`assistant-api.mjs` 尚无 send/事件订阅接线。后台首片通过后，再在既有同源 api/state/render 模块小范围开启发送、受众隔离与 run 事件；不能只删除 disabled 就称完成对话生成。CH-04 是主模型接线，不表示 CH-06 工具或 CH-07 档案已实现。

## 4. 能揭露真实缺口的失败验收

全部从独立合成文本/附件及本地模拟 HTTP 开始；下表尚未编写或运行。

| 故障/竞争 | 必须观察的结果 |
|---|---|
| 无配置/凭据、未获准接收方、local-only 附件、过期策略 | 模拟服务收到 0 请求；本地草稿仍能保存；没有 Mock 成功或自动换供应商 |
| 两线程/进程同键及异键并发、重复提交、客户端响应丢失 | 同键最多一次 claim/POST，异 payload 拒绝；总预算和并发上限原子生效；GET 原 request_id 找回，不产生新键重试 |
| claim 前后崩溃、供应商已收请求但超时、请求体中途断开 | 有 durable marker；无法证明未发出则 sent_unknown、费用不补零、不自动重发；普通重启和备份恢复都不再 POST |
| 慢连接/慢读/拖延完整响应 | 外层总截止生效；独立连接完成接待写入、状态读取、取消；生成期间无长写事务或 event loop 阻塞。沿用 `test_budget_concurrency.py::test_network_has_durable_marker_and_no_database_write_lock` 的事件/barrier 方式，避免只睡眠猜时序 |
| 发出前与响应后撤销 session/角色/案件成员；取消、切材料版本 | 发出前拒绝；发出后不提交当前结果或泄露流；仅原 attempt 得到回执，费用是否发生与结果采用分离 |
| 401/429/500、跳转、错误 TLS/不受信 URL/代理环境 | 有界失败且不自动重试/换 endpoint；不跟随重定向、不把凭据转发；具体发送未知判断以 transport 可证明的阶段为准 |
| 过大或无限响应、重复键、NaN、bool token、模型身份漂移、截断、非法引用 | 拒绝不合格成果，保留真实调用状态；usage 缺失为 unknown，精确引用必须匹配该输入清单；供应商自报 verified/approved 不成为本机事实状态 |
| client/internal 混合输出与未校验结构化流 | 校验前仅状态；内部意见不能进入客户输出或一键导出；拒绝模型自行决定最终 audience/generation_kind |
| 凭据/调试字段、错误受众材料、允许引用的成果正文分别含合成 canary；HTTP 异常与 debug logger 开启 | 凭据不出现在任何用户结果；秘密/调试/无权材料标记不进入普通日志、错误、状态事件、配置摘要或不匹配受众。获准正文只在经过授权和结构校验的对应成果通道/SSE/导出出现；原始供应商响应或混合未验证 JSON 不直通。受保护材料/回执存储按策略保留必要内容 |
| 新表升级、迁移中断、旧 qxbak 恢复、已有 sending attempt 恢复 | 旧结构摘要与原件不变；新结构精确识别；恢复只读、未知费用保留、worker 0 请求；随后冻结 EXE 验证真实安装运行依赖可 import |

相关现有测试入口：`tests/unit/test_deepseek_codec.py`（严格数据/未知费用）、`tests/integration/test_budget_concurrency.py`（去重/并发/网络释放锁）、`test_assistant_storage.py`、`test_assistant_control.py`、`test_assistant_routes.py`（权限/版本/取消/SSE）、`test_assistant_backup.py`/`test_assistant_attachment_backup.py`（恢复）。新增建议集中在规格列出的 `test_assistant_main_provider.py`、`test_assistant_generation.py`，账本迁移用独立目标文件；不把 CH-03A 的已完成目标或正在执行的完整回归计作 CH-04 验证。

## 5. 尚未核验的前提

独立计划审核核对了源码与 v2.1：Standards 无待修项；发现的 canary 断言过宽已在上表区分秘密、错误受众和获准正文。这是下一切片的测试契约澄清，不是已经运行 CH-04 测试或接通模型。

- 本轮没有重新联网核对 DeepSeek/OpenAI/TypeSafe 官方协议、当前模型目录、价格、账户额度、数据保留或 SDK 发行物。规格中的外部快照及离线源码模型名仅供定位；正式实现参数之前做针对性一手核验。
- 未读取机器的实际 key 或费用设置，也未运行一次真实调用。真实合成联网验证仍取决于现有受信账户、该接收方数据许可和明确预算；协议模拟成功不能写成真实接入成功。
- 本文只保存下一首片的源码接线准备；没有新增运行代码、测试、依赖、表或 worker，没有开启发送按钮，也没有改动正在回归的冻结输入。
