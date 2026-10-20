# CH-06B2b 存储与备份设计复核（只读）

- 基线：`0d53fdfdae806c6fec90c01cab1531a7cb666831`，2026-10-20。
- 工作目录：`D:\Documents\ChatGPT\律所项目`。
- 范围：最终“选定已保存片段后一次回答”的存储方案；本轮仅做选片、完整确定性预览和独立 codec，**预览不需要任何 schema 变更**，不授予许可、不登记 attempt、不调用供应商。
- 方法：读取 `library-context-readiness.md`，CodeGraph 核对迁移/恢复调用关系，并按当前源码检查严格 schema、V1 编码、模型账本和归档接口。使用 ponytail 与 codebase-design；未运行产品测试，以下是设计结论与后续验收要求。

## 结论

推荐后续发送切片采用 **一个明确的新 schema 版本、attempt 上一个不可变格式列、一张有序来源关联表**。批准清单与待发送投影放在独立上下文 PreparedInput DTO 内，继续保存到既有 `assistant_model_attempts.input_json`。不用为清单再复制一份 JSON，不增加第二套 attempt、队列、费用或输出账本。

本轮预览要使用新的上下文 DTO 与编解码入口。不得给 `MainRequest` 加可选 citations/context 字段，也不得把含引用的大字符串伪装成普通 `content` 后交给旧发送链；当前 `MainSendApproval.content_sha256` 只证明原用户文字，不能证明选定资料和模板。

## 为什么不能只加一个可选旁表

当前 `storage_schema.identify_schema()` 对整个 sqlite_master 严格匹配；旧原生 `_open_workspace()` 和 qxbak `_validate_database()` 会拒绝新增表。然而 `assistant/model_schema.initialize_storage()` 只检查旧三个账本表及它们的索引/触发器。若只加旁表，这个旧通用初始化入口可能忽略它，新资料格式没有贯穿所有已有入口的明确屏障。

将格式列加入既有 attempts 表后，旧版本的全库检查及模型族局部检查都会不匹配。该结论来自源码检查，**需以冻结旧版本入口的实际拒绝测试证明，尚未运行**。不宣称持有任意 SQLite 读取权限的软件也无法读取文件。

## 最小结构（后续发送切片实施）

建议新 schema 标识 `assistant-context-v1`。名字可按最终 codec 一次确定，不使用可选字段推断格式。

1. 对既有 `assistant_model_attempts` 增加：

   ```sql
   ALTER TABLE assistant_model_attempts ADD COLUMN input_format TEXT NOT NULL
       DEFAULT 'plain-text-v1'
       CHECK(input_format IN ('plain-text-v1', 'library-context-v1'));
   ```

   迁移得到的旧行明确属于 `plain-text-v1`；原 `input_json`、`policy_json`、config、哈希、receipt、output 与事件字符串不重编码。将 `input_format` 加入既有 `immutable_assistant_model_input` 的 UPDATE 禁止字段；既有 DELETE 禁止保留。未来新登记必须显式写格式，默认值仅服务旧行升级和 SQLite ADD COLUMN。

2. 新增一张有序关联表（名称建议）：

   ```sql
   CREATE TABLE assistant_model_input_citations (
       attempt_id TEXT NOT NULL REFERENCES assistant_model_attempts(id),
       ordinal INTEGER NOT NULL CHECK(ordinal >= 0 AND ordinal < 8),
       saved_citation_id TEXT NOT NULL REFERENCES assistant_library_citations(id),
       PRIMARY KEY(attempt_id, ordinal),
       UNIQUE(attempt_id, saved_citation_id)
   );
   ```

   该表 UPDATE/DELETE 均禁止。普通文字 attempt 的关联必须是空集；上下文 attempt 的关联必须逐项等于其不可变输入中的有序引用集合，且连续 ordinal 从 0 起、1—8 条。外键只证明对象存在，不能替代范围、清单摘要和内容一致性检查。额外 INSERT 也不能被视为合法追加：读取、claim 和归档必须核对关联的精确集合。

