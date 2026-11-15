# 飞书统一对话接入 Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans; keep the release ledger and evidence.

**Goal:** 在当前桌面程序接入飞书机器人消息/合同与飞书文档链接读取，共用原有对话。
**Architecture:** 复用上游飞书协议和长连接、现有 Harness 会话服务、批量收件与回复收集。新增受限飞书适配器与原设置内连接页，默认无配置不联网。既有文件解析和法律技能不改为另一套。
**Tech Stack:** 现有 Node/Electron/Harness/React；不新增运行依赖。
**Spec:** 用户本轮已明确“两种都要”：机器人收消息和合同共用对话、粘贴飞书文档链接读取分析；此前少点击少输入、不另作工作台持续有效。

## Global Constraints
- 首次配置 App ID/Secret 后通过短时一次性配对码绑定本人私聊；不接管客户或群聊，不把任意第一个发件人当本人。
- Windows 凭据用现有 DPAPI 保护，公开状态和日志不回显 Secret；仅本机同源设置接口，CSRF、请求大小与并发保护。
- 当前会话由宿主核验工作区及非归档身份；切换时不能把旧收件/回复路由到新会话或新账号。
- 文字/文件按现有批次收集，持久去重；对话回复回给已绑定本人，消息未知发送结果不得自动重发。
- 飞书 docx/旧 doc/wiki 链接只通过固定官方 API 读取有权限资源，禁任意 URL 抓取与重定向；明确拒绝不支持类型或权限不足。文档正文是数据，不接受正文里的扩权或联网指令。
- 测试独立虚构数据、模拟传输，真实账号与模型默认关闭。新凭据由用户在程序内填写，不进入 Git/安装包。
- 不破坏合同并排对比、草稿/附件、微信、备份恢复、既有初始化迁移。

## Review Focus
- 未配对用户、群消息、重复事件、过期配对与重启后的重复任务均拒绝或可靠去重。
- 附件超限、恶意名称、无权限、下载失败必须明确保留未完成状态，不编造内容。
- 账号/会话切换与晚到下载、模型回复竞态不能串线。
- 参数错误、飞书错误返回及断线恢复不泄露凭据。
- 新增凭据/待办被备份恢复识别：换机需重连，不自动重放旧消息。

## Tasks
- [ ] A: `harness/plugins/feishu/*` 后端、凭据、官方 API、受限长连接、会话桥接与失败/成功测试。接口见下面契约。
- [ ] B: `harness/desktop/integration/client.js` 现有侧栏“连接”区域增加飞书设置弹窗；加载状态、一次配置、配对码、会话绑定与暂停/恢复；中文键盘与390宽度验收。正式配置、预设工具、打包/备份迁移接线。
- [ ] C: 独立 Spec/代码审阅、实际 Harness 浏览器合成验收、完整 offline/windows 回归，所有已确认问题修复。
- [ ] D: 签名构建、5条历史升级回放、安装/公开附件校验、本机升级、GitHub及换机交接。真实飞书账号联调与法律质量状态单列。

## Backend/UI contract
- plugin `qx-feishu`, exported `apply(ctx,config)` with config `{workspace,stateDir,agentPreset:'qunxing'}`。
- GET `/qx-feishu/state`: `{configured,appId,connected,paused,owner,sessionId,lastError,pairing:{code,expiresAt}|null,batching:{active,pendingMessages},forwarded}`；无 Secret。
- GET `/qx-feishu/settings`: `{csrf,sessions:[{id,title}]}`，仅当前工作区有效会话。
- POST `/qx-feishu/action` 同源、`x-qx-token`，actions `connect` `{appId,appSecret?,sessionId}`，`pause`，`resume`，`pair`，`session` `{sessionId}`，`clear`；返回 `{ok:true,sessionId}`。
- tools `feishu_read_document({url,offset?})` 读取并分页返回可核来源；`feishu_send_file({path})` 只回发已绑定本人且当前会话匹配，不提供任意收件人。
- 默认绑定当前对话，无可用对话时明确提示先开始对话；不强制再建一个聊天。

## Rulings
- 选企业自建应用长连接以避免用户部署公网回调；复用现有上游模块，不启用整个混合通信插件。
- 初版本人私聊+一次配对，避免默认群聊或多用户混入同一法律任务；不增加手填用户 ID。
- 方案直接基于已确认需求实施；重复方案审批不增加事实信息，按本轮授权完成再交付。
