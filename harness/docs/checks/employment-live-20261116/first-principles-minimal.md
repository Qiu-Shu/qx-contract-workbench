# 第一性原理设计一：小 interface 的来源约束审查 module

2026-11-16；只读设计，源码基线 `8fd8ce4ff55582cbe218950bced231b243ce17ff`。未调用模型、未改产品。设计目标不是让任意法律自由文经 schema 后变正确，而是让程序只交付自己有能力约束的陈述，并将模型判断及未知留在正确的位置。

## 已核实的根因

`EmploymentFinding` 的 fact/basis/source/risk/action 都是自由字符串。`save_employment_review` 仅对有限关键词调用工资规则或 `DraftReview`，再对部分字段做替换；来源匹配能约束 fact，却不能证明 action 中的新断言。模型可以通过换一种表达绕过正则，D/H/J 是同一种失败的三个实例。

`verified_delivery.attach_delivery` 验证已存笔记和文件的版本、哈希及出处。这解决“保存与交付不一致”，并不解决“存下来的话是否有依据”。扩大交付保护的覆盖率会忠实交付同一份错误，不能替代内容的权责划分。

本项目已有可复用方向：`source_bound_litigation` 不收任意正文，使用 `_reference` 回读同案、同版本完整片段，生成来源摘录、明确算术和有限条件式请求；`source_bound_registers` 把模型分类留在 classification_audit，实际条目保持 source_excerpt。后者明确承认分类仍可能不正确。这些已有能力应复用，而不是再建一个并行事实数据库。

## Interface：一个公开入口

```python
record_review(cases, case_id, plan: ReviewPlan,
              request_id='', supersedes='') -> ReviewReceipt
```

此 seam 放在模型结果进入持久化笔记之前；现有 MCP 工具是 adapter，聊天和 Word 都使用同一返回记录。调用者不再获得一个可以自行填正文的中间对象。compile、规则求值、正文组装及写入都在 implementation 内，防止调用者绕过编译直接保存“已验证正文”。

```text
ReviewPlan
  domain/stage                 已有阶段；决定相关条件卡，不决定事实
  sources: Citation[]          已有关联原件的定位，仍逐一回读
  selections: Selection[]     引文分组、审查目标、可选规则与文书意图
  legacy_draft?: object        迁移期旧工具的原始入参；仅内部审计

Selection
  source_indices: int[]        指向本次 sources，不新增事实文本
  review_kind: enum            source_review / conditional_clause /
                               clarification_request / supported_rule
  rule_id?: known-id           仅 supported_rule；选择不证明适用
  parameter_refs?: existing source-bound parameter types

ReviewReceipt
  id / revision / user_summary / delivery    复用已有保存与交付
  coverage: source-only | conditional | computed-under-conditions
  pending[]                    所缺条件及未支持的能力，不是“全部失败”
  audit_ref                    模型原稿、选择及不采用原因
```

这里公开入口虽只有一个，但嵌套类型仍是 interface 的真实成本；因此第一版不引入可编程规则语言、任意 AST、远程插件系统或可任意拼句的模板语法。`review_kind` 是输出能力，不枚举 D/H/J 个案。引用任何已解析法律材料都可走 source_review；有限条件卡支持的事项再生成候选和计算。未知领域仍能得到原文、问题和可填结构，不伪称覆盖全部法律工作。

不变量：

