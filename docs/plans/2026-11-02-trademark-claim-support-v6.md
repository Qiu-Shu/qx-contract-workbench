# 商标来源陈述与分析依赖：v6 工程小片

状态：实施中；本片只做工程候选，不切换当前默认 v5，不据结构通过宣称内容采用。
工作副本：`C:/Users/Administrator/.codex/worktrees/trademark-claim-support/律所项目`。主仓与三个旧实验副本产品源码只读。

## 已确认诊断
冻结 v4/v5 四份原答回放：4 项原请求/成果兼容控制通过；5 个内容症状断言失败，原答确实含该句，展示层没有制造错误。135 项既有商标测试通过。记录在 .audit-local/trademark-claim-diagnosis-20261102。
根因优先级：1. 当前 DTO 只有 text/quote_ids，无法表达角色、对象或时间依赖；2. 精确引文只能证明字面位置，不能证明归属或推断；3. 增加 v5 自然语言规则未消除此问题。独立子代理三个最小探针同样被 candidate/codec 接受。
保留旧 RED，不通过改旧输出把历史症状变绿。

## 决策
同一次回答先声明来源陈述，再由八因素分析引用它们。复用现有单请求、账本、codec 和保存流程。两阶段额外调用会改变 max_calls=1、费用预占及未知请求恢复，当前不采用。
新增 method_id trademark-triage-v6，输出 format_version trademark-triage-v3；旧 v1–v5 的提示、路由、字节输出不改。默认仍为 v5，内容比较之后另议。
DTO 只在 domain.py：新增类型，并向后兼容地追加 method literal 和 candidate union；不改 CaseEvidenceStatement 或刑事格式。

## 数据约定
- quotes：复用现有 1..40 个精确原文引用。
- source_statements：1..40 项；id、quote_ids（1..8、唯一，均属同一 source_id/原文段落），以及七个必填可空槽 issuer/speaker/actor/object/event_time/report_time/record_time。null 表示模型声明本槽未知；非空严格为 quote_id/start/end，坐标相对 source 的 anchor.quote 原文（不是相对引文截取段），不另信任自由输入的值。片段必须落在单条已列引文内部，长度1..200且非空白。不同段落分别建陈述，再用观察关联。
- factors：原八因素固定顺序，holder/respondent 各0..5，neutral 0..10，unresolved 1..20。
- 每个观察为 text（1..1000）、statement_ids（1..8唯一）、relation（recorded/conditional_inference/comparison）、dependencies（0..24唯一 statement_id/slot）。
- recorded 只描述材料记载；其声明依赖不能引用未知槽。conditional_inference 必须列至少一个依赖，允许未知，但展示层自动列明每个已声明的未知前提，分析始终标为条件推断。comparison 至少两条陈述；各陈述 actor/object 槽都须非空且作为依赖列出，并且两类槽的精确文本各自一致。这仅是保守的可比性机械门槛，既不证明同一主体/对象，也不证明存在矛盾。依赖按具体时间槽校验，不能用 report_time 非空满足一个指向 record_time 的依赖；自由文本是否错误替换时间仍不由机械检查证明。
- 所有引用、陈述必须被使用；禁止悬空、重复、错版本、越界、未绑定来源和额外字段。
- 来源陈述只渲染一次，槽名称用中文，未知逐项显示；各因素通过陈述编号及依赖定位，完整引文和文件/解析版本照常显示。recorded 固定说明模型归纳非事实认定，comparison 固定说明字面相同不证明同一主体/对象或矛盾；未知前提不显示为事实不成立。
- 顶层字段 format_version/quotes/source_statements/factors/gaps；gaps 保留1..20条待核。先列陈述是提示与渲染次序，不声称校验JSON键顺序能约束模型推理顺序。
- 不扩展 32KiB 历史、请求限制或费用策略；超限照常拒收。

## 明确保留的局限
模型可能把印章文字误标为陈述者，或把转述时间误标为成文时间；只要位置精确，机械检查不能证明语义归类正确。自由分析也可能漏报依赖或绕开 comparison，包括全空槽陈述被 recorded 的自由文本错误归纳。为保留作者、对象未知但原文存在的中性材料，本片不强制 actor/object 有值，也不添加新谓词、相对方、对象类别或模板语言；许可方向等未结构化内容仍需内容复核。跨陈述可作有来源的分析，但不声称这些分析的支持关系已机械证明。本片不声称消除全部无依据断言，保留对此的反例测试和内容验收待办。展示中明示角色是模型提取、材料和推断均待核。不得把模型自填角色当权威事实。

## 实施与检查
1. 先写新格式正例、未知依赖、时间槽混用、异对象比较、越界及引用完整性测试并保存真实 RED。
2. 新 DTO、窄验证与渲染模块；v6 显式方法选择、系统提示、codec/历史重建及桌面白名单接线，默认 v5 不变。
3. 合成保存/回读/同任务历史，以及老方法字节兼容；独立代码审阅后修正有证据的问题。
4. 关联后端、桌面/页面及开发门，保存实际命令、退出码、数量；不继承旧 PASS。按修改风险扩展验证。
5. 更新状态/证据/记忆与本聊天自动化。下一片先冻结新材料与评分协议后才能生成新的内容对照；原失败不得改名重试。
