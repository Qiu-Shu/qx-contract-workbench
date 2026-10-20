# CH-06B2 接线准备：只读工程审查

2026-10-20，工作目录 `D:\Documents\ChatGPT\律所项目`。本报告读取当前 B1 冻结工作树；不代表 B1 最终验收，也不代表 B2 已实现。独立代理使用 CodeGraph 和源码定位，没有改动 src/tests、调用真实模型或法库、运行测试；统筹随后核对了单次表唯一键、发送许可 max_calls=1、每次 settle 终结、provider 拒绝 tool_calls、Jev 结果尚未用于分流及 manager 装配边界。本文作为接续计划共享，B1 实测见对应阶段证据。

## 结论

不能把现有 `execute_attempt` 放进四次循环，也不能把查库摘录直接追加到当前 `MainRequest.content`。当前产品是一条获准文字、一次主模型发送和一次终结；新 B1 是本机查询回执与历史快照。两者之间缺少完整上下文的外发许可、可恢复的逐轮模型账本及模型工具协议。

推荐下一片先完成 **显式本机法律检索 → 保存 B1 回执 → 对话中列出引用 → 点击核对历史原文片段**。复用现有生命周期管理器，主模型和 Jev 发送路径保持现有许可语义。这个切片可在没有任何模型配置时独立验收，不能称“模型自动查库”或“4 轮 runner 完成”。随后再实现经过确认的完整外发上下文和最多 4 次主模型调用；不引入另一套队列或泛化插件注册平台。

## 当前代码证据与可复用接口

