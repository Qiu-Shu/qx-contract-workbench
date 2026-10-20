# CH-05B Jev 持久账本与权限边界独立架构复核

日期：2026-10-20。只读基线：`a4c3c6706caad31c2335b4d055240dbddbfbd372`，开始时工作树干净。使用既有 CodeGraph 索引定位并读取当前源码；补充 rg 精确版本/调用方定位。未修改产品或计划，未运行产品回归，未提交；本文是建议，不是功能验收。

## 结论与最小切片选择

**不能直接把 Jev 写入现有 Main 表或 Main DTO。推荐新增 additive `assistant-judge-v1` 的 attempt/receipt/adoption 三表，但仍挂在现有 `assistant_runs` 上，不建立第二队列。** 这是较少风险的存储扩展；保留 Main 历史结构和解释规则，比本轮泛化整个生成账本更小。

先只做内存 registry/费用 policy 能形成授权准备，但不能证明发送、未知费用、恢复或备份安全，因而不足以称 CH-05B 接线。较小而实质完整的后端切片应同时包含：固定 schema/升级、Jev 专属授权快照、短事务 reserve/claim/settle/recover、CH-05A 提供器回环执行、跨重启及备份校验。可以先不接网页与原生凭据设置，但必须明确称“账本后端切片”；不能用临时内存 grant 或测试 preflight 替代产品许可。

本轮持久化用途建议先限定 **primary_intent 的一段独立文字咨询**，沿用当前主生成“不发送附件”的限制。material_kind 和 possible_result_guarantee 的协议保留于 CH-05A；它们需要材料/公开稿对应来源及独立目的授权，不能因为可离线 judge 就自动进入本轮外发路径。

## 1. 已确认的代码事实及不可直接复用点

| 文件与符号 | 当前事实 | 对 Jev 的影响 |
|---|---|---|
| `assistant/model_schema.py:7-24` | `assistant_model_attempts.run_id UNIQUE`，`assistant_model_outputs.run_id UNIQUE`；输入不可变、回执/输出全量不可更新删除 | 一轮先辅助判断再生成不能直接插两条 Main attempt；强改约束会影响全部读取与历史解释 |
| `assistant/providers/attempts.py:67 enqueue_generation` | 保存用户消息/运行、准备 MainRequest；更新 run.selected_provider/model/budget_json | Jev 不应再次 save_message，也不能把选定主供应商改成 TypeSafe |
| `attempts.py:30 read_attempt`、`:50 _budget`、`:120 _current` | 均按 MainPreparedInput/MainConfig/MainPolicy/MainReceipt 解码；require_policy、prepare 均属 DeepSeek 主调用 | 不是接受任意 provider 的通用账本；不能只新增 provider 字符串 |
| `attempts.py:139 _abandon_unsent`、`:200 settle`、`:251 recover_attempts` | 失败/结算/恢复会终结整个 assistant_run；settle 创建 MainOutputView | 辅助判断跳过/超时不能把已经授权的主生成标 failed；辅助结果不能作为生成正文 |
| `assistant/runner.py:8 execute_attempt` | 实际执行文件是 runner.py；没有本轮设想的 execution.py。使用 config.timeout_seconds、provider.generate、MainReply | 必须有 Jev typed dispatch 或独立内部执行函数；不能把 judge 改名 generate 来迎合 Main 类型 |
| `assistant/task_manager.py:61 submit` | 一次提交创建一个 task；只接新提交已持久化 attempt，不重放历史任务；容量 4；requested_skill 当前被拒 | 保留该生命周期与容量，不新增 JevTasks 或独立扫描器；本轮不能宣称显式技能 UI 已接通 |
| `domain.py:2782 MainModelConfig` | provider 固定 deepseek，protocol 固定 deepseek-chat-json-v1；价目/输出 token 配置为主模型语义 | JevConfig 已独立存在，应继续独立；不能放宽 Main Literal 来逃避验证 |
| `domain.py:2857 MainUsage`、`:2912 MainReceipt` | MainUsage 强制 prompt/completion/total 完整且一致；receipt 通过这些数和主价目估费 | JudgeUsage 两项均可空；缺失不得补零或伪造 total，不能复用 MainReceipt |
| `domain.py:2934 MainOutputView` | internal/model_generated/unverified、MainCandidate 文本/引用 | RouteDecision/JudgeChoice/JudgeNoul 是辅助数据，不是律师文本成果 |
| `providers/jev.py:80 judge` | CH-05A 已有独立严格协议、证据 not_sent/sent_unknown/received、默认无 preflight 时 no_egress | 能复用；preflight 必须由本次真实后端授权构造，不可固定 lambda 返回 None |
| `providers/jev_codec.py:48 input_hash` | hash 包括模板版本、JudgeRequest（含 local_request_id、scope、purpose）、JevConfig | 持久层必须保留同一输入身份；不能重新生成 local_request_id 后称同一 attempt |

