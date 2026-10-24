# TaskDraft A＋B：迁移、备份与恢复验证

日期：2026-10-24；工作区：`D:\Documents\ChatGPT\律所项目`；分支：`codex/contract-review-v2`。

本文件只记录存储子任务的实际验证，不代表整体产品验收、真实通道或真实模型完成。测试材料均为独立合成材料。本子任务未提交、推送或操作真实运行库。

## 实现范围

- 追加 `task-drafts-v1`；初始化、数据库复制升级和原生升级共用已有迁移链。新表为 channel bindings、inbox events、drafts、draft event links、executions、media resolutions。
- 保留 12 个旧版本、普通/原生 24 种结构的 48 份 raw/normalized 指纹，固定于 `tests/fixtures/task_drafts_schema_predecessors.json`。旧档案、模型、裁判、法库和附件完整性校验继续执行。
- `task_drafts/integrity.py` 校验规范 JSON/摘要、工作区及会话归属、原附件/解析版本、事件顺序、媒体处理历史、冻结清单及案件文档/审查成果映射。审查输入摘要从持久 ReviewContext 重建；最终执行状态不得与真实 Mock ReviewRun 状态相反。
- `.qxbak` 验证新表及其来源链；非原生 `.cnbak` 中存在 TaskDraft 历史时明确拒绝，不静默遗漏。
- 两条恢复入口均调用 `quarantine_executions`：prepared、creating_matter、awaiting_facts、queued、running 转为 blocked/restored_read_only。恢复围栏记录收件关闭；历史保持可读，创建绑定、收件、重复冻结和推进执行被现有 `require_active` 阻断。
- 修正两处旧测试的“最新版本”预期：历史版本定义及旧指纹夹具不变。

## 实际命令及结果

所有命令在上述工作区执行；解释器为 `.venv/Scripts/python.exe`。输出来自本会话实际工具执行，未另存独立终端原始日志；以下数量不跨重叠运行累计。

| 阶段 | 命令（解释器后参数） | 退出码 | 实际结果 |
| --- | --- | --- | --- |
| 迁移 RED | `-m pytest tests/integration/test_task_drafts_migration.py -q` | 1 | 27 failed、24 passed；36.58s。新版本尚缺，旧指纹通过。 |
| 中间开发检查 | `-m pytest tests/integration/test_task_drafts_migration.py -q --tb=short` | 1 | 12 failed、51 passed；42.61s。其中 4 项发现部分 schema 初始化未拒绝；另 8 项被临时 `model_integrity.py` 语法错误阻断，不能当作有效功能 RED。已修正。 |
| 来源损坏 RED | `-m pytest tests/integration/test_task_drafts_migration.py -q -k 'source_corruption' --tb=short` | 1 | 7 failed、1 passed、55 deselected；18.84s。7 类任务篡改未被已有备份校验发现。 |
| 来源/结构 GREEN | `-m pytest tests/integration/test_task_drafts_migration.py -q -k 'source_corruption or partial_task' --tb=short` | 0 | 12 passed、51 deselected；24.19s。包括认证但语义损坏的备份拒绝发布恢复目录。 |
| 恢复隔离 RED | `-m pytest tests/integration/test_task_drafts_migration.py -q -k 'restore_blocks or actual_task_service' --tb=short` | 1 | 5 failed、1 passed、63 deselected；15.67s。未完成任务恢复后仍保持可执行状态。 |
| 存储整文件 GREEN | `-m pytest tests/integration/test_task_drafts_migration.py -q --tb=short` | 0 | 69 passed；83.99s。当时该文件全部用例。 |
| 审查映射 RED | `-m pytest tests/integration/test_task_drafts_migration.py -q -k completed_bridge --tb=short` | 1 | 1 failed、2 passed、69 deselected；6.18s。发现 review_input_sha256 未重建核验。 |
| 审查映射 GREEN | 同上 | 0 | 3 passed、69 deselected；7.92s。 |
| 旧 latest 断言 RED | `-m pytest tests/integration/test_assistant_profile_model_integrity.py::test_empty_successor_runs_all_archive_validators -q --tb=short` | 1 | 2 failed；1.93s。断言硬编码旧当前版本。 |
| 旧 latest 断言 GREEN | 同上 | 0 | 2 passed；2.05s。 |
| 终态一致性 RED | `-m pytest tests/integration/test_task_drafts_migration.py -q -k archive_execution_state --tb=short` | 1 | 2 failed、72 deselected；5.16s。真实 Mock 成功/失败记录均被伪造相反执行终态；失败样本通过真实 workflow 的 require_legal_rules 阻断路径产生。 |
| 终态/映射 GREEN | `-m pytest tests/integration/test_task_drafts_migration.py -q -k 'archive_execution_state or completed_bridge' --tb=short` | 0 | 5 passed、69 deselected；11.73s。 |
| 差异空白检查 | `git diff --check` | 0 | 无输出。 |

