# CH-04E：配置版本与登录会话授权的运行接口

基线 `4435396`，接续已批准 v2.1 和 post-home-readiness。CH-04D 只完成本机凭据保护；本片解决既有单个全局 runtime/policy 不能安全承接多个登录会话的问题。复用同一任务管理器、费用账本、attempt 和不可变原文；不修改存储 schema，不新增队列或运行依赖。

## 契约

- 新增受信任的进程内 `MainModelRegistry`，提供 configure(provider)、grant(policy, session_id)、revoke(session_id)、resolve(actor, scope)。配置及授权只能由服务端装配调用，本片没有新增 HTTP/页面授权入口，不从请求正文或模型输出创建 grant。
- configure 校验已有 MainModelConfig 后生成配置代次；更换/关闭配置清空当前会话授权，使旧 lease 失效；相同配置重新启用也不恢复旧授权。注册表重建为空，不恢复 DB 中的历史授权或排队请求。
- grant 沿用 MainModelPolicy，绑定 workspace_id/user_id/session_id，校验配置摘要、有效期、额度及原文摘要 allowlist。相同 policy_id 不允许换内容或重置预算；既有 DB 账本仍是费用依据，不以 registry 的内存计数代替。
- 每个会话键仅有一份当前 grant；替换使该会话旧 lease 失效，重复同一当前授权可以幂等。撤销后再授予同一 policy 必须有新身份，旧 lease 不复活；跨会话共用同 policy_id 时仍共享账本。runtime.snapshot_for(actor, scope) 在入队与 claim/settle 验证 lease 的会话身份，不能把 A 会话 lease 交给 B 会话使用。
- resolve 为当前登录会话取得固定 provider/config/policy 的运行 lease。未配置返回空；已配置未授权只能显示 unapproved。lease 的 snapshot 在入队、claim、settle 及实际 generate 前重核当前配置代次和授权身份；更换其他会话授权不会影响本会话。新 grant 不让已撤销的旧 lease 复活。
- 注册表首次由应用事件循环 resolve 后绑定该循环，配置/授权修改与任务调度均强制在此循环；初始化前可同步装配，绑定后拒绝工作线程/其他循环调用。claim/settle 的最终检查与短事务提交不跨 await。请求中的 actor/scope 仍由已有数据库权限核验，不让 grant 替代当前会话、案件权限及版本复核。
- GenerationTasks 在短事务内选定 lease，整个 attempt 始终使用该 lease；取得发送 claim 后变更配置或撤权，按旧配置保留真实用量回执或 unknown，不采用过期结果。只有尚未取得 claim 的旧任务能证明未发并释放为 not_sent；任何结果未知都不自动重发。
- 旧可信 MainModelRuntime 的合成/服务端装配入口兼容，默认 None 不变。普通读、保存、GET capability 不会创建授权或启动网络。原生密钥到后端的可信管道及用户配置界面是下一片，不能在此声称真实模型已接通。

## 本片验证

先失败用例，再最小实现与关联回归。覆盖不同用户和同用户不同登录会话隔离、不同会话并发、配置代次失效、换回相同配置不复活、同 policy_id 改内容拒绝、重授权不重置累计预算、撤权/变更发生在发送前和发送中、取消与重启无补发、当前权限与恢复副本保持关闭。通过真实应用 HTTP 与独立合成回环供应商验证既有页面能力状态及单次发送/回执，不接真实端点。

结束保留实际命令/退出码/数量/输入摘要及独立复核，更新 TASK_STATUS 和 Obsidian，本地提交。WorkBuddy 当轮状态为 busy/unknown，不抢占、清状态或沿用历史回执。
