# CH-04A 模型备份与恢复独立复核

复核时间：2026-10-17。范围为 `assistant/model_integrity.py`、`ops/backup.py`、`ops/workspace_backup.py` 新增接线、`test_assistant_model_backup.py`，并追踪 model attempts、事件回放和恢复隔离调用。CodeGraph 用于定位，当前源码用于判断。未修改产品或测试，未运行全套回归；仅运行一个独立合成探针。

## 明确发现

### P2：模型事件序号断档的备份仍被验证、恢复发布，恢复后无法回放

- 定位：`src/cn_contract/assistant/model_integrity.py:93–115`。`_events` 先过滤 `model.%`，随后校验事件类型和载荷，没有验证完整 run 的事件序号从 1 连续。
- 下游：`src/cn_contract/assistant/service.py:342` 的事件回放要求完整连续序号。
- 实际复现：在独立合成工作区完成一次合成模型任务，然后把 3 条模型事件序号从 2/3/4 改为 102/103/104。篡改工具在操作后恢复原触发器，schema 仍与已知版本相同。
- 结果：`backup._file_references` 接受；真实加密 qxbak 创建返回 `verified=True`；恢复成功发布隔离副本；恢复后事件序号为 `[1,102,103,104]`，`service.read_events(..., after_seq=0)` 返回 `STATE_CONFLICT`。
- 影响：认证成功但事件结构损坏的备份被认定可用，恢复后任务历史无法通过正常分页接口回放。本发现不代表权限绕过、自动补发或原件损坏。
- 最小修复建议：读取该 run 全部事件并先验证序号从 1 连续，再筛选模型事件执行现有类型/载荷检查；加入篡改序号时创建/恢复拒绝的目标回归。
- 探针：`model_event_sequence_probe.py`；原始结果：`model-event-sequence-probe.json`。运行命令：`.venv/Scripts/python.exe -c "import runpy,sys; sys.path.insert(0,'tests/integration'); runpy.run_path('.local/chat-model-20261017/model_event_sequence_probe.py', run_name='__main__')"`，退出码 0。只调用合成 provider 一次，恢复阶段无 provider 调用。

## 其余范围结论

未发现其他明确缺陷：

- 超预算真实用量保留在 receipt 中；只禁止超出请求包络的 output 采纳，不因累计费用超预算拒绝合法历史备份。
- reserved/sending 在恢复隔离副本发布前分别封存为 failed_before_send/not_sent、sent_unknown/unknown。恢复处理不调用 provider，原会话撤销、未完成旧任务隔离。
- 输入、配置、政策与 wire 摘要、作用域、原消息、receipt 费用、output 引用和模型状态事件的内容存在交叉校验；上述事件序号是本次发现的具体缺口。
- cnbak 收集与恢复均经过 `allow_assistant=False` 的同一入口，非空模型历史被拒绝；旧 schema 仅在精确识别后跳过新模型表。
- 现有测试包含 5 类状态的 qxbak 往返、恢复后二次备份、超预算回执、撤销会话、摘要/来源/回执/输出/事件内容篡改。未将既有测试文件的存在或历史日志等同于本次重新执行通过。

## 复核源码 SHA-256

- `assistant/model_integrity.py`：`d9b6ab0bc2470a3f12d0ede39ae69922f5b1e27c840e7151e8f1313c38caefc8`
- `ops/backup.py`：`39416546994ee1bcc399949a484a57427ca6ffc157bb472b25958a88d29f12a7`
- `ops/workspace_backup.py`：`44109bd82ed113d94b79c6cd837f683b1b56b77c737000b8542ed160545808df`
- `tests/integration/test_assistant_model_backup.py`：`869319096350f7da77abde9fff3ad8909cd9787c0001a97138674d870c5b25b4`

结论针对上述源码快照。若协调代理后续修复，请保留本次发现和原始探针证据，另记复验结果。

## 修复后独立关闭记录

作者修复稳定后，复核代理使用完全相同的原探针字节在独立 `sequence-after-fix` 目录执行，未改产品或测试。当前 `_events` 先核对完整 run 事件序号为 1..N，再执行模型事件校验。

- 命令：`.venv/Scripts/python.exe -c "import runpy,sys; sys.path.insert(0,'tests/integration'); runpy.run_path('.local/chat-model-20261017/model_event_sequence_after_fix.py', run_name='__main__')"`
- 退出码：0；耗时约 1.80 秒。
- 同一损坏历史现在在 `backup._file_references` 阶段抛出 `ASSISTANT_MODEL_INTEGRITY`，未进入备份创建或恢复发布。
- `model-event-sequence-after-fix.json` 记录 `rejected_before_backup=true`、`before_evidence_unchanged=true`。
- 原探针 SHA-256：`2df49f3e5a31be5e63edf361bb07dd4fbe3bed5e66e8c503ad1d95da855d819f`。
- 修复前结果 SHA-256 保持：`d4054cbe3fac72740ca5b0ff5555471fae477edc27aefb59c8aec9134232a888`。
- 修复后 `model_integrity.py` SHA-256：`3f8fd8de9a27163ea7cd7ad64cba2565b8182c8432806d1d32f98b24054e5f35`。
- 修复后备份测试 SHA-256：`ad3e93b2ff79f530f5a3e765fd31d7958b9c1b69cc925e7f03a32f898c5e79ed`。

本次 P2 已关闭；指定备份与恢复范围剩余明确缺陷为 0。此结论是定向独立复验，不替代协调代理的全套回归和冻结构建。

另外只读核对 `docs/plans/2026-10-17-main-model-http-readiness.md` 的接口和预算身份前提，未发现必须更正项。文档准确区分规划与实现，保留旧消息登记语义、结果读取再鉴权、固定预算归属、政策内容不可原地漂移及仅合成清单的近期验收范围；真实动态授权与凭据入口仍是待实现前提。
