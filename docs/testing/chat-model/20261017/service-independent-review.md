# CH-04A 应用服务独立审核

2026-10-17；工作区 `D:\Documents\ChatGPT\律所项目`。范围：新增 Main DTO、`assistant/providers/policy.py`、`attempts.py`、`assistant/runner.py`，结合现有授权与事务实现、已确认执行计划。未依赖传输作者结论代替代码检查。产品和正式测试只读；仅运行本目录的独立合成探针，无秘密读取、真实外发或完整回归。

## Standards

发现 1 项与安全事务约定有关的问题，与 Spec 第 3 项为同一缺陷，不重复计数：现有 `security.deny()` 会结束事务，不能在捕获其异常后继续依赖该事务内的 fence 和 claim 检查。DTO 集中定义、费用 Decimal、原始输入不可变、网络位于 DB session 之外均符合当前约定。

## Spec

本次初审有 3 项可复现问题；均已即时反馈根代理，以下记录的是修复前结果，不是修复后状态。

1. **P1：回执超预算后，已预占请求仍能发送。** `attempts.py::claim` 未重新核对已结算费用与保留预占。两会话各预占 0.024576 USD、政策总上限 0.049152 USD；第一回执估算 0.3 USD 后，第二任务执行仍调用 provider 一次并变为 received。供应商自报超出请求上限时，传输适配器会保留 usage 并拒绝正文，这正是执行计划明确要阻断后续调用的情况。应在 claim 的原子事务核查当前预算，不能只在 enqueue 时核查。

2. **P2：发送前取消仍占用预算和次数。** 既有 `service.cancel_run` 将 queued run 取消，但相应 attempt 留在 reserved；执行又因版本/取消拒绝，无未发送回执。在 max_calls=1 的合成政策下，整个过程 provider 调用数为 0，下一条合成请求却得到 CALL_LIMIT_EXCEEDED。应将未 claim 且已取消/确定失去发送资格的 attempt 封为 failed_before_send，留下可审计回执并释放预占；同时保留已 claim 请求的未知费用边界。

3. **P1：撤销案件成员权限时，结算可越过新提交的恢复 fence。** `settle` 初始检查 fence 和 sending/claim；随后 `_current` 经 `service._owned → authorize → deny` 结束该事务。捕获 ServiceError 后直接进入新事务写回执。合成探针在 denial commit 返回后用第二连接插入 fence，实际观察到 fence=1、随后模型回执=1、attempt=received。应在权限核验之后、真正落库前重新检查 fence 并读取当前 sending/claim，或者采用不会结束事务的受限权限检查。session 撤销路径不经过该提交，不能替代案件成员撤销测试。

## 证据与后续复核

- `independent_service_probe.py` → `independent-service-probe-before-fix.json`，成功退出码 0；实证第 1、2 项。早期仅探针装配失败（tests 导入与临时目录清理）不计产品失败。
- `independent_denial_fence_probe.py` → `independent-denial-fence-probe.json`，成功退出码 0；实证第 3 项。该探针仅在自己的会话实例包裹 commit，模拟另一连接在事务释放后的确定性维护提交，没有替换产品源码。
- 已检查主模型/Jev 边界、旧 queued 不晋升、消息 SHA 授权、材料非空拒绝、配置/策略摘要、wire 比对、claim 单次性、未知费用预占、受众固定 internal、取消后拒绝采用成果。除上述问题外未发现新的明确缺口；此表述不是功能通过。
- 普通启动路径的 attempt 封存接线尚需在实现结束时确认；qxbak 已出现 recover_attempts 调用。当前没有生产 runner 装配，未把正在施工的接线作为第四项缺陷。
- 根代理补回归与修复后，应针对这三条实证独立复核。未运行或声称通过完整回归。

## 修复后的独立关闭

三项均已窄范围复核关闭，Standards / Spec 残余均为 0（限本次范围）。

1. `claim` 在受控事务复核该 policy 全部已结算费用与在途预占，超限时封存未 claim 的尝试。原合成探针复跑：第一估算 0.3 USD、总限 0.049152 USD，第二任务变 `failed_before_send`，provider 调用 0 次。
2. `service.cancel_run` 调用 `cancel_reserved_for_run`，只释放 `reserved + claim_sha256 IS NULL`。原探针复跑：已取消任务有 `not_sent / 0 USD` 回执，下一次 enqueue 成功，provider 调用仍为 0。修复后原探针输出保存在 `independent-service-probe-after-fix.json`，退出码 0；修复前输出另存，没有覆盖。
3. `settle` 在采用权限检查之后重新执行 `require_active`、重新读取 attempt 并核对 sending 与 claim；这三步与写入同属新的短事务。持久回归新增 `tests/integration/test_assistant_model_denial_fence.py`，覆盖真实案件撤权审计提交后由另一连接插入 fence，确认零回执/零成果、attempt 全行不变、run 与事件数量不变，返回 BLOCKED_LIVE。

持久回归第一次执行时，根代理已经提交工作树修复，实际 **1 passed，1.34s，exit 0**，保存在 `denial-fence-first-green.xml/.log/.exit`。没有把这次执行称为 RED；修复前错误证据来自先前的 `independent-denial-fence-probe.json`。持久测试 SHA256 为 `13ef9185d9d8d7ba1300c2816cc57c69404c242d0b819eb15dc9dd470948ba78`。

仅新增上述一个正式测试文件；未修改产品源码或其他正式测试。最终完整回归由根代理统筹，本次窄验证不替代它。
