# 第一性原理候选修复：Standards 独立审阅

2026-11-16。只读审阅；未改产品、未调用模型。基线 `8fd8ce4ff55582cbe218950bced231b243ce17ff`，比较 `git diff --cached 8fd8ce4 --` 的9个文件；另纳入主代理明确指定的 `employment_drafts.py` 未暂存修订（补齐1/2/6个月上限，删除暗示已有材料/工资审查项的措辞）。没有新增提交可作为本次终点 SHA。

## 结论

**未发现本轮变更中有实际影响、需阻断的新增 Standards 问题。** 本结论限于三个候选构造分支及其保存接入，不是完整劳动 Skill 或自由法律分析的质量通过。

- 编译入口只接收有限意图枚举；空值、重复、未知类型及夹带正文的对象被拒绝，没有悄悄退回自由候选。MCP schema 与实现一致。
- 原自由 action 在替换前保留到内部修订稿；候选与既有工资程序结果可以共存，独立审查项保留。内部稿与主稿身份区分沿用现有交付机制。
- 新候选不消费调用者填写的历史事实；来源验证、同案归属及原件保护沿用已有路径。未把引用匹配或模板选择改成语义认证，返回 `semantic_verified=false`。
- 同参数重复请求保持同一笔记；保存正文进入摘要及实际 Word 的路径有真实 MCP 测试。评测输出上限调整继续使用同一预算台账并预留实际配置的上限，没有改模型或增加运行时核对调用。
- 模板集中在一个 module，未引入额外依赖、空转 adapter 或通用规则语言；固定 smell baseline 未发现值得单独提出的实际维护风险。

## 实跑证据

1. `pytest bridge/test_employment_drafts.py bridge/test_employment_pay_binding.py bridge/test_employment_tool_schema.py -q`：**50通过，退出0，16.39秒**；包括真实 MCP schema、保存、回读、Word。
2. Node `--test scripts/skill-eval-campaign.test.cjs`：**4通过，退出0**。
3. 独立临时案件探针：**8/8通过，最终退出0**，验证工资与两种候选共存、独立项及原稿保留、同稿摘要、同参数一次笔记、原件不变、候选引用跨案拒绝、无效意图不落笔记。证据：`D:/CodexChecks/AI-Shixiong-employment-20261116/first-principles-standards-probes.json`。首轮7/8退出1：探针错误地要求既有工资规则的引用失败必须抛错，实际该路径保留待核；改用本轮普通候选引用验证跨案拒绝，没有据此修改产品。

## 标准与界限

读取根 `AGENTS.md`、`CONTRIBUTING.md`、`harness/README.md`、`harness/docs/2026-11-03-GitHub交接.md`，结合本轮 `first-principles.md` 与明确范围。旧 Python 工程的 DTO 集中约定按根 AGENTS 仅用于对应工程；Harness 沿用已有 `source_bound_inputs.py` 类型。技能的 smell 清单作为判断建议，不以格式或行长重复工具检查。

未重跑完整离线集、未核验安装器或真实模型质量。旧自由分析和模板适用性仍未认证；新候选成功不能反推旧自由入口已通用修复。

## 补审：请求措辞修复（后加入的未暂存改动）

**发现1项 P2 实际回归，待修复后复核。** 位置：`bridge/employment_source_claims.py:6` 的 `REQUEST`，以及 `REQUEST.match(prefix)` 放行处。`向[^，,；;。\n]{1,30}` 可把“已”作为受询对象的一部分吞入；谓词只匹配“核实/询问”前缀，不排除随后“了”“后确认”等完成描述。因此原本需要来源支持的已完成行为被误当核实请求。

实际 save 对照 `8fd8ce4`：下列四句在原版本都不进入主稿，本次改动都原样落盘，引用原文仅为“是否曾口头同意未知；陈述媒介未说明”：

- 同时向主管核实了口头同意一事。
- 向主管已核实口头同意一事。
- 向主管核实后确认口头同意一事。
- 询问了员工的口头陈述。

对照“已向主管核实…”仍拦、“请向主管核实…”恢复保留，说明新增负例没有覆盖受询对象后或谓词后的完成描述。建议收紧请求识别：显式请求与裸谓词区别处理，对后者排除已经/完成体描述，受询对象段不能吞入时态词；保留本轮五步建议正例。不要求用本次局部修复证明任意自由文语义正确，但不能扩大既有可识别错误的放行范围。

证据：`D:/CodexChecks/AI-Shixiong-employment-20261116/first-principles-request-probes.json`；6组旧/新真实 save 对比，脚本退出0（数据采集成功，4组展示回归），未调用模型。这是补审发现，不推翻上文冻结9文件时未发现阻断项的历史结果。

### 收紧后的复核

原6组均符合预期（5个已完成句不保留，显式请求保留）；目标 `test_employment_source_claims.py` **20通过、退出0、11.73秒**。记录在 `first-principles-request-recheck.json`（与上述本机证据同目录）。原4个具体反例已经修复。

同一 P2 仍有直接遗漏：**“向主管核实口头同意一事的工作已经完成。”** 在 `8fd8ce4` 被拦、收紧后仍原样进入主稿。引文仅为“是否曾口头同意未知；是否完成核实也未知。”完成状态出现在命中词之后，前缀或动词紧邻负向匹配无法看到。见本机 `first-principles-request-tail-probe.json`，真实旧/新 save，退出0（采集成功）。建议把新增“向/同时向/询问”放行限定在显式请求或明确整句建议语境，避免靠不断补尾词扩大旧自由入口权限。当前应保留此发现未关闭，不能把20项通过当成该行为已经消失。

### 最终复核：P2 已关闭

以上未关闭状态属于中间版本。最终实现保留既有 `DIRECT_REQUEST` 行为，新增 directed `REQUEST` 必须同时处于 `EXPLICIT_REQUEST` 当前分句或整句语境；不再因为裸“向主管核实”就自动放行。独立复核结果：

- `pytest bridge/test_employment_source_claims.py bridge/test_employment_drafts.py -q`：**35通过，退出0，13.34秒**。
- 新建临时案件逐项经真实保存入口复核：**10/10通过，退出0**。六类已完成陈述均未原样进入主稿；真实五步建议、证明力分析、显式请求、口头同意是否成立问句完整保留。证据：`D:/CodexChecks/AI-Shixiong-employment-20261116/first-principles-request-final-recheck.json`。

**本次补审发现的有限语法回归已关闭，没有本轮已确认而未解决的 Standards 项。** 此结论不扩大为任意自由分析的语义保证；继承的有界识别、来源真实性及模板适用性限制继续保留。未改产品、未调用模型或发布。

换机可用的原始探针副本已归档至[本报告旁的 first-principles-standards 目录](first-principles-standards/)，含初查、中间失败及最终10项复核；上述本机路径作为原采集位置保留。
