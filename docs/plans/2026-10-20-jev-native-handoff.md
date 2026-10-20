# CH-05 下一切片：Jev 原生配置、逐请求授权与可选前置阶段

基线：`3d53f2f5a012f1f9a344203ad194b9b438864c5b`；2026-10-20。开始时工作树干净。只读 CodeGraph/源码核对，未运行产品测试、构建、真实供应商请求或旧回归；初稿为本机只读报告；本次同步到仓库供协作，不表示产品已实现。沿既有 v2.1、CH-05A/B，不重新论证 Jev 必要性。

2026-10-20执行更新：第2节第一片已完成为 CH-05C，见[实施交接](2026-10-20-jev-native-implementation.md)和[实际证据](../testing/jev-native/20261020/README.md)。以下保留原方案口径；第3–4节第二片CH-05D尚未实施，不能把本片配置验收当作辅助发送完成。

## 建议结论

**先交付完整的“原生配置生命周期”，再交付“独立逐请求批准＋同一主任务中的可选前置阶段”。** 两个切片各有完整验收结果，不能把只多一个设置输入框称为 Jev 已接入。

第一片范围：独立受保护凭据、可信设置页、同一私有父子管道、配置/停用/换钥匙、配置版本、安全状态、窗口/后端退出时失效。可完整离线验收；不创建 JudgePolicy、不运行 judge、不扩展数据库 schema。

第二片范围：确认时后端将保存前草稿绑定到保存后的精确 JudgeRequest，建立独立 TypeSafe policy，再在现有 GenerationTasks 的一个 task 中 reserve→execute_judge_attempt→既有主模型。缺少辅助许可或判断失败时按当前已批准主流程继续。无需第二 registry、队列、后台扫描器或外网探测。

## 1. 当前可复用事实

| 已有代码 | 可复用能力 / 明确限制 |
|---|---|
| `desktop/model-credentials.cjs:12 createModelCredentialStore` | Windows safeStorage 异步加解密、受限路径、单链接文件、原子替换、withSecret 回调及串行操作已有；文件名目前硬编码 `model-credentials/deepseek.bin` |
| `desktop/model-settings.cjs:17 registerModelSettings` | 仅可信设置文档可调用，异步前后 guard；改密钥前先 disable；对外只回安全状态。模型结果白名单目前只支持 DeepSeek |
| `desktop/model-session.cjs:32 createModelSession` | 配置清旧权、私有 secret 消费、后台 identity/配置版本、失效窗口拒用、失败关闭。configuration/reservation/withAuthorization 仍是主模型专用，不能照搬价目或授权 |
| `desktop/model-control.cjs:36 ModelControl` 与 `backend.cjs:52` | 单父子管道、nonce、sequence、长度、一次 pending、精确回包、超时/坏帧停止进程；目前只有 Main configure/disable/authorize/revoke |
| `src/cn_contract/desktop_control.py:63 ParentControlChannel` | 在应用事件循环执行控制操作，不创建 HTTP 密钥入口；close 和未预期异常当前仅调用 handler.disable() |
| `desktop_entry.py:102-107` | MainModelRegistry 与 NativeModelControl 的可信装配点已存在；新 Jev 复用该入口，不另启后端 |
| `assistant/native_model_control.py:53 configure/:82 authorize` | 后端认证 cookie、查真实草稿、配置版本、前后 scope、请求摘要、有效期；_intents 留 fingerprint/token 墓碑，避免长期保留旧 provider/secret |
| `providers/judge_policy.py:53 JudgeRuntime` | 已有 configure/grant/revoke、事件循环绑定、配置与授权 UUID、ABA 失效、policy ID 禁止改义；无需再新建 JevRegistry |
| `judge_policy.py:134 snapshot_for` | policy 精确绑定 actor/session/workspace/config 与 local_request_id/purpose/input_hash；不同于 Main 的内容摘要授权 |
| `judge_attempts.py:36 request_for_run` | 从已保存用户消息构造完整 JudgeRequest；local_request_id=run.request_id；只支持无附件文字 primary_intent，显式技能跳过 |
| `judge_execution.py:11 execute_attempt` | 已有持久 claim、事务外网络、发送前权限/预算 preflight、取消保留已收到证据、settle；可直接作为前置协程调用 |
| `task_manager.py:61 submit` | 一个提交只创建一个 asyncio task，运行前已提交主 attempt；重放返回历史且不调度；当前尚不接 JudgeRuntime |

