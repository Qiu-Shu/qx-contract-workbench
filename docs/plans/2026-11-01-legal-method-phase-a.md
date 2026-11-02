# 法律方法第一批 A：引用与时间线候选

用户在只读审计后要求继续。本批只接案件整理中明确的时间线、年表、引文核对、文书、起诉状或答辩状请求；其余案件整理保留现有方法。客户接待仍使用既有超级销冠派生能力。合同分流、刑事、商标分析分后续批次实施，伙伴模型接口仍待办。

采用 `case-evidence-v1`，方法由群兴编写；借鉴上一轮已审计的 Chronology 与 Brief Section Drafter 方法，不执行或安装上游 Skill。上轮独立审计包在桌面 `群兴法律Skill只读审计_20261101_01a19764`。不把上游静态法条带入运行规则。

## 本批契约

- manifest 可选 `case_method={method_id:'case-evidence-v1',method_sha256}`，仅 case；缺省省略以保持旧快照字节。后端路由选择，新旧提示分开保存。原生桌面允许并验证新形状，实际方法摘要由后端核验。
- 新模型 JSON 严格为 `format_version,quotes,statements,timeline,gaps`。quotes 为 `{id,source_id,start,end,exact_quote}`，偏移相对该 source 的原文；statements 为 `{kind,text,support,opposing,unresolved}`，kind 区分 source_statement/inference/legal_analysis/proposed_text；support/opposing 为引文 id 数组。timeline 为 `{id,event_text,raw_date,quote_ids,conflict_group,uncertainty}`。无日期用空 raw_date，冲突保留多个事件，不按同日或相似文本去重。
- 引文必须逐字匹配指定偏移；所有引用必须有来源。材料陈述和时间线仅可引用案件材料，知识片段仅供方法或待核法律分析。法律分析始终待核，不接受模型的已核验标志。日期保留原样，非明确完整日期不推算。
- 后端生成可读 text/citations，保存 `MainMaterialCandidate.case_evidence`，现有聊天、历史及 Word 导出直接复用该文本。结算、回读、备份恢复按 manifest 校验同一格式并重新生成对照；拒绝擅改派生文本及内嵌伪来源。整条成果超过既有字节上限则拒绝保存，保留用量回执。
- 候选不自动写入律师证据底稿，不改变原有人工 reviewed 状态。后续人工采纳仍沿既有底稿和来源版本机制，本批不新增自动采纳入口。

## 验证与交接

先写失败测试，再实现。覆盖同事件多来源、同日不同事件、冲突日期、无日期、改写引文、未知引用、未核法条、协议降级、旧历史字节、新结果回读/导出/恢复、撤权/未知不重发。使用独立虚构材料和隔离数据库；真实模型质量 A/B 未运行。

已先备份拟修改的既有文件及暂存摘要至 `.audit-local/legal-method-phase-a-20261101`，保持当前分支与已有改动。本轮不提交或推送混合工作树。Codex 负责后端；WorkBuddy 仅修改桌面格式校验和独立测试；子智能体检查兼容与独立复核。最终实际命令、退出码、数量记入阶段测试报告。
