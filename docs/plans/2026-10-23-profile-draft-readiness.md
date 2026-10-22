# CH-07 只读设计复核：档案合并与接待投影

核对时间：2026-10-23（本机）；基线 `1a73e36f687b6dc0eab98892149737c02e8d9ce6`。只读设计，不是已实现或已运行测试的证据。未运行产品测试、模型请求、外网、导入或真实资料读取；仅新增本报告。

依据：`docs/plans/chat-first-architecture-v2.1.md` 第 5、10 节及 CH-07；当前 TODO；CodeGraph 返回的当前源码。采用 ponytail 与 codebase-design 的最小充分改动、纯返回值和小 interface 原则。历史记忆只作背景，以本次源码为准。

## 结论

先复用现有接待，增加“来源与人工保护覆盖层”，不创建另一套可独立编辑的接待记录。`IntakeDraft` 仍是接待常用字段的唯一投影类型；档案修订保存提案、逐字段出处、待核/冲突、保护元数据及投影回执。

建议先做有明确交付边界的纯合并内核 CH-07A，再做不可拆开的持久化闭环。纯内核只有在实现实际合并/来源/保护/映射行为并经测试后才有价值，不应仅建 DTO、空服务和未调用的占位方法。其完成不等于“自动建档已经可用”。

主代理本轮已选更小前置 **CH-00A3 接待依赖解耦**：将 `web.services.create_matter` 原行为下沉到非 Web 应用 module，`web.storage.now/encode/sha` 原语义下沉通用 codec，旧模块保留兼容别名；接待直接依赖下沉实现，Word 依赖延迟到导出。此方向合理，避免未来档案 module 继承整个 Web/审查/导出依赖。该片应测冷导入前后和行为/字节兼容，不能把拆文件当作安装包已减小。本报告不修改相关代码。

## 1. 当前可直接复用与不能直接套用的内容

| 位置 | 已核实能力 | CH-07 使用方式 |
|---|---|---|
| `domain.py:1532–1579` | `IntakeText/IntakeLabel` 限长、`IntakeMaterial`、`IntakeDraft`、`IntakeCreateInput/IntakeUpdateInput/IntakeRecord` | 保持原字段、限制及客户/内部分离；投影最终再构造合法 IntakeDraft，不截断超限内容 |
| `intake/service.py:66–100` | 追加修订；create 按 owner/request/digest 幂等；save 核对 expected_revision 与未转案状态 | 接受调用方 db，直接 create/save；不复制 INSERT 和接待权限实现，不在 helper 内 commit |
| `intake/service.py:103–117` | 正式转案与接待链接在调用方事务中完成 | 自动档案不调用 convert；保留显式转案 |
| `assistant/service.py:20–83` | 当前会话身份、工作区、scope、投影接待权限重核；ScopeSnapshot；草稿额外 composer 版本 | 提交使用 `_owned`、`_snapshot` 与当前 scope 精确比较；不能直接使用 `_expected` 使未发送输入变化令生成结果过期 |
| `assistant/service.py:225–274` | 用户消息不可变、input_revision、run 快照、消息/运行/事件 savepoint | 新来源引用固定已发送 message ID/revision/原文范围；不能引用未发送 draft_input |
| `attachment_records.py:14–85` | 所有权、选定材料快照、指定 parse revision、ParseResult 摘要校验 | 服务端组装合法资料集合，不接受模型自报附件/作用域/路径；保留 partial 与 unread 状态 |
| `domain.py:436–473,1086–1100` | Anchor 精确 quote/SHA/[start,end)、版本一致；ParseResult 锚点唯一 | 文档出处复用 Anchor 与版本定位，不自造模糊文本搜索 |
| `domain.py:474–561`、`facts/confirm.py` | FactValue 精确类型；Fact 有 matter_id、确认者/时间；人工确认追加快照并 savepoint | 可复用 FactValue/ExactDecimal/UTC，借确认规则；**不能直接拿 Fact 作建案前档案**，更不能伪造 matter_id 迁就它 |
| `facts/party.py` | 明确人工选择，候选 ID 不升级为真实实体 ID | 借同名不合并的规则；它是 matter 作用域，不直接用于客户临时卡 |
| `assistant/schema.py` | conversation 已有 projection_intake_id | 首次投影只设置该链接，不悄悄改变 scope_kind/ref/binding_revision |
| `storage_schema.py/schema_migrations.py`、既有 *_integrity.py | 精确 schema 识别与封闭归档检查 | 新表引入时同步所有 schema 识别、迁移、完整性、备份/只读恢复；不只 CREATE TABLE |