主模型政策、DeepSeek 密钥及“允许本机处理”的材料 policy 都不能授权 TypeSafe。`domain.py:2668 AssistantMaterialPolicy` 当前明确 external_processing=False；第一轮原生 Jev 仍坚持无附件文字，不把上传能力与外发许可混为一谈。

## 2. 第一片：原生配置生命周期的最小完整范围

### 2.1 凭据：复用实现，独立身份

在现有 credential store 工厂增加**后端固定白名单**的供应商选项，映射 `deepseek.bin` 与独立 `typesafe.bin`；不接受 renderer 自定路径/文件名，不复制整套文件安全实现。DeepSeek 的既有文件及读取语义保持兼容。

Jev 新密文建议加受保护的 `format/provider/secret` envelope，读取时强制 provider=typesafe。只靠不同文件名仍可能把复制错位置的密文解密成另一个厂商的有效字符串并发送。旧 DeepSeek 裸密钥兼容只限其原供应商；不能作为 TypeSafe 格式回退。密钥不进入 DB、备份工作区、URL、命令行、环境、日志、网页 storage 或返回状态；withSecret 的回调结果不向 renderer 暴露。

第一次保存可在可信原生设置页输入秘密；保存后不回显。保存/删除前先清除现有 Jev runtime 与授权，得到明确 disable 回执后才变更密文；新密文读取失败时不能继续沿用旧运行身份。配置只读取已有受保护密文并经私有管道发给 Python，不做 API “连通性检查”。

### 2.2 私有控制：同一通道、固定新增操作

在现有协议解析器与 Backend facade 增加固定 `configure_judge / disable_judge` 操作；第二片再增加 authorize_judge/revoke_judge。名称只是建议，关键是操作不靠 payload 猜类型，也不把 Main Literal 放宽为任意对象。复用 nonce、sequence、字节上限、固定返回与失败关闭。

Python 可新增小的 `native_judge_control.py`，仅处理 Jev DTO/配置版本和现有 JudgeRuntime；在原装配点用固定控制分派把 Main 与 Judge 接到同一 channel。该分派不是 registry/队列。

生命周期需显式 `disable_all`：父管道 EOF、关闭、未预期处理异常或协议故障清除两类运行身份；普通 disable-main/disable-judge 只停对应能力，不能相互暗中授予/撤销。`ParentControlChannel.close:80`、`_dispatch:108` 当前仅 disable-main，是必改接点。

协议版本/能力声明需与两端一起更新。不能把旧 `control.enabled` 解释为已经支持 Judge，然后给旧后端发送它无法识别的新帧。采用固定新协议版本或有限能力标记，旧后端的 Jev 设置显示不可用；不得在未知 operation 时忽略检查继续发送。一次 pipe pending 的串行边界保持，Main/Judge 不抢同一 sequence。

### 2.3 配置：不顺便授权

新增 NativeJudgeConfigure/安全状态 DTO，仍放 domain.py。秘密只留受信任 provider 所需生命周期；native control 持有的配置版本只标识当前装配，不包含 secret。`JevConfig` 固定 `jev-1.13.0`、现有总截止/字节限制，状态可为未配置/已配置/不可用；“已配置”只说明本地配置成立，不是供应商连通、余额或费用验证。

使用现有 JudgeRuntime.configure(None/provider)，每次配置都撤旧 policy、改变授权 UUID；重新使用同一密钥/同一配置也必须使旧授权无效。不要在旧 runtime 外再加一个平行 JevRegistry。设置窗口过期、后台更换、配置 ACK 不确定或禁用失败，延用现有 fail-closed 行为；可确认的配置错误只影响 Jev，但无法确认旧 secret/权力是否已清掉的私有管道故障仍可停止整个子进程。

