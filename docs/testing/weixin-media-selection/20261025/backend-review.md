# D2g5f 附件选择：后端只读核对

工作目录：`D:\Documents\ChatGPT\律所项目`。2026-10-25；父任务给定基线 `49e7b55`。本审阅只读取当前源码与现有测试，使用现有 CodeGraph 索引定位，再以当前文件内容核对。未改产品、测试、Git、状态或记忆。测试执行为 **NOT_RUN**，以下“已有测试”不表示本轮重新通过。

## 结论

可以让用户为无 `attachment_id` 的微信 pending 项，**显式选择本 CID 已保存且完整解析的 DOCX/PDF**，复用 `TaskDraftUpdateInput.media_resolutions[].replacement`；无需新 DTO、schema 或后端接口，也无需为本切片增加后端权限限制。

现有断点在 `src/cn_contract/web/static/assistant-tasks.mjs:157` 的更新按钮：第 158 行只按 `original.attachment_id` 查询 `materials.attachments`。微信 pending 没有该 ID，必然进入第 159 行“尚未找到对应原件”。后端本来支持无 ID 的原始项被显式 replacement 替换；原始收件 payload 不覆盖，resolution 另存。

这是一条本机材料人工关联路径，不构成微信文件下载、解密、远端来源真实性认证或合同事实确认。不要按名称自动猜选，也不要把替代原件描述为已与微信字节核对一致。

## 调用链与约束

| 层 | 当前符号与准确起始行 | 核验内容 |
|---|---|---|
| HTTP | `web/task_drafts.py:22 write`，`:57 update` | PATCH 在读取 JSON 前及后均验证实际 session、owner/当前对象 ACL 与 restore fence；第二次核验后同事务执行更新。 |
| HTTP 身份 | `web/request_context.py:21 actor_in` | 写操作要求同源及 CSRF；`:46 body_input` 限 256 KiB、拒绝重复键/非有限数/深嵌套，再校验 DTO。 |
| 集中 DTO | `domain.py:4196 TaskMediaInput`，`:4297 TaskMediaResolutionInput`，`:4374 TaskDraftUpdateInput` | ready 必须同时有附件 ID、SHA、parse revision；resolve 必须带 ready replacement 且保留相同 media ID；exclude 必须有原因且不能带 replacement；更新带 expected revision，resolution 的 event/media 对不能重复。 |
| 当前归属 | `assistant/service.py:61 _owned`，`:44 _intake_access`，`:54 _scope_access` | 从数据库当前 principal 核 owner、workspace、matter/intake/projection ACL。 |
| 写状态 | `task_drafts/service.py:22 _write`，`:376 update_draft` | 当前会话未归档、未被恢复隔离；expected revision 相等；冻结任务拒绝更新，暂停/取消任务须先恢复 collecting。 |
| 原始项成员 | `task_drafts/service.py:397` | resolution event 必须属于该 draft，media ID 必须属于该事件；不能凭任意事件 ID 写 resolution。 |
| 本 CID 附件 | `task_drafts/service.py:96 _media` → `assistant/attachment_records.py:13 owned_attachment` | 附件 ID 必须来自该 CID 且 owner/workspace 匹配；name、MIME、提供的 SHA 必须与已保存原件记录完全一致。 |
| 精确解析 | `task_drafts/service.py:103` → `assistant/attachment_records.py:74 parse_row`、`:83 parse_view` | `(CID, attachment_id, revision)` 精确查询；解析 result 与附件 ID、结果摘要、reading/failure 字段一致。不要求 replacement 对应原先不存在的附件 ID。 |
| 可冻结条件 | `task_drafts/service.py:112 _manifest`，尤其 `:127`–`:147` | 非 ready、非完整 readable、非 DOCX/PDF、同附件解析版本冲突仍为 blocker；多份可读原件仍须主合同选择。保存 resolution 不等于允许冻结。 |
| 原件字节 | `task_drafts/service.py:416 freeze_draft`，`:425` | 冻结时重新构建 manifest、读取受保护原件核 SHA，并核 revision/manifest SHA；保存 resolution 本身不重新读原件字节。 |
| 独立原件读取 | `assistant/attachments.py:286 read_parse` | UI 的 `getParse` 在返回解析前调用 `read_original` 校验当前受保护原件，并重新验证当前 owner。 |
| 恢复隔离 | `ops/storage.py:45 require_active` | 恢复副本写入统一 `BLOCKED_LIVE`；只读历史保留。 |

