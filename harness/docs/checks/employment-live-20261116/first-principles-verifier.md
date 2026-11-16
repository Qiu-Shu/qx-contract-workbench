# 第一性原理方案二：自由拟稿、逐断言核验与定向修订

2026-11-16。只读设计，基线 `8fd8ce4`，未修改产品、未调用模型、未产生费用。约束为保留自由法律意见与可用候选文本，不增加用户输入，不用同模型自评通过冒充事实证明。本方案供主代理与其他设计比较，并非已实施状态。

## 证据与根因

`first-principles-probe.py/json` 的三个反例具有同一结构：引用确实存在，模型在行动文字内新增了该引用未提供的断言。既往试用记录变成“同一岗位未约定”，未展示的考勤摘录变成“HR核对发现系统无出勤”，员工是否同意未说明变成“未作同意表示”。当前 `save_employment_review` 对 fact/source 进行来源绑定，却允许 action/risk/basis 带入开放断言；`DraftReview` 的有限正则覆盖已知措辞族，不能承载无限自然语言蕴含关系。

`plugins/verified-delivery/core.mjs` 通过同一笔记、来源和文档摘要交付 `user_summary`。它解决保存与交付版本一致性，不能证明保存正文的断言正确。把语义核验塞入最后的聊天改写会使 Word、笔记与聊天分裂，因此 seam 应在保存之前。

最小任务不是“让模型永远不犯错”，而是分别保存：来源实际说了什么、模型拟主张什么、各断言获得了哪一类支持、最终正文采取了什么。引用匹配、原文陈述、程序计算、法律判断是四种不同的证明义务。`matched` 不能自动满足后三种。

## Interface

对 caller 暴露一个异步入口；原有 MCP 名称和输入不变，所有新信息由已读取材料和当前请求生成。外部公开 seam 不要求模型先填一套自证字段。

```python
async def prepare_review(
    request: ReviewRequest,       # case_id/stage/findings/request_id，既有输入
    sources: SourceSnapshot,     # 案件归属、原件摘要、完整句/上下文，程序创建
    verifier: ClaimVerifier,     # 注入依赖；无凭据或预算时为显式未核 adapter
) -> PreparedReview:
    ...

class PreparedReview:
    body_findings: list[dict]     # 实际准备用于笔记、Word、聊天的同一版本
    draft_sha256: str
    source_snapshot_sha256: str
    verdicts: list[ClaimVerdict]
    changes: list[SpanPatch]
    status: str                 # prepared / prepared_with_unresolved / unavailable

class ClaimVerdict:
    target: FieldSpan           # finding index, field, start, end, exact text hash
    kind: str                  # quotation / factual_assertion / assumption /
                               # proposed_obligation / legal_rule / inference
    result: str                # supported_as_source_statement / computed /
                               # contradicted / unsupported / unknown
    evidence: list[SourceSpan]  # 只能指向程序提供的快照，不能由 verifier 添材料
    reason_code: str

class SpanPatch:
    target: FieldSpan
    original: str
    replacement: str
    basis: list[SourceSpan]
    reason_code: str
```

内部 `ClaimVerifier` adapter 只有 `assess(snapshot, draft_spans) -> proposed_verdicts`。模型给出的 verdicts 是待校验提议，不是对外“已核”状态。初期只有真实已使用的两种 adapter：受预算约束的既有 Flash profile 请求、离线显式 `unavailable`。测试用捕获响应/故障 adapter，不先搭建多供应商平台。

### Invariants

