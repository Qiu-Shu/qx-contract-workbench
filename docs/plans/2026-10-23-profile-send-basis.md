# CH-07C2a 档案发送与保存计划绑定

基线 `37773d92f08e0b3bc2fed27064ceb011e8a72cd6`。沿用已批准的 v2.1 和 CH-07C1；本片由 Codex 认领，独立复核使用既有子智能体。当前桌面进程仍在运行，不接触其数据库或真实资料。

## 问题与范围

C1 的同次回答协议已经能生成精确来源的档案提案，但普通文字许可没有说明自动整理用途，也没有绑定将被更新的档案/接待版本。完整 C2 还涉及三条 schema 迁移入口、历史验收、原生确认和固定保存事件。这些运行入口不能只接一半就启用。

本片先交付可直接供这些入口复用的纯离线准备模块，**不是发送或保存授权**，不改 registry、HTTP、桌面、数据库或旧许可。无新依赖、额外模型调用或第二套账本。

- 复用 AssistantMessageInput 和 C1 的精确 MainProfileRequest，通过组合建立 MainProfileSendBasis / MainProfilePreparedInput。仅当前文字、无点选技能、无提交附件；会话已选择的附件还必须由后续可信装配器核对，离线函数不能证明其不存在。
- basis 固定用途 reply_and_profile_draft、profile-text-v1/template、handler profile.save/1；绑定 request_id、提交前完整 scope、composer_revision、content SHA、档案基线和接待目标/版本、是否投影接待。manual_edits 不在模型或准备输入中，自动保存必须恒空。
- 同时绑定 C1 完整实际出站 JSON 的 UTF-8 字节数与摘要、system 摘要、配置摘要。模型、字节上限、输出上限及费用配置变化也失效。保存计划不外发；整个 basis 的摘要才是后续许可键，单独 content/wire SHA 不能授予存档。
- prepare 复用实际保存的 AssistantRunView/AssistantMessageView 构造 C1 请求，重新验证 basis、配置；核对 run 的 request_id、message_id、user 角色、当前文字、scope 仅 input_revision 加一、source_revision 和 composer_revision 加一。未知用途、格式、handler、越界/成对缺失版本、篡改完整 wire 均拒绝。当前档案/接待版本须由后续可信装配器读出并重建 basis 比较，不能把本片的离线自洽称为当前数据库核验。
- 原 C1 wire 保持逐字节兼容；拆出同一私有正文构建函数供准备和发送使用，不复制 prompt。保存后的 run/message 与原 request_id 的数据库关系、当前权限、活动状态、实际选择附件、最新档案/接待版本仍由 C2b 核验，不能用离线自洽代替。

## 验证

先运行失败测试，再实现。合成测试覆盖 UTF-8/Unicode、明确用途与目标计划、保存前后版本桥接、同wire不同保存计划的许可摘要差异、配置/模板变更、伪造DTO、预算边界和旧字节兼容；运行既有 profile codec/HTTP、普通与上下文准备、registry关联回归和四开发门。独立 Spec/Standards 复核后记录实际命令、退出码及数量，更新 TODO/TASK_STATUS/README，正常推送并核对远端。

## C2b 的闭合条件（尚未实现）

新输入格式必须通过新命名 schema 版本和旧签名冻结接入登记、claim/settle、历史与恢复，不能以 profile 混入 plain-text-v1。原生许可须由服务器重建完整 basis 并核对整个摘要。固定 response.ready 事件回执与 profile_store._commit 在同一短事务/保存点写入；不从 settle 调用另开 session 的 save_profile。现有 assistant_handler_receipts 的 CHECK 仅允许法库 handler，须显式迁移及完整性分派，不能冒名插入。

收到有效回答并不等于保存成功；费用回执独立保留，取消/撤权/过期响应不提交草稿。网络未知不自动重发；恢复只能处理已有可信响应，不能制造新模型调用。不得在响应到达时用最新档案/接待版本替换批准基线。C2b 完整闭合后才启用新发送，C3 再接档案面板与本地联系方式。WIN-PATH-02 仍开放。