1. 主体、日期、行为、同意/拒绝、已发生/未发生等动态事实只来自服务端恢复的原文，统一标为“材料记载”。选中一个词不能脱离其完整句和限制语。
2. 来源位置匹配、数值转换、选题分类、法律适用、事实真实性是不同状态，不能由一个 `verified=true` 代表。
3. 主正文的每个节点只能由三类 producer 生成：来源摘录；程序规则的条件结论；固定模板＋有类型的来源/规则槽位。模型自由字符串没有进入主正文的通道；不能靠加“待核”标题获得该通道。
4. 固定模板中也不能暗含过去事实。例如“请核对下列来源所涉考勤事项”不暗含公司已核查；试用条款不能暗含双方此前没有试用；竞业核对不能暗含另一方未同意。模板正文和占位本身须纳入测试及审阅。
5. 支持一个规则不等于该规则在本案适用。输入只足以做算术时，输出保留“在这些原文参数及适用条件成立时”的条件，显示参数所有者、期间、单位和来源。
6. 原始模型意见可保存在内部审计中，但不可与候选正文混排或被无条件导出为对外文书；用户明确要看原稿时，按“未核模型草稿”展示，不能升级为来源约束成品。
7. 不把没选到的引文当作没有该事实。缺材料、未选入、矛盾、语义不明分别保留；不自动补零、补否定、补同意状态。

顺序及错误模式：

- 回读本案当前来源快照 → 验证引用并恢复上下文 → 建立只读来源节点 → 求值可支持规则 → 生成候选/待核 → 保存一次 → 从保存记录生成交付回执。
- 跨案、原件版本变化、引用冒用、非法索引是输入错误；不凭旧快照写入。调用者回读后重试；已有 request_id 幂等语义和 supersedes 规则保留。
- 材料不足、未知单位、冲突参数、未支持规则是业务待核：尽可能保存无争议摘录与中性候选，只暂停相关推论；不循环要求模型改原文直到通过。
- 原件在准备与保存间变化时，在持久化前复核用到的版本，失败可重试；既有文件交付仍复核哈希。
- 全部引用不合法时不能伪造有效来源稿；原始失败草稿可按既有审计能力保留，明确输入错误。零可用候选时仍能返回已存来源整理和能力范围。

## Caller 例子

```python
# 模型/旧 MCP adapter 只选原文与意图，不编写已发生事实。
receipt = record_review(cases, case_id, ReviewPlan(
    domain='employment', stage='termination', sources=[attendance_ref],
    selections=[Selection(source_indices=[0],
                          review_kind='clarification_request')]),
    request_id=request_id)
# 原文说“考勤记录内容未展示”时，候选可以请双方核对相关记录；
# 不会生成“HR发现无出勤记录”，因为没有接受该自由断言的字段。
return attach_delivery(cases, case_id, receipt)
```

旧 `save_employment_review` 的调用 schema 继续接受已存在字段，避免打断已有任务。adapter 将 citations、显式 rule/parameters 转成 plan；其余自由字段原样归入 legacy_draft。已支持规则照常产生结果。未指定生成意图时输出来源审查及中性核对候选，不从自由语句猜出“已经查明”。新的 Skill 可以使用可选结构化选择，用户仍在同一对话提出相同需求，不增加点击或输入。

旧自由内容从主正文转入审计是可见行为变化，不能仅以“兼容旧 schema”声称输出完全兼容。回执需明确“模型提出了某候选，但尚无受支持生成方式；原稿保留于内部核对稿”，不能默默丢掉用户要求，也不能宣称完整文书已生成。

## Implementation 隐藏什么

- 同案材料归属、哈希、片段、唯一位置、完整上下文、模型草稿不能作原始证据等已有核验。
- 来源节点与审查选择分离，分类或分组不产生额外事实；反证和限制材料按来源保留，不自动裁决。
- 单位、金额、期间、同一主体关联、算式及适用前提的已有程序规则；复用现有金额/工资实现，不另算一套。
- 模型原稿与实际主正文的差异审计；对被降为候选或未采用的内容给出可行动说明，不用通用“律师复核”代替处理。
- 从同一节点树生成笔记、内部核对稿及 Word；聊天使用已保存正文和 delivery 回执，不让模型再自由总结成新事实。

## Dependencies 与 adapters

