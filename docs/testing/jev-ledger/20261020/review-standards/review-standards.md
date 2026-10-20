# CH-05B 独立 Standards 审阅

**结论：无 P0–P3 发现；硬性标准违规 0，需修复 smell 0。** 已合并重新冻结后的取消专项复核；本报告仅为 Standards 轴，不替代 Spec 或生产验收。

基线 `a4c3c6706caad31c2335b4d055240dbddbfbd372`；审查时 HEAD 等于基线，按任务审阅 `git diff a4c3c67 --` 加未跟踪新模块。依据 AGENTS、Ponytail full、code-review 的 12 项 Fowler smell baseline，以及 CH-05B 计划和 v2.1 §6.4–6.5；以明确仓库规则优先，不因行数或抽象偏好提重构。

## 源码证据

- `domain.py:3092–3159` 集中 JudgePermission/Policy/Receipt/Decision/Attempt DTO，沿用不可变快照；费用为有界 Decimal、明确 USD，UTC 失效期。没有供应商调用或权限判定塞入 DTO。
- `judge_attempts.py:36–145,173–236` 复用当前会话/归属/案件访问/恢复 fence；核对原 run、完整文字、scope、用途、policy/config/hash/授权代次。保留和 claim 使用既有短事务，CAS 与不可变 claim 防重复；预算检查不把 unknown 当零。
- `judge_execution.py:11–58` 在 claim 事务退出后调用固定 JevProvider，preflight 另开短事务；收到回执和可采用建议分别处理。唯一截止由提供器负责，避免外层重复计时抹去收到的使用量。已收到的安全回执在取消通道中仍先结算，再向上传播取消；未收到时保守记为未知占用。
- `judge_schema.py:5–40` 只增加引用原 run 的三表及不可变触发器；没有第二调度器。`judge_attempts.py:239–256` 的取消/恢复仅收尾辅助账本，不写 Main run 终态、供应商、模型、预算字段。
- `judge_integrity.py:45–175` 校验不可变请求、来源、身份、金额、回执与采用记录；不以当前 live grant 判断历史真实性。`storage_schema.py:2–35` 固定旧 Main DDL，并保留旧版本识别；migration/bootstrap/backup/startup 只增加对应调用。主入口未堆业务逻辑。
- `jev.py:49–64,161–204` 的可信单次 preflight 在密钥前和实际 POST 前复核；默认无许可拒绝。没有新 SDK、环境端点或日志正文；Main 授权不等于 Jev 授权。

## 独立验证

`standards-final.json` 保存实际命令、退出码及前后完整哈希；`standards-final.log/.exit/.xml`：**3 passed，退出码 0，1.63s**，17 个产品文件摘要稳定。

1. 实际慢回环尚未响应时，独立 `BEGIN IMMEDIATE` 写事务完成；仅 1 次 POST，重复 execute 不再发送。Main run 全字段、事件数不变，Main attempt 为 0；未知输出用量仍占 **0.031 USD**。
2. 无 runtime、无配置、无政策、传入 Main runtime 均拒绝且 0 密钥读取、0 Jev attempt，不改变原 run。
3. 固定 Main DDL 与 `git show a4c3c67:.../model_schema.py` 的实际结果逐项一致；native/non-native 当前 schema 均只增 Jev 三表及其对象。

首次冻结 SHA-256（保留作为中间证据；下文列重新冻结后的两项变化，JSON 保存最终 17 文件摘要）：

| 文件 | SHA-256 |
|---|---|
| domain.py | `088cc8d08e435128b81d057e7017d4f46d42ea43303a1d2ba789d7dac46dde0f` |
| judge_attempts.py | `3058deae4fbd09edba6fb470da28f57881b0f5e5d890fef3de5f14eadb5e4c4d` |
| judge_policy.py | `708eee0dc681138834a15e07629f59cc002afd850be8c0278a54ec6233acef2e` |
| judge_execution.py | `97dc6dec12151474d334337e572e5e8ac17e8203530c8f5b18acbe0c59473d18` |
| judge_integrity.py | `c6369ee0f59bdc0837c1fbf1887b6bf2fa17f8fdba80fdf5e3b1ec2d4ded60bd` |
| judge_schema.py | `44de9e38b94a6ffb77f12124158cb64fa2a783dac3630548f85903fa9ff288f3` |
| jev.py | `80bf399ade7a0bc7114971e68d458eb5efdee39b1c31f423ae5afe0693b8f29e` |

未改产品、作者测试、项目状态或提交；无真实密钥/资料/外网。未重复作者目标回归或 Windows 验收。原生 Jev UI、主 runner 接线、供应商实际计价及材料映射均属明确后续边界，不作本片缺陷。


## 重新冻结后的取消专项复核

Spec 轴在首次报告后发现：响应已解析、清理资源期间收到外部取消，会丢失已知使用量和供应商请求号。作者只修改 `jev.py` 与 `judge_execution.py`；本轴复核这两处 diff，并仅增跑直接相关的一个独立探针，未重复前三项。

`jev.py:54–59,232–236` 以 `JevCancelledError` 携带既有 `domain.JudgeResult`，仅对 received 回执启用，强制非 ok、清空答案；异常不新增业务 DTO、密钥或授权接口。`judge_execution.py:34–56` 将取消与正常结果收敛到同一严格 DTO/request/scope/hash 边界；无效取消回执退回未知占用，合法回执落账但不采用建议，最后继续抛出 `CancelledError`。

`cancellation-final.log/.exit/.xml/.json`：**1 passed，退出码 0，1.43s**。真实回环回复已解析后暂停客户端 cleanup 并取消：取消向上传播，input/output tokens **23/7** 和固定合成 request ID 保留；answers 为空、decision 为 0，仍保守占 **0.031 USD**；重复 execute 无追加 POST，Main run 全字段及事件数不变。仅 1 次合成 POST，外网与真实模型调用均为 0。

17 个产品文件运行前后摘要稳定；相比首次验证仅下列两项改变，并与作者重新冻结摘要一致。原报告另存 `review-standards-intermediate.md/json`，原 3 项实际日志未覆盖。累计独立 **3 + 1 项 PASS**，不混计作者或 Spec 结果；取消残余已独立确认关闭，当前仍无 P0–P3 或可行动 Standards 发现。

| 最终变化文件 | SHA-256 |
|---|---|
| jev.py | `0ef430717db2f11c225ba0fddbb1ac23b736b1d033105d4e027e02bede1fa686` |
| judge_execution.py | `7ad51bb46ba8002a83be414e04247f66d1c78c7293f29303988f27d53cb9951b` |
