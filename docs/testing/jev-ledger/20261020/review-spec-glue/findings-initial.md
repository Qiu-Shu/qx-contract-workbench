# CH-05B 独立 Spec 初审

基线：`a4c3c6706caad31c2335b4d055240dbddbfbd372`。依据本片 `2026-10-20-jev-ledger.md` 与 v2.1 的权限、费用未知、晚到回执、恢复隔离和旧版本保留要求。产品仍在实现，未将占位内容当缺陷。

## 已复现 P2：双重截止取消丢弃同次已经解析的供应商回执

`judge_execution.execute_attempt` 用与 JevProvider 内部相同长度、但更早开始的 timeout 包裹整个 `provider.judge`。响应已收齐并完成解析后，若客户端关闭耗时越过外层截止，外层先取消任务；提供器按取消契约继续抛 CancelledError，执行层遂写入 fallback(sent_unknown)。已安全解析的 usage 与 supplier request ID 丢失。

独立本机回环反例：配置 200ms，在 `httpx2.AsyncClient.__aexit__` 注入可取消的 250ms 清理等待；decode 已记录 `input_tokens=20` 与 `independent-late-receipt`，实际只收到 1 POST。最终账本却为 sent_unknown，没有使用量或追踪 ID。预留仍占用、没有采用 decision，这两点正确，但违背“同次已收到的回执应保留，晚到不得改变路由”的完整要求。

`probe_deadline_receipt.py` 的两个场景：同步解码迟到通过、退出清理迟到失败。`deadline-red.log/xml`：exit 1，1 failed / 1 passed，2.53s。只有合成材料/密钥与随机本机端口；未使用真实模型。

建议统一截止边界或以受控回执通道保留已经收到且通过安全解析的信息；不要延长业务采用期限，不重发，不将费用占用改成零。此审阅没有改产品。

### 修复复验及同根取消分支

移除执行层重复计时器后，原样两个deadline场景均通过（`deadline-green.log/xml`：2 passed，exit 0）。随后沿同一问题精确检查外部取消：decode明确取得 usage 后，在仍进行清理的执行任务上调用 `task.cancel()`，取消虽正常向上传播，账本仍写 sent_unknown 而丢失已收使用量与request ID。`cancellation-red.log/xml`：1 failed / 2 deselected，exit 1。

这不是要求跨重启人工补账，也不是要求吞掉取消；仍只涉及同次调用已经安全解析的数据。外部取消应继续抛出、路由建议不可采用，但执行层应能收到安全回执用于原attempt记账。这作为原P2的取消分支记录，不重复计为另一个独立问题。

## 胶水检查

- 当前 schema 在固定旧 Main DDL 上只增加 Jev 三表，旧版本识别仍是完整结构比对；初始化与恢复不存在自动修补损坏旧schema的入口。
- `schema_migrations` 的隔离恢复链在单一事务中升级；native 升级每步保留旧数据库与回执，标记落盘前的异常已有精确恢复条件。
- qxbak 先完整验证旧字节/结构/引用，只在独立 staging 副本升级与 fence，最后发布。judge恢复在主恢复/主run隔离前执行，没有独立队列或网络对象。
- 普通 cnbak 的 `allow_assistant=False` 会拒绝非空辅助历史，因此它没有调用 judge recovery 不构成本片遗漏。
- 取消hook只处理保留中的辅助请求；发送中的请求由已有回执结算/授权复查处理。没有把Jev权限扩展为主模型批准，也没有写主运行选中供应商字段。

独立 `probe_schema_glue.py` 4 项通过（exit 0，2.25s）：从真实基线 commit 读取旧 storage_schema，逐一对照五个历史版本、两种native形式完全一致；从 pre-intake 到最后Jev步故意失败时整条缺失链原子回滚，无FK破坏，独立合成原件字节保留。没有复跑父代理的14项备份测试。

最终完整评审与摘要将在产品冻结及缺陷处理后记录，本文件为保留的初始观察。