## 2. 可复用的机制，而非原类型

- `Database.session`（`persistence.py:196`）的短事务、已有 BEGIN IMMEDIATE/活动存储门禁，以及 `service._owned/_owned_run/_snapshot` 的归属与当前 scope 校验。
- 已有 ledger 的原理：不可变输入/配置/许可快照，原子 `reserved -> sending` 和一次性 claim token；HTTP await 不持 DB session；发送后不明保留预留；恢复禁止重发。
- `policy.py:44 validated/:73 add_costs` 的精确 Decimal 上下文和 canonical JSON/hash 工具可复用。不要把 `policy.py:57 prepare/:62 reservation/:78 receipt` 当通用函数，它们绑定主模型格式与价格。
- `MainModelRegistry` 的会话绑定、配置版本、grant nonce、旧 policy ID 禁止改义、租约固定 provider 的模式（`registry.py:76/:106/:131`）。推荐最小 Jev 专属租约，不复制整个原生配置 UI；若抽共同生命周期工具，保持两个授权类型独立。
- `GenerationTasks` 的一个 task 一轮、启动/关闭/取消、无历史重排机制。新增表并不等于第二队列；第二套活动任务容器/轮询执行器才会重复调度。

## 3. 建议的三表及状态职责

建议三表不依赖任何 Main DTO，名字可为 `assistant_judge_attempts`、`assistant_judge_receipts`、`assistant_judge_adoptions`。

### Attempt：保存“允许向谁、为哪件事发送什么”

- 主键 id；外键 run_id、conversation_id；固定 purpose；本机 local_request_id；对应 message/source 引用；scope_snapshot；输入/模板/config/policy 的原文快照与摘要；单次预留金额与币种；创建/更新时间；发送状态和 claim hash。
- 首片 `UNIQUE(run_id,purpose)` 足以禁止重复辅助调用；同一键若输入/config/policy 不同则 conflict，而非覆盖或新发。run_id 不唯一，以免未来合法的另一种 purpose 必须重建用户消息。
- 关键输入与 claim fence 不可覆盖；无 secret/token 明文入库。JudgeRequest.text 必须对应本轮已授权消息原文或显式绑定的衍生文本；首片无需支持任意外部字符串、材料片段拼接或自动截断。
- `request_sha256` 可保留实际 wire payload 摘要；`input_hash` 按 CH-05A 规则验证。两者不混用：一个证明对外字节，一个绑定本地 scope/purpose/config/模板。

### Receipt：只保存“发生过什么、可能花了多少”

- 持久化 JudgeResult 的 status/reason/evidence 和可空 usage、安全 provider_request_id、实际 model、耗时。保存费用状态及单独价目快照；用量未知保持未知。
- `ok` 且 received 不等于允许采用；timed_out + received 可以有用量但不能有可采用答案。恢复得到 sent_unknown 不得生成假 provider_request_id。
- 不能从“调用已取消/超时/HTTP 4xx”推出零费用；只有可信的 not_sent 证据可释放全部预留。
- 若本轮要求实际支持晚到用量补记，receipt 从首次 schema 就设计为**同一 attempt 下可追加、不可覆盖**的序号回执，保留原未知结算。费用按已验证的有效账务证据计算一次，不累计两次；晚到不改变 adoption。若首片只存一条 immutable receipt，则必须明确“尚不支持晚到补记”，不能在恢复后 UPDATE/DELETE 它，也不能伪称满足 v2.1 此项。

