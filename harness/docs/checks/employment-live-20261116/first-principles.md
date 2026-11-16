# 劳动审查：第一性原理诊断与候选修复

日期：2026-11-16。起点：`8fd8ce4ff55582cbe218950bced231b243ce17ff`。真实模型沿用 DeepSeek Flash / thinking high、同一 10 元预算，仅合成材料。

## 已证实的根因

业务需要的是：材料陈述不被改写成另一项事实，法律判断保留条件，拟议条款不虚构历史前提。原接口把 fact/basis/source/risk/action 都作为自由文字保存；引用匹配只能证明原文存在，不能证明行动字段的新命题。正则只能覆盖有限措辞。保存、Word、聊天一致性检查会忠实交付同一错误，不能证明错误消失。

`first-principles-probe.py/json` 在真实保存入口复现 D/H/J：三项引用均匹配，三项无依据候选均仍落盘。它是修复前基线；不要覆盖该证据，也不要把仅新增模板分支描述成旧自由入口已经具备通用语义保证。

F 的空回答是另一类问题：原输出额度 8192 全部用在推理，没有可见正文。扩大单次诊断额度后一次完成，但新调用实际仅用了2421个输出token，且仍含试用范围和既往记录错误，故不能据一次重试证明额度是语义错误的原因。

## 比较及决定

并行设计见 `first-principles-minimal.md`、`first-principles-verifier.md`、`first-principles-staged.md`。

一次独立模型核对实验直接输入原材料、完整旧稿和已有规则参考，未手填逐题答案。6份中 A/D/I 返回正文，F/H/J在16384输出额度下仍截断且正文为空。A修正了月度单位却仍将未确认周期的数写进候选；I出现把可选约定视作已有事实等过度修订。此结果不足以启用自动复核放行，也不能证明分阶段完全无价值。原始实验保留在 `model/repair-independent-audit-long-thinking`。

本轮实施范围：深化现有保存入口，增加有限的程序候选构造。`drafts`只收意图枚举，首批为试用条件、考勤/请假核实、竞业解除及款项核对；候选不接收模型自填的历史事实、主体同意状态或自由正文。工资规则继续保留具体计算结果。原action留内部修订稿，独立AI分析继续保留并标注身份；无新增页面、点击、问卷或运行时付费调用。

兼容决定：旧自由分析入口保留，避免把任意意见统一换成待核清单。所有返回明确 `semantic_verified=false`，并列出自由分析项。候选Skill对这三种正文使用编译路径。这是**有限候选构造修复**，不是所有自由法律分析的可靠性修复；仅选模板也不能证明模板适用。

## 实施与验收

1. 新接口先失败测试，再实现候选编译与原稿审计。
2. 覆盖三类原反例、同意/拒绝/未知来源、多个独立候选、输入不能夹带自由正文、旧意见不冒充语义已核。
3. 实际MCP读取、保存、回读和Word使用同一候选；原文及其他意见保留。
4. 真实模型自行选择模板，检查最终交付而非只看工具成功。
5. 完整离线回归和独立代码审阅；结果另记。未验收的完整Skill继续候选，不打包为已修复版本。

法源编制核对：[劳动合同法](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html)第19条；[劳动争议解释（一）](https://www.court.gov.cn/zixun/xiangqing/282121.html)第39条。链接是编制来源，不代表每次运行已联网。

## 最终实际结果

| 检查 | 实际结果及边界 |
| --- | --- |
| 原入口反例 `first-principles-probe.py` | 3项引用均匹配、3项无依据候选均落盘，exit1；RED原件保留。 |
| 新入口 `first-principles-probe.py --compiled` | 3/3不再将原错误候选放入主稿，exit0；这是迁移至三个受约束类型，不是旧自由路径自动安全。 |
| `pytest bridge/test_employment_source_claims.py bridge/test_employment_drafts.py -q` | 最终35通过，exit0；含无依据完成态、合理请求、多个候选、实际MCP schema及保存导出。 |
| `node scripts/test-suite.cjs offline` 的 Node 部分 | 724通过、23跳过，exit0；此后未更改Node源码。该次Python606通过属于中间版本，不冒充最终计数。 |
| `test-suite.cjs` 的最终完整 offline Python plan | 最后产品修订后重跑，616通过、5跳过、36子测试通过，124.29秒，exit0。 |
| 独立 Standards | 最终35目标测试、10/10实际保存探针通过；新增请求识别放过完成态的P2已修，历史失败保留。 |
| 独立 Spec：`first-principles-spec-replay.py` | 三例真实模型的全部save入参仅替换case_id重放；41检查通过，exit0；代码摘要不变，原件、笔记、Word及受保护聊天一致。缺source那次原失败仍被拒绝且不保存。 |

三例真实模型分别用了7/6/7轮，自己选择`probation_clause`、`attendance_inquiry`、`noncompete_inquiry`，见`e2e/principles-drafts`。真实结果暴露两项范围内问题：程序模板误称期限已经给出、旧过滤器误删五步建议/证明力分析。已修复并用原参数在最终源码重放，**没有把原模型结果改写成新版模型结果**。

同一真实结果还含自由risk的来源归属错误：原文只写“员工离职前接触技术秘密”，模型增加“员工自述”。该P3仍未解决，是自由分析未验收的明确证据，不以标注AI分析代替修复。[Spec报告](first-principles-spec-review.md)、[Standards报告](first-principles-standards-review.md)、[最终重放](first-principles-spec-replay.json)、[独立保存探针](first-principles-standards/first-principles-request-final-recheck.json)。

本轮新增27次付费请求（F重试1、独立核对6、实际MCP20轮），原账本累计128次，保守估算7.948642/10元，未知或在途0；费用估算不等于账户账单。没有新增运行时付费复核，也没有重置预算。

**交付状态：有限候选构造修复和关联工程验证完成；完整劳动Skill全文质量未通过。** 未变更194/158/36开放计数、seed、路由或迁移；本机安装版仍0.2.19，本轮未打包升级。下一步应针对自由分析的事实归属和适用条件设计可检验边界，用保留的失败与新反例验证，不继续把引用匹配或第二个模型当成正确性证明。
