# D2a 合成微信收件存储底座证据（2026-10-24）

本片完成版本化存储、历史完整性及恢复基础，真实微信尚未接通。[实施合同](../../../plans/2026-10-24-weixin-inbox-d2a.md)沿用 D1 官方协议离线适配，不引入依赖、网络或账号凭据。

## 源码实现和范围

- `weixin_inbox/schema.py`：追加第 14 个版本 `weixin-inbox-v1`，4 张表、25 个 sqlite_master 对象。账号与精确 peer 映射、历史 scope、完整 poll 回执及逐条 accepted/blocked/duplicate 结果可持久保存。身份、映射和回执不可覆盖；checkpoint revision 只可加一，首次撤权不可反转。
- `domain.py`：仅在 DTO 集中位置追加 4 个 frozen snapshot。accepted payload 只含规范化文字及 pending DOCX/PDF，不能选择任务、启动执行或携带附件读取/解析能力。
- `weixin_inbox/integrity.py:validate_weixin_records`：重算历史 scope 和完整有序 receipt 摘要；核对 workspace/owner、映射、精确来源命名空间、连续 revision、opaque 游标链和 checkpoint、重复/冲突的更早原始记录、撤权时间、已知引用的同账号/peer/mapping 归属。历史 blocked 不会随授权恢复变成 accepted；未知引用仍未解析。历史快照可以过期，不冒充当前权限。
- bootstrap、逐版迁移、原生工作区升级及 qxbak 沿用既有架构；保留 13 个前驱 native/non-native 的 26 组原始和规范化指纹，既有冻结 JSON 未改。附件、模型（含 context/rounds/profile feature modes）、judge、法库、档案、任务等旧校验在后继版本继续运行。
- 非空新历史只允许完整工作区 qxbak；局部归档拒绝。两种恢复 fence 均明确 `weixin_inbox_enabled=false`，仍由 `require_active` 阻断活动写入。运行 SQLite 未加密；现有 qxbak 的加密不能称为运行库加密。

**尚未实现**：账号/映射创建服务、`record_synthetic_poll` 原子收件 API、上游 checkpoint 提交、真实绑定认证和 TaskInbox 分发。本片夹具通过直接 SQL 插入独立虚构历史，不是运行收件验证；DDL 的 revision 约束也不等于已实现服务层 CAS/事务。原始请求/响应/消息已丢弃，其 SHA 只能检查格式，不能重建或证明远端真实性。无 AES/CDN/context/session 能力数据保存路径。

## 本轮实际验证

最终相关结果按测试身份去重为 **16 文件、587 个不同 Python 用例通过**，不是单次全仓全绿。原始日志/XML/退出码及 `verification-summary.json` 留在本机 `.local/weixin-inbox-20261024/`；不提交临时库、完整日志或本机资料。

下表命令除注明外以前缀 `.venv/Scripts/python.exe -B -X utf8 -m pytest -q` 执行；XML 均位于上述本机目录。

| 实际测试目标 | 回执 | 实际结果 |
| --- | --- | --- |
| `tests/integration/test_weixin_inbox_schema.py tests/integration/test_storage_schema_versions.py tests/integration/test_storage_bootstrap.py` | `storage-green-final.xml` | exit 0；102 passed，54.79s |
| `tests/integration/test_assistant_library_schema.py tests/integration/test_workspace_upgrade.py` | `storage-old-schema-native.xml` | exit 0；96 passed，194.67s |
| `tests/integration/test_task_drafts_migration.py` | `storage-task-history-regression.xml` | exit 0；74 passed，162.29s |
| `tests/unit/test_weixin_inbox_dto.py tests/integration/test_weixin_inbox_integrity.py tests/unit/test_weixin_offline_protocol.py tests/integration/test_weixin_offline.py`（实际前缀不含 `-B`） | `integrity-verified.txt` | exit 0；232 passed，38.27s；日志 SHA256 `07ec39bf6c4217d026a1be9ecdaac6b7f04b00febc713836bcb860739b961130` |
| `tests/integration/test_weixin_inbox_backup.py` | `backup-final.xml` | exit 0；4 passed，16.39s |
| 原附件/model/judge/法库/profile 5 个 corruption 目标，见下段 | `old-gates.xml` | exit 1；56 passed、23 setup errors，99.39s；不是全绿 |
| 原法库同一 23 项，`--basetemp=.local/weixin-inbox-20261024/library-temp-d` | `old-library-d.xml` | exit 0；23 passed，23.65s；替代上行未进入行为断言的 23 项，不重复累计 |