最小前端接法：读当前 `getMaterials(cid)`，用其 `attachments` 显式列出 DOCX/PDF；读取当前 `items` 中该附件的 `parse_revision`（没有则提示先在材料区解析）。复用 `assistant-tasks.mjs:101 media` 对完整 readable、parser version、baseline 做现有检查，用已保存附件的 name/MIME/SHA 与原始 `media_id` 组成 replacement，再 PATCH 当前 draft revision。应在异步 materials/parse 返回后重验 CID/epoch，拒绝旧对话响应；失败/未知不宣告已关联。若支持再次替换或恢复已排除项，仍用同一原始 event/media key，不能改写原始事件。

当前后端不会要求替代附件名与微信显示名相同，这是显式人工替代所需；它要求请求中的附件名与选中的本机原件记录相同。也不会仅凭 status ready 放行扫描 PDF、partial 或 failed 解析，manifest 会继续阻断。

## 已有测试证据与本片最小验收矩阵

已有源码测试（本审阅均未运行）：

- `tests/integration/test_task_drafts.py:220 test_pending_resolution_and_explicit_exclusion_are_auditable`：无 ID pending 解析替代、排除原因独立保存、原始 pending 状态保留、冻结 manifest 取 replacement。
- 同文件 `:167 test_media_reference_is_rechecked_on_server`：错误 hash、parse revision、跨 CID 引用；`:184 test_unready_media_cannot_freeze`；`:239 test_repeated_resolution_survives_frozen_child_creation`；`:320 test_original_hash_is_checked_again_when_freezing`。
- `tests/integration/test_weixin_reauthorization_atomic.py:108 test_actual_local_docx_upload_then_refresh_allows_prior_pending_material`：独立 DOCX 本机上传/解析、授权 scope 刷新、微信 pending 分发后显式 replacement，最终仍 collecting 且无 task execution / assistant run / review run。
- `tests/integration/test_weixin_dispatch.py:185 test_frozen_known_reply_creates_supplement_after_controlled_local_material_resolution`：冻结历史不改写、后补进入新草稿。
- `tests/integration/test_task_drafts_pdf.py:108 test_complete_pdf_is_a_freezable_main_contract`；`:146 test_unread_pdf_pages_remain_partial_and_cannot_freeze`；`:160 test_pdf_annotation_is_retained_as_unread_and_blocks_task`；`:374 test_mixed_pdf_docx_task_requires_main_choice_and_preserves_both_sources`。
- `tests/integration/test_task_draft_routes.py:41 test_task_routes_authenticate_before_reading_body`；`:52 test_task_binding_checks_owner_and_csrf`；`:133 test_batch_reauthenticates_after_body_read`；`:152 test_pending_media_stays_visible_and_can_be_excluded_with_reason`；`:257 test_recovery_reads_saved_tasks_but_fences_every_task_write`。
- `tests/integration/test_task_drafts_migration.py:205 test_restore_blocks_each_pending_execution_and_all_task_writes`；`test_task_drafts_completed_backup.py:99 test_completed_native_task_rebackup_preserves_sources_results_and_never_replays`。

