# 中国法研究增量验证（2026-11-12）

范围：审核后续计划 Task 1。工作树为 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，产品目录为其下 `harness/`。本轮没有修改原工作目录、安装产品、发布或调用付费模型。以下均为源码与本机合成资料验证，不是法律质量认证。

## 交付与接口

新增四项 Harness 适配入口及同内容安装副本：

| 方法 | 中文名 | 既有底稿 kind |
| --- | --- | --- |
| qx-authority-check | 法源与版本核验 | legal_research_authority_check |
| qx-case-comparison | 类案对比 | legal_research_case_comparison |
| qx-issue-memo | 争点研究备忘录 | legal_research_issue_memo |
| qx-lecture-source-pack | 法律讲座来源包 | legal_research_lecture_source_pack |

共用 `workspace-seed/legal-library/workbench/legal-research.md`，配置参考副本在 `config/skill-references/legal-research.md`。检索复用 legal_search / legal_search_read，官方原文回读复用 web_fetch，本地原文复用案件材料读取。正文证据卡保存 original、title、issuer、article、caseNo、factDate、researchDate、region、version、effect、applicability、evidence、status、unresolved 及来源编号。

**实现决定：复用既有持久化。** record_case_note 的正文及 citations 已能保存完整研究内容、原始引用和版本；read_case_note 支持分页回读，export_case 按指定 note_ids 导出，CaseStore 提供案件隔离、追加及更正历史。因此没有新增数据库、DTO 或 MCP 工具，也没有修改共享业务工具目录。四态“已核验／部分核验／未核验／不适用”是有依据的研究者评估，程序的 matched 只表示逐字引用匹配；review_status 仍为 unverified。自由底稿保存不具备来源约束专用工具的法律事实验证能力，适配方法明确区分这些含义。

已有上下文、案件记录和研究先回读复用，缺关键事实才补问，不重跑首用画像问卷。无法取得原文或效力/适用依据时保存缺口和失败信息，未知不写成否定。讲座日期与研究日期分开，未来复核只是待办，不创建自动任务或发送材料。

安装继续使用 initialize 的非覆盖式 workspace-seed 复制与已有技能根目录配置；没有额外迁移版本或重写用户配置。测试中一个同名自定义且禁用的方法保持逐字不变，另外三项新增后可发现，自有方法保留，二次初始化仍保留上述状态。实际 Harness provider 的指定目录发现 **194 项，158 项可自动调用，36 项旧入口继续停用**。旧法律 ZIP 175 项目录及其历史统计不改写；新研究来源单列 research_adapters 与 provenance。

中文名同时进入配置及源安装 UI 补丁。打包阶段从现有 UI 映射补充配置名称，保留其它名称及周边 UI 代码，将标签配置记为源文件、变换后 UI 记为 generated 哈希，供既有来源校验使用。补丁：`patches/@deepseek-ai__dsh-client-ui-skill@0.2.2-alpha.2.patch`；其 lock 哈希由主任务统一刷新。本 Task 未改 package.json 或 pnpm-lock.yaml。

## 来源核验