| 位置 | 当前真实行为 | 接线用途 / 断点 |
|---|---|---|
| `assistant/task_manager.py:19` `GenerationTasks` | 一个应用 lifespan/event loop 持有 `_tasks`；新持久 attempt 提交后才 dispatch；旧 request_id 只读回，不再派发 | 可复用生命周期、并发容量和 shutdown；`MAX_ACTIVE_TASKS=4` 是并发任务数，**不是每 run 的 4 轮模型上限** |
| `assistant/task_manager.py:65` `submit` | 明确拒绝任何 `requested_skill`；resolve 一次 runtime lease；仅主模型 attempt 驱动 | `legal_research` 不能仅打开前端按钮；必须有明确本机工作流入口，并复用同一个 manager 的 admission/closing |
| `assistant/task_manager.py:109` `_execute` | 可选 Jev 先执行，随后只调用一次 `runner.execute_attempt`；Jev decision 未被用作查询参数或业务路由 | 不得宣称已有“Jev 自动分流到法库”；下一片显式技能可直接跳过 Jev |
| `assistant/runner.py:8` `execute_attempt` | claim → 无 DB session 的网络 await → settle；取消和异常保守记为 sent_unknown | 可复用模式，但当前函数不承担多轮；未知发送不能再次 dispatch |
| `assistant/providers/attempts.py:67` `enqueue_generation` | 保存一条消息/一个 run；冻结完整 wire JSON 摘要；有附件即阻断 | 不能把现有附件或查询结果悄悄塞进主请求；本机检索入口必须与旧 `/messages` 只登记语义区分 |
| `assistant/providers/attempts.py:120` `_current` | 固定 actor/session/scope/config/policy/消息摘要；仅 queued/generating；重新构造 wire 必须相同 | 新阶段 retrieving/persisting/awaiting approval 需要独立而一致的执行状态合同，不能简单删掉检查 |
| `assistant/providers/attempts.py:200` `settle` | 每一次模型响应即写唯一 output 并使 run completed/failed/cancelled | 非最终工具请求不能走此终结路径 |
| `assistant/model_schema.py` | `assistant_model_attempts.run_id UNIQUE`、`assistant_model_outputs.run_id UNIQUE`；input/receipt/output 不可变 | 物理结构只能容纳一次主模型尝试，无法用增加 for 循环实现 4 轮 |
| `assistant/providers/main.py:44` `build_request` | 固定 system + 单 user JSON，stream=False，只有 content/message_id/quote_sha256 | 无上下文清单、模型历史或 tool result 格式 |
| `assistant/providers/main.py:107` `_decode` | 明确拒绝非空 `tool_calls`；候选只允许文本及最多一条消息引用 | 工具协议必须显式增加受限 codec；不能把模型文本当 shell/函数名执行 |
| `domain.py:2796` `MainSendApproval`；`assistant/native_model_control.py:82` `authorize` | 原生许可绑定 request_id/scope/composer/content SHA；policy 只有该文字 hash，`max_calls=1`；有附件阻断 | 许可不覆盖新查询摘录、既往会话、附件正文或 4 次调用 |
| `assistant/providers/registry.py:160` `_RuntimeLease` 检查系列 | 同一配置/会话 grant 的 lease；更换配置或 revoke 使旧 lease 失效；执行 hash 必须等于获准文字 | 不要通过 basis=None 或重新发 policy 来绕过旧边界；新 context manifest 需要新明确授权类型 |
| `desktop/model-approval.cjs` `snapshot` / `registerModelApproval` | 通过后端读取草稿/能力/材料；原生窗口展示全部文字/接收方/费用；确认后重读并校验 | 新许可应继续用可信后端快照；不能信任 renderer 提交的“已核对”上下文、引用或收件人 |
| `assistant/library_handlers.py:155/234` `begin_library_call` / `execute_library_handler` | 先持久 tool.before 后 I/O，再短事务发布；8 个逻辑 call，包括失败/未完成；只接受服务器 saved UUID | 本机 runner 直接复用，固定仅 search/read_original 两工具；call_id 必须由受信执行器分配并持久关联 |
| `assistant/library_handlers.py:124` `read_saved_citation` | 当前账户和当前/历史范围授权；完整历史快照校验；不访问当前外部法库 | 适合作为引用面板读接口；刷新不得通过 execute 来冒充“读取历史” |
| `assistant/library_handlers.py:61` `_execution` | 当前会话、run active、scope、composer；awaiting_input 不在执行允许列表 | B2 等待许可不能顺手继续工具；需要显式恢复条件与状态转换 |
| `web/assistant.py` `read_events`/SSE、run/by-request/read/cancel | 已有持久游标、短读重验、注销反馈、request 找回 | 复用这些读路径，禁止 GET/轮询/SSE 触发 work |
| `web/assistant_generation.py` | 当前生成/能力/历史接口都以单 attempt 为中心 | 多轮历史需要新有界 run/round DTO；不要让 history join 返回多条后悄悄覆盖 |
| `web/static/assistant-generation.mjs` | pending request、unknown 后只查找、scope/epoch 护栏；有技能或附件时禁止发送 | 复用迟到响应隔离，不去掉所有限制以“支持检索” |
| `web/static/assistant-render.mjs` `renderAttempt` | 只展示内部待核模型候选；引用仅跳至原始输入消息 | 增加法库引用展示必须有新的引用类型和服务器 UUID 校验 |
| `web/static/assistant-materials.mjs` `preview` | 已有右侧面板、previewEpoch、切会话清空、textContent、关闭后焦点恢复、分批渲染 | 可复用布局和隔离模式；建议单独 `assistant-citations.mjs`，不要把业务检索塞入附件模块 |
| `web/library.py:42` `attach_library`；`local_server.py:188` | 有可信本机 library_root 装配；通用库 API 无 run/receipt 关联 | 可在装配处建立一个 `LegalLibraryAdapter`，传入 manager；不要让浏览器选择路径或把通用 API 结果作为 saved citation |
| `ops/workspace_backup.py:303` `_fence`；`local_server.py` 启动恢复 | 已撤销旧 session、封存未知发送、隔离恢复 run，无自动重发 | 新 round 记录必须纳入同一个恢复链，不建后台“续跑历史”服务 |

## 许可和上下文必须先补齐的合同

所有业务 DTO 仍只在 `domain.py` 定义。以下是需设计的概念，不是已经可调用的类型名或已批准 DDL。