3. 新 `MainContextPreparedInput`（业务 DTO 只放 `domain.py`）在既有 input_json 中保存明确格式/codec 版本、请求及批准清单、实际传输 JSON。批准清单包含原问题、服务器重建的有序外发投影、各 saved citation UUID 与本机完整 citation 摘要、模板版本，以及相关范围/草稿版本。确切字段与本轮 preview codec 对齐。

   - 真正外发投影只包含必要标题、片段、位置、版本与 UUID；本机路径不外发。
   - 完整 CitationRef 仍复用已有 `assistant_library_citations.citation_json`，不在新表再次复制。
   - 完整清单摘要、最终 wire 摘要分别定义，避免摘要包含自身；输入包含服务器 run/message UUID 时，不把尚不存在的 ID 塞进批准清单。最后封套必须可确定性证明仅添加允许的服务器字段。
   - 字段级格式身份既存于 `input_format`，也由对应上下文 DTO 的固定格式验证；两者不一致报错。上下文行缺关联、缺清单、缺原引用，均拒绝；不能尝试 V1 解析后继续。

直接存 JSON 已经满足不可变清单存储；上面关联表提供数据库层同 attempt / 引用身份关系，无需额外 manifest header 表或历史草稿表。

## 版本与迁移接口

| 精确文件/入口 | 最小改动与必须保持的行为 |
| --- | --- |
| `src/cn_contract/assistant/model_schema.py`：`STATEMENTS`、`expected_objects()`、`initialize_storage()` | 旧 `STATEMENTS`/旧 expected 仍定义 V1 模型族，不能编辑它们让旧版本目录跟着漂移。初始化器需要明确接受已识别的新模型族结构；对缺触发器、半迁移和未知结构仍拒绝，不“补齐修好”。 |
| 新 `src/cn_contract/assistant/context_schema.py` | 放 ALTER、替换旧 immutable input trigger、建立引用表及 immutable triggers。以 V1 表结构运行这组语句产生精确新 model rows；新建库也先 V1 后同样 ALTER，避免 CREATE 与 ALTER 生成不同 sqlite_master SQL。迁移在现有事务内完成。 |
| `src/cn_contract/storage_schema.py`：`CURRENT_VERSION`、`VERSIONS`、`schema_rows()` | 追加 `assistant-context-v1`。所有旧版本行与 normalized hash 必须原样保留；新版本保留 library rows，并只替换被 ALTER 的模型表/触发器项、添加新关联对象。现有 `if version == 'assistant-library-v1'` 必须覆盖新后继，否则会漏法库表。不能改 `ASSISTANT_MODEL_V1_ROWS`。 |
| `src/cn_contract/schema_migrations.py`：`statements_for()` / `upgrade_database()` | 增加新步骤，沿用 BEGIN IMMEDIATE、逐步精确 rows 与 FK 检查、出错 rollback。旧版本模型步骤仍读取冻结旧 DDL。 |
| `src/cn_contract/storage_bootstrap.py` | 在 library 后组合 context 初始化；全新库最终必须等于新 schema；不能顺序导致 context FK 先于 library。 |
| `src/cn_contract/web/workspace_upgrade.py`：`upgrade()`、`pending_matches()` | 通用版本链应直接复用。验证新版本的 before.db、安全备份、upgrade receipt、数据库提交后 marker 写入失败恢复，不复制升级器。 |
| `src/cn_contract/web/local_server.py`：`_open_workspace()`、`_database()` | 既有严格识别/只读先验机制应复用，正常不需添加第二套兼容逻辑。以旧代码和新结构验证拒绝。 |

不要直接覆盖 `model_schema.STATEMENTS` 为新 DDL：`schema_migrations.statements_for('assistant-model-v1')` 依赖它逐步还原旧 schema，改动会让从更早归档恢复时中间版本校验失败。也不要让 `schema_rows(old_version)` 调用当前 initializer 推导旧定义。

## 模型读取、登记与历史的分派

