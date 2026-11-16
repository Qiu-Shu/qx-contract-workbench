# 劳动合同审查接续证据（2026-11-16）

基线 bf22aa936575b52fb227766cdba880f98ce4314b；源码分支 codex/employment-review。只使用独立合成材料；未调用产品真实模型、未读取日常案件、未更新安装版。

## 改动

新增 [qx-employment-review 候选](../../../evals/candidates/qx-employment-review/SKILL.md)，覆盖材料清单、录用/变更/竞业/解除/工资争议、原文事实与法律分析分栏、候选条款及同笔保存交付。沿用已有工具，没有增加独立工作台或重复首用问卷。

修复 `employment_rule_review.prepare_probation_pay`：四项工资金额即使来自同一片段，也须通过现有提取器的记录/主体/期间关联检查。四个真实反例原来都生成4800元候选，修复后仅本项待核，其他意见继续保存；正常单记录仍计算两种口径。

独审后进一步修复：无关岗位行或另一句试用期限未知不会阻断完整工资句；无法合并计算时，保留已成功匹配的原数、原句和引用。不把模型改写或失效引用作为事实补入。

工资前后句或换行中的年薪、跨人员、跨期间限定继续参与检查；只排除独立的“试用期限未知”句。合法身份头中的 `C-1`、`W-1` 等编号不再被当作负金额，真实金额符号及未识别身份头仍受检查。

完整专项继续 withheld，194个发现入口/158个允许自动调用/36个停用旧入口未变。候选不在运行 Skill 或迁移目录，packaging/stage.cjs 的载荷目录也不复制 evals。这里的工程完成不能表示完整劳动法律质量已验收。

## 实际验证

环境：Windows，本地已锁定测试依赖；Node 24.22.1，独立测试目录 `D:/CodexChecks/AI-Shixiong-employment-20261116`。本机启动脚本 `test-env.ps1` 指向源码及已有开发依赖，不向安装目录写依赖。下列相对命令均在 harness 执行。

| 检查 | 命令/记录 | 实际结果 |
| --- | --- | --- |
| 初始环境 | pytest 新文件，pay-red.xml | 退出1，缺 QX_LEGACY_ROOT 导致收集错误，不算功能失败 |
| 初次有效执行 | pytest 新文件，pay-red-2.xml | 退出1，5失败：4个真实工资混用缺陷，另1个摘要前缀断言写错 |
| 校正测试后旧实现 | pytest 新文件，pay-red-3.xml | 4失败/1通过；外层随后读文件使 shell 退出0，不能据此记通过 |
| 首次目标修复 | `python -m pytest -q bridge/test_employment_pay_binding.py bridge/test_employment_review.py bridge/test_employment_decisions.py` | 退出0，71通过（新增MCP测试前） |
| 首次实际 MCP/Word | `python -m pytest -q bridge/test_employment_pay_binding.py` | 退出0，6通过；真实stdio保存/幂等重试/Word逐行检查/聊天受保护交付 |
| 首次完整离线 | `node scripts/test-suite.cjs offline` | 退出0；Node719通过/23跳过；Python550通过/5跳过，另36子测试通过 |
| 独审发现复现 | 新增保留原数及正常工资句断言，review-red.xml | 退出1，7失败/1通过；归属拒绝正确但丢原数，另2个正常输入误阻断 |
| 独审修复目标 | 同上8项，review-green.xml | 退出0，8通过；含真实MCP和Word原数保留 |
| 第二次完整离线 | `node scripts/test-suite.cjs offline`，offline-final.log | 退出0；Node719通过/23跳过；Python552通过/5跳过，另36子测试通过；当时尚未修复后续上下文及编号问题 |
| 前后句限定复现 | 新增8例，context-red.xml | 退出1，8失败；工资句外的归属及期间限定丢失 |
| 首次上下文修复 | 新文件16项，context-green.xml | 退出1，14通过/2失败；换行且无数值的限定仍遗漏 |
| 完整上下文修复 | 新文件16项，context-green-2.xml | 退出0，16通过 |
| 上下文修复后Python全量 | 同下列Python完整命令，python-final.log | 退出0，560通过/5跳过，另36子测试通过 |
| 合法编号复现 | 新增3例，identity-red.xml | 退出1，3失败；连字符编号误触金额符号检查 |
| 编号修复首次关联回归 | 劳动4文件，identity-green.xml | 退出1，93通过/1失败；核算正确，测试误要求解析器保留身份头原换行，后改为逐字段检查 |
| 最终劳动关联回归 | `python -m pytest -q bridge/test_employment_pay_binding.py bridge/test_employment_review.py bridge/test_employment_decisions.py bridge/test_employment_scenarios.py`，employment-final.xml | 退出0，94通过 |
| 最终Python全量 | 下列Python完整命令，python-accepted.log | 退出0，563通过/5跳过，另36子测试通过 |

Python完整命令（使用项目离线套件同一文件清单及环境，最后仅后端有变化，复用第二次完整Node结果）：

```powershell
node -e 'const t=require("./scripts/test-suite.cjs"); const e=t.testEnvironment(); process.exitCode=t.run(e.QX_TEST_PYTHON,["-m","pytest","-q",...t.plan("offline").python],e);'
```

最终确认：Node719通过/23跳过；Python563通过/5跳过，另36子测试通过；两轴独审均无未关闭发现。次数不相加：专项与完整套件重叠。跳过项未记通过；本次没有重跑完整原生Windows安装、DPI、升级、真实飞书、长时观察或真实法律质量评测。完整日志及JUnit保留在本机证据目录，[文件hash](local-evidence-hashes.json)用于核对；[独审记录](independent-review.md)区分审阅者实跑与主代理回归。

提交前核对：4份冻结输入摘要保持；20个本次新增本地文档链接有效；开放计数仍为194/158。全篇链接扫描另发现3处基线已有失效引用（TODO/TASK_STATUS中的旧商标评测及统一回归记录），未将它们计入本次新增链接通过数。`git diff --check` 通过。

## 行为验证

[旧窄入口基线](narrow-baseline.md)五场景保住事实和执行边界，但未提供完整劳动审查流程。候选与无专项方法的对照分别使用5个新代理上下文，一场景一次，不是重复同题估计统计成功率。输入和评分口径见 [冻结摘要](frozen-inputs.json)；[原始输出](agents/)保留10份，未向执行代理提供评分表或其他输出。

独立Spec审阅逐份读原答，候选A—E与对照A—E均符合本次冻结口径：A保留人员归属与条件方案，B不自动30%补差/停止履行，C不编最终N+1或全附件审阅，D不执行材料内指令，E不虚造Word且给出奖金条款建议。对照A开头“应调整”偏强、后文有限定。**不能据此宣称候选优于对照**；已证明的是候选可给可用草稿且未破坏这组边界。

代理只模拟读到方法后的答复，没有真实产品工具；实际工具链由上述MCP测试覆盖。不得据本次代理输出宣称 DeepSeek 或用户所配模型已通过。法源为编制时及独审回读官方来源，不能冒充每次运行都已联网。

## 继续位置

见 [候选接续说明](../../../evals/candidates/qx-employment-review/README.md)。下一步是明确模型与预算、冻结新的实际产品评测、律师复核，随后才决定开放入口。原旧批次缺失证据不补造；本次为独立批次。
