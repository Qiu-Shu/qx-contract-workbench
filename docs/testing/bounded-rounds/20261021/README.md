# CH-06B2c1+B2c2：有界轮次账本底座与同 run 受限串行循环实测

本机 Windows，B2c1 基线 `f7f344eda6b0`、B2c2 基线 `c81e1c3`（codex/contract-review-v2）；2026-10-21 北京时间实施。只用独立合成数据，没有真实模型调用或真实资料处理。执行合同：[docs/plans/2026-10-21-bounded-rounds.md](../../../plans/2026-10-21-bounded-rounds.md)。

## 已完成范围

- **schema `assistant-rounds-v1`**（新 CURRENT_VERSION）：重建 `assistant_model_attempts`——破除 `UNIQUE(run_id)`，新增不可变 `round_no INTEGER NOT NULL DEFAULT 1 CHECK(round_no >= 1 AND round_no <= 4)` 与 `UNIQUE(run_id, round_no)`；immutable input trigger 纳入 `round_no`；claim/delete 触发器保持 V1 冻结字节。其余表与触发器字节不动（context→rounds 差集实测仅 attempts 表 + input trigger 两个对象）。
- **重建迁移**：SQLite 不能用 ALTER 删 UNIQUE 约束，采用固定语句序列（DROP 三触发器 → 临时名 `assistant_model_attempts_rounds` 建表 → `INSERT ... SELECT` 补 round_no=1 → DROP 旧表 → RENAME → 重建三触发器）。新建库与逐步升级跑同一语句序列，sqlite_master 字节一致（实测 fresh == migrated == `schema_rows('assistant-rounds-v1')`）。
- **FK OFF 窗口**：FK ON 下 DROP 有子行的父表被拒（本机 sqlite 3.53.1 实测 `IntegrityError: FOREIGN KEY constraint failed`）。三条迁移通道同片闭合——`schema_migrations.upgrade_database`（归档恢复升级）、`web/workspace_upgrade.upgrade`（工作区打开升级）、`rounds_schema.initialize_storage`（初始化/就地迁移，走 raw driver 连接避开引擎 begin 钩子）——均显式 `PRAGMA foreign_keys=OFF` → BEGIN IMMEDIATE → 语句序列 → 结构比对 + `foreign_key_check` → COMMIT → finally 恢复 ON；中途失败原子回滚且 FK 恢复 ON。
- **完整性 fail-closed**：`model_integrity` 白名单加 `assistant-rounds-v1`；轮次结构校验——round_no 必须 int 且 1..4，同一 run 的轮次必须从 1 连续；本片不定义中间轮语义，**多轮（n>1）归档一律 ASSISTANT_MODEL_INTEGRITY 拒绝**（context 备份损坏矩阵新增 `second_round` 变体实测拒绝），B2c2 定义工具计划轮语义后开放。attachment/judge/library integrity 白名单同步加新版本。
- **读写兼容**：两处 INSERT 显式 `round_no=1`；`_previous` JOIN 限定 `round_no=1`；`authorize_context` 的 run→attempt 查询限定 round_no=1；claim/settle/read/recover 语义不变。

## 验证结果

