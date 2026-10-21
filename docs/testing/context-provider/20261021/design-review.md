# CH-06B2b2 首片：上下文 DTO / 纯 codec / 共享传输设计复核

基线 `aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9`，工作目录 `D:\Documents\ChatGPT\律所项目`。只读核对当前源码、既定存储设计及相关记忆，使用 ponytail/codebase-design 与 CodeGraph 定位；没有运行产品测试、联网、WorkBuddy、配置或真实资料操作。本文是实施建议，不是已实现或通过。

## 结论

本片可以独立闭合纯 DTO/codec 与可注入合成传输，但必须继续让应用发送入口关闭。新增一套严格上下文类型，复用已有 Manifest/Preview 和现有 DeepSeek HTTP 实现；旧 MainRequest/MainPreparedInput/MainCandidate/MainReply/MainModelPolicy 的定义及规范 JSON 不动。下一片统一实现格式列、许可、来源关系、原生确认及归档，不能先把新对象送入现有 attempts/runner。

## 最小字段契约（全部业务 DTO 放 domain.py）

命名可调整，语义不能省略。建议按下面结构各存一份内容，避免在多个对象中复制完整 manifest：

| 类型 | 必需内容与不变量 |
| --- | --- |
| `MainContextCitation` | `saved_citation_id: UUID`、`quote_sha256: SHA256`；仅用于供应商候选引用，不允许原文、路径、审核状态或工具字段。 |
| `MainContextSourceBinding` | `saved_citation_id: UUID`、`citation_sha256: SHA256`；本机有序证明，后一个摘要严格定义为 `sha(encoded(saved.citation))`，与既有 library ledger 的完整 `citation_json` 一致。不能以 quote hash 替代，也不需要把整份 CitationRef 再复制到新表。 |
| `MainContextSendBasis` | `request_id`、`expected_scope`、`expected_composer_revision`、明确 `input_format='library-context-v1'`、固定 `codec_version`/`template_version`、`system_sha256`、`manifest_sha256`、有序 `source_bindings`（1—8、UUID唯一）、`config_sha256`、`wire_sha256`。这是描述待批准内容的不可变数据，构造成功不代表已获授权。 |
| `MainContextRequest` | `run_id`、`message_id`、登记后的 `scope`、`manifest: MainContextManifest`、`basis: MainContextSendBasis`。问题只存 manifest.question，不另造可分歧的 content。`scope` 必须是 basis.expected_scope 仅 input_revision 加1，其余字段完全相同；run/message ID由可信登记器产生。 |
| `MainContextPreparedInput` | 明确格式/codec版本（可固定在 basis，只要能与未来数据库 input_format 精确核对）、`request`、`wire_payload_json`；wire UTF-8字节摘要必须等于basis.wire_sha256，不能仅检查JSON自洽。预览状态与sending_enabled不必作为第二份对象持久化。 |
| `MainContextCandidate` | 非空 `text`，`citations: tuple[MainContextCitation,...]`，0—8条、UUID不重复；每项UUID及quote hash必须同时匹配本次manifest同一项。未知、交换hash、重复、额外字段一律拒绝。空引用允许，不等于答案已获证实。 |
| `MainContextReply` | 与MainReply同state、provider_request_id、MainUsage、固定error_code及一致性规则，output只接受MainContextCandidate。可复用MainUsage/MainReceipt和费用纯函数；不可扩宽V1 Reply的output联合类型。 |

固定字面值要区分：已有 manifest 的 `saved-library-context-v1` 是外发文档格式；未来行的 `library-context-v1` 是attempt输入身份；`assistant-context-v1` 是数据库schema。不要用可选字段存在与否猜测这三个身份。

basis摘要 `approval_sha256 = sha(canonical_json(basis))` 在外层策略中保存，basis本身不包含自己的摘要，避免循环。完整config摘要沿用现有 `sha(encoded(MainModelConfig))`，包括所有限额、价格和说明字段，不只是模型名。原生config_version及注册表nonce仍用于活动许可新鲜度，不应被持久hash取代。

## 纯 codec 接口