本次未找到已存在的 `assistant/provenance.py`、`assistant/profiles.py` 或 `facts/merge.py`；不要把计划名当现存接口。当前模型结果协议主要提供正文/引用及受限工具计划，没有已经可用的 ProfilePatch 输出分支；不得从任意回复中正则截 JSON 后直接入档。

## 2. 纯合并内核的最小完整 interface

建议 `assistant/profiles.py` 暴露一个实际运算入口，例如：

`merge_profile(previous, patch, source_snapshot, *, intake_baseline=None, intake_current=None) -> ProfileMergeResult`

名称可调整；关键是同一入口完成提案复验、来源核对、人工保护、冲突保留和合法接待投影。调用方只获得新快照/差异建议/投影草稿/是否变化；无数据库、时间获取、随机 ID、模型请求、环境扫描。业务 DTO 全放 domain.py，固定来源/字段枚举而非任意 JSON。

`source_snapshot` 必须由服务端在有效授权下从当前消息、材料快照构建。纯函数只能证明提案与给定快照相符，不能因此声称权限有效或原件客观真实。真正提交仍须重新检查权限及版本。

最小 DTO 要表达：固定 ScopeSnapshot、base_profile_revision、字段提案、每值 origin/verification/source_refs、人工保护元数据、未采用差异。模型提案不能携带 owner、created_by、确认者、确认时间、自动生成 client_id、matter_id；模型可接受 origin 限定为其有资格声称的来源，不能自报 lawyer_input 或 confirmed。服务端人工更正用独立受信入口/类型。

不要把扩展金额直接塞入 IntakeDraft：支持十进制值+单位+语义角色+来源并列保留，投影时才形成有标识的摘要。可复用 FactValue，但各字段必须有具体类型约束；例如 title 不能接受 BooleanFactValue，金额不能接受无单位 decimal 或 float。

### 必须一片闭合的纯行为

1. **未提供与 unknown 与主动清空区分**：patch 缺字段不覆盖；模型 unknown 不抹去已有值；人工清空可保留空值且仍受保护。不能以空字符串表示所有三种状态。
2. **来源精确匹配**：message 引用绑定 conversation/message/source_revision、明确字符区间和原文 SHA；区间匹配原文，不只做 `quote in text`。document 引用绑定 attachment、original SHA、parse_revision/result SHA、anchor；必须属于该材料快照，quote 与指定 anchor 精确一致。重复片段不能随意落到另一位置。
3. **多个值并列**：本金、利息、付款额分别有角色；同角色冲突并列、verification=conflicted，不按最新/最大金额/置信度取一个。同名主体不归并，未知身份不新增真实客户索引。
4. **人工保护与事实核实独立**：律师输入是受保护编辑，但 verification 仍可 unverified；人工确认值另有明确操作。模型对人工值只能产生可见差异建议，不能改值或解除锁。
5. **旧接待兼容保护**：有上次 projection receipt 时，比较其具体 intake_revision 的投影基线与当前接待修订，人工改过的字段转入保护；第一次连接既有人工接待而没有来源元数据时，原字段按人工保护，不能因“缺元数据/值为空”认定模型可覆盖。先保守保护整字段，暂不做列表项智能合并。
6. **确定性与幂等**：标准化字段/来源顺序后比较语义快照；同提案重放不新增差异项，不靠新 UUID/时间制造“变化”。相同内容新增真正来源可以追加出处，这是有效变化，需在测试中与纯重复区分。
7. **合法投影**：只映射 v2.1 5.3 的支持字段；保持客户回复与内部意见分离；未确认不能自动 checked；status 沿用，不自动 closed；超限拒绝或返回需整理，不能截断。follow_up_at 只有明确时区的确定时刻，模糊日期原话留作候选，不算法律期限。
8. **不制造空接待**：纯内核不创建记录；后续是否投影由受信工作流目的决定。通用学习/写作和空 patch 无接待创建副作用；不能只要模型说“咨询”就创建客户/正式事项。

## 3. 第一片持久化闭环不能再分拆的事项

一旦允许实际保存档案，下列必须同片完成，而不是先写 profile、下一片再补接待回执：

