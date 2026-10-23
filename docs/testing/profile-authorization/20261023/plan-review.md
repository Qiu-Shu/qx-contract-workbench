# C2b2b 内部用途隔离切片：独立计划复核

基线：`60eb041536dc36dfd4133f0d09b909681146500c`。结论：**可行，但只构成内部用途许可，不构成发送/保存链路完成。** 无需新 DTO、第二套 registry、队列或 schema。当前 `MainModelPolicy.allowed_content_sha256s` 已用于 context manifest 摘要，因此可继续承载完整 profile basis 摘要；摘要算法必须直接复用 `profile_preparation.basis_digest`。

## 最小接口与修改范围

1. `MainModelRegistry.grant(..., basis=MainProfileSendBasis)` 增加明确分支：深度重验 basis；policy 的允许摘要必须**精确等于** `(basis_digest(basis),)`，`policy.max_calls == 1`，workspace/config 与当前配置一致且未过期；当前 provider 必须已有 callable `generate_profile`。沿用同一 `(workspace, actor, session)` grant、nonce、配置版本和 `_seen_policies`。一个 policy_id 不得换用途/改保存计划；相同授权重入保持既有幂等，不另开 profile grant 存储。
2. lease 增加 `check_profile_submission(actor, message, rebuilt_basis)`：仅接收 profile grant，完整 basis 相等；核对 request_id、保存前 scope/composer、精确 content SHA，skill/附件为空。数据库真实草稿、当前权限及 profile/intake 基线仍由 C2b2a 服务读取，registry 不复制 SQL 或自行查询 DB。
3. 保存后检查使用 `check_profile_execution(actor, prepared: MainProfilePreparedInput)`；生成走 `lease.provider.generate_profile(prepared, expected_config=...)`，复用该检查。**不能只传 MainProfileRequest**：它没有接待目标/修订、project_intake 和完整保存计划。严格重验 prepared 后，与 grant 的完整 basis 相等；发送前复用 `profile_preparation.build_basis`，用当前精确正文、原提交scope/composer及已绑定的保存计划重建整个basis，与授权basis完全相等；再用现有 profile codec 按当前 config 重建实际 wire，与 prepared 中 wire 逐字节相等，拒绝 model_copy 形成的自洽伪造或模板变化。最终调用既有供应商 `generate_profile(prepared.request, expected_config=config, preflight=...)`，不复制 HTTP 或二次提炼。

主要产品修改可限定 `providers/registry.py`，按需要用一个私有 helper 集中 profile 校验；无需改 MainRequest/V1、domain、profile codec、provider transport 或主程序。新增小范围 registry/合成 provider 测试即可；本报告未实施或运行。

## 必须保持的隔离与失效规则

- 普通无 basis、MainSendApproval、context v1/v2 grant 均不能调用 profile 检查/生成；profile grant 也不能经旧 `check_draft`、`check_submission`、`check_execution`、普通 `generate` 或 context/rounds 入口使用。现有 `check_draft:177` / `check_execution:217` 只特别排除 context，新增 profile 后必须显式排除。`granted_context_format` 不应把 profile 伪称为默认 context v1；该用途下拒绝即可。
- 完整摘要包含目的/handler/version、请求ID、scope/composer、正文、profile基线、intake目标/修订、project_intake、模板/config/wire摘要及字节数。相同正文/相同wire但不同本机保存目标仍须拒绝。不能以 content_sha256 或 wire_sha256 代替 basis_digest。
- 新 profile 发送前回调不能直接照搬现有 `_preflight:232-241`：它只查 loop/version/provider/nonce/basis，**没有检查 policy 到期或 provider.config 原地变化**。闭包应调用实际 `snapshot`、完整 profile 检查和 `require_policy(..., basis_digest)`，异常返回 False。既有供应商在读密钥前后执行 callback；**lease wrapper 在 await 返回后还应独立做最后一次检查**，不依赖替身或未来 provider 自觉复核。撤权/到期/重配置后丢弃候选，保留 received、已收到 usage 与 provider_request_id，标记 BLOCKED_LIVE；不得异常跳出并丢掉费用证据，也不得把 sent_unknown 改记未发送。
- `revoke(session)`、替换 grant、configure/disable、跨 event loop、改 config 与同一 session 的用途切换，都必须使旧 lease 失效；外部传来的可变对象须先复制深验。缺少供应商 `generate_profile` 能力应拒绝，不回退普通 generate 或更换供应商。
- 此片只提供 registry 内的会话绑定及撤销，不证明数据库 session 仍有效、案件权限未撤或资料版本未变。不得给旧 `MainModelRuntime` 增加无操作的 profile 许可方法来绕过 registry；整体接线仍须由 C2b2a/current actor 在登记、claim、结算时实际复核。

## 后续整体接线仍不可省略

registry 不消耗 max_calls、不形成持久费用预留，也不保证同一许可只调用一次；`max_calls == 1` 是此用途的许可约束，不等于已落实一次性claim。数据库当前权限、预算和claim职责仍在后续持久服务，不能把新内部 generate_profile 直接暴露到 UI/HTTP/native。后续必须在已有 attempt 生命周期闭合相同 basis 的登记→claim→发送→费用回执→固定 response.ready/profile.save 原子保存，保留失败/未知发送不重试、阻断回执终态及语义历史重放，然后才可解除 model_integrity guard。预算预留与供应商实际收费保持区别。不得宣称本片已能自动存档。

## 建议目标测试

- profile 正常许可→草稿检查→可信 prepared→单次合成调用；wire/配置/用途摘要一致。
- 普通、context v1/v2、profile 三类许可双向错用，另测无 basis 和旧 MainModelRuntime 不获新能力。
- 相同文字但变更 project_intake/目标/修订/档案基线/request/scope/composer/template/wire，全部拒绝；同 policy_id 改目的/内容不复活。
- 同 grant 幂等、替换/撤销/重配置/过期使旧 lease 失效；配置在密钥解析期间改变、policy 在发送前/响应期间到期也拒绝，晚到结果保留 usage 而不保留候选；故意忽略 preflight 的合成 provider 返回候选时，wrapper 仍独立丢弃。
- profile policy.max_calls 非1或配置provider没有 callable generate_profile，在 grant 阶段就拒绝，不影响旧用途的原计数约束。
- 跨 actor/workspace/session/loop、伪造 DTO、缺少 generate_profile、错误 expected_config 均失败关闭且不输出内容/密钥。
- 静态确认 native/HTTP/runner/ledger/guard 未开启，旧文本/context 许可行为不改。

只读设计评估；未改产品、未测试、未提交，未调用 WorkBuddy 或真实供应商。现有记忆仅用于定位，结论以当前源码和 C2a/C2b1/C2b2a 契约为据。