- 进程内：上下文恢复、节点组装、Decimal、条件卡、既有规则函数。不因抽 module 给这些纯函数另造 adapter。
- 本地可替换：CaseStore、SQLite、材料文件、Word 生成器，沿用临时案件目录/数据库的真实测试 stand-in；在同一个公开入口测试真实保存和导出，依赖注入仍用已有 cases。
- 第三方模型：位于 seam 上游，输出 plan 或 legacy_draft；该 module 不发第二轮“自我核验”调用、不新增费用。模型更换不改变可持久化内容的权限。
- 法律来源：先复用已登记、有版本出处的有限规则卡；无法证明当前效力或适用时保持条件并展示法源待核。不要在 record_review 内偷偷联网、付费、抓取或把 model law text 认证成规则。
- MCP adapter 有新/旧调用两个真实使用方式，不需要预设十种 transport。verified_delivery 保留其“版本一致”职责，不改名为法律质量认证。

## 可证明与不可证明

可以通过接口和真实存储回放证明：未给的自由行动断言不会进入主正文；引文来自当前本案；明确参数运算一致；未知不会经模板变成事实否定；同一记录进入 Word/聊天；未支持项被显式保留而不是悄悄丢弃。这些是机制层面的可测性质，不依赖某一句错误是否匹配正则。

不能仅凭该设计证明：原文是真实事实、引用代表完整案情、模型选的相关材料没有遗漏、条件卡在当前案件必然适用、规则库完整或所有合法候选都能表达。也不能声称“结构化了，所以任意自由文语义正确”。schema 只限制形状；由受限 producer 生成正文才建立可证明的内容来源。模型的分类、法律推断和建议优劣仍需独立质量评测；其作用是找盲点，不能把不确定判断自动提升为已核结论。

## 最小可落地范围与验收

1. 建一个内部主正文节点/renderer，支持 source、conditional、calculated 三类，服务端生成节点，禁止自由 `body` 插入。
2. 旧 save 走此入口；显式工资/竞业规则接入既有实现；其他自由意见审计保留。增加通用“原文核对请求”和有占位的候选结构，已知原文不清空为未知。
3. 劳动录用、考勤核对、竞业协商使用现有规则/模板为首批能力，不写 D/H/J 字串特判。设计任意其他合同材料仍可保存引用、条件问题和结构，不能冒称跨领域法律质量已完成。
4. 对原 D/H/J 真实 save 探针做持久化回归；再用未见案例验证换主体、换语序、插入相反记载、变换同意状态、条件句、来源中本就存在明确否定等。断言主正文 provenance 与实际内容，不能只断言某禁词不在。
5. 在真实 MCP 入口测旧 schema 和结构化调用；测试带合法事实的正例与仅相关但不支持候选的反例；验证未知部分不阻断其他项、原件不变、原稿审计可查、记录/Word/聊天一致。
6. 删除被替代的内容修补 regex 及其重复细节测试；留与来源/规则计算有关的实现。接口行为测试应能承受内部重构，不能因新 module 再叠一层同样的关键词过滤。

Trade-offs：一个入口复用已有保存链，locality 和 caller leverage 高；迁移可逐步进行且不用新界面。代价是旧自由文“看起来完整”的程度会降低，有限模板不能覆盖所有写法。应明确暴露真实能力、逐步增加经验证的条件模板；不能为了看起来聪明把自由文本偷偷加回主正文。若每种用例都要新增十几个字段或 caller 自己做法律判定，interface 已变 shallow，应收紧到来源选择与生成意图，将组合复杂度留在 implementation。

## 核查来源

- `bridge/source_bound_inputs.py`：当前 EmploymentFinding 及 Citation/Money 结构。
- `bridge/employment_review.py`、`bridge/employment_source_claims.py`：有限关键词路由及字段替换。
- `bridge/business_server.py`：现有 MCP schema、保存、来源约束文书及审查工具。
- `bridge/source_bound_litigation.py`：原文回读、完整语境、数值来源和有限条件请求。
- `bridge/source_bound_registers.py`：source_excerpt 与 classification_audit 分离。
- `bridge/verified_delivery.py`：生产者持有的保存/文件版本回执。
- `docs/checks/employment-live-20261116/first-principles-probe.py`：本轮三个真实 save 探针。
- `docs/checks/employment-live-20261116/repair.md`：此前修复和质量失败界限。
