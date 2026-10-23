# CH-07C2c 应用入口设计复核

基线 `3d0e1859041572ed9c574e7a917afd044aedc6bf`。只读对照本片合同、v2.1 的短事务/当前权限/固定保存约束，以及现有 `NativeModelControl.authorize_context`、`ParentControlChannel`、`GenerationTasks`、`profile_attempts.enqueue` 和 generation 读取路由；CodeGraph 仅用于定位，施工中的源码不作为最终实现结论。

**结论：采用统筹确认的两路重入语义后，0 项必须修复的设计问题。** 后端/私有管道的切片边界可执行，不要求本片加入桌面 IPC、确认窗或档案侧栏。

必须写清的接口区别：

1. 尚未登记的原生授权重入：先从当前草稿、档案与接待基线重建完整 basis，再核对原 token；不能因 token 仍在而忽略保存目标已变化。撤权、过期或配置更换后的 tombstone 不复活。
2. 已登记的原生请求：验证原始消息/摘要、作用域、格式、stored prepared basis，返回 `existing`；不按现有草稿或新档案修订重建旧发送计划，不新增 grant，也不 dispatch。`existing` 只说明原登记存在，不是 `authorized`。
3. 重复 POST 保持原 `profile_attempts.enqueue` 语义，仍需原有效 lease/policy；过期、撤销或被替换后可以拒绝。消费者随后通过既有 GET by-request/history/attempt 找回，无需重新授权或发送。此分工没有新增越权读取，也不扩大写权限；未来界面收到 `existing` 应走 GET。
4. 同一请求不能只比较通用消息摘要：新增 `project_intake` 不在原 `AssistantMessageInput` 摘要内，必须与完整 stored basis 一并核对。新登记的 DTO 转换应明确剥离该字段后构造精确旧消息类型，并独立传递严格布尔用途参数。

预览应读取当前配置而非索取发送 lease；私有管道固定 operation/receipt 白名单、当前会话与活动工作区检查继续保留。HTTP 的 body 前后鉴权/同源/CSRF 及复用队列，不代表增加网络授权入口。现有读路由不派发任务，可直接服务新格式。

未修改源码、执行测试或审判施工态；最终实现的 Spec 审查待冻结后另行进行。Obsidian/TencentDB 检索只作背景，决策以实际代码与本轮统筹澄清为准。
