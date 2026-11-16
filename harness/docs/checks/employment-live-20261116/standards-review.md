# Standards 独立审阅

- 基线：`0a88d1f4891c19d39ecba7c0cc6736b6d050c932`；比较当前未提交 `git diff 0a88d1f4`。
- 范围：`scripts/evaluate_skills.cjs`、`evaluate_practice_e2e.cjs`、campaign/budget/log及相关测试、`bridge/practice_eval_session.py`及测试。Skill最终开放配置待后续复核。
- 标准：仓库`AGENTS.md`、`CONTRIBUTING.md`、`docs/TESTING.md`、本轮`2026-11-16-employment-live-and-templates.md`；Ponytail及Fowler smells仅作审阅启发，不作为独立硬性门禁。
- 本审阅未调用真实模型、未读取真实凭据、未改产品或测试实现，未干预正在运行的评测。

## 发现

**P2，已修并独立复核关闭：E2E回调前置失败可能返回成功退出码。** 原实现中，`evaluate_practice_e2e.cjs`的`relay(id)`在`evaluate`的`try`之前执行。缺少`QX_TEST_PYTHON`时抛出的异常被`createModelCredentialStore.withSecret`转换成`unavailable`结果；主程序只检查`used`，不传播回调错误，随后`app.exit(0)`。已有结果文件触发的前置异常也处于同一传播缺口。当前脚本第88–95行在回调中捕获并脱敏保存`evaluationError`，返回后重新抛出，同时核验凭据封装返回状态，进入非零退出路径。来源标准：`docs/TESTING.md`要求失败返回非零，`CONTRIBUTING.md`要求按实际执行结果记录验证状态。

独立复现使用真实评测器源码与凭据封装实现，Electron、safeStorage及凭据内容均为临时合成夹具，`fetch`被禁止。修复前结果：`expectedExit=1`、`actualExit=0`、`networkRequests=0`；带断言探针退出码1。修复后同一独立探针为`expectedExit=1`、`actualExit=1`、`networkRequests=0`，断言退出码0。新增长期回归`evaluate-practice-preflight.test.cjs`的缺运行时及既有结果两项也独立实跑通过；核对无网络、无秘密进入进度日志、锁释放、既有结果保留。

当前预算、凭据隔离和失败状态范围没有剩余可行动的Standards发现。另按用户新增根因要求确认的工资正例三项误拦截仍未修复，详见[实际E2E根因诊断](e2e-diagnosis.md)。这些是本轮实际评测暴露的既有业务提取边界，不与退出码P2混为同一问题，也不据本审阅认定法律质量通过。

## 实际离线验证

以下Node命令工作目录均为本工作树`harness`。模型接口、真实安全存储、在途账本和真实案件均未访问。

```powershell
& 'F:/ai/resources/workbench/runtime/node.exe' --test scripts/skill-eval-budget.test.cjs scripts/skill-eval-campaign.test.cjs scripts/skill-eval-log.test.cjs scripts/test-practice-e2e-checks.cjs scripts/test-suite.test.cjs
```

结果：16通过、0失败、0跳过，退出码0。此前仅budget/campaign的5项检查为同一审阅第一阶段结果，不与此16项相加。

在工作树根目录执行：

```powershell
. 'D:/CodexChecks/AI-Shixiong-employment-20261116/test-env.ps1'
& $env:QX_TEST_PYTHON -m pytest -q harness/bridge/test_practice_eval_session.py
```

结果：2通过，退出码0；验证旧目录与新`.local`目录的真实MCP往返、越案/路径/工具限制、完整笔记和Word回读、原件不变。不是实际模型测试。

独立失败探针（工作目录`harness`）：

```powershell
& 'F:/ai/resources/workbench/runtime/node.exe' 'D:/CodexChecks/AI-Shixiong-employment-20261116/standards-e2e-missing-python-probe.cjs'
```

修复前结果：上述P2可复现，断言退出码1。修复后原探针重跑退出码0；脚本只在本机证据目录。长期回归可在其他机器复用：

```powershell
& 'F:/ai/resources/workbench/runtime/node.exe' --test scripts/evaluate-practice-preflight.test.cjs
```

本独审实际结果：2通过、0失败、0跳过，退出码0。不是付费模型测试。

工资诊断用原真实评测中的合成输入做10次实际MCP调用重放、9个函数级最小变体，以及最后一份笔记的显式回读/导出。原正例仍无工资比较结果，带`--assert-supported`的诊断命令退出码1，属于保留的失败证据；具体命令、逐轮归因和限制见[e2e-diagnosis.md](e2e-diagnosis.md)与[e2e-diagnosis.json](e2e-diagnosis.json)。

## 已核对边界与限制

两个评测入口复用同一employment campaign的10元账本及全局互斥锁；请求前同步预留，失败或未知usage保留预留，不能继承旧20元账本。live显式开关位于真实凭据模块加载之前；MCP仅暴露合成场景与固定允许集合交集，实际材料写入隔离`.local/employment-live-20261116/e2e`。费用费率沿用既有实现，本独审没有重新核验官网价格。内容/法律质量、当前真实评测结果、最终Skill开放及安装版不由本离线结果证明。
