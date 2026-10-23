# CH-07C2b2b-A 档案用途许可内核

基线 `60eb041536dc36dfd4133f0d09b909681146500c`。Codex认领，沿v2.1及C2a/C2b1/C2b2a接续。C2b2b的整体激活仍须许可、账本、固定事件原子保存和历史/恢复全部闭合；本片是其内部许可实现，不开放应用入口，也不移除新格式完整性封闭检查。

## 最小改动范围

复用 `assistant/providers/registry.py` 的配置、登录会话隔离、许可身份及失效机制，并复用 `profile_preparation` 的完整basis摘要/构造和既有DeepSeek档案协议。无新DTO、依赖、schema或第二模型调用；不扩写主应用。

1. `grant`显式识别 `MainProfileSendBasis`，完整basis摘要是唯一允许内容键，同时核对配置/工作区、单次调用上限及provider具备档案接口。普通内容摘要或出站wire摘要不构成整理和保存计划的许可。
2. lease新增档案提交核验与执行核验。提交核验接收实际 `AssistantMessageInput` 及服务器重建的basis，完整相等并核对原提交。执行核验接收 `MainProfilePreparedInput` 和原request_id，不能只接缺少本地保存计划的 `MainProfileRequest`；以当前配置/模板重建basis及出站字节，拒绝自洽但替换过的准备内容。
3. lease provider新增 `generate_profile(prepared, expected_config=...)`，复用既有provider `generate_profile(request, expected_config, preflight)`。发送前、传输预检及返回时复核当前许可、配置、到期与完整准备内容。撤权/换配置/换许可后的迟到候选丢弃，已收到usage和供应商请求标识保留。无自动重试。
4. profile许可显式不能用于普通草稿、普通提交/执行/生成、资料上下文或多轮生成；plain/context许可也不能用于档案。同policy ID改变用途、目标、版本或内容仍遵守现有冲突墓碑语义；撤权、重新配置或不同事件循环均不恢复旧lease。

许可内核只核对已提供内容及当前registry状态；服务器须用C2b2a真实数据库装配并在实际使用时重核权限/版本。费用预留、调用次数的持久消费、运行claim、成功事件与档案保存仍由后续同一执行链实现，不能把max_calls=1解释为本模块已提供持久幂等或供应商收费上限。

## 实施与验证

沿现有用户批准的模块边界，不重复需求访谈。先保留一个有效失败测试再实现；独立合成测试覆盖完整计划绑定、普通/上下文/档案双向隔离、篡改/旧许可/跨会话/配置/到期、发送前拒绝及迟到usage保留。使用既有本机回环HTTP验证实际请求字节与不重试；不得连接真实供应商。补关联registry、普通/上下文、多轮、原生控制、档案协议/可信装配回归和四开发门。双轴独立复核后记录实际数量、日志及输入摘要，更新协作文档并正常推送。

开工工作区干净、fetch后0/0且无开放PR；无活动测试，现有安装版进程不动。WorkBuddy本轮 `native_unavailable`，采用子智能体复核。安装版0.4.1与WIN-PATH-02开放项保持，真实材料/法库/模型/云未参与。
