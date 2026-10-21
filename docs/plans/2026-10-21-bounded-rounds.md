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

---

# CH-06B2c2：受限串行循环 runner（本片）

基线：B2c1 已合并（`287ff6a`，结构版本 `assistant-rounds-v1`）。本片定义中间轮语义并开放多轮完整性校验。

## 设计定稿（调研结论）

### 1. 工具计划响应协议（library-context-v2）

- 多轮能力从 round 1 起就需要模型被允许输出工具计划，故引入新输入格式 **`library-context-v2`**（basis.template_version `saved-library-context-system-v2`），v1 字节与语义完全不变。
- 新 DTO：`MainContextToolCall{tool, query|saved_citation_id}`（互斥规则同 LibraryHandlerRequest，tool 仅限两个固定 `AssistantLibraryTool` 字面量——陌生 tool 在 DTO 层即拒绝）；`MainContextToolPlan{calls: 1..8}`。
- `MainContextReply` 增加 `tool_plan` 字段：state='received' 时 output 与 tool_plan 恰好其一；非 received 时两者皆空。v1 attempt 收到 plan 一律 MODEL_OUTPUT_INVALID。
- **tool plan 持久化**：不落 outputs 表（该表只存最终候选、不重建 schema），写 internal 事件 `model.tool_plan{attempt_id, plan}`；attempt 照写 received receipt，run 保持 generating。下轮 wire 从持久事件与 handler receipts 确定性重建。

### 2. 轮次 wire

- 统一 prepared 类型 `MainContextRoundsPreparedInput{request: MainContextRequest, round_no: 1..4, exchanges: 0..3, wire_payload_json}`（round 1 exchanges=()）。
- wire = [system-v2, user(manifest)] + 每个历史交换 [assistant(plan canonical), user(outcomes canonical)]；outcome 为 receipt 的确定性投影 `MainContextToolOutcome{receipt_id, tool, citations:≤8×{saved_citation_id,title,quote,quote_sha256}}`。
- basis.wire_sha256 只承诺 round 1 wire；round n 的 request_sha256 由持久化 + 重建比对保护（context_integrity 同一 seam）。

### 3. 轮间授权演进（显式形状）

- `NativeContextAuthorization.max_rounds: int 1..4 = 1`（默认旧行为）；`MainContextSelection.max_rounds` 同步（preview 按模板重建 basis）。
- v2 ⟺ max_rounds>1，不一致即 BLOCKED_LIVE；policy.max_calls = max_rounds；指纹自动纳入新字段；registry grant 键（manifest_sha256）不变。
- 预算：authorize 保留单次下限检查；每轮 dispatch/claim 由既有 `_budget` 按 policy_id 累计计数与费用（多轮共享 policy_id，自然 ≤max_calls）。
- lease 增加 v2 prepared 发送分支：校验内嵌 request.basis 全等 + require_policy(manifest_sha256) + preflight，与 v1 同一强度。

### 4. runner 循环（rounds_runner.execute_context_run）

- round n：execute_attempt（复用 claim/settle）→ 读持久状态：candidate→completed 返回；error→failed 返回；plan→继续。
- plan 处理：逐项 `begin_library_call_in_session`（call_id 服务端生成，持久 tool.before 计数到 8 拒绝 LIBRARY_TOOL_LIMIT）→ `execute_library_handler`（adapter I/O 走 to_thread）；任何拒绝 → `model.bounded_stop{reason: tool_rejected|tool_limit}` + run failed。
- 下轮 dispatch 前短事务 `attempts.dispatch_round`：重建 exchanges、prepare_rounds、INSERT 占用 UNIQUE(run_id, round_no)、budget 检查；末轮仍收到 plan → 先停后执行（`rounds_exhausted`，不再跑工具）；预算不足 → `budget_exhausted`；均写 bounded_stop + run failed。
- 轮间撤权/换 session：dispatch 不做预检——先占用轮次，claim 的 _current/snapshot 拒绝走既有 abandon 通道（attempt failed_before_send + run failed，立即闭合）。恢复封存（interrupted）或取消后重入：STATE_CONFLICT 安静返回当前视图，绝不重发。
- task_manager.submit_context 按 view.input_format 分派 v2 → execute_context_run（传 library_adapter）。
- 新增结构版本 `assistant-rounds-v2`：rounds-v1 的 CHECK 不含 library-context-v2 且 SQLite 不能 ALTER CHECK，故按同一 12 步重建加宽；其余对象字节不动；v1 归档多轮仍 fail-closed。

### 5. 完整性开放（model_integrity rounds 模式）

- v1 run 恒单轮；v2 run 1..4 轮连续从 1。
- 中间轮（非末轮）：state='received'、error_code=None、无 output、恰一 `model.tool_plan` 事件（位置在其 finished 之后、下轮 reserved 之前）。
- 末轮：completed→候选 output；failed→receipt error 或 bounded_stop；interrupted→recover 封存语义；generating 仅当有活动 attempt 或末轮 received-plan（备份时点）。
- 篡改矩阵：plan 事件缺失/多余、round 跳空、v1 多轮、中间轮带 output、bounded_stop 伪造 → 全部 ASSISTANT_MODEL_INTEGRITY。

### 6. 恢复封存

- recover_attempts 既有逻辑封存 reserved/sending 轮；新增：run='generating' 且无活动 attempt（末轮 received-plan 后崩溃）→ run interrupted，不写新事件、不重发。重启后同 request_id 走既有 replay-existing，绝不自动续跑。

## 验收

- 合成 provider 双轮 happy path：round1 plan（1 次 search）→ 固定 handler 执行 → round2 candidate → run completed，预算计数 2/2。**（已达成，含 wire 逐字节与事件序列断言）**
- 反例全拒：伪造/跨 run saved_citation_id、陌生 tool、plan>8、轮间撤权、rounds_exhausted、tool_limit、v1 收 plan、max_rounds 与 basis 格式不一致。**（已达成；另补 budget_exhausted）**
- 恢复：plan 后崩溃 → interrupted，重提交幂等返回不重发。**（已达成）**
- integrity：合法双轮归档通过；篡改矩阵全拒。**（已达成，5 变体）**
- 既有关联测试回归全绿；四开发门 exit 0。**（已达成：目标 10 文件 240 项通过；广域 214 通过 / 13 失败为基线同等复现的预存在环境家族，见证据目录）**

## 边界

真实供应商仍不接（合成 provider 回环）；无 UI 变更（API DTO 仅追加默认保持旧行为的字段）；plain-text 路径与 v1 context 字节不变。**实施修正**：原表述「schema 结构不再变更」不成立——rounds-v1 表 `CHECK(input_format IN (...))` 不含 v2 且 SQLite 无法 ALTER CHECK，故新增结构版本 `assistant-rounds-v2`（复用本片 12 步重建序列加宽 CHECK，无新表/列/触发器，其余对象字节不动，v1 冻结摘要固化入测试）。