- 保存前快照由程序冻结案件和原件版本；跨案引用、已变材料、模型草稿作原证据不能通过。
- 每个被改写范围必须匹配原字段摘要，补丁不能重叠、越界或同时修改不相关意见；原始 findings 与每次修订均可追溯。
- 模型不能通过新增 `verified=true`、语气或重复保存把断言升级。`supported_as_source_statement` 仅指材料这样陈述，主体、传递关系、单位、日期、否定与条件应一并保留；不等于客观事实成立。
- 自由法律判断始终为 opinion；法律规则需要对应版本来源及适用条件，算术只能来自程序输出。模型“认为正确”不是法律规则验证器。
- 未知、未提供、不存在、对方否认不得互换。候选条款的将来义务允许提议；含“此前”“已经”“发现”等历史断言必须获得独立来源支持，不能借“候选条款”身份豁免。
- 无法完成核验时不能返回绿色通过。已安全准备的部分照常保存，未解决断言转为具体待核/中性候选，原稿保留；无需用户再填一轮表单。
- `PreparedReview` 不是可被模型自行传入的能力令牌。MCP wrapper 内创建、核验并立即保存，caller 看不到可绕过准备的第二保存入口。

### Ordering 与 errors

1. 校验输入与案件范围，冻结来源快照。校验失败是普通参数/来源错误，不花模型费用。
2. 运行现有可判定规则：金额、单位、身份绑定、来源引文、版本与支持的法律条件；这些结果是 verifier 输入约束，不允许被其推翻。
3. 对 **所有字段** 的非引用自由文本形成带偏移的段/句集合，按“来源内容→候选断言”单向检查。引用部分也保留其外层陈述主体；不能让局部引文切掉条件或冒充直接陈述。
4. 最多一次 verifier 调用，报告准确断言范围、引用范围和反证/缺口。重新校验返回结构、覆盖范围、证据路径和摘要；格式错误或输出截断视为 `unknown`，不重试同一网络请求。
5. 程序直接处理可判定修正；语义问题采用定向补丁。无可靠替代句时保留明确来源转述或中性核实请求，不清空整个 finding。补丁后再运行程序规则和覆盖检查。
6. 最多一次定向改写/复核调用，仅针对有缺口范围；不得无限自我反思。仍未解决的范围保持 `unknown` 并生成保守候选；不让保存流程循环等待“所有项通过”。
7. 保存前重验快照摘要；源变化返回 `source_changed` 且不写笔记。成功后仍沿既有回读、Word 导出和 `attach_delivery`。

错误为 `invalid_input / source_changed / budget_unavailable / verifier_timeout / verifier_incomplete / verifier_invalid / patch_conflict`。后三类不伪装业务完成，也不丢原稿：返回准备完成的部分及具体未核范围。取消发生在保存前则不保存；保存完成后按既有 `request_id` 回读同一回执，不第二次付费。

## Caller 示例与最小接入

```python
@mcp.tool()
@friendly_errors
async def save_employment_review(case_id, stage, findings, request_id='', supersedes=''):
    request = existing_request(case_id, stage, findings, request_id, supersedes)
    # 先复用既有幂等回执；不能在每次重试里重新审稿、重新扣预算。
    if receipt := existing_receipt(request):
        return receipt
    sources = freeze_current_case_sources(cases, request)
    prepared = await prepare_review(request, sources, verifier=current_verifier)
    assert_current_sources(cases, sources)
    result = persist_prepared_review(cases, request, prepared)
    return attach_delivery(cases, case_id, result)
```

当前 `business_server.py` 保存工具是同步函数，且没有模型凭据/预算依赖。不能假装仅在 Python 内增加一个 callback 就已接上生产模型。实际接入需要一个异步 wrapper 和可信本机模型 transport；credential/budget/cancellation 留在现有宿主模型层，Python 只拿返回内容。若宿主暂时没有可复用的调用与预算 seam，先用离线/捕获响应验证本方案，再决定是否增加这条窄 transport。不要让 `verified-delivery` 在最终输出阶段再偷偷调用付费模型。

原有 `prepare_probation_pay`、`prepare_noncompete_comparison`、`DraftReview.sources`、引文校验、内部修订稿和交付回执均可复用。正则规则退回为可解释的快速检查，不再被表述为一般语义校验。逐断言核验结果持久化在与本次笔记绑定的审计区，不把新 fields 倒灌给旧 MCP caller。