1. `prepare_context(request, config) -> MainContextPreparedInput`：先按确切类型重新验证（不能信任 model_construct/model_copy 或子类）；复用 `build_preview(manifest, basis.expected_scope, basis.expected_composer_revision, config)` 重建，而非信任传入Preview.wire。要求ready；拒绝disabled、超限、config/manifest/template/system/wire摘要不符。只允许完整预算，不截断。旧preview `_SYSTEM` 原字节可以固定为模板v1，后续变更新增模板版本，不能覆盖历史映射。
2. 校验 `source_bindings` 的UUID顺序严格等于manifest.sources；完整CitationRef摘要只有拿到可信源记录才可核验。可另设纯 `validate_context_sources(manifest, bindings, saved_records)`，复用 `library_records.encoded` 与 `project_source`，逐项重算摘要/投影/保存范围。需要包含保存范围与expected_scope的原有绑定、revision约束。不能声称仅凭Preview已证明完整来源身份。
3. `decode_context_response(raw, request, config, secret)`：复用现有严格JSON资源限额、重复key拒绝、供应商identity/model/choices/finish_reason/usage验证；仅替换候选DTO及引用集合验证。合法usage即使候选非法仍保留received回执；secret反射沿用现有清除规则；无工具调用、无推理内容、无额外输出字段。
4. 后续历史验证用保存的config、basis、manifest及来源记录；不查当前法库、当前草稿、活动grant或墙上时间。当前执行另做授权/撤销/取消/fence检查。两个语义不得合并。

预览wire完全由模板+manifest+config决定，不含将来才生成的run/message UUID。这样登记只增加本机封套；此前律师看到并批准的wire字节保持一致。现有save_message还会把composer_revision加1并清空草稿，后续claim需要检查这个确定后继值，不能误比登记前值或放过任意最新值。

## 许可预核验

本片可以实现**纯预核验**，不登记grant、不接NativeModelControl/registry/HTTP。建议独立 `MainContextPolicy`（policy_id/workspace_id/actor_id/config_sha256/approved_basis_sha256/max_total_usd/max_calls/expires_at，首版max_calls固定1），不要把上下文hash偷偷放进V1 allowed_content_sha256s再共用旧许可。

`require_context_policy(config, policy, actor, request, *, now)` 检查确切DTO、配置enabled、actor/workspace、完整config摘要、basis摘要、expires_at>now、预算>=既有reservation(config)、max_calls=1及prepare_context全部不变量。明确now为UTC输入，纯函数不读系统时钟/DB/密钥/网络。它只证明传入策略与输入一致；当前真实授权仍须下一片registry的session/config版本/撤销nonce和持久claim。单靠构造可用policy或此函数返回成功不能发送。

## 共享 DeepSeek 传输拆分

推荐把 main.py 中严格JSON/供应商响应封套与有界HTTP移到私有共享模块，普通/上下文provider各只有固定build与decode选择；不造可由网页传URL、模板、codec名字或回调的通用发送API。原 `DeepSeekProvider` 导入路径、`build_request`、`_strict_json` 等现有使用位置保留兼容导出或精确更新已知caller；`model_integrity.py`直接导入main._strict_json，Jev测试还调用main._protect_logs，不能漏。

必须原样保留：固定正式endpoint、显式合成loopback工厂、发送前config相等和enabled检查、延迟解析密钥及httpx2导入、trust_env=false/retries=0/禁止重定向、整体/连接超时、响应原始字节上限、编码/secret反射保护、日志ContextVar、CancelledError继续抛出；进入传输后的异常为sent_unknown，不能轻率改成未发送。旧V1 wire/错误状态及usage处理必须保持。

暂不让MainModelRegistry接受新provider或让旧generate接受ContextRequest；现有 `_LeaseProvider.generate`、attempts、runner均严格V1。新上下文adapter只是独立底座，应用接线仍零入口。下一片再对同一注册表/队列明确分派，无第二套attempt/队列/费用账本。

## 下片存储接续与最小验收建议

- 新PreparedInput完整存入既有attempt.input_json；既有config_json/policy_json继续各存一份。input_format不可变列和一张 `(attempt_id,ordinal,saved_citation_id)` 表即可，无manifest表。读取/claim/backup同时验证行格式、basis有序绑定、manifest投影、关联精确集合及原citation摘要。
- 旧V1冻结973字节与历史hash不变；新context不能由V1 request/prepared/registry接受，preview始终sending_enabled=false；当前应用入口探针证明不调用新provider。
- 纯codec重点负例：同quote不同完整citation、同UUID换版本/顺序、manifest/system/template/config价格或预算变更、超限UTF-8、非法post-scope、伪造DTO、候选UUID/hash调换、重复key与恶意资料字段。
- 共享传输只做少量有意义合成回环，比较旧V1真实发送字节及错误/usage状态；新候选合法/非法、秘密反射、超时/断开不重试各有目标覆盖。许可预核验不被当成当前合法发送证明。

尚未实施以上DTO/codec/schema或运行测试；本片不宣称完成一次资料辅助回答。核心风险是把自洽预览当授权、把quote摘要当完整来源摘要、重构HTTP时丢失旧账本的保守状态语义，以及未来升级后无法重建旧模板。