### Adoption：只保存“这个判断是否被当前运行采用”

- 每 attempt 最多一条终态决定：adopted / not_adopted 和稳定原因、选择时 scope、原 input_hash、RouteDecision；保留目的字段和已允许技能集合/版本的服务端快照。
- 只有未过截止、status=ok、当前会话/授权/scope 均仍有效的 primary_intent 才能影响初始流程；采用前按后端白名单再次运行纯 choose_workflow。
- 晚到、撤销、换案、取消和输入变更后允许记账，但固定 not_adopted；不得修改已保存路由或档案。
- 不修改 `assistant_model_outputs`，不修改 run.selected_provider/model/budget_json，也不自行写 run completed/failed。为维持现有 Main 完整性，首片 Jev 前置阶段可保持 run queued；若要显示 routing 状态，必须同步调整 Main `_current` 和 integrity 对 reserved run 的状态约束，不能只改显示枚举。

## 4. 独立授权、目的与预算

Jev 必须有专用 policy/approval DTO：至少明确 recipient=`typesafe`、固定 endpoint/protocol、purpose、actor/session/workspace、精确 scope/输入摘要、config/模板版本、有效期、可调用次数、单次预留与总费用预算。许可由受信任后端建立；renderer、模型内容和 HTTP 普通字段不能自行声明 `approved=True`。

主模型获准向 DeepSeek 发送某段文字，只能证明那一收件方和目的；不能从 MainModelPolicy 推导 Jev 许可。更不能把本地资料 policy 的“允许本地分析”当 TypeSafe 外发许可。共享 workspace/用户并不代表共享材料授权。

`JevConfig` 当前没有价格、硬输出 token 上限，也没有厂商强制金额限制。建议单独、严格的 Jev 计费策略保存明确 `reserved_usd`、max_total_usd/max_calls、price_reference/版本和可空单价；无法形成有限授权预留时 no_budget 跳过。不要套用 Main 的 max_input_bytes/max_output_tokens 估算，更不能以 max_response_bytes 充当供应商 token 费用上限。预留是本机预算控制，不是供应商费用绝对封顶保证。

费用估算仅在已报告的字段足以按已授权价目计算时形成 estimated，保持 Decimal/USD。所需计数缺失、价格未知或发送结果未知则继续按保守预留占用预算；不能补零。实际回执可超过预留，保留事实并阻止后续超额执行，不删除回执凑账。主与辅分别扣自己的明确许可；若产品将来要跨供应商总预算，应聚合两种账本，而不是使主授权自动支付辅助调用。

reserve 和 claim 均验证所有权、会话、restore fence、scope、许可有效性及预算；claim 后网络不持事务。settle 先保全原调用账务，再独立判采用是否仍允许。原 Main 结算在权限拒绝可能提交审计后重新取锁和复验 claim（`attempts.py:224-229`）值得直接沿用。历史读取验证当前所有权/案卷绑定，但不能要求旧费用记录的运行许可今天仍未过期。

## 5. 同一 task 的接线边界

完整调度接线建议是 `GenerationTasks` 在原提交短事务中一次保存用户消息/主 attempt，并可选保存 Jev reservation；事务提交后仍只创建一个 task。该 task 顺序执行已记录 Jev attempt，再沿原 Main runtime/attempt 继续；Jev 返回不论 skipped/invalid/timeout 都不能换掉主供应商或扩大工具范围。已取消/失去当前授权则主流程自己按旧规则停止，不能把“辅助失败后继续”理解为绕过这些检查。

如果先交账本后端切片：提供 `reserve_judge(existing_run, ...)`、`execute_judge_attempt(...)`、`read_judge_attempt(...)` 的受信任内部 seam，并在回环中证明持久链；不新增 HTTP 入口、独立后台扫描器或自动 replay。随后在现有 runner/task_manager 增加可选前置段。必须在阶段记录中注明尚未默认集成日常聊天。