- `assistant/providers/attempts.py`：`read_attempt()`、`enqueue_generation()`、`_current()`、`claim()`、`settle()` 当前直接解析 `MainPreparedInput`。引入一个私有格式分派入口供这些 caller 复用，不让每个 caller 尝试多个 DTO。当前 schema 缺 `input_format` 是损坏；只有已识别旧 schema 的历史归档校验才能明确按 V1 解码。
- 新上下文登记在同一个 `begin_nested()` 中完成新 message/run、attempt、来源关系、预算及 reserved event；旧检索 run/receipt/citation 不变。不复制 `claim_sha256` 或 recover 队列。
- 新 input_format 不得由网页任意指定；可信上下文登记入口固定写 `library-context-v1`，普通入口固定写 `plain-text-v1`。
- `providers/policy.py`、`providers/main.py`、`providers/registry.py` 与 `native_model_control.py` 必须显式区分许可和输入格式。旧 V1 `MainRequest` / `MainPreparedInput` / `MainCandidate` / `MainOutputView` 的规范 JSON保持不变；上下文输出含选中引用时用新的严格 DTO，禁止给 V1 类型添加默认字段使历史 encoded 比较失效。
- `providers/history.py` 及 view DTO 按格式读输出；若使用 union，须证明 V1 dump 字节没有变化。来源 selection 不是对现有模型历史 binding 限制的放宽。
- `_current()` 对新上下文验证保存后的确定后继 input/composer 值，以及同一来源选择；不能比较登记前版本或任意最新值。晚到撤权导致不采用答案时，settle 仍先按既有回执规则保存真实使用量。
- manager 新上下文分支明确不进入 Jev 预留/执行；即使有有效 Jev grant 也为零调用。预算/claim/退出机制共用。

## 归档与恢复：同一个校验 seam

`ops/backup.py::_file_references()` 已同时调用 model、judge、library、attachment 校验；`workspace_backup` 的创建、验包与恢复通过它。优先在这个既有 seam 中闭合，不在打包层复制业务解析。

1. `assistant/model_integrity.py::validate_model_records()` / `_validate()` 按已识别 schema + 不可变格式解析。旧schema只允许旧格式；新 schema 每条 attempt 必须有合法格式。上下文校验精确输入/许可/wire、所选来源关联、原引用哈希与同 scope 关系、结果引用仅属批准集合。普通 V1 仍用当前验证，不重新编码旧记录。
2. 可将上下文的纯清单/关联验证集中到 `assistant/context_integrity.py` 或当前 codec 的私有 helper，运行时读取与 model_integrity 复用，避免 B2a 曾出现“运行时严格而备份遗漏”的差异。返回 typed value / error，内部不读当前法库、不取活动许可。
3. `assistant/attachment_integrity.py::file_references()` 和 `judge_integrity.py::validate_judge_records()` 当前使用支持版本白名单，必须加入新版本；`library_integrity.py::validate_library_records()` 当前只有版本恰为 library-v1 才读法库记录，必须让新版本也继续验证，不能因新版本静默跳过。
4. 归档是历史证明：session 已撤销、法库文件离线、问题草稿后来改过都不应让合法旧快照失败。验证保存时范围与顺序/原文关系，不重新执行“当前允许外发”。不要调用 `read_saved_citation(actor...)` 作为备份校验，它有当前权限语义；复用其纯记录验证部分。
5. `ops/workspace_backup.py::restore_workspace_backup()` 继续“验证旧 bytes/refs → 隔离副本升级 → fence → 检查 → 发布”。`_fence()` 复用 `attempts.recover_attempts()`：reserved 转未发送、sending 转发送状态未知；新上下文输入与关联保留、旧 session 全部撤销，不建立新许可或自动重发。
6. 不改变 qxbak 加密容器格式。含 assistant 模型记录的 cnbak 继续拒绝；无这些记录的旧 cnbak 可以在隔离恢复时升级结构。

## 后续有意义验收（不是已经通过的测试）

### 本轮预览 slice

