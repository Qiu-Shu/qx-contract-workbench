# CH-05B Jev 账本独立 Spec 审阅

结论：本片已冻结实现符合已批准的后端范围，未发现仍需阻断的 Spec 问题。最初确认的同次已收回执丢失 P2，其截止与外部取消两个分支均已修复，独立原样反例通过。本结论不代表真实 TypeSafe 调用、原生设置、主流程接线或生产对账已经完成。

## 审阅边界

- 工作区：`D:\Documents\ChatGPT\律所项目`。
- 基线：`a4c3c6706caad31c2335b4d055240dbddbfbd372`。
- 依据：`docs/plans/2026-10-20-jev-ledger.md`、已批准 v2.1 的权限、来源、费用与迁移规则，以及项目 AGENTS。
- 只读审查存储版本、旧 schema 固定、升级与恢复胶水、取消 hook、独立 Judge DTO/政策/账本/校验器、Jev 单次 preflight 和执行器。探针与证据仅写入本目录；未修改产品、作者测试或提交 Git。
- 没有调用真实模型、读取实际凭据或处理真实材料。独立网络反例只使用本机随机回环端口，每个场景严格检查一次 POST，共三个 POST；恢复/授权探针不联网。

## 已关闭发现

### P2：同次已收到的回执在截止或外部取消时丢失

原实现的执行器与提供器各设同长度计时器，外层先开始。在响应已完整解析、客户端清理尚未结束时，外层取消导致执行器丢弃 usage 与供应商请求 ID，以 sent_unknown 结算。外层计时器移除后，该反例通过；沿同根路径进一步检查外部 `task.cancel()`，发现仍会丢弃已经安全解析的回执。

最终实现由精确 JevProvider 持有单一截止；仅已 received 的取消携带安全 JudgeResult，状态不能是 ok、answers 为空。执行器对正常与取消结果统一严格重建 DTO，并核对本次请求 ID、作用域和输入摘要；不合格取消回执退回未知，合格回执落入原 attempt 后仍向上抛 CancelledError。没有采用建议、追加重试、释放未知费用或延长业务截止。

原始证据保留：

| 运行 | 退出码 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| 双截止初次反例 | 1 | 1 failed / 1 passed，2.53s | `deadline-red.log/xml` |
| 移除外层计时器后原样复验 | 0 | 2 passed，2.18s | `deadline-green.log/xml` |
| 外部取消残余反例 | 1 | 1 failed / 2 deselected，1.49s | `cancellation-red.log/xml` |
| 最终冻结全部独立探针 | 0 | 10 passed，5.94s | `final.log/xml`、`report.json` |

这按一个根因、两个分支记录，不把迭代复验累计成更多独立用例。

## 最终独立验证

运行命令（工作目录为上述实际工作区）：

```powershell
.\.venv\Scripts\python.exe .local/jev-ledger-20261020/review-spec-glue/run_final.py
```

驱动器实际执行的完整 Python/pytest 参数、UTC 时间、10 个去重节点、测试输入摘要、17 个产品文件运行前后 SHA-256 均在 `report.json`；pytest 退出码 0，驱动器退出码 0，失败/错误/跳过均为 0。17 个产品文件前后字节稳定。

| 独立探针 | 去重节点数 | 证明范围 |
| --- | ---: | --- |
| `probe_schema_glue.py` | 4 | 从真实基线提交读取旧 schema，对比五个历史版本、两种 native 形态；故意让最后 Jev 升级步失败，整条缺失迁移链回滚，旧结构/FK与独立合成原件保持不变 |
| `probe_deadline_receipt.py` | 3 | 同步解码迟到、异步清理迟到、解析完成后的外部取消；均保留已收使用量/请求 ID与费用占用，不采用 decision；外部取消继续传播 |
| `probe_recovery_authorization.py` | 3 | reserved/sending 分别保守恢复为 not_sent/sent_unknown，未虚构用量，主 runs/messages/events 原样；主模型 runtime 不取得 Jev 权限；相同用户的新登录会话不能继承原政策 |

没有重跑父代理的 14 项备份批次或整套关联回归。作者将其中三个反例纳入其确认运行，不改变本审阅的 10 节点计数；父代理和作者的数量不能与本报告重复相加。

## 静态 Spec 核对

1. 新版本在固定旧 Main DDL 上增加 Jev 三表，保留所有旧版本的精确识别。隔离升级使用单事务；native 升级仍沿既有备份/回执与精确失败恢复路径。
2. qxbak 在独立 staging 升级与恢复，先核验旧结构/字节/引用，最后才发布副本；启动及恢复只收尾辅助历史，不恢复联网、不结束主 run、不新建队列。普通 cnbak 明确拒绝非空辅助历史，因此不是遗漏恢复步骤。
3. JudgePolicy 独立绑定固定接收方、用户、登录会话、工作区、配置、用途、请求 ID、完整输入摘要、期限和 Decimal 预留；主模型授权不等于 Jev 授权。配置/政策撤销代次仍检查在途请求。
4. reserve/claim/preflight/settle 使用同一主 run；发送不占数据库事务，持久一次 claim 与预算串行核验保留。未知用量不记零，只有明确未发送才释放占用；received 也不被冒称供应商已结算金额。
5. 回执与采用记录分离；取消、过期、撤权、作用域/材料/配置变化后仍可保留安全回执，但不得写入采用建议。Judge 不重写 Main 的 selected_provider、model 或 budget 字段。
6. 本片普通文本 primary_intent 保留原话；显式技能直接跳过辅助。无可靠来源映射的附件分类/运营风险用途保持阻断。后续接线契约明确主生成管理器尚未调用、配置/批准须同 loop、未提供重启后外部账单追补。

## 最终绑定

完整 17 文件摘要见 `report.json` 的 `product_hashes_before` 与 `product_hashes_after`。本次修复两文件与作者正式冻结一致：

- `src/cn_contract/assistant/providers/jev.py`：`0ef430717db2f11c225ba0fddbb1ac23b736b1d033105d4e027e02bede1fa686`
- `src/cn_contract/assistant/providers/judge_execution.py`：`7ad51bb46ba8002a83be414e04247f66d1c78c7293f29303988f27d53cb9951b`

当前结论仅绑定这些字节及本片范围。父代理负责最终关联回归、Windows 子后端/冻结构建与总执行记录；本审阅没有把 host Python 回环试验称作原生 Jev 执行或真实服务验证。
