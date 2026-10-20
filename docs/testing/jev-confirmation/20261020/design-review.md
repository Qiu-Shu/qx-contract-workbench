# CH-05D2 原生确认与嵌套许可：实现前复核

基线：`a1ecd7e7d06112e228719586e4d35fe65a906036`。复核日期：2026-10-20。范围为 `desktop/model-approval.cjs`、`model-session.cjs`、`main.cjs` 的可信调用关系，结合 `docs/plans/2026-10-20-jev-native-handoff.md` 第 3–5 节及现有 Python Main/Judge 授权语义。CodeGraph 已用于检查调用影响。实现作者同时在修改 UI；本报告不是最终代码验收。

## 结论

可沿现有 session/lease 和确认窗口实施；无需新 registry、队列、通用许可框架。需要明确 Judge 的“允许不授权”返回契约，并为“内层已关闭、外层最终检查失败”的组合结果添加最小补偿。所有最终 cookie/HTTP 核验应留在两份 lease 均 open 的回调内。

## 必须落实的语义

1. **可选 Judge 不得继承 Main 的强制 `authorized` 成功条件。** 基线 `model-session.cjs:139` 的 `!authorized` 对 Main 正确，但对 Judge 未勾选或明确辅助拒绝不正确。Judge callback 返回成功且 `valid()` 成立时，可以零次授权，或在明确拒绝后继续 Main。未知 ACK、管道异常、context/guard 不成立、回调异常必须保留失败关闭；不能以 optional 为由统一吞掉。
2. **能力及预算只从可信装配取得。** Judge 授权还需 `judgeAuthorizationEnabled === true` 及 authorize/revoke 方法；只有 `judgeEnabled` 表示配置能力，不表示可以授权。缺预算、未配置、旧后端、busy 时可调用一次 `callback(null)` 展示禁用辅助；真实装配保持预算 `null`，只测试装配注入合成值。不要把 Main 预算、renderer 传参、环境变量或随意常量当 TypeSafe 价格。
3. **先 Main 明确成功，再只对明确选中的辅助调用 Judge authorize。** 主失败不调用辅助。主成功＋辅助明确拒绝仅跳过辅助；辅助未知回执须停止捕获的后端。精确选择对象为 `{main:true, judge:boolean}`，有 Judge 详情时布尔 `true` 不应绕过独立选择；保留旧无 Judge 详情的布尔契约。

## 嵌套关闭窗口的精确判断

现有单个 `withAuthorization` 会在 callback 返回后 `await flight`，再次核验 `valid()`，最后 `open=false; active=false`。直接采用外 Main、内 Judge 时，Judge 可以先完成并关闭，随后 Main 再执行自己的最终 `valid()`。此时若失败，Main 只拥有自己的 `grantedToken`，不能撤销已经关闭的 Judge lease；公开 `lease.revoke()` 已按契约拒绝关闭后调用。

实际 Electron 路径的风险应准确描述：如果内层关闭后只有已完成 promise 的 await 和同步最终检查，普通导航/pipe I/O 事件不会在同一次 Promise microtask drain 中插入，且 shared busy 禁止另一个设置/批准操作。因此本次没有证明普通 UI 操作可触发一个生产竞态。但函数组合本身没有跨 lease 失败补偿；后续在内层结束后添加 cookie/HTTP await、依赖回调产生微任务状态变化，或最终 guard 严格变为 false，会暴露这一缺口。不应把“单事件循环”直接当成跨异步组合的自动原子性。

本地纯合成探针 `nested-lease-probe.cjs` 实际执行 exit 0，复用了基线 `createModelSession` 两次和内存假 ACK。在内层关闭时令外层 guard 失效，结果为 `STATE_CONFLICT`，调用序列为授予 Main、授予 inner、仅撤销 Main，留下 1 个内层 grant。报告见 `nested-lease-probe.json`。这是组合契约反例，不是现成 Judge 产品回归，也不是已发现真实供应商发送。

建议最小处理：

- 最后 `tokenFor` 及任何异步核验均在内层 callback 内完成，确保两份 lease 可以自行撤销。
- orchestration 的可信闭包记录是否已收到 Judge 成功回执；外层最终结果失败且曾收到该回执时，停止最初捕获的 backend，等待停止完成再释放 shared busy。只停止捕获对象，绝不停止 `getBackend()` 后来的新实例。
- 这个停止属于异常最终检查的保守补偿，不适用于普通未勾选或明确辅助拒绝；这些路径应继续 Main。
- 不扩展公开 `lease.revoke()` 使其在关闭后长期可用。现有 revoke 基于会话，迟用可能撤掉同会话的新授权；保留单次短生命周期更容易证明安全。
- 如果团队选择另一种最小补偿契约，也必须覆盖“inner 已成功关闭，outer 最终失败”而非仅测试 callback 内失败。

## 建议目标用例

- Main 同意＋Judge 未选：只授 Main，成功；不调用 Judge authorize/revoke。
- Main 同意＋Judge 明确 `STATE_CONFLICT`/`BLOCKED_LIVE`/预算拒绝：Main 成功，Judge 未获得新 grant。
- Main 拒绝：不调用 Judge authorize。
- Main 成功＋Judge ACK 异常/超时：停止捕获后端，不返回批准成功。
- 两份 grant 已授予，最终 cookie 改变或 guard 失效：在 callback 内时两者撤销；内层已关闭时触发组合补偿。
- 后端被替换：只清旧后端，不改变新后端；待处理确认与两类设置互斥。
- 缺预算/未配置/能力不足/busy：callback(null) 恰好一次；无辅助授权，不把旧配置能力当授权能力。
- 缺辅助预算的真实 main 装配静态断言：确认 UI 可见禁用原因，但不开放真实辅助外发。

## 未执行与边界

未修改产品、未提交、未调用外部模型或真实材料。只运行上述合成函数组合探针；未运行新 UI、完整 Node 回归、Electron 或冻结后端。作者完成后仍需独立最终复核及对应实测，不能将本设计建议标为实现已通过。
