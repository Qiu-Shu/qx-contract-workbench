# CH-06B2c：有界多轮执行合同（B2c1 轮次账本底座先行）

基线：`f7f344e`（codex/contract-review-v2）。依据 [B2 就绪审查](2026-10-20-library-b2-readiness.md) 的 B2c 段与 v2.1 §6.3「一个运行默认最多4轮主模型响应、8次工具调用」。执行者：WorkBuddy（本机直接实施）。

## 总目标（CH-06B2c 全片）

同一 run 内串行受限循环：model round → 固定 library handler → 下轮或 final；主模型逻辑轮 ≤4、工具调用 ≤8（B1 持久 tool.before 为最终核验）；仅最终合法候选使 run completed；到上限保存有界停止原因；恢复封存轮次与工具记录，不重发。

## 拆分理由

多轮要求 `assistant_model_attempts` 破除 `UNIQUE(run_id)`。SQLite 不能用 ALTER 删除约束，只能按 12 步重建表；这是全片风险最高点（FK 子表 receipts/outputs/input_citations、不可变触发器、sqlite_master 字节一致铁律、FK OFF 窗口）。故拆两片：

- **B2c1（本片）**：轮次账本结构底座 `assistant-rounds-v1`，行为不变（恒 round_no=1）。
- **B2c2（后续）**：受限循环 runner、工具计划响应协议、轮间授权演进、≤4/≤8 执行与有界停止。

## B2c1 本片范围

1. **schema `assistant-rounds-v1`**（新 CURRENT_VERSION）：重建 `assistant_model_attempts`——去掉 `UNIQUE(run_id)`，新增不可变 `round_no INTEGER NOT NULL DEFAULT 1 CHECK(round_no BETWEEN 1 AND 4)`，新增 `UNIQUE(run_id, round_no)`；immutable input trigger 纳入 `round_no`；三个 attempts 触发器重建。其余表与触发器字节不动。
   - 重建序列（固定语句，新建库与迁移库同序执行保证字节一致）：DROP 三个 attempts 触发器 → `CREATE TABLE assistant_model_attempts_rounds(...)`（临时名）→ `INSERT ... SELECT ..., 1` → `DROP TABLE assistant_model_attempts` → `RENAME TO assistant_model_attempts` → 重建三个触发器。
   - FK 事实：FK ON 下 DROP 有子行的父表被拒（本机 sqlite 3.53.1 实测 IntegrityError）。`schema_migrations.upgrade_database` 增加显式「本目标链含重建迁移」分支：BEGIN 前 `PRAGMA foreign_keys=OFF`，提交前 foreign_key_check，提交后恢复 ON；`rounds_schema.initialize_storage`（SQLAlchemy 连接常开 FK）在 connect 后、BEGIN 前显式 OFF，同序语句，提交前校验。
2. **入口一致**：`storage_schema` 追加版本并冻结全部旧版本行；`schema_migrations.statements_for` 接受新版本；`storage_bootstrap` 链追加 rounds 初始化；`model_schema`/`context_schema` 的 initialize_storage 明确接受 rounds 后继结构，拒绝半迁移。
3. **读写兼容**：`attempts.py` 两个 INSERT 显式写 `round_no=1`；`_previous` JOIN 限定 `round_no=1`；`native_model_control.authorize_context` 的 run→attempt 查询限定 round_no=1；claim/settle/read/recover 语义不变。
4. **完整性闭合（fail-closed）**：`model_integrity` 白名单加 `assistant-rounds-v1`；轮次结构校验——同一 run 的 round_no 必须恰好为从 1 开始的连续整数且 ≤4；**本片不定义中间轮语义，多轮（n>1）归档一律 ASSISTANT_MODEL_INTEGRITY 拒绝**，B2c2 定义工具计划轮语义后开放。attachment/judge/library integrity 白名单同步加新版本。
5. **备份恢复同一 seam**：context-v1 归档恢复后按既有链升级到 rounds-v1；多轮手工构造归档在恢复校验中拒绝；恢复 fence 复用 recover_attempts，不重建许可、不重发。

## 验收

- 冻结 context-v1（及全部旧版本）结构摘要不变；旧固定 fixture 升级逐条比对、数据行保留、round_no 全为 1、foreign_key_check 空。
- 三入口结构相等：新建 bootstrap == 逐步升级 == schema_rows('assistant-rounds-v1')。
- 重建中途失败（伪造冲突对象/非法语句）原子回滚，原结构原数据字节不动，无半迁移。
- 结构损坏矩阵（缺触发器/旧触发器/多余索引/缺关联表/轮次越界与重复）全部拒绝且不修复。
- round_no 不可变（UPDATE 触发器拒绝）、DELETE 拒绝、CHECK 0/5 拒绝、UNIQUE(run_id,round_no) 重复拒绝。
- 单轮既有行为回归：context send/native/backup/routes 等关联目标全绿；四开发门 exit 0。
- 多轮合成归档：schema 层可构造合法双轮行；完整性校验按本片边界拒绝（n>1），证明 fail-closed。

## 边界

无新发送能力、无 runner 循环、无协议/授权/UI 变更；真实供应商仍不接；旧 V1/context 字节与权限语义不变；合成数据，不用真实材料。
