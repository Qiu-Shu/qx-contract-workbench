# CH-04A：受控单次生成与费用回执

基线 `114a1ab`。接续已批准 v2.1 与已独立复核的 `2026-10-17-main-model-readiness.md`，沿现有分支实施；不重新访谈。Ponytail／implement／codebase-design／TDD 用于限定改动和验证既定接口。

本片打通应用服务到单一 DeepSeek 适配器的完整闭环；先完整校验非流式 JSON，再保存内部待核候选。首片只发送当前一条已获准消息，附件保持本机处理，已有材料选择非空时拒绝生成。历史上下文、多来源材料授权、客户成果、页面发送、Jev、工具和自动档案随后接入，不用本片结果冒充它们已完成。

## 接口与执行资格

- `enqueue_generation(actor, conversation_id, message_request, db, runtime) -> MainAttemptView`：复用既有 `save_message`，在同一短事务登记消息、run、不可变输入和预算预占。只有本入口新登记的 run 才产生可执行 attempt；旧 queued 不自动取得资格。原请求重放先找原回执，仍查当前身份，同键不同输入或配置／策略拒绝。
- `execute_attempt(actor, attempt_id, database, runtime) -> MainAttemptView`：准备、原子 claim、网络等待、结算各阶段分开；发送前及落成果前重新核验身份、作用域、当前策略和恢复 fence。claim 后进程中断保守为已发出未知；本接口再次调用不重发。
- `read_attempt(actor, attempt_id, db) -> MainAttemptView`：当前用户及业务权限核验后读取；费用回执不包含模型正文，只有独立且已通过校验的成果表保存正文，防止未采用结果从账本旁路展示。
- `recover_attempts(db)`：受信启动／恢复维护将 reserved 封为未发送，将 sending 置为 sent_unknown；不调用网络。恢复副本继续只读，旧会话撤销。

`MainModelRuntime` 是受信装配对象，持有 provider 和可由管理员替换的当前 policy；HTTP 输入不能创建它。每次准备和提交重新读取当前配置／policy，绑定不可变摘要。当前没有设置页或生产装配，默认不配置、不发送；测试显式构造只含合成消息摘要的政策，不能由 renderer 声明 synthetic 自证。

`MainPreparedInput` 保存本次 `MainRequest` 与实际规范化 HTTP JSON；摘要覆盖系统提示词、输出契约、模型参数及原文，不仅是律师输入。`protocol_version=deepseek-chat-json-v1` 绑定当前协议。重放／claim 重建相同字节核对，提示词或契约变化拒绝沿用旧资格；未来变更需要保留历史协议重建器，不能覆盖历史正文。

政策绑定 workspace、actor、config 摘要、允许的消息 SHA256 集合、截止时间、总 USD 上限和调用次数。政策 ID 复用但内容不同必须拒绝，换 ID 不属于用户请求重试。政策是本片可核验的明确授权输入，后续统一设置页需要受信持久配置，不扫描其他工具密钥。

## 传输、成果与费用

`DeepSeekProvider(config, secret_resolver)` 使用现有 httpx2 2.13.1。`build_request` 纯函数生成固定 JSON 并核对整个 UTF-8 请求大小；`generate` 只做供应商调用、严格解析和安全回执。默认固定官方 HTTPS 地址；独立测试构造仅允许明确的 loopback，正式默认不可接收任意 URL。凭据仅由受信 resolver 提供，不进入配置、账本、日志或错误。零自动 POST 重试，无代理环境、跳转和工具；流式保持关闭，thinking 显式关闭。总截止独立于逐次读超时，防止空行保活无限等待。

运行器调用 `generate(request, expected_config=claim_config)`；适配器重新核对当前配置与 claim 快照一致，之后始终使用已验证的局部快照，不能在 claim 后重新挑选模型或增加输出量。没有配置变化权限的请求端不能创建或覆盖这些参数。

模型输出只有 `text` 和本次消息的 `message_id/quote_sha256` 引用；extra forbid。受众 internal、生成类型 model_generated、审核状态 unverified 由应用固定，模型无确认事实或正式签发权限。合法 usage 与合法正文分开：无效正文不抹去已获得的使用量；usage 缺失仍是未知费用。

预占采用配置的输入单价 × 输入字节上限，加输出单价 × 最大输出 token。这是本片保守预占策略，没有把 UTF-8 字节数证明为供应商计费 token 的严格上界。收到 usage 后检查是否超界；超界保留真实估算账本、拒绝采用正文，若超总预算则再次 claim 前阻断其他排队请求。自动记账不是供应商确认账单；缓存未折扣、价格峰谷不自动推测。未知发送／未知 usage 保留预占，不能改成零。每个 token 计数严格限制在 0 至 2^31−1；不合规计数按无效响应处理，费用保持未知。Decimal 运算与回执构造隔离调用者精度和陷阱；已锁定的 httpx2 仅提升为显式直接依赖，不安装新包。

网络和 SQLite 不能原子完成。发出前持久一次性 claim；超时、取消等待、崩溃等无法证明未发出则保留未知。取消／撤权／输入变化不再保存当前成果，但已 claim 的受限结算通道可以保存该次非正文回执，不能读取其他材料或写档案。恢复 fence 拒绝运行器所有写入。

未 claim 的取消在同一事务释放预占与次数，形成未发送回执；已 claim 的取消保留未知或实际使用量。部分权限拒绝会提交审计并结束原事务，结算在此之后必须重新取得短事务、检查恢复 fence 与一次性 claim，不能沿用事务中断前的检查结果。

## 追加结构与兼容

新增 `assistant_model_attempts`、`assistant_model_receipts`、`assistant_model_outputs`，精确 schema 版本 `assistant-model-v1`；冻结旧 attachments-v1 参考，受控迁移不重写历史 DDL。attempt 的输入、配置、政策、预占和归属不可变，首次 claim 不可换；回执和成果追加且不可删除。

qxbak 校验归属、JSON、摘要、状态、费用与输出对应关系并完整保留；恢复封存任务。cnbak 仍为旧合成合同契约，对非空 model 表明确拒绝，不静默漏备。旧库和旧归档按各自结构先验证再升级隔离副本。

## 分工与验证顺序

1. 根代理：domain DTO、策略／attempt 服务、runner、归档完整性与 ops 对接、主链故障测试；集中业务 DTO，不改旧 Mock 白名单。
2. 协议代理：官方协议证据、`assistant/providers/main.py` 与真实 loopback HTTP 测试；不读真实 key、不调用真实模型。
3. 存储代理：新 DDL、旧附件固定参考、升级链、schema／迁移测试；不与根代理并改业务文件。
4. 独立复核：源码双轴检查，实际问题有回归证据后关闭。WorkBuddy 本轮状态无 live endpoint，未派发任务，不能引用历史回执。

关键验收：并发同键只发送一次；不同输入拒绝；预算与次数并发；旧 queued 拒绝；未配置/政策过期/local-only 附件零请求；网络期间独立接待写入与取消不被长事务阻塞；撤权/取消/改输入/改policy 后只记非正文回执；unknown 不重试/不归零；严格 JSON/引用/受众；慢读/保活总截止；重启和恢复零补发；原件、旧结构与已有流程兼容。

先针对接口逐个失败验证，根代理汇合后目标回归、独立复核、最终完整回归和新冻结 Windows 后端验证。最后更新 TASK_STATUS、执行记录和实际证据，本地提交。保持现有安装版和真实工作区不动，不自动安装更新或推送云端。