取消/关闭必须处理同一 run 所有未发送 Jev reservation；已经 claim 的仅原执行者可 settle，管理器不能抢先改为 not_sent。发送未知不重新入队。进程恢复把 reserved 封为 not_sent，把 sending 封为 sent_unknown；不会因下次配置已可用而重排历史运行。旧 scope/config/policy 的重提应 conflict 或返回原历史，不创建新 POST。

## 6. 必须同时覆盖的 schema / 备份 / 恢复接点

| 位置 | 必要变更影响 |
|---|---|
| `storage_schema.py:8-31` | CURRENT_VERSION 增为 assistant-judge-v1；VERSIONS 必须显式保留 assistant-model-v1，不能用替换 CURRENT_VERSION 意外丢掉旧版本；新版本继承旧 assistant/attachments/model 精确 DDL 后再加 judge |
| `schema_migrations.py:9 statements_for` | 新增纯 additive DDL；旧版本结构/记录不改义；旧库到新库链仍在已验证 staging 中原子执行 |
| `storage_bootstrap.py:20-23` | 新建库的初始化顺序追加 judge；不可让普通 read 初始化/升级真实旧库 |
| `assistant/attachment_integrity.py:62` | 接受已识别新完整 schema；不把附加未知表当可忽略 |
| `assistant/model_integrity.py:215` | 接受新版本并继续完整检查旧 Main 记录；不跳过 main provenance 校验 |
| 新 judge integrity | 验证表间 FK、所属 run/message/scope、输入/模板/config/policy 摘要、状态/claim、费用、回执、采用决定及事件的一致性；含空表版本和未知 schema 拒绝 |
| `ops/backup.py:162 _file_references` | 与既有 model/attachment validator 一起调用 judge validator；含 judge 私密输入的旧通用导出仍拒绝，不能悄悄漏掉；新 QXBAK 包含并验证记录 |
| `web/local_server.py:221-225` | 锁定启动恢复中追加 judge recovery，再配合既有运行隔离；不创建重复 worker，不访问供应商 |
| `ops/workspace_backup.py:303 _fence` | 旧 session 全撤销后恢复 judge 状态，记录 judge 中断计数；新副本仍 quarantined/live_egress=False，不复制可执行 grant |
| `web/workspace_upgrade.py:103-132` | 既有 per-version 备份、回执、DDL、marker 故障恢复路径可沿用；须测试 assistant-judge 新步骤，不破坏旧冻结步骤 |
| `providers/history.py:14` 与 Main API | 保持现有一主 attempt 查询语义；新辅助历史采用独立视图，不能把 Jev rows 混入 MainHistoryItem |

`assistant_run_events` 的序号是整轮全局递增，Jev 用独立 `judge.*` 事件命名；现有 Main `_events` 只取 `model.*`，可以共存。不要为方便对齐把 Jev 事件命名为 model.started/finished。Judge validator 必须也校验其自身事件及整个 run 的连续序号。

## 7. 最小必要验证建议（本复核未执行）

1. 旧 assistant-model-v1 纯升级、幂等升级、错误 DDL 回滚、marker 中断恢复；旧结构和记录摘要不变。
2. 同一 run 可同时保留主 attempt 与一个同目的 Jev attempt；重复 reserve/claim 仅一次 POST；无 Jev grant/预算/资料许可时不发送。
3. 真实 Main grant 不能授权 Jev；错目的/错 scope/撤销/过期/config/template 漂移不发送或不采用；回执可记录但结果拒用。
4. 超时/取消/HTTP 异常/received invalid/部分用量的账务与采用状态独立；晚到（若支持）只追加原 attempt 账务；未知不自动零结算、不重发。
5. 进程恢复、关闭未启动 task、发送中关闭及恢复副本：未发送释放、已发送未知保留；不启动外网任务；主 run 最终状态仍由原主流程/隔离决定。
6. QXBAK 往返、原 schema 包恢复到新版本、伪造 recipient/purpose/scope/hash/费用/事件/claim/adoption 拒绝；旧通用备份不漏出 judge 私密输入；备份不持久化凭据和可复活许可。

风险边界：本复核没有跑行为测试，不能把上述静态分析称为已验证接线。Main 表当前具有较强的一调用一运行不变量；本轮为了减少新表而拆除这些不变量，改动会明显大于独立辅助账本。