设置可显示“Jev 辅助判断（可选）”“已保存密钥”“本次运行已配置；尚未批准发送”。不要显示“已连接”“免费”“已获得法律判断能力”。配置后前端对话仍使用原 Main 路径。

### 2.4 这一片的完成证据

独立合成凭据可保存、配置、停用、换钥匙、删除；窗口导航、迟到 ACK、后端更换、坏帧/EOF 使旧配置失效；DeepSeek 与 TypeSafe 密文/操作隔离。源码与冻结程序可通过私有管道实际收回配置版本，不接外网；默认启动不读取/初始化 Jev 网络客户端。普通 renderer 无权配置、不能取回 secret；受保护目录不进入工作区备份。

这是一片完整可交付的配置生命周期。它不证明逐请求授权、实际辅助判断或主流程前置已经完成。

## 3. 第二片：每请求 policy basis 的精确转换

第一片不自动产生任何 policy。第二片复用主批准窗口的 before/after 草稿读取与 guard，但接收方、用途、费用语义及同意项必须独立。不能一次点击“允许 DeepSeek”就默认为勾选 TypeSafe。

新增 Jev 独立 basis：request_id、保存前 expected_scope、expected_composer_revision、content_sha256、purpose=primary_intent，以及期望 Jev config_version；权限由 Python 基于真实草稿构造，renderer 不提交已完成 policy/input_hash/actor/session/允许材料列表。

后端 authorize_judge 的确定算法：

1. authenticate 当前 session token；按同一会话/用户读取 conversation，检查可写存储与 scope/composer revision；草稿非空、无附件、无显式技能、摘要匹配。
2. 读取当前 Jev 配置与版本；校验调用方确认的版本。固定 purpose 为 primary_intent。
3. 仅预测 save_message 的确定变换：`post_scope = expected_scope`，只将 input_revision 加 1，其余 workspace/conversation/binding/materials/scope_ref 原样保持。建立 `JudgeRequest(local_request_id=basis.request_id, scope=post_scope, text=真实完整草稿, purpose='primary_intent', explicit_skill=None)`。
4. 用现有 `jev_codec.input_hash(request, config)` 得到许可摘要；不能用 content_sha256 替代，该摘要还绑定请求 ID、scope、purpose、配置与模板版本。
5. 构造现有 JudgePolicy：固定 recipient、当前 actor/session/workspace、一个 permission、max_calls=1、明确预留和有效期；交给既有 JudgeRuntime.grant。
6. 保存后 `request_for_run` 重新从已持久消息构造请求，必须与批准预测逐字段及 hash 一致。没有匹配许可则跳过 Jev，绝不迁就新输入改写政策。

批准操作的 request_id/fingerprint 墓碑模式可复用 NativeModelControl：相同请求不同内容/config/purpose/会话拒绝；撤权或重配后的旧授权不能借相同 payload“再确认一次”复活。已存在 run 的请求最多返回 historical existing，不能给旧 queued/interrupted run 补授执行能力。墓碑仅存摘要和短 token/version，不保留 retired provider、密钥或草稿全文。

**当前 JudgeRuntime 只有一个 `_policy` 槽。** 配置生命周期可直接复用；接逐请求批准时不能假装已有多会话租约。最小首版可明确限制一个待执行辅助许可：另一个请求/会话在前一辅助调用未收尾时不覆盖它，而是跳过辅助并保留主流程；不排进第二队列。已有同一请求的幂等重放应成功，其他请求不能替换正在使用的政策。以后确需并行授权，在既有 JudgeRuntime 内扩展按 session/request 的 grant 与固定 lease，先调整 exact-type 调用契约；不要新造另一个 registry 保存同一批权限。

revoke_judge 必须认证 session，且只撤该 session 持有的许可；当前无参数 JudgeRuntime.revoke 不等于任何已登录用户都能撤其他人的 policy。停用/换钥匙则可信设置层可使所有旧授权失效。恢复副本仍受现有 fence、失效 session 和空 runtime 限制，不能由密文存在自动恢复授权。

## 4. 前置阶段：原有一个 task 内完成