- 完整 schema rows 与所有业务表计数在预览前后相同；无 attempt/receipt/output/Jev、无模型配置改变、无网络请求。
- 旧 MainRequest 明确拒绝额外上下文字段；旧 V1 固定样例 encoded/prepared wire/hash 不变。
- 已保存来源全部从服务端重建，跨案/旧绑定/重复/无权/失效选择拒绝；offline 仍能预览合法历史片段。
- 完整预览包含模板和全部实际外发字段；UTF-8 总预算、确定性/选中顺序、路径排除及恶意原文只作资料分别测。

### 发送 slice 的结构与迁移

1. **冻结 V1 fixture**：具有真实合成历史 model attempts/receipts/outputs、B2a citations 的 library-v1 库升级。逐条比较原 JSON、哈希、事件、保护文件原字节；新 format 都是 plain-text-v1，关联空集。不能用“当前 initializer 生成的旧库”作为唯一fixture。
2. **所有入口结构一致**：新 bootstrap、逐步旧库 upgrade、qxbak恢复的新 sqlite_master 完全相等；所有历史 schema_rows/normalized_schema 与冻结参考相等。含 native/non-native 两类。
3. **实际旧代码拒绝**：用0d53fdf的 identify_schema、model_schema.initialize_storage、原生 _open_workspace/qxbak校验检查独立新结构fixture，全部拒绝，源fixture字节不被改写；不是只assert版本字符串不同。
4. **原子失败**：在 ALTER 后、触发器替换后、关系表创建后分别注入失败，旧 schema/行保持一致，无半关系，无公开恢复目录；模拟数据库提交后 marker写失败，再次启动仅用现有 receipt/backup 安全恢复。
5. **格式/关系损坏矩阵**：修改input_format被数据库拒绝；缺/未知/不匹配格式、缺context清单、空/缺/多/乱序/重复/孤立引用、跨attempt换源、引用哈希变化全部在历史读取/claim/备份创建/重封装归档恢复拒绝，不能回落V1。攻击fixture应显式绕过约束制造损坏，恢复校验不能只依赖原数据库trigger。
6. **登记事务**：在 source relation 写入中途注入失败，message/run/attempt/预算/reserved event 一起回滚，原已保存来源不变。相同 request_id 不创建第二attempt，改变问题/选片/格式冲突。

### 发送 slice 的恢复与生命周期

7. **多状态 roundtrip**：reserved、sending、received有效输出、received拒绝输出但有usage、failed_before_send、sent_unknown；恢复后格式和全部context字节/顺序保留，state/fence转换正确，所有网络0。含普通V1和上下文混合工作区。
8. **历史合法性**：新问题/较新composer、session撤销、当前法库offline后仍可备份旧合法上下文；恢复后重新登录可只读核对，不能沿用旧permit发请求。当前执行仍检查权限和确定后继状态。
9. **费用与来源**：撤权/取消/切案/许可失效后迟到reply不采用但保留真实使用量；模型输出未知UUID、替换原文或伪造审核状态拒绝采用；合法引用保留原未核状态。
10. **无重复授权/调用**：unknown结果只读找回不重派发，context分支遇已有有效Jevgrant仍零预留/请求；旧普通文字原生许可+历史/backup回归通过。

建议扩充既有 `test_assistant_model_schema.py`、`test_assistant_model_upgrade_backup.py`、`test_assistant_model_backup.py` 的 fixture/矩阵，新增专门的 `test_assistant_context_schema.py` 和 `test_assistant_context_backup.py`；共享恢复测试不得只测试新 helper 而跳过真实 `create_workspace_backup` / `restore_workspace_backup` 入口。当前各版本硬编码断言位于 model/judge/library schema 与升级测试，升级时应明确保留历史预期和当前版本预期的区别。

## 本轮边界与未检查

只读复核，没有改产品文件、没有运行产品/迁移/恢复测试、没有接触真实法律库或案件、没有推送。上述 schema 与调用方案是后续设计建议，不应被 TODO 写成已实现。当前预览工作可以不等待存储实现；真正发送必须把新许可、持久格式身份、关系验证、原生确认与归档恢复一起闭合。