最新文件有 74 个用例；69 项整文件通过发生在最后 5 项新增之前，最后 5 项随后定向通过，不表述为一次 74 项整文件运行。旧存储大范围兼容回归、整体应用回归和独立审查由主任务另记。

## 最后产品修改及边界

2026-10-24 16:39（Asia/Shanghai）状态一致性补丁之后，相关 5 项已通过；本子任务此时不再修改产品。

- `src/cn_contract/task_drafts/integrity.py` SHA-256：`970de33ea5825513a61817a359f7fd152be2e93d0db42c49f44a8d0b49f787d3`。
- `tests/integration/test_task_drafts_migration.py` SHA-256：`14c622e64c55780b159c0e9f44fcb632d38a472922f5b7dbfaa721e6a0cc5785`。
- `tests/fixtures/task_drafts_schema_predecessors.json` SHA-256：`2e5e07ad05e0193edba8aeda0cad0d05bf3d4c1842b77584bae0fb73be58b88a`。

未运行：真实微信、真实模型、真实合同、真实账户/外发、生产迁移、全仓完整测试、Windows 安装包验收。这里的恢复通过不关闭既有 WIN-PATH-02 偶发长路径目录改名问题。以上时点的真实 `.qxbak` 往返覆盖待执行状态；随后补充的已完成成果往返见下段。

## 原生已完成 Mock 成果往返补验

主任务随后贯通原生 assisted 工作区的受控 Mock 路径，运行配置绑定 `task_execution_id`。本子任务新增独立 `tests/integration/test_task_drafts_completed_backup.py`，不修改正在由主任务回归的迁移测试及产品文件。

用例使用真实 `initialize_workspace` 创建合成原生工作区，复用既有桥接夹具、注册合成 DOCX、事实人工确认及 Mock 审查。冻结父任务后再补充子任务：一项待到材料经 resolve 关联第二份附件，一项不支持的合成资料经明确理由 exclude；两份来源字节相同但附件及目标版本 ID 不同。子任务完成 Mock，父任务仍待执行。

随后实际执行 `.qxbak` 创建 → 恢复 → 对恢复副本再次创建 `.qxbak` → 再次恢复。两代均验证：

- 11 张来源/任务/媒体处理/文档/审查历史表逐行相等；已完成 execution 行及历史 ReviewRun 完全相等。
- 2 项媒体 resolve/exclude 历史、2 个事件、两份同哈希不同附件的独立版本映射及 4 份受保护原件完整保留；附件原件与目标案件原件实际读取字节一致。
- 已完成子任务保持 completed；待执行父任务恢复为 blocked；两代围栏数分别为 1、2。
- 每代重复准备、重复审查、创建绑定、新收件、重复冻结共 5 种操作均返回 `BLOCKED_LIVE`；两代共 10 次拒绝，任务及审查记录不变，review 调用 0。
- 原始工作区数据库字节和全部受保护文件摘要不变。恢复后仅使用 `read_run(current=False)` 核对历史成果，不将其解释为当前批准仍有效。

实际命令：`.venv/Scripts/python.exe -m pytest tests/integration/test_task_drafts_completed_backup.py -q --tb=short`。

| 执行 | 退出码 | 实际结果 |
| --- | --- | --- |
| 首跑 | 1 | 1 failed，7.98s。第一次恢复、历史/原件读取及禁写验证已通过；测试用普通 `Path.rglob` 未枚举到 Windows 长路径下的两份附件。此为测试枚举方式缺陷，非已证实的数据丢失。 |
| 修正测试后 | 0 | 1 passed，9.07s。测试文件枚举复用已有 `filesystem_path`；两代完整往返及全部断言通过。产品没有因此修改。 |