- 读取当前授权/工作区与会话，检查未归档/非恢复副本；固定 run/ScopeSnapshot、profile revision、intake revision 和来源快照。
- 当前 binding/input/materials 不等于提案固定版本则拒绝当前提交。composer 单独变化不影响已发送轮次。接待被其他 conversation 投影、旧页人工更正或转案均不能静默重基线重试。
- 在调用方一个短事务及内部 savepoint 中：写 profile 修订 → 调已有 intake.create/save → 写 projection receipt（固定 profile/intake revisions 与 payload digest）→ 更新 projection_intake_id（首次）→ 写成功事件/幂等回执。任一步失败整体回滚，包含调用方捕获异常仍提交外层的场景。
- 相同 request/提案摘要重放返回原回执；不同 payload 同键拒绝；没有有效变化不生新 profile/intake revision。必须能在成功响应丢失后找回，不重复建接待。
- 现有接待页读取具体修订元数据：原手工 consultation 仍标原话；自动投影修订标“接待摘要”，原消息入口可回查。不能统一重命名所有历史版本。
- 新表及不可变约束、所有老 schema 迁移路径、完整性校验、旧备份兼容、qxbak 恢复和只读 API 一起完成。档案历史读取不能因为当前登录撤销或材料当前重新解析就伪称旧历史损坏；当前读取权限仍重核。

不在数据库事务里跑模型/解析文件/联网。事务外模型结果只是候选，提交期必须以当前数据库复核结果为准。

建议仍用规格所列 profile_revisions 与 projection_receipts 的独立职责。profile 的 JSON 是来源/保护/扩展值覆盖层，接待可编辑业务字段仍由现有版本链持有，不新增一套可独立修改 status/contact/client_reply 的 CRM。

## 4. 可以独立推进的边界

- **CH-00A3（本轮）**：接待依赖下沉、导出延迟导入；保持原行为、alias、字节、错误/权限/事务。它与 CH-07 数据协议无耦合。
- **CH-07A**：上述纯合并/出处验证/人工保护/映射与单元测试。无表/HTTP/UI/网络，作为已测领域行为交付，不创建空 schema。不宣称自动建档已接通。
- **CH-07B**：本地持久化及原子投影+迁移备份恢复+人工编辑/读取入口，与旧接待兼容闭合，可先合成输入端到端。
- **CH-07C**：主模型结构化提案输出与固定钩子，复用现有同一次调用/费用/取消/来源授权；不能暗中增加第二次付费抽取调用。与对应输入模板/输出协议/原生确认内容同步。模型不可用时显示未提炼或本地保存，不能 mock 装作真实自动整理。
- 临时客户索引与显式关联/解除、跨事项材料分组、正式导出可在核心档案后分别做。未完成时不要提供会默默合并身份的半成品按钮。

## 5. 针对性测试入口（建议，未运行）

### 纯内核新增

`tests/unit/test_assistant_profiles.py`：合法 source exact quote 和错误 offset/hash/跨对话/错 parse 版；model_copy 绕过 DTO 后入口复验；unknown 不清空；人工清空锁；旧接待空字段仍保护；相同提案幂等；同值新出处；金额角色冲突/单位/float 拒绝；相同姓名不合并；普通写作不建接待；边界限长不截断；客户/内部不能串字段。

### 持久化新增及复用

- `tests/integration/test_assistant_profiles.py`：版本、权限重核、恢复拒写、历史来源可查；单次消息和材料新修订令旧提案过期；composer-only 改动不误拒。
- `tests/integration/test_assistant_intake_projection.py`：多 conversation 竞争、旧页人工改动、已转案拒绝、同键重放与不同摘要冲突、在 profile/intake/receipt/event 各步注入失败，外层 catch 仍无部分成功。
- 复用 `tests/integration/test_intake.py` 全文件：原历史/权限/受众导出/转案/限制不得回退；人工和模型修订标签分别验。
- 复用 `test_assistant_storage.py`：重点 157/200/246/262/298/333/408 行的伪作用域、撤权、已转案、恢复栅栏、savepoint/事件失败行为。
- 复用 `test_assistant_attachment_backup.py` 的来源损坏、未来 parse 引用、归档恢复完整性方法；新增 profile 对应归档故障矩阵，不把原测试改成只验证新实现自己的序列化。

### CH-00A3 特别提醒

当前 `intake.service.convert` 在运行时通过 `services.create_matter` 调用。下沉后旧失败注入若仍只 monkeypatch `web.services.create_matter`，可能已不在实际路径上。应让测试在真实调用 seam 注入失败，并继续证明创建 matter/默认规则/政策/接待链接都回滚；仅保持别名存在不能证明探针仍有效。

`web.storage.encode` 是 `json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`，sha 对其 UTF-8 字节摘要。不要在“通用化”时换成近似 canonical_json 或更严格的新值转换而改变已有 request 摘要。原 now() 为 UTC aware datetime，保持时间含义。

## 未核验范围

本报告无运行结果、无 Windows 性能结论、无模型协议外部核验、无真实资料结论。源代码动态变化由主代理提交前复核；WIN-PATH-02 的两项历史失败据主代理本轮在两目录未重现，保留待查，本设计不推定根因或建议猜测修复。
