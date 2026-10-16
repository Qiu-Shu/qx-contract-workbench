# CH-01 schema、迁移与旧备份设计复核

日期：2026-10-17（Asia/Shanghai）

代码基线：`7b58b92`，分支 `codex/contract-review-v2`。

性质：依据当前源码及 `chat-first-architecture-v2.1.md` 第10、12节、CH-01的设计复核；不代表迁移、assistant表或旧备份兼容已实现。

## 当前进度

主代理正在把 `web.app.initialize_storage` 的现有组合移至 `storage_bootstrap.py`，并让 `ops.backup.schema_reference` 直接依赖该模块，以解除备份模块对Web应用的反向依赖。此步正在验证原始及规范化schema摘要完全不变；本文不预报验证结果。

已知版本注册、有序迁移链、assistant-v1、旧档案恢复升级仍为下述实施建议。本复核未修改源码、未运行测试，也未读取真实案件材料。

## 不能混用的两种schema表示

| 使用位置 | 当前算法 | 保留要求 |
|---|---|---|
| `web.local_server._schema_hash`、`web.workspace_upgrade._rows/_hash` | 对按type/name排序的全部 `sqlite_master` 行序列化后取SHA256；保留原始SQL、SQL为NULL的隐式索引等 | 旧 `workspace.json` 和升级回执依赖此算法，不改成规范化摘要 |
| `ops.backup._schema`、`schema_reference` | 排除SQL为NULL及 `sqlite_*` 对象；折叠SQL空白后返回排序结构 | `.cnbak` 的schema摘要及 `.qxbak` 的已知结构比较依赖此表示，不与native摘要互换 |

版本识别须基于程序内固定的受支持参考，不能只相信档案、marker或回执自报摘要。旧版本参考不能随着最新版初始化而漂移。首批明确区分 pre-intake 工作区、intake-v1、未来 assistant-v1；旧qxbak至少覆盖现有0.4.1/intake-v1，不宣称任意历史格式兼容。

## 最小实现顺序与关键函数

1. **先完成初始化组合解耦。** 维持原初始化次序、schema及调用契约；`web.app`继续提供既有名称，`ops.backup.schema_reference(settings)`保留接口。后者被现有并发边界测试替换，不应在重构时绕开该测试入口。
2. **建立固定已知版本及逐级升级。** `web.workspace_upgrade.upgrade` 目前在恢复marker后、发现完整intake对象后均直接返回；改为完成当前步骤后继续检查下一步骤。`pending_matches`仅认可已登记的相邻跃迁，核对已知before/after结构、工作区身份、独立备份摘要及完整性。
3. **再登记assistant表。** `assistant/schema.py`固定DDL，并让新建与升级共用同一份定义。`local_server._open_workspace`在任何自动初始化前识别受支持结构；未知对象即使与修改后的marker自洽也应拒绝。`_database`应区分已有库与新建库，防止补表掩盖损坏。

`Database.__init__` 默认执行全局 `Base.metadata.create_all`。新增ORM类的导入可能提前把表加入metadata；assistant首版宜沿用intake固定SQL方式。旧库须先校验或完成受控迁移，再进入正常初始化；只读检查使用 `initialize_schema=False`。

每个升级步骤保持：调用者持worker锁 → 验证源结构 → 原生SQLite备份并验证 → 写pending回执 → `BEGIN IMMEDIATE` → 再核对源结构 → DDL → 核对完整目标结构 → 提交 → 原子更新marker。保留 `upgrade-intake-v1.json` 的旧格式和路径；assistant使用独立回执及备份目录，不覆盖intake证据。DDL失败回滚；提交成功而marker失败时只能凭完整回执恢复，然后继续下一步。

## 旧qxbak的校验与恢复顺序

`ops.workspace_backup._validate_database`当前只接受由最新初始化生成的唯一schema；直接增加assistant表会使有效旧包在 `_unpack` 阶段被判结构不匹配。

恢复流程应为：

1. 解密并核对manifest、原始文件字节、受支持旧schema、身份及文件引用。
2. 仅在恢复staging目录中持锁受控升级至当前版本；不改原archive或原工作区。
3. 执行 `_fence` 撤销旧会话、写隔离记录；新assistant worker及服务写入也检查同一fence。
4. 再验证当前结构、受保护文件与引用，最后发布独立恢复目录。

`_unpack`保持验证和解包职责，不在其中升级，因为 `create_workspace_backup` 的创建后自校验同样调用它。迁移放在 `restore_workspace_backup` 的 `_unpack` 之后、`_fence` 之前。对未识别版本不调用自动补表。

`_inventory`虽会收集protected目录，但不能证明所有数据库引用文件均存在。CH-03增加附件时同步扩展 `backup._file_references` 和恢复引用校验，验证路径、Hash、大小及归属。旧版本仅在已识别结构下不查询assistant表，不能用宽松的“无表就忽略”代替版本校验。

## cnbak不可遗漏

`ops.backup.restore_backup`当前先将manifest的schema摘要与最新 `schema_reference` 比较，再在临时目录调用 `validate_raw_database(..., expected_schema=...)` 校验结构和表内容，随后核对数据库文件引用与manifest、材料字节，最后在独立staging创建隔离恢复副本。`open_restored_database`也只接受最新结构。

组合抽取先保持以上行为。登记新表时须明确选择受支持的旧schema参考，**先完整验证旧档案原始内容，再在隔离副本迁移、设置fence、验证新结构**，不能拿升级后的表统计去比较旧manifest，不能绕过旧引用及合成材料政策校验。`.cnbak`没有native `workspace.json`，不能直接假定可调用native升级器；应复用已验证的数据库升级步骤，另保留该格式的完整性和隔离契约。

## 必要测试

复用 `tests/integration/test_workspace_upgrade.py`、`test_workspace_backup.py`、`test_backup_restore.py`、`test_local_material_boundaries.py`、`test_assisted_backup.py`，新增以下行为验证：

- 抽取前后完整schema及两种摘要不变；schema工具不再加载 `web.app`。
- pre-intake→intake-v1→assistant-v1、intake-v1→assistant-v1均保持身份、案件及接待修订；重复打开不重复备份或迁移。
- 分别在两个步骤注入DDL失败、提交后marker失败；正确回滚或重启恢复，并继续下一步。
- 回执、备份、目标触发器被改，或新增未知对象并同步修改marker，均拒绝且不自动修复。
- 固定旧schema生成的旧qxbak经新版恢复可登录和读原件、接待；不能仅测试新版自产包。原工作区及原archive不变。旧cnbak另测其支持路径。
- 恢复历史消息和未完成run只读可见；HTTP与直接服务调用均受fence约束，provider调用计数不增加。
- 加附件后覆盖缺blob、Hash错误、路径／硬链接越界、超限拒绝；失败不发布恢复目录，不留下看似成功的残缺备份。

以上是待实施及待实测清单。本设计复核不替代目标测试、独立实现复核或安装版验收。