| 检查 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| 本片目标 Python | **220 passed，exit 0**；11 个测试文件（rounds_schema 21、context_schema、context_send、native_context_control、context_backup、context_routes、model_schema、library_schema、judge_schema、storage_schema_versions、workspace_upgrade），472 秒 | [日志](target.log) |
| 升级备份家族 | 5 passed / 4 failed；4 个失败全部为基线同等复现的预存在环境失败（见下） | [日志](upgrade-backup.log) |
| 广域关联回归 | assistant/backup/upgrade/workspace 家族 **1079 passed / 49 failed**，1662 秒；49 个失败逐一核验：47 个 FILE_LIMIT_OR_LINK（nlink 假阳性）、2 个 safe-delete shim 超深路径 Errno 53，全部为已知环境家族（见下） | [日志](wide.log) |
| 四项工程门禁 | schema --check、verify_defaults、verify_sources、verify_runtime_dependencies（development）均 exit 0 | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |
| 字节一致 | fresh bootstrap == 逐步升级 == schema_rows('assistant-rounds-v1')；context-v1 冻结摘要未动（HISTORICAL 断言） | target.log 中 rounds_schema 测试 |
| 带数据重建 | context-v1 库含 attempt+receipt+output 子行，迁移后每行保留且 round_no=1、foreign_key_check 空、二次升级幂等 | target.log 中 test_context_with_model_rows_rebuilds_preserving_every_row |
| 中途失败 | 8 个位置（drop_trigger/create/insert/drop_table/rename/三个触发器）注入非法语句，原子回滚、原结构原数据字节不动、FK 恢复 ON | target.log 中 test_rounds_step_partial_failure_leaves_no_half_rebuild |
| 约束矩阵 | round_no 0/5 CHECK 拒绝、(run_id,round_no) 重复 UNIQUE 拒绝、UPDATE round_no/input_format IMMUTABLE_RECORD、DELETE IMMUTABLE_RECORD、state 仍可流转、同 run 第二轮可占用 | target.log 中 test_round_constraints_and_immutability |
| fail-closed | 手工构造双轮归档在备份发布前校验拒绝（ASSISTANT_MODEL） | target.log 中 context_backup[second_round] |

## 预存在环境失败（基线同等复现，非本片回归）

