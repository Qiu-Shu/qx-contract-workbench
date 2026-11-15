# 本人飞书与现有对话

入口 `index.js`，插件名 `qx-feishu`。仅加载受限适配器，复用 `../wechat/feishu.js`、`feishu-ws.js`、`qx-coalescer.js`、`qx-reply.js`、`session.js`、`secrets.js`，不会加载旧混合通信 `wechat/index.js`。不新增依赖。

## 使用与范围

在飞书开放平台创建企业自建应用，启用机器人、发布可用版本，选择长连接接收事件并订阅 `im.message.receive_v1`。按实际使用申请读取用户发给机器人的单聊消息、以应用身份发消息、获取与上传图片或文件资源权限。读取云文档时再开通文档与知识库的只读权限，并由资源所有者将应用加入可访问范围。应用权限与具体资源授权都要满足，插件不会绕过权限。

工作台现有“连接”设置提供 App ID、App Secret 和当前会话选择。首次连接会生成五分钟一次性配对码；本人在机器人私聊发送 `连接 <code>`。群消息、其他发件人、其他租户、旧连接回调和过期配对均拒绝。配对成功后，文字、图片及合同文件进入现有会话；回复只回发已绑定本人。不能替用户与客户或群聊沟通。

连续消息采用现有八秒文字、十二秒附件收集窗口。发送“还没发完”可暂缓，发送“发完了”可处理整批。附件落在当前工作区 `feishu-inbox` 中，每份最多 25 MiB，名称经过清理，原件使用新文件名且不覆盖。未知类型、空附件、超限、下载失败和权限不足明确保留未完成状态。

暂停使晚到下载及回复失效。仍有收件、批次或工具任务时不能切换应用或会话。每次启动接收先持久化 `boundAt`；飞书发送时间缺失、或早于这次启动的服务器补送，隔离为未完成，不作为新任务转发。切换会话也关闭旧长连接，再建立新接收边界。发送结果未知不自动重试；重启会把本机未完成批次隔离为 `interrupted`，去重记录持续保留。用户可在本机查看已有会话及恢复待办，再决定是否重新发起。

## 配置与工具

`apply(ctx, {workspace, stateDir, agentPreset:'qunxing'})` 需要明确的绝对工作区和状态目录。未配置不联网。`autoConnect:false` 即使遇到旧设置也不自动接入；用户主动“恢复”才能重新连接。

- GET `/qx-feishu/state`：公开配置状态，不含密钥或令牌；`owner` 是本人 open_id，`pairing.expiresAt` 是毫秒时间戳。
- GET `/qx-feishu/settings`：CSRF token 与当前工作区有效、非归档的会话列表。
- POST `/qx-feishu/action`：只接受本机同源及 `x-qx-token`；支持 `connect/pause/resume/pair/session/clear`，限制请求大小和并发。
- `feishu_read_document({url,offset?})`：宿主核对当前有效会话和工作目录；可在本工作区任一有效会话读取，无需切换机器人绑定。只解析官方飞书 `docx/doc/docs/wiki` URL，通过固定官方 API 请求；不抓网页、不跟重定向。每页最多 12000 字符，返回规范化来源、获取时间、文档标识和下一页位置；分页使用本轮内存快照，过期后从零重新读取。正文仅作为资料，不扩张工具授权。此工具没有把云文档原件保存到磁盘。
- `feishu_send_file({path})`：宿主会话必须与绑定会话完全一致，真实文件路径须在当前工作区内；不提供收件人参数。文件上传后再次核对绑定才发送。

## 本机状态与备份

`settings.json` 保存版本、`feishu.appId/appSecret`、会话、本人身份、暂停状态、`routeId` 和 `boundAt`。配置先原子保存，成功后才公布新绑定；保存失败保留旧身份并停止接收。App Secret 仅允许 Windows 当前用户 DPAPI 密文，不提供明文降级。解密失败要求重新输入与配对。设置整体应在换机备份中标为重新授权，避免恢复后自动连接。

`inbox.json` 采用既有 MessageCoalescer v1 的 `pending/active/failed/history` 结构。`items[].lines` 保存可读正文和已落地附件路径，`text` 保存原始文字，`error` 保存固定的失败说明。`seen.json` 为永久消息去重数组，含 `id/sessionId/status/receivedAt`。临时原子文件命名为 `<name>.json.<UUID>.tmp`。恢复时排除凭据、禁止重连、清空待发 pending/active，保留 failed/history/seen 与人工选择的恢复草稿。

## 验证与尚未验证

专项测试只用虚构文字、文件、身份和可注入传输；Windows DPAPI 测试使用虚构密钥，但实际调用本机保护机制。没有访问真实飞书账号、合同或模型。

2026-11-15 专项 27/27 通过；连同复用协议、长连接、批次、凭据和会话测试，Node runner 40/40 通过。旧自执行测试还分别报告 35、29、12、17 个内部检查。完整安装包、浏览器接线、离线与 Windows 总回归由本次发布主流程另行记录。

真实账号的事件订阅、应用发布与资源授权仍须联调。云文档纯文本接口不含图片及完整排版；wiki 中的表格、多维表格和其他类型明确不支持。旧 `doc/v2/:token/raw_content` 路径目前仅有模拟契约测试，官方旧详情页本轮未能读取，须在有权限的真实旧文档上核对。不能把这些测试称为飞书生产验收或法律质量验收。

## 官方核对来源（2026-11-15）

- 文档与纯文本读取：[文档概述](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/docs)、[新版文档纯文本](https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/raw_content)。
- wiki `get_node` 与 `obj_token`、资源授权：[知识库概述](https://open.feishu.cn/document/server-docs/docs/wiki-v2/wiki-overview)。
- 私聊消息事件、消息资源下载、文件上传与发送：[消息概述](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1)、[发送内容结构](https://open.feishu.cn/document/server-docs/im-v1/message-content-description/create_json?lang=zh-CN)。
- 至少一次推送及去重：[事件概述](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide)。