2026-11-12T06:50:01Z，通过 GitHub 连接器读取 [CSlawyer1985/claude-for-legal-ZH 固定提交](https://github.com/CSlawyer1985/claude-for-legal-ZH/tree/59f37f1c8851b8277e24f7a45f4e773bee97bab9/legal-research-cn)。四个原始 SKILL.md 与 LICENSE 保存在 `workspace-seed/legal-library/research-cn/`；上游 Apache-2.0，作者 CSlawyer、主页 chenshi.ai。该提交递归树未见 NOTICE 文件。上游脚本未执行，外部数据库未接入。

逐文件 URL、Git blob SHA 与本地 SHA-256 见 `sources/legal-research-cn.json` 和随安装种子保留的 provenance.json。离线测试对五个原文件同时核对 SHA-256 与 Git blob SHA（含 blob 长度头），并验证 Apache 2.0 文本、适配修改声明、本机引用链接、真实业务工具名和目录映射。

## 实际执行记录

以下命令除单独标注外 cwd 均为本工作树的 `harness/`。环境复用 `.local/audit-0216/build/test-env.ps1` 指定的已有 Node/Python 依赖，未安装依赖。

```powershell
. './.local/audit-0216/build/test-env.ps1'
node --test tests/legal-research-skills.test.cjs
```

首次新增检查后退出 **1**，**3 失败**：四项方法、来源清单和安装副本尚不存在。实现后检查夹具另修正了实际 provider 必需的 customSkillDirs、模型恢复迁移测试配置以及停用前置字段 user-invocable，均未修改生产迁移逻辑。

```powershell
. './.local/audit-0216/build/test-env.ps1'
node --test packaging/skill-labels.test.cjs
```

新增中文名检查后退出 **1**，**3 失败**：打包标签函数尚不存在，源码 UI 补丁尚无四项名称。随后实现标签变换及补丁，并增加实际已装 UI 副本与无效配置验证。

```powershell
. './.local/audit-0216/build/test-env.ps1'
node --test packaging/skill-labels.test.cjs packaging/stage.test.cjs packaging/verify-stage.test.cjs tests/legal-research-skills.test.cjs desktop/installed-skill-migration.test.cjs desktop/skill-quality-migration.test.cjs plugins/legal-search/core.test.mjs plugins/legal-search/integration.test.mjs
```

退出 **0**，**44 项：42 通过、2 跳过、0 失败**。跳过项为既有测试缺少历史本机路由/基线记录，未称为通过。覆盖实际技能发现/执行、旧自定义和禁用保留、搜索原始响应与失败状态持久化、中文名映射及发布输入哈希检查。

```powershell
. './.local/audit-0216/build/test-env.ps1'
$env:PYTHONPATH=(Join-Path (Get-Location) 'bridge')+';'+(Join-Path (Get-Location) 'legacy/src')+';'+$env:PYTHONPATH
$env:QX_LEGACY_ROOT=Join-Path (Get-Location) 'legacy'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& $env:QX_TEST_PYTHON -m pytest -q bridge/test_legal_research_persistence.py bridge/test_business_store.py bridge/test_source_bound_mcp.py bridge/test_legal_search_fallback.py
```

退出 **0**，**30 测试和 9 子测试通过**。研究新增部分为 **5 项**：实际 stdio MCP 四种底稿保存/幂等重试/分页回读/选定记录导出和重开存储；缺引用、伪造引用、变更版本三种情形均不认证；跨案读取/引用被拒绝且更正保留历史。导出的真实 DOCX 回读检查字段、四态及内容，原件字节不变。最初单独 Python 尝试因未设置 QX_LEGACY_ROOT 在收集阶段退出 **2**（1 收集错误、未执行测试）；补齐上述环境后正常通过。

最终小改动（标签字符串替换使用回调以保留字面值；合成证据示例的核验范围明确）后的目标复测：

```powershell
. './.local/audit-0216/build/test-env.ps1'
node --test packaging/skill-labels.test.cjs tests/legal-research-skills.test.cjs
# Python 环境同上
& $env:QX_TEST_PYTHON -m pytest -q bridge/test_legal_research_persistence.py
```

分别退出 **0 / 0**，**8 个 Node 测试、5 个 Python 测试通过**。未请求真实模型或实际法律检索；所有法律示例均为虚构演示资料。

在工作树根执行 `git apply --numstat harness/patches/@deepseek-ai__dsh-client-ui-skill@0.2.2-alpha.2.patch`，退出 **0**，补丁解析为 lib/client.js **207 增、6 删**；本任务文件 `git diff --check` 退出 **0**。没有将补丁应用到用户安装目录。

## 仍需区分的边界

本轮证明目录可发现、工具可调用、证据及未知状态能持久保存回读、升级保留设置和中文名称映射；没有运行全部方法的真实模型法律研究，也未由律师逐案验收适用性判断。离线证据卡的四态往返保存不等于程序能自行判断法律有效性。未制作或安装产品新版；完整分支测试、独立审阅与合并提交由主任务统一执行和记录。