旧校验实际目标为 `test_assistant_attachment_backup.py::test_native_backup_rejects_broken_attachment_provenance`、`test_assistant_model_backup.py::test_native_backup_rejects_model_provenance_corruption`、`test_judge_backup.py::test_authenticated_invalid_judge_archive_is_rejected_before_publication`、`test_assistant_library_backup.py::test_native_references_reject_library_history_corruption`、`test_assistant_profile_execution_backup.py::test_hostile_authenticated_profile_archive_rejects_restore_without_publishing`，均在 `tests/integration/`。首轮法库 fixture 所在 C 盘实际空闲 33,354,543,104 字节，低于既有 40 GiB guard；移到空闲 222,329,688,064 字节的 D 盘独立合成临时目录后通过。未改资源 guard 或伪造磁盘余量。

新 schema 实测覆盖所有前驱升级、新建/升级/expected 相等、失败 DDL 整体回滚、未知/部分结构拒绝、原生 marker 更新失败与恢复、不可变记录和 NULL 约束。旧任务 8 类来源损坏在新版本的备份/认证归档恢复中仍被拒绝；其他旧校验实际损坏目标覆盖附件、模型、judge、法库、档案，不能仅凭 allowlist 改动宣称成功。

合成历史含 2 个 peer、3 个 poll（4/4/0 descriptors）：pending DOCX/PDF 和文字、未知发送者/无效 ID blocked、重复、内容冲突、既往 blocked、之后撤权，以及 opaque cursor 不变的空 poll。真实 qxbak 两代往返逐表保持一致；恢复仍隔离，task inbox/draft/execution/assistant run 均 0、任务 cursor 和源文件字节不变。另 3 类经合法加密认证但内部来源损坏的归档拒绝发布恢复目录。此证据不表示测试了尚不存在的生产收件方法。

四开发门均实际 exit 0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`（同一 Python 前缀）。来源保留 13 项 NOT_PRODUCTION_APPROVED，依赖为 55 runtime＋1 build、native_build_verified=false、network_calls=0。

## 失败记录和独立复核

- 有效 RED：缺新增版本 1 failed；缺 4 DTO 为 31 failed/0 errors；缺完整性实现为 32 failed/0 errors。缺模块 fixture setup errors、长参数 ID 路径错误及一次目标文件名拼写错误另存为开发辅助失败，不冒充行为 RED。
- SQLite `CHECK` 的 NULL duplicate reason 反例 1 failed/9 passed 后加入显式非 NULL 条件；空白撤权原因 1 failed/31 passed 后拒绝。
- 独立 reviewer 复现跨 peer 已知引用通过恢复的问题。定向 RED 为 2 failed/2 passed；修复以完整 archive 原始来源索引检查同账号/peer/mapping，GREEN 为 4 passed。独立再次运行同 4 项、另用临时 native 工作区核对跨 peer/账号拒绝、同 peer/未知允许，均 exit 0；无遗留可证实发现。
- 根代理 qxbak 初两轮各 1 failed/3 passed：分别为旧 task guard 先拒绝局部归档、首次维护创建 `worker.lock` 的测试预期错误。更正 fixture/断言后 4 passed，未为此修改产品代码，原记录保留。
- WorkBuddy 任务 `wb-bg-debb307fe33c` 已完成，桥接核实实际模型 `kimi-k3-2`。它只读实施前计划/旧源码提出 5 类反例，新模块当时未存在；不是最终源码审查或实测。根代理分别用后继旧 gate 损坏、游标/hash/ordinal、重复/冲突、qxbak fence 和局部拒绝证据核对，未盲采纳“已实测”等推断。

| 最终源码 | SHA256 |
| --- | --- |
| `src/cn_contract/domain.py` | `fb7f64eef04c41c3869be10db67d592e4cf01bc5d4e4af38cc9eae4484ac8d30` |
| `src/cn_contract/weixin_inbox/schema.py` | `e194dc41c69c1b1e0103f8c17557715dbdc46ef95a4771427e07d1c10fcacdf0` |
| `src/cn_contract/weixin_inbox/integrity.py` | `14ba54a6f075125dd25b238d9ed31ddbb3e0b8bd2f34d0c6cd274e46feca02ac` |

## 后续与 NOT_RUN

D2b 才提供当前桌面 principal 下创建/撤销合成账号与精确 peer 映射、逐条结果先完整持久化再以 revision CAS 确认 opaque 游标的短事务 API；同 request 回读固定回执、结果未知只查询恢复，不能因分类失败触发 `security.deny` 的 rollback/commit 而提交半批。随后 D2c 分发到共享 TaskDraft，并在每次使用时核验当前权限、材料/绑定修订及恢复 fence；历史 snapshot 不是当前授权。

NOT_RUN：真实微信认证/轮询/机器人安装、真实合同、媒体下载解密、Outbox/发送、产品真实模型或付费调用、E 原生有限期许可、新安装包、全仓/Node/浏览器。安装版仍 0.4.1。既有原生长进程崩溃和 WIN-PATH-02 继续开放，本片没有修复证据。