| 本片待验收 | 最小预期 | 当前状态 |
|---|---|---|
| 无 ID 微信 pending，显式选同 CID 已完整读取 DOCX；同样 PDF | PATCH 一次，replacement 保留原 media ID；原始 pending 不变，revision +1；无自动冻结/模型调用 | NOT_RUN，建议新增 UI 与 HTTP 直达用例 |
| 未选择、无候选、未解析、partial/needs_baseline/failed、非 DOCX/PDF | 不提交 ready replacement，给下一步提示；后端直达仍不能冻结 | NOT_RUN；已有服务/PDF oracle 可复用 |
| 同名不同附件 | 不自动选择；由用户选具体 ID/解析版本 | NOT_RUN，建议 Node/DOM 用例 |
| 错 CID/owner、错 SHA/name/MIME、缺失解析版本、错 event/media key | 后端拒绝，不新增 resolution/不递增 draft revision | NOT_RUN，建议 PATCH resolve 参数矩阵补齐已有 HTTP 主要测 exclude 的缺口 |
| stale revision、frozen、paused/cancelled、恢复副本 | 分别 CAS/状态/fence 拒绝，历史和源附件不变 | NOT_RUN；已有源码测试覆盖部分 |
| CID 切换/撤权发生在 materials/parse 请求期间 | 旧响应不渲染、不向旧或新 CID 提交 PATCH；不保留私人候选文字 | NOT_RUN，建议 Node/DOM 延迟响应测试 |
| 同一项再次替换/排除后恢复、多材料选主合同 | 记录新 resolution，原始 payload 与旧 resolution 不改；保留主合同/可读性 blocker | NOT_RUN；服务级已有部分 |
| 网络结果未知 | 显示未确认，查询当前草稿/固定 CAS 状态后再处理；不得把失败当保存成功 | NOT_RUN，建议 UI 用例 |

## 读取快照 SHA256

以下仅证明本审阅读取的源文件快照，不表示产品全仓已审查。

```text
src/cn_contract/task_drafts/service.py 377c70eaf877506ef9df72200ae065dbabe73da66c122ec54315b3cb3f5b2c2e
src/cn_contract/domain.py f8f64176edbc9866887ade894680492769ae46b8ddd4bc3c6bc107632b89fe2e
src/cn_contract/web/task_drafts.py 924a87d7e43494d210ccd93dc50edcf1a881d16187493e1ff268fc684907db35
src/cn_contract/assistant/attachment_records.py d6384abc36f639908110494da6b781dfa7a67f510c1a5eee6e2cf8bfdf1c32ca
src/cn_contract/assistant/attachments.py 6e6f30bf8ee510e8d7968696019055a381b473cec0b1a1064a3acfbc3348249f
src/cn_contract/web/static/assistant-tasks.mjs ae4771a9bee58ec8cdedf5568b5e103eb03ec21a66b63ae665ce99698b291d57
```

未检查真实微信身份/下载/解密、真实合同、模型、外发、安装版与长进程原生崩溃；全部 NOT_RUN。后续独立审阅可以基于本片最终 diff 与冻结测试证据执行，本审阅者未编写任何产品代码。

## 后续授权的 HTTP 实测（与上述初始静态核对分开）

父任务随后授权新增且仅新增 `tests/integration/test_task_media_selection_routes.py`，对既有后端能力作真实 native 合成 FastAPI HTTP 验收。该模块首次精确运行 **22 passed in 25.00s，exit 0**，墙钟 26.3122074 秒；271 个 src 文件与新测试输入的前后 SHA 全部一致。新测试 SHA256 为 `e5e411d459e6ba734c118cc65b1fb2ef63fecc87d3be75fd1c8eab998a69f39f`。

实际 argv、UTC、退出码、271 项前后摘要与空 changed_inputs 已保存 `backend-http.json`；原始日志 `backend-http.log`，JUnit `backend-http.xml`。basetemp 为本轮 D 盘 `.local/weixin-media-selection-20261025/backend-http-tmp`。这不是新增功能先失败证据，后端产品保持未改。

22 项涵盖 DOCX/PDF 的无 ID 原始 pending→当前 CID 已真实上传/解析 replacement、源事件/原件/解析记录保留、无模型或自动执行；7 类错误引用/CID/元数据/解析版本；第二项失败时 resolution 全批回滚；旧 revision/冻结/暂停取消；身份/CSRF/同源/owner 在读取请求前拒绝；当前 matter 权限在读体前后撤销；持久恢复 fence 拒绝；partial PDF 可保存引用但保持 blocker 且禁止冻结。恢复用持久 fence 行验证同一写边界，**没有宣称本模块重新执行真实 qxbak 导出恢复**。

本审阅者编写了该 HTTP 模块，后续独立审阅声明只适用于由其他代理编写的前端产品与 Node 测试，不把本模块称为独立自审通过。
