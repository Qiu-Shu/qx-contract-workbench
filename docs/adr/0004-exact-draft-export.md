# ADR 0004 — T09 精确草案修改与受众范围

状态：采用，仅独立虚构开发。真实法律验收、外部查询材料再分发与正式签发仍阻断。

T09 复用 T02 后端会话、成员、只读原件、审计和事务文件清理，T03 原件重算结构锚点，以及 T06 `read_run(..., current=True)`。不新增业务 DTO；技术批准、撤销、补丁结果及 bundle 快照存于 `exports.storage.ExportRecordRow`，SQL 禁止更新/删除。`ExportRow` 只保留原有制品状态基础。

`Patch.approved_by` 或 Actor.roles 的客户端值不构成授权。批准绑定实际 run 完整哈希、finding、原件版本/哈希、锚点、完整 old/new/reason 与选定 audiences。普通草案修改由实际经办或复核律师批准；high 必须是不同于运行创建者的实际 reviewing_lawyer。本阶段 high 批准在读取时重验批准会话、当前成员、角色和禁用状态；can_sign 仅属于正式签发门。任意 exception UUID 不提供豁免。

初版只自动处理普通正文完整段落。段落由实际 `body/p[n]` 定位，原件重新解析，old_text 必须精确等于 full anchor.quote。重复句不按文字搜索猜位置。支持跨多个 run 的真实 w:del/w:delText 与 w:ins/w:t，保留删除内容的 run 属性和空格，分配全包无冲突修订 ID。新文使用首个 run 的文字样式；复杂对象、表格、字段、书签、隐藏内容、目标已有修订、子串或已有页眉页脚需要人工。人工项同一行绑定结构位置、批准旧文/新文/修改说明和降级原因。此路径不保证任意文档结构自动修改。

原件磁盘字节不变。内部修订副本只修改目标主文档及新增水印所需支持部件，未触及 ZIP 部件的解压后原始字节逐项保留。客户、对方 bundle 均为全新 DOCX，不带原件副本：单条修改批准不能证明原包 comments/header/footer/custom props/embeddings/隐藏 part 可对外。对方稿只列已批准文字及说明，客户稿列范围、观察、材料缺口与建议，内部稿额外投影实际案件立场、目标、已批准客户政策与复核任务。不存在默认对外批准。

报告读取范围来自实际 run manifest 和后端原件重算，包括文件 hash、parts、锚点、页码不足、unsupported/quality、事实/规则/政策快照。C01–C18 显示中文名称和中文状态。当前 T06 为 QCC0，无外查 receipt 被关联或使用。T08 receipt → T09 报告消费者尚未实现，不把合成 gateway 成功当现实外查报告通过；未来需具体 evidence 引用与对外范围批准后另行接入。无关 T08 scope 变动不使当前无查询 run 的草案过期。

公开服务都显式接受 caller Session，不提交它，也无隐藏数据库：

- `initialize_storage(Database)`：显式创建技术表和 immutable triggers。
- `approve_patch(matter_id, run_id, patch, actor, *, db, audiences=('internal',), exception_authorization_id=None) -> Patch`。
- `revoke_patch(matter_id, patch_id, actor, *, db)`。
- `apply_patch(version, patch, *, actor, db) -> PatchResult`；返回 applied 或 manual_required。
- `prepare_exports(run, audience, patches, actor, *, db) -> ArtifactBundle`。
- `read_bundle(bundle_id, actor, *, db) -> ArtifactBundle`。
- `download_artifact(artifact_id, actor, *, db) -> BytesIO`。
- `read_patch_artifact(matter_id, patch_id, actor, *, db) -> bytes`：受保护的内部修订结果读取，同样核验当前批准/run。
- `approve_bundle(bundle_id, expected_hash, actor, *, db, exception_authorization_id=None)`：核验候选 hash/当前 run/实际 reviewing+can_sign 后仍抛 `BLOCKED_LIVE`；本阶段不产生正式 Approval。

每个逻辑写操作有服务 savepoint。派生文件在 exclusive create 后、实际写入前即登记事务所有权；partial write、后续 flush/审计/末尾 current check 失败与 caller 外层 rollback 均清理新文件及记录。UUID 文件名、只读字节、完整 file/bundle hash、当前 patch approval 和 run 共同决定可读性。案内助理可读当前草案而不能批准/撤销。缺失/跨案读取统一受控拒绝。路径仅限实际 derived_exports 子目录，并拒绝 symlink、Windows reparse/junction 和多硬链接。此边界不是任意具有本机管理员权限的进程的隔离沙箱。

固定 patch_approved/patch_revoked/export_prepared audit 只写 UUID、hash、固定 reason 的 hash，在同一 savepoint 内，不记录正文。授权拒绝审计加入 caller 事务；没有网络计费或额外独立 commit，因此不宣称 caller 任意 rollback 后仍有独立 durable denial。T08 网络账本工厂事务模型保持原实现。

依赖采用固定 G08 python-docx1.2.0 与既有 lxml6.1.3，实际离线 hash 安装、许可证闭包和开发/生产状态见 `docs/reuse/T09-dependencies.md`。G04 仅独立适配 ins/del 构造方法，未安装或复制其上游包，不使用 fuzzy replace 或受限 PDF 路径。Word/字体未作为新产品依赖安装，原生 Word 验证由独立根任务处理，不能由 XML 检查替代。