## 费用、循环与同模型自证

复用用户已授权的主模型与 profile，不擅自切换另一付费模型。一次独立请求、独立上下文只带来源、候选断言与判定协议，不带作者“我已经检查过”的自评或思考链；优先要求找矛盾及缺失前提。这样减少上下文诱导，但同一模型仍可能同错，不能称真正独立事实认证。

现有评测 ledger 的 `reserve -> settle`、并发锁、未知用量保留预算、请求 ID 唯一机制可用于实验；它是评测设施，不应直接成为产品付费逻辑。产品 adapter 需要复用宿主实际费用控制。如果没有它，返回 unavailable，不在保存工具偷偷外连。

费用上界由实际提交字节数、输出额度和既有保守费率计算；预留“核验+可选一次局部修订”的总上界后才开始。输入上限和分块策略固定，超限不要静默截断。每份正文最多两次额外模型请求，超时/截断不自动重发。实验仍计入现有 10 元 campaign，不能开新 ledger 获得第二份额度。

独立 LLM 核验的收益是覆盖新说法、新主题和跨句矛盾；程序核验的收益是确定可重复的范围、单位、数值、来源和版本。两者不能互相替代：程序不能可靠理解任意法律自然语言；同模型的“通过”也不能证明没有隐含错误。真实评价必须由固定题面、固定错误 taxonomy、未见案例和逐字独立审阅承担。

## 防止有效内容丢失与样本过拟合

以断言/最小完整子句为变更单位，保存精确补丁；不要重复此前“有工资数字就替换整个意见”的做法。一个长句包含已支持的报价、待核工资周期和无依据确认时，只改无依据确认；不能因一个 claim 未通过而删除已支持的条款建议。模糊边界采取整句保留为内部原稿，并输出具体中性替代，不拼接残缺语义。

测试以变形族而非三条字面反例为单位：主体交换、转述层级、未知↔否定、未来义务↔历史确认、年/月/件单位、条件前后位置、同岗/同关系/同双方范围、无关待核掩护、引文截短、反证藏在其他材料。每个失败族有对应可保留的正例，另含混合多意见、不相关内容不变与真实原文明确否定的例子。固定 holdout，不把全部题面词组加入 prompt 或正则；记录缺漏率和误删率，不能只报“问题被替换次数”。

LLM 提取“所有断言”本身可能漏项，程序句子覆盖只能证明每段被处理，不能证明每个命题被识别。因此要用遗漏型对抗样本检验，不能把 100% 字符覆盖称为 100% 语义覆盖。模型 verifier 输出全 pass、编造支持引用、超长输出或报错时也必须测试。

## Trade-offs 与结论

本方案最大 leverage 是在一个保存 seam 上保护所有事实/风险/行动/候选文本，兼容不同劳动事项，保留自由拟稿能力；locality 是来源解释、语义审计和局部修订集中在一个 module。代价为一次或两次额外模型调用、延迟、预算与取消的真实生产接入，以及仍无法消除模型同错。界面不多点一步，但工程和失败状态比纯结构化输出更复杂。

可以证明：案件/原件/摘要未变、引用文字匹配、程序计算与单位检查成立、补丁只改指定范围、保存/Word/聊天为同一结果、费用与调用次数有界。不能证明：源材料真实、法律适用最终正确、同模型未漏掉新错误、全部自由文字断言已经被识别。

推荐将它作为结构化事实与程序规则之上的 **有界语义检查层**，而非唯一安全核心。若当前目标是以最小变更可靠交付，则优先让关键事实、数值和候选中的历史前提由程序掌握；自由意见保留明确 opinion 身份。等本机可信模型 transport 与 holdout 证明有净增益后，再启用本方案的在线 adapter。不要用第三次提示词加长或一轮“自检通过”宣布完整 Skill 验收完成。

本设计没有运行新测试、付费请求或生产接入；以上是待实施设计及已读取源码分析，不能当成修复完成证据。