本补验没有连接真实微信、真实模型、外部账号或真实合同，没有提交/推送。该结果不替代主任务整体回归或 WIN-PATH-02 专项验收。

## 原生旧版升级夹具补修

主任务的 27 文件广泛存储回归发现 `test_workspace_upgrade.py` 失败；其定向诊断实际命令为 `.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_workspace_upgrade.py::test_upgrade_keeps_identity_login_case_and_independent_backup --tb=short --basetemp .local/task-drafts-20261024/verification/tmp-upgrade-diagnosis`，退出 1，1 failed，3.26s，错误 `WORKSPACE_DATABASE_MISMATCH`（主任务提供执行结果）。

核实根因：该文件 legacy 夹具先创建最新数据库，再按旧列表删除扩展表来模拟 pre-intake；列表遗漏本片新增 6 张 task 表及其附属触发器/索引，因此生成的并非受支持的 pre-intake 数据库。产品严格拒绝这一混合结构是正确行为。

本子任务仅更新此测试夹具，先删除 task_media_resolutions、task_executions、task_draft_events、task_drafts、task_inbox_events、task_channel_bindings；再显式断言实际 sqlite_master 与固定 `schema_rows('pre-intake', native=True)` 相等。产品识别、旧结构/指纹及拒绝断言均未放宽。

首次整文件复验命令：`.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_workspace_upgrade.py --tb=short --basetemp .local/task-drafts-20261024/verification/tmp-workspace-upgrade-storage`。exec session 为 16148，执行中用户中断；没有取得最终退出码或结果计数，不能记为整文件通过。2026-10-24 16:55:30 检查实际 Windows Python 进程，只有主任务广泛回归仍运行，本文件独立进程已不存在；临时目录最后到部分 marker failure 测试。后续完整结果另补，未以临时目录数量推算 PASS。

确认该独立进程已结束后，使用新临时目录补跑一次完整文件：`.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_workspace_upgrade.py --tb=short --basetemp .local/task-drafts-20261024/verification/tmp-workspace-upgrade-storage-complete --junitxml=.local/task-drafts-20261024/verification/workspace-upgrade-storage-complete.xml`。实际退出码 **0**，**58 passed in 144.29s**。JUnit 同时确认 tests=58、failures=0、errors=0、skipped=0。stdout 和退出码分别保存在 `.local/task-drafts-20261024/verification/workspace-upgrade-storage-complete.log`、同名前缀的 `.exitcode` 文件。

本补修仅改旧版测试夹具及此记录；任务表、旧库指纹、迁移实现和恢复完整性检查没有因此修改。主任务此前已导入旧夹具的广泛回归结果仍需如实保留，其旧夹具失败由本次独立 58 项完整复验覆盖，不能改写为原广泛运行全通过。

## Library 迁移精确增量预期补修

主任务广泛存储回归最终结果为 **675 passed、56 failed，退出码 1，1364.94s**（`.local/task-drafts-20261024/verification/storage.log`）。其中 55 个失败来自上述已补修的旧版升级夹具；其余 1 个为 `test_assistant_library_schema.py::test_library_chain_upgrades_judge_to_current_with_exact_delta`。已直接核对该日志的失败差异：实际迁移增量仅比旧精确集合多出 task_channel_bindings、task_inbox_events、task_drafts、task_draft_events、task_executions、task_media_resolutions 六张表。此结果作为实际 RED，不重复运行旧断言。

本次只在该精确集合中逐个加入这六个表名；仍然使用集合相等断言，未改动态集合或子集比较。`HISTORICAL` 两个固定指纹、历史对象替换集合、旧 schema 检查及产品实现均未改。

完整复验命令：`.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/integration/test_assistant_library_schema.py --tb=short --basetemp .local/task-drafts-20261024/verification/tmp-library-schema-storage-complete --junitxml=.local/task-drafts-20261024/verification/library-schema-storage-complete.xml`。实际退出码 **0**，**38 passed in 39.56s**；JUnit tests=38、failures=0、errors=0、skipped=0。stdout、JUnit、退出码保存在 `.local/task-drafts-20261024/verification/library-schema-storage-complete.log`、同名前缀的 `.xml` 和 `.exitcode`。

原广泛运行的失败结果保留；两个受影响文件分别完成 58 项、38 项整文件补验，不表述为原 731 项运行全通过。
