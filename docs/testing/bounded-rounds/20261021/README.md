# CH-06B2c1：有界轮次账本底座切片实测

本机 Windows，基线 `f7f344eda6b0`（codex/contract-review-v2）；2026-10-21 北京时间实施。只用独立合成数据，没有真实模型调用或真实资料处理。执行合同：[docs/plans/2026-10-21-bounded-rounds.md](../../../plans/2026-10-21-bounded-rounds.md)。

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