在原 `GenerationTasks.submit` 事务先按原逻辑保存 Main attempt，再尝试为同一 run reserve 可选 Jev attempt。已提交历史 request_id 仍直接返回原记录，不新建辅助调用。无配置/无许可/无预算/不需要等可预期辅助拒绝，只影响辅助；不能把此类异常冒泡使原主提交回滚。存储损坏、事务已失效或身份主校验失败则不能吞掉并继续。

事务成功提交后仍只创建一个任务：先执行已持久化的 judge attempt，再执行原 Main attempt。调用现成 judge_execution.execute_attempt，其内部维护 deadline 和收到回执；**不要再包更短外层 timeout 截断已收到的账务证据**。Jev timed_out/failed/invalid/无建议均继续当前主 runtime；不得切供应商、删除原请求、修改 Main output 契约或替用户选择其他案件。

主 runtime 租约必须在原提交时固定；Jev 等待结束后主 attempt 的 claim 仍重新检查当前会话、原授权、scope、取消、配置和预算。用户已取消/退出或权限失效时停止主调用，这是主流程自身限制，不是“Jev 失败阻断”。收到判断但 scope/授权已失效时只保留 receipt，不采用 decision。

关闭/取消需要处理同一 run 的两类 reserved 记录：未启动辅助释放预留；已发送由原 judge runner 收尾并保留未知占用；主未发送按既有逻辑释放。一个 manager task 的 `_finished/_release_unsent` 清理两种 reservation，不增一个 task manager。网络 await 期间两种 DB 事务都关闭。

本阶段可显示已记录的辅助状态/初始流程建议，但 CH-06 工具编排尚未接通时不能声称“Jev 自动调用了业务技能”。现有 task_manager 拒绝 requested_skill 的行为是另一明确接口边界，不能为接 Jev 顺带删掉限制后假装全部技能可运行。

## 5. 真实费用未知的产品表达

现有 JudgePolicy.reserved_usd/max_total_usd 控制本机预算占用；JudgeReceipt 只有 not_sent/unknown，收到 tokens 也仍不计算已收费用。这是诚实的当前能力。

不要照搬主窗口的 `max_total_usd` 展示为“本次最高收费”。预留金额没有在 TypeSafe 请求中成为厂商硬上限，也没有账号账单对账；它只能决定本程序还能否再发一次请求。建议确认文案为：“本次允许将这段文字发给 TypeSafe，用于判断首个处理流程。程序将预留 X 美元预算；这不是供应商收费上限，实际费用尚未核对。”

真实调用入口在未确认账户许可、价目来源和可接受预算前保持关闭；本轮预留只是独立合成值，不能把某个任意常量当作正式价格。后续若使用真实预留，配置来源及知情预算选择需可追溯；不因输入少或输出计价为零就声称免费。

Jev 的许可与主费用分别成立。拒绝/未勾选辅助时不应连带取消已经确认的主流程；可以在一个原生确认窗里分别呈现收件方与可选项，默认辅助未选。不要新增频繁的逐字段弹窗；但也不能把现有只指向 DeepSeek 的按钮文案偷偷扩大到 TypeSafe。

## 6. 下一实施片建议与验收边界

建议本轮先落第一片：凭据工厂固定供应商隔离、Jev 配置控制/状态与设置页、同一私有管道分派、全生命周期失效及合成私有进程验证。它不依赖新的 grant 并行设计、不改已封存的账本 schema，能够独立做完；随后按第 3–4 节补逐请求许可和可选前置。

第二片最小验收至少覆盖：保存前后 scope 精确转换；相同 basis 幂等与变更拒绝；主许可不能开 Jev；会话/撤权/重配/ABA 旧 runtime 失效；没有辅助许可时主流程照常；一个 task 两个账本、一次辅助 POST；超时/未知费用与采用分离；取消/关闭前后不复活旧运行。所有输入和端点用独立合成与本机回环，禁止借验收读取真实密钥或向外部模型发送。

本报告没有执行上述验收，不能当作运行通过。历史 CH-05A/B 验证已经完成；下一片只跑受新改动影响的验证，不据记忆摘要重复整个历史回归。
