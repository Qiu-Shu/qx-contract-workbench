# CH-05D2 Standards / correctness 独立复核

2026-10-20，基线 `a1ecd7e7d06112e228719586e4d35fe65a906036`。审查相对此基线的当前工作树；尚未提交，不能将空的 base…HEAD 视为实现差异。按 code-review 的 Standards 轴线和 ponytail 核对，Spec 由另一代理负责。

依据为 AGENTS.md、CONTRIBUTING.md、`docs/plans/2026-10-20-jev-confirmation.md`，以及实现前独立设计复核。使用CodeGraph定位调用关系，并核对当前生产源码。无产品写入和提交。

## 结论

**未发现需修复的阻断缺陷或代码气味，Standards findings：0。** 结论仅适用于摘要清单中的8个生产文件。

- 真实 `main.cjs` 没有传入 `judgeBudget`；可选授权默认关闭。预算由可信构造参数提供，保留精确十进制字符串；窗口、preload和主进程不接受用户页面扩写预算或接收方。
- 同窗选择必须为精确 `{main:true,judge:boolean}`；旧无辅助详情仍保留布尔决定。辅助默认未选，不可用时不能伪选。文本以textContent呈现，窗口沿用隔离会话、来源检查、网络禁止、失效取消和默认取消焦点。
- 外层Main租约覆盖整个流程。Main明确成功后才尝试辅助；已知辅助拒绝允许继续，未知回执触发停止原后台。最终cookie检查仍在两份租约内；内层已关闭而外层失败时，编排等待停止捕获的旧后台，未把关闭后的revoke扩为长期权限。
- 缺辅助配置、预算或能力只执行一次callback(null)，不借用Main授权；原Main必须完成授权的成功语义保留。配置、迟到ACK、后台替换均经过原生命周期检查。

## 本人实际执行

独立合成探针：`node .local/jev-confirm-20261020/standards-probe.cjs`，exit **0**，4个断言场景：默认空预算无授权；回调不等待授权promise时，明确拒绝仍可安全跳过；同样情况下未知ACK关闭旧后台且拒绝成功；迟到成功ACK遇后台替换仅撤旧授权，不停止新后台。结果见 `standards-probe.log`。

读过作者目标测试覆盖，没有把它们记为本人执行。未重复全套回归，未操作Electron/GUI、冻结程序、真实供应商、公网或真实材料；这些需以统筹实测报告为准。现有设计探针描述的是组合契约反例，不能夸称普通用户操作已触发现实竞态。真实费用和账号基础未落实，本次界面完成也不等于真实辅助发送开放。

受审文件和差异摘要见 `standards-reviewed-files.json`；之后生产字节变化需重新核对。
