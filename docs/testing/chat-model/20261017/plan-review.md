# CH-04A 执行计划与 DTO 独立审核

日期：2026-10-17。范围：`docs/plans/2026-10-17-main-model-execution.md`、新增 Main* DTO，参照已批准 v2.1、已复核 readiness、现有 run/save_message、授权、取消、恢复与备份边界。只读检查，无测试、密钥读取或真实外发；未修改产品/测试/其他代理文件。

## Standards

0 项计划层残余问题。DTO 集中于 domain；传输不改旧 Mock 注册器；原件/附件本机政策不放宽；不制造假案件复用 QCC 预算对象；既有 SQLite 与受控迁移继续使用。仅单一 DeepSeek、单条获准消息、内部候选，未扩展 UI/Jev/多来源。

## Spec

初审 1 项遗漏，已由根代理接受并明确补法；落地代码仍须独立复核。

- **P2 — 实际提示与输出契约须进入不可变调用证据。** 初审 MainRequest/config 和 attempt 元数据没有模板或输出契约摘要，固定系统提示变化可能不改变输入、配置和 policy 摘要，与 readiness 第 27 行冲突。根代理已决定新增 `MainPreparedInput(request, wire_payload_json)`；持久化完整规范化 wire JSON，request_sha256 明确为该 UTF-8 字节摘要，enqueue/claim/同键重放重建并逐字比对，同时核对 config/policy 摘要；配置加固定 `protocol_version`；qxbak 校验 wire 摘要、严格 JSON 与消息/模型对应，旧版本不由新 prompt 重算覆盖。该补法足以关闭**计划层**遗漏，不能据此宣称代码已实现或测试通过。

其余检查无新增意见：旧 queued 无自动执行资格；附件选择非空拒绝此首片生成；政策由受信装配提供并绑定身份、内容摘要、期限、预算；unknown usage/cost 不填零；预占、claim、发送、结算分阶段，网络不占 SQLite 写事务；取消/撤权/版本变化禁止成果采用，但受限非正文费用回执可留证；恢复保留 fence 且不补发；cnbak 非空模型表拒绝而非静默遗漏；主模型与后续 Jev 分工符合已批准范围。

后续审核重点仅为确认上述 wire 证据约束真正进入 enqueue、claim、归档校验与失败回归，不需要新增用户设计审批。未发现必须扩展首片范围的前提。