1. **不可变外发上下文快照**：run/request、scope 与 composer revision、配置版本、当前文字摘要、所选服务器 saved_citation_id 及其规范内容摘要、实际发送的每段摘录/标题/必要元数据、模板/工具协议版本、完整 wire UTF-8 字节上限、manifest 摘要。必须由服务器从已授权记录构建；模型或网页不能直接上传一份 CitationRef 充当来源身份。引用少于等于8/每段1200只是 B1 数据上限，完整 wire 仍受 config.max_input_bytes 约束。
2. **新的外发批准依据**：在原有原生确认模式中显示实际正文和拟外发摘录、接收方、最多主模型调用数（≤4）、总费用上限、有效期、会话与配置身份，并绑定 manifest 摘要。普通文字旧许可继续只允许一条文字和一次调用，不“兼容升级”为上下文许可。主模型和 Jev 分开；法库快照许可不得自动加入 Jev 的数据范围。
3. **逐轮持久模型记录**：同一个 assistant_run 下 round_no、不可变上下文/线协议摘要、父轮/工具回执引用、预留费用、一次性 send claim、实际回执、最终/工具计划结果。每轮必须先持久 reservation 再 dispatch；不能仅用内存 counter。已有单次表 UNIQUE(run_id)，需要明示版本化迁移或独立的加法 round 表方案；本审查建议保留旧单次表/历史语义，新增仅用于同一 run 的 round 账本，**这不是第二套队列**。具体表设计应与 model_integrity/backup 同片评审，不在本报告锁定。
4. **受限模型回复联合类型**：`final` 与 `library_calls` 两条路径；后者只允许既有两个工具，search 查询使用 `AssistantLibraryQuery`，read_original 只接受本 run 可见 saved UUID。服务器为模型工具请求生成稳定 call_id/event_seq 对应，不能由模型控制幂等身份。未知工具、额外字段、任意文件路径、超限输出拒绝并结算实际响应费用。
5. **最终候选的法库引用**：允许引用的 saved UUID 必须属于本 run、在该轮获准 manifest 中、且来源回执存在；另外可保留现有输入消息引用。由服务器组装展示摘要与定位，模型不能自报“律师审核通过”或更改 source/support/applicability 状态。旧 `MainCitation` 不应被重解释为法库 UUID。
6. **有界历史视图**：当前已授权对话范围、历史 run/message 关联、回执列表/游标、saved citation。读历史快照不要求外部法库在线，也不把快照的 `record_quote_matched` 解释为本次重新验证；当前法库再核对是独立明确操作。跨旧绑定的展示按服务端当前与历史范围权限决定，前端不能只凭 conversation_id 越权，也不能要求所有 input/material revision 永远相等而使正常历史无法读取。

### 外发批准不能被“本地自动查询”扩权

推荐先本机查库，固定选中的摘录，再一次性让律师确认“本次文字＋这些资料＋至多4次调用”。此后只允许使用这个固定获准资料包，模型回答和可见历史也须在既定协议内。后续查询发现新的摘录，允许本机保存及展示；**未经新批准不能进入下一次主模型 wire**。应进入明确等待/阻断状态，现有许可不可用于新增内容。

如果为了体验希望“所有未来本地法库命中自动外发”，那是一个新的、范围更宽的产品许可方案，不是原许可的实施细节；当前材料没有给出这种批准。不能用“法条通常公开”推断整库、案件检索词及组合上下文都已准许外发。

## 建议的最小可验顺序

### B2a：显式本机检索与引用面板（优先建议）

- 新增一个明确的本机 research 提交入口，按 request_id 保存 message/run/初始 tool 事件；同一 request_id 找回原 run，不能把既有 `/messages` 中任意 queued 行当作新执行请求。只支持 `legal_research` 的固定查询合同，不做自然语言任意工具推断。
- 将本机 workflow 纳入同一个 `GenerationTasks` 的生命周期/admission/closing，在同一个 `_tasks` 集合登记；需要小范围把“任务身份”和单 attempt 区分，不能旁建线程队列/守护扫描器。无模型配置时也能执行本机 workflow；`attach_generation` 当前只在 runtime 非空时建 manager，需明确调整装配，不通过伪 MainModelRuntime 获取资格。
- 执行期间复用 `begin_library_call`→`execute_library_handler`；后台阻塞的本机查询可在固定线程执行且不带 DB session，最终发布仍由 B1 重验。完成/失败/取消写既有 run 状态和事件；不创建模型输出，不自动把查询结果称法律结论。
- 在独立薄路由中增加受权回执列表和 saved citation 历史 GET，使用 B1 只读服务；给对话增加“本机检索结果/待核对”卡片。UI只读请求不会产生新 tool.before 或外部法库I/O。
- 引用面板展示原文片段、标题、来源版本/代际、位置及待核状态；复用现有中文阅读与焦点/epoch模式。B1保存的是有界片段，文案不能声称已保存整篇全文；整篇当前原文查看应使用服务器保存的record/version标识再受权读取，并明确是当前重新核对。
- 包含法库离线/代际变化后历史仍可读、0模型调用、恢复副本只读、切案清除/迟到不渲染、CSRF和跨账号拒绝、request未知时仅找回、不重复query事件等合成验收。此片不声称4轮模型完成。

