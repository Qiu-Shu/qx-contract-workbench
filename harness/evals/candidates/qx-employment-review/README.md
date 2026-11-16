# 劳动合同审查候选

2026-11-16 接续 qx-employment-review。此目录是开发与评测输入，未加入 config/skills、practice-skill-additions 或安装迁移。当前安装版仍使用 qx-employment-checklist，不能将本目录当成已开放的产品功能。

- [方法入口](SKILL.md)：复用原对话，按实际材料覆盖组织审查、候选条款和保存交付。
- [按需参考](references/method.md)：工资口径、竞业与解除的条件及官方来源。
- [独立虚构场景](scenarios.json) 与 [评分规则](rubric.md)：代理测试输入，非真实客户材料。
- [本次证据](../../../docs/checks/employment-review-20261116/README.md)：失败、修复、工具回归和行为评测分别记录。

换机先按仓库打包/开发说明准备锁定依赖，在 harness 运行 `node scripts/test-suite.cjs offline`。重点复跑 `bridge/test_employment_pay_binding.py`、`test_employment_review.py`、`test_employment_decisions.py` 和 `test_employment_scenarios.py`。测试必须指向独立合成目录；无需导入日常案件或模型密钥。

2026-11-16 已按用户授权完成实际 DeepSeek Flash 评测，批次总上限10元，律师复核前置已由用户取消。两轮完整指令评测仍有事实状态、工资单位及法条错误；另已运行真实模型调用 MCP 的保存/回读/Word 链路，不能用响应收齐或文件生成代替内容通过。见[实际模型证据与根因](../../../docs/checks/employment-live-20261116/README.md)。当前未开放的依据是这些实际失败，不是等待律师审批。

正式开放的下一步：先修复已经复现的工资条件作用范围、阶段切换绕过金额规则及自由文本事实约束，再用保留失败例和新反例复测。继续本批须先读取现有台账，累计不超过10元；新批次不自动继承历史额度。不以重复抽样直到偶然通过代替修复。通过后才修改开放清单、迁移摘要、路由及配套测试。

已知边界：候选 Skill 的文字指引不等于后台自动理解全部法律事实。后台只执行已实现的局部来源/算术保护，复杂主体和跨文件关系仍须人工核对。代理无业务工具场景和实际 MCP 测试分开，均不代替真实应用模型验收。
