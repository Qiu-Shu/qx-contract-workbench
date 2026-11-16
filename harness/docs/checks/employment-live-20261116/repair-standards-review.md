# 修复 Standards 独立审阅

冻结范围：`git diff 0681cb2281f0fdb6996413428571767c46396bab...3fcae9da03edc88fc656737ebcbdd2b110b4f229`；commit仅`3fcae9da fix(employment): bind saved facts and wage opinions to source context`。依据当前`AGENTS.md`、`CONTRIBUTING.md`、Harness来源边界约定及Ponytail的“Never cut: validation at trust boundaries”；旧DTO规则不套用Harness。Fowler smells仅启发式，本次不报告风格项。

## 首轮发现（3fcae9da，历史保留）

1. **P1：标题与金额分字段会绕过工资规则。** `bridge/employment_review.py:45–46`要求单一字段同时匹配“试用工资”和金额。来源为“乙试用工资3500元，周期未说明。甲合同工资6000元。”，`topic="试用工资"`、`action="建议改为4800元/月。"`在hiring和dispute均原样保存，`rule_reviews=[]`、`workflow_status="saved"`。hiring亦丢失旧实现按标题触发的保护。应在同一finding内结合工资主题与金额意见判断，保留覆盖说明。违反既有金额来源校验边界及Ponytail上述规则；是功能缺陷，不是smell判断。

2. **P2：“材料中”被当成不确定限定，放过明确事实补造。** `bridge/employment_source_claims.py:42`复用`draft_review.QUALIFIED`，其中包含“材料中/材料内”。原文明确考勤条目未展示、媒介未说明，risk写“材料中考勤记录显示张三连续旷工。”或“材料中记载的情况属于员工口头陈述。”仍完整保存；去掉“材料中”的控制组会正确替换。应检查实际不确定语义及其作用范围，不能把来源措辞视为免责限定。违反本模块保留原句、阻止未支持考勤/媒介断言的来源边界及Ponytail上述规则；不是要求通用语义证明。

## 实际验证

工作目录为仓库根；以下使用既有合成测试环境，未联网付费、未读凭据、未改产品。

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON 'D:/CodexChecks/AI-Shixiong-employment-20261116/repair-standards-probes.py' 'F:/.codex/worktrees/employment-review/律所项目' 'D:/CodexChecks/AI-Shixiong-employment-20261116/repair-standards-probes.json'
& $env:QX_TEST_PYTHON -m pytest -q harness/bridge/test_employment_tool_schema.py
```

独立探针8项：4失败、4通过，退出1；上述两项问题各有2例，重复request_id未增笔记、正常待核措辞保留等控制通过。证据为命令中的本机脚本及JSON。真实MCP schema测试1通过，退出0。未重跑完整offline或实际模型；不将主代理的测试数量列为本独审结果。**该冻结提交有2项发现，最严重P1。**

## 修复复核（2026-11-16）

`2be190dabaa666200e4504a6efe24d62749db48c`修复跨字段工资触发及“材料中”绕过。原脚本未改，8项实跑7通过、1失败，断言退出1：正常句“考勤是否显示张三连续旷工待核。”被替换，因为CLAIM匹配吞入“是否”，而限定判断只查匹配之前的prefix。原两项反例已消失，但保留该回退待修。同期MCP schema仍1通过、退出0；证据`repair-standards-probes-2be190da.json`。

最终`2321cee2d71a3572ad3d0ef70cd10532b2c5fd30`下，bridge无未提交差异，原8项探针**8通过、0失败、退出0**；两项发现及上述限定句回退关闭。实际命令（仓库根）：

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON 'D:/CodexChecks/AI-Shixiong-employment-20261116/repair-standards-probes.py' 'F:/.codex/worktrees/employment-review/律所项目' 'D:/CodexChecks/AI-Shixiong-employment-20261116/repair-standards-probes-2321cee.json' > $null
exit $LASTEXITCODE
```

结论限于本独审两项及原控制组；不是整个新增修复面的再次完整审查，也不替代实际模型质量。后者逐例判读另见[retest4独立质量审阅](retest4-quality-review.md)。
