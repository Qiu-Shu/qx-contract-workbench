# CH-05D1 Standards / correctness 独立复核

2026-10-20；基线 `27f224c6568fcfdd4c16f49c6533cf9741dbb464`。审查对象是相对此基线的当前工作树；本轮尚未提交，因此没有把空的 base…HEAD 当作实现差异。按 code-review 的 Standards 轴线及 ponytail 执行；Spec 由另一个代理独立负责。

依据：仓库 AGENTS.md、CONTRIBUTING.md（DTO/Decimal/UTC、后端权限、事务外网络、主辅独立许可、未知费用、取消恢复不重发），以及 CH-05D1 执行文档和已批准原生交接第3–4节。CodeGraph用于调用关系定位，最终判断核对当前磁盘源码。

## 最终结论

当前审查范围内未发现未解决的阻断项或需修复的代码气味。发现并复现 **1项 P2，已修复且独立复验通过**。

- **已解决 P2：发布许可后到期导致同意图可续权。** 原 `native_judge_control.py:169–171` 在 `grant` 成功后才调用 `snapshot_for` 并记墓碑。将1秒许可在 grant 成功后推进时钟2秒，首次返回 `BLOCKED_LIVE`、墓碑为空；不改请求再次授权会创建新许可。修复让现有 `JudgeRuntime.grant` 返回其同步发布的授权UUID，native直接记录；不再发布后调用会因到期失败的快照。相同意图现被阻断，未产生新policy。

## 独立执行证据

仅运行一个无供应商调用的合成边界探针，复用既有临时工作区夹具：

`PYTHONPATH=<仓库> .venv/Scripts/python.exe .local/jev-request-20261020/standards-expiry-probe.py`

修复前 `standards-expiry-red.log`：exit **1**，`first=BLOCKED_LIVE, tombstone_after_first=false, repeated=authorized, new_policy=true`。

修复后同一探针 `standards-expiry-green.log`：exit **0**，`first=authorized, tombstone_after_first=true, repeated=BLOCKED_LIVE, new_policy=false`。首次响应与过期前后并不等于仍有可执行授权；后续发送仍走原到期检查。

## 覆盖与边界

静态覆盖12个生产文件：原生Jev控制及DTO、runtime身份、可选reserve精确降级、单事务双账本/固定Main租约/取消释放、Python与Node固定协议/独立能力门禁、desktop及web装配。对照目标测试的身份/损坏/回滚/重放场景，但没有把作者测试计为本人执行。

未运行全量回归、GUI、冻结后端、安装包、真实供应商或公网测试；未检查CH-05D2确认界面，亦不把其按计划留后当作缺陷。源码及差异最终摘要见 `standards-reviewed-files.json`，只覆盖列明的生产文件；后续字节变化需要重新核对。