### B2b：固定上下文的一次获准回答

- 先落地上文 context snapshot + 原生批准依据 + 法库候选引用的协议，首个 tracer 只发送一次合成请求。
- 核对原生显示的全文/摘录与最终 wire 摘要相同；确认后新增材料、改草稿、改变所选引用/版本、撤权/停用/换密钥/切会话全部拒绝迟到采用。参考库有新代际时不悄改已批准快照。
- 这是完整多轮的必要界面/权限前提；不能直接改旧 `max_calls=1` 成4而跳过。

### B2c：同一 run 的完整受限循环

- 复用现有 manager，在新受限 runner 模块中串行执行 model round → 固定 library handler → 下轮或final；HTTP只提交/读取，不放循环；原生窗口只负责批准，不直接查库。
- 每个 run 的主模型逻辑轮数最多4，dispatch前在短事务占用唯一 round_no。失败/未知结果不自动重新分配新轮以重试；证明发送前失败可以释放费用，但逻辑轮身份不能被重用成另一次发送。
- 8工具上限继续由B1持久tool.before担任最终核验；失败、未完成也占额度。并行工具先不做。新结果不在获准manifest时先停止外发并等待新许可，不能默默继续。
- 仅最终合法候选可使 run completed；工具计划响应保留已付费用和响应证据，但不充当最终法律意见。到4轮/8工具尚未完成时保存有界停止原因和已有快照，要求律师决定后续，不自动开新run续费。
- Jev仍可选；显式skill不需Jev。自动分流若纳入后片，应读取已核验 decision 并由固定规则选择受限workflow；失败按既有fallback，不让Jev控制批准、版本或数据范围。
- 启动恢复和qxbak恢复均结算/封存round与工具记录，不重新发送任何历史claim；缺失当前法库仅影响新执行，不能使合法历史备份不可读。

## 不可省略的目标反例

| 验证点 | 必须看到的行为 |
|---|---|
| 旧文字许可下新增摘录 | 主模型发送0次；提示需新上下文批准 |
| 原生确认后换引用、输入或配置 | 不发送或不采用迟到结果；保留原有回执/预算真实性 |
| 4→5轮 / 8→9工具 | 持久计数在dispatch前拒绝；刷新/重启/新临时policy不能绕过同run上限 |
| 模型伪造saved UUID/陌生tool/跨run引用 | 固定错误，不运行未知工具、不显示伪来源 |
| 同一request/call/round并发或响应丢失 | 读回既有记录；不创建第二条队列任务；物理本机读取不承诺exactly-once |
| 网络已claim后取消/退出/超时 | 结果未知则保留预算，绝不自动重发 |
| 第2轮撤权/换session/切案 | 下一次claim前拒绝；迟到回复不能写入新scope |
| 工具保存成功而下一轮批准失败 | 可读原引用快照，不伪造模型输出，不触发自动归档 |
| 法库离线和恢复副本 | 已保存片段可读；恢复不能继续任务或刷新来源 |
| 引用面板HTML/脚本/恶意“指令”文本 | 按资料显示，使用textContent或既有安全渲染，不执行内容 |

## 明确未完成 / 工程选择

本报告未设计正式DDL迁移版本或完成任何B2产品功能；不是测试通过证明。以上最小范围仍需根代理将DTO、状态机和验收边界写成短执行合同。没有新增依赖需求，现有 Python/SQLite/前端静态模块与线程调用机制足够承担 B2a；多轮 provider 协议变更应另核对当时官方接口事实，不依赖本报告猜测外部API。

代码中当前只落地 DeepSeek 主provider；“DeepSeek/GPT”产品愿景不能当成已经有第二个provider。也未发现真正使用Jev结果驱动法库查询的代码。建议共享文档继续把这些与B1已实现的本机引用底座分开陈述。