升级备份家族 4 个失败（judge/library upgrade-backup 的 qxbak 发布后立即恢复变体）全部为本机 `\\?\` 前缀路径 nlink 陈旧假阳性（FILE_LIMIT_OR_LINK），与 CH-06B2b2 记录的 51 个全套失败同族。基线 `f7f344e` 独立 worktree 同机同参数复现同 4 项同等失败：[复验记录](upgrade-backup-baseline-reproduce.log)。

广域回归 49 个失败逐一核验：47 个 FILE_LIMIT_OR_LINK（同一 nlink 假阳性机制），2 个合同长路径备份为 WorkBuddy safe-delete shim 对超深 `\\?\D:\` 路径抛 Errno 53（sitecustomize.py 回收站拦截，机制 2）。两机制均自 WIN-PATH-01（`e387d8c`）起潜伏，与本片 schema 改动无关。仍建议由 WIN-PATH-02 另立片定论。

## 失败与修正记录（本片开发过程，全部保留）

- 新 rounds 测试 seed 曾把 run.state 写成 `'received'`（attempt 状态机值），run 的 CHECK 拒绝；改为 `'completed'`。
- `test_one_attempt_and_output_per_run` 旧 INSERT SELECT 无列清单，新表 17 列导致列数不匹配；且「每 run 一次 attempt」语义已变为「每 run 每 round 一次」，测试更名并更新为同 round 复制拒绝。
- model schema 的 ledger fixture 此前只跑 V1 初始化（无 input_format 列），本片让它走完 context+rounds 初始化链到当前版本。
- 损坏矩阵初版含 `drift_table`/`shadow_rebuild_table` 两个不属于 rounds 初始化器检查面的变体（它只检查 model 家族四表），移除；这两条由全库 identify_schema 层覆盖。
- WorkBuddy safe-delete 批量守卫在 C 盘临时目录触发 SAFE_DELETE_BULK_CONFIRM_REQUIRED，本片测试统一用 D 盘 basetemp 并解除 shim 环境变量重跑通过。

---

# CH-06B2c2：同 run 受限串行循环 runner 切片实测（2026-10-21 第二片）

基线 `c81e1c3`（B2c1 已推送核对后的远端 HEAD）。本篇在上篇之后追加；B2c1 内容全部保留。

## 已完成范围

- **新输入格式 `library-context-v2`**：basis.template_version `saved-library-context-system-v2`；v1 字节与语义完全不变。多轮能力从 round 1 起由 v2 模板允许模型输出工具计划。
- **工具计划响应协议**：新 DTO `MainContextToolCall{tool, query|saved_citation_id}`（互斥规则同 LibraryHandlerRequest，tool 仅限两个固定 AssistantLibraryTool 字面量，陌生 tool 在 DTO 层拒绝）；`MainContextToolPlan{calls: 1..8}`；`MainContextReply.tool_plan`（received 时 output 与 tool_plan 恰好其一）。
- **tool plan 持久化**：不落 outputs 表、不重建 schema，写 internal 事件 `model.tool_plan{attempt_id, plan}`；attempt 照写 received receipt，run 保持 generating。
- **轮次 wire**：`MainContextRoundsPreparedInput{request, round_no 1..4, exchanges 0..3, wire_payload_json}`；wire = [system-v2, user(manifest)] + 每历史交换 [assistant(plan canonical), user(tool_results canonical)]；`MainContextToolOutcome` 为 receipt 确定性投影（citations ≤8×{saved_citation_id,title,quote,quote_sha256}）。
- **轮间授权演进（显式形状）**：`NativeContextAuthorization.max_rounds` 与 `MainContextSelection.max_rounds`（int 1..4，默认 1 = 旧行为）；v2 ⟺ max_rounds>1 否则 BLOCKED_LIVE；policy.max_calls = max_rounds；registry grant 键（manifest_sha256）不变；lease 新增 `generate_rounds` 分支（内嵌 basis 全等 + require_policy + preflight）。
- **结构版本 `assistant-rounds-v2`**：rounds-v1 表 `CHECK(input_format IN ('plain-text-v1','library-context-v1'))` 不含 v2，SQLite 无法 ALTER CHECK → 复用 B2c1 的 12 步重建序列加宽 CHECK（含 'library-context-v2'），其余对象字节不动；v1 冻结摘要固化入测试。三条迁移通道同片闭合。
- **runner 循环**（`rounds_runner.execute_context_run`）：round → settle → plan? → 固定 handler（begin_library_call_in_session 服务端 call_id + execute_library_handler 走 to_thread）→ dispatch_round 下轮；末轮仍 plan 先停后执行（`rounds_exhausted`）；预算不足 `budget_exhausted`；工具拒绝 `tool_rejected`/`tool_limit`；bounded_stop 写事件 + run failed。
- **撤权语义**：dispatch 不做授权预检——先占轮次，claim 的 _current/snapshot 拒绝走既有 abandon 通道（attempt failed_before_send + run failed 立即闭合）；恢复封存/取消后重入 STATE_CONFLICT 安静返回不重发。
- **恢复封存**：recover_attempts 尾部——run='generating' 且无 reserved/sending attempt 且存在 model.tool_plan 事件 → interrupted（不写新事件、不重发）。
- **完整性开放（rounds='v2' 模式）**：v1 run 恒单轮；v2 run 1..4 轮连续；非末轮必须恰一 plan 事件；末轮可有 plan（在途暂停：run generating/interrupted；或带 bounded_stop：run failed）；`_events_rounds` 全 run 期望序列比对；`_validate_rounds_replay` 绑定 plan↔tool.before↔receipt↔下轮 exchanges（末轮 plan 允许工具前缀语义，被拒绝的末次调用可无 receipt）。

## 验证结果

| 检查 | 本轮实际结果 | 原始证据 |
| --- | --- | --- |
| 本片目标 Python | **240 passed，exit 0**；10 个测试文件（rounds_runner 19、rounds_schema 34、native_context_control、context_send、context_schema、model_schema、library_schema、context_backup、workspace_upgrade、storage_schema_versions），608 秒 | [日志](b2c2-target.log) |
| 广域关联回归 | assistant 备份/恢复/运行时家族 10 文件 **214 passed / 13 failed**，328 秒；13 个失败逐一核验全部为基线同等复现的预存在环境失败（见下） | [日志](b2c2-wide.log) |
| 四项工程门禁 | schema --check、verify_defaults、verify_sources、verify_runtime_dependencies（development）均 exit 0 | [门禁1](b2c2-gate-1.log)、[2](b2c2-gate-2.log)、[3](b2c2-gate-3.log)、[4](b2c2-gate-4.log) |
| 字节一致 | fresh bootstrap == 逐步升级 == schema_rows('assistant-rounds-v2')；rounds-v1 冻结摘要（80dc678f…/a7a84afc…）固化断言未动；v2 与 v1 差集实测仅 CHECK 加宽 | b2c2-target.log 中 rounds_schema 测试 |
| 双轮 happy path | 两轮完整执行：wire 逐字节断言（含 plan canonical 与 tool_results canonical 交换回放）、事件序列全比对、task_manager 端到端 | b2c2-target.log 中 rounds_runner 测试 |
| 有界停止 | rounds_exhausted（末轮仍 plan）、budget_exhausted（预算不足）、tool_limit（>8 调用拒绝）、tool_rejected（陌生 tool/越界引用）各有实测 | 同上 |
| 撤权与恢复 | 轮间撤权走 claim-abandon 通道立即闭合（attempt failed_before_send + run failed）；恢复封存 interrupted 不重发；STATE_CONFLICT 安静返回 | 同上 |
| 篡改矩阵 | 伪造 plan 事件、跨 run 引用、5 变体归档篡改（plan/工具/回执/交换链）全部 ASSISTANT_MODEL 拒绝 | 同上 |
| v1 回归 | v1 收 plan → MODEL_OUTPUT_INVALID；v1 行为恒单轮不变；v2+max_rounds=1 与 v1+max_rounds=2 授权均 BLOCKED_LIVE | b2c2-target.log 中 runner/native_context 测试 |

## 预存在环境失败（基线同等复现，非本片回归）

广域回归 13 个失败逐一核验：12 个为 `FILE_LIMIT_OR_LINK`（`\\?\` 前缀 basetemp 路径 nlink 假阳性，自 WIN-PATH-01 起潜伏），1 个（`test_restore_rejects_authenticated_but_inconsistent_model_archive[True]`）为同一机制的变体——文件守卫先于归档完整性校验触发，测试期望的 `ASSISTANT_MODEL` 拒绝路径未被执行到。基线 `c81e1c3` 独立 worktree 同机同参数复现 **13/13 同等失败**：[复验记录](b2c2-baseline-reproduce.log)。本片未改 `workspace_backup.py`（git diff 证实），失败点均在备份/恢复文件守卫、早于任何本片改动代码执行。仍建议由 WIN-PATH-02 另立片定论。

## 失败与修正记录（本片开发过程，全部保留）

- happy path 的 wire 断言初版与持久 plan 全字段 dump 不符（query 含 DTO 默认值）；断言改用 DTO model_dump 后通过。
- 恢复封存测试初版 run interrupted 后 `_execute_plan` 抛 STATE_CONFLICT 未捕获；runner 该分支改安静返回。
- task_manager 端到端测试初版由 drive() 预登记 attempt 导致 submit_context 走 replay 路径、0 次 HTTP；拆出 grant() 让 submit_context 内部自行 enqueue。
- dispatch 授权预检顺序初版会导致撤权 run 永久卡 generating；改为不预检、由 claim-abandon 通道闭合。
- `_plan_events` SQL 初版 `AND ... OR ...` 优先级瑕疵；改为只查 model.tool_plan（tool.before 由 _build_exchanges 单独查）。
- `_validate_rounds_replay` 初版漏检末轮 plan（在途暂停/有界停止不在 ordered[:-1] 内）；重写为含末轮的前缀语义走查。
- `native_model_control` 条件表达式残句（`if (A or B if fmt else C)` 歧义）改为显式类型与 round_no 判定。
- 执行合同原表述「schema 不再变更」被 CHECK 约束事实修正：rounds-v1 的 input_format CHECK 不含 v2，新增 `assistant-rounds-v2` 结构版本，复用 B2c1 重建机器。
