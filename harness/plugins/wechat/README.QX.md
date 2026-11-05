# AI师兄法律助手平台：本人微信通道

本地入口为 `qx-plugin.js`。它复用 dsh-wechat-media 1.24.13 的 iLink 协议、二维码登录、媒体和持久状态模块；不加载上游 `index.js` / `client.js`，因此不注册其外联、邮件、SSH、剪贴板或群发工具。

## 启用到扫码前

当前工作台已验证可以通过绝对文件入口加载，不需要额外安装本地 npm 包。根配置 `config/cordis.patch.yml` 合并此目录的 patch，由启动器设置独立 DSH home。初始化共用会话使用：

```powershell
node scripts/prepare-wechat.mjs
```

命令在根项目、Harness 启动后执行。它注册当前工作区、创建/恢复固定会话，并通过官方 `Workspace.attachSession` 把原会话加入工作区；不会另建替代会话，不扫码、不提交模型轮次。插件配置如下：

```yaml
- insert:
    - id: qx-personal-wechat
      name: D:/qx-harness-workbench-20261102/plugins/wechat/qx-plugin.js
      config:
        workspace: D:/qx-harness-workbench-20261102/workspace
        stateDir: D:/qx-harness-workbench-20261102/.local/dsh-home/qx-wechat
        sessionId: qx-personal-workbench
        agentPreset: qunxing
        autoConnect: true
```

插件随工作台加载后，打开工作台同一端口的 `/qx-wechat`（例如 `http://127.0.0.1:3080/qx-wechat`）。页面不会自动申请二维码。本人点击“扫码连接”后才访问微信，手机确认后才保存凭据和接收消息。初始安装无账号时不会调用微信或模型。

## 会话与文件

- 默认会话 `qx-personal-workbench` 首次收到本人消息时创建；以后只恢复同一个编号。在桌面历史中打开它即可继续。页面也可在暂停微信后绑定已有桌面对话编号。
- 只有全新绑定且 Harness 明确返回 `SessionPersistenceNotFoundError` 时才首次创建相同编号；已有路由记录后，包括日志丢失在内的恢复错误保持失败，不切换编号、不创建空会话、不重发模型请求。
- 登录响应中的 `userId` 是唯一允许的私聊发送人。没有这个标识就不启用；他人和群消息直接忽略，也不发拒收通知。没有“首个来信者自动获得授权”的路径。
- 附件保存到 `workspace/wechat-inbox/<日期>/<本人>/`，在对话中传本地路径，Python MCP 工具可继续读取。没有产品层面的 100 MB 默认限额；微信平台和本机内存仍有实际边界。上游下载目前整文件缓冲，超大附件不是无限内存流式传输。
- 唯一外发工具 `wechat_send_file` 没有收件人参数，只回传已绑定本人。工作区文件可直接发送；本人明确要求桌面文件时，`wechat_find_desktop_files` 按名称返回最多 30 个候选（不读取正文，支持明确的桌面相对子目录），选定后自动复制到工作区 `wechat-outbound-*` 再发送，原件不改动。桌面位置通过 Windows Known Folders 识别，支持重定向/OneDrive；禁止跟随指向桌面外部的链接及快捷方式。多个匹配先让本人选择，不扫全盘。正文回复使用该轮本人消息的 context token。
- 桌面和微信并行使用同一会话时，回执按准确的 user message id / turn 对应，桌面消息不会被误发到微信。

## 连续消息统一处理（2026-11-03 修复）

接收循环只等待本机附件接收和队列落盘，不再等待模型回答。文字连续静默 8 秒、包含附件的消息连续静默 12 秒后，按原顺序合为一次模型任务。持续来信会重置计时，没有 30 秒强制截断；同一次微信拉取中的全部消息与附件下载完成前不会抢先处理。

“还没发完”“先别处理”“稍等”等明确指令保持收集，直到“发完了”“就这些”“请开始”等明确完成指令才放行；普通“继续”不解除等待。已经开始的任务不被后续消息自动打断，新消息组成下一批，等当前任务结束后处理。使用官方 Agent.whenIdle 等待桌面共用会话空闲，回复超时也不会误以为模型已经结束。

`qx-pending.json` 保存待处理文字、已落盘附件路径、原会话编号及批次状态，不包含微信 token 或媒体解密凭据。收件去重和 cursor 推进在队列落盘后进行。待处理批次重启后继续等待/处理；已派发而未确认结束的批次保留为 interrupted，不自动重发模型或回复，避免重复扣费。同批个别附件接收失败时，成功文字和附件继续处理，未读取项明确交给模型说明并请求补发，不假称完整读取；整批没有任何可读内容才直接提示失败且不调用模型。处理失败保留原批次，并在设置页和状态接口的 `batching` 中显示数量；具体本机记录可按回复中的批次号追踪。暂停接收也会暂停新批次启动，恢复后继续。

这次没有新增 Jev 调用。旧工作台的 Jev 用于意图、材料类型、事项归属及 readiness 辅助；它不能预测尚未送达的消息。此处用确定的收件顺序、静默窗口和用户完成指令解决接收问题，主模型仍统一理解整批内容。

离线验证：`node --test plugins/wechat/test/qx-coalescer.test.mjs plugins/wechat/test/qx-plugin.test.mjs plugins/wechat/test/qx-correlation.test.mjs plugins/wechat/test/qx-collector.test.mjs plugins/wechat/test/qx-stable.test.mjs plugins/wechat/test/qx-owner.test.mjs`。22 项通过，其中 collector 文件另含 5 条内部断言；包含假时钟持续输入、明确等待/完成、附件与正文顺序、在途收件、去重、落盘失败、重启不重发，以及实际薄插件模拟两次拉取、第一轮模型故意不结束时第二批仍能落盘。此次验证没有真实微信或模型请求，生效需要正常重载本机插件。

## 已验证范围

```powershell
node --test plugins/wechat/test/qx-owner.test.mjs plugins/wechat/test/qx-stable.test.mjs plugins/wechat/test/qx-plugin.test.mjs plugins/wechat/test/qx-correlation.test.mjs plugins/wechat/test/qx-collector.test.mjs plugins/wechat/test/login.test.mjs plugins/wechat/test/ilink.test.mjs plugins/wechat/test/media.test.mjs
```

这些测试不联网：虚构 iLink 消息进入真实薄入口，恢复固定会话、去重、忽略他人/群、解密附件落盘、转交路径、把虚构回复发送给固定本人；另覆盖上游登录状态机、媒体、加解密和回执关联。

2026-11-03 已在实际安装的 Harness 0.2.2-alpha.2 上验证绝对入口加载，设置页与状态接口均返回 200；`prepare-wechat.mjs` 实际注册工作区并创建固定会话，重复执行保持同一编号和 0 个模型轮次。没有进行扫码、真实微信消息、真实模型请求。

真实账号是否能通过 iLink 扫码，以及手机响应中本人标识与消息发送人是否一致，要由首次扫码实际确认；错误会显示在此页。此为第三方桥接，不称作 Harness 官方微信插件。

## 来源与许可证

- [dsh-wechat-media 固定提交 feb4088fc36365111d4a5a09ad4407c6e06b7374](https://github.com/wjh-ux/dsh-wechat-media/tree/feb4088fc36365111d4a5a09ad4407c6e06b7374)，MIT，见 `LICENSE`、`THIRD-PARTY.md`。原始源码归档在 `sources/dsh-wechat-media-feb4088.tar.gz`。
- [腾讯 iLink 上游 874637a0dbc24050f72d1385add4fc6170a2d726](https://github.com/Tencent/openclaw-weixin/tree/874637a0dbc24050f72d1385add4fc6170a2d726)，MIT，见 `LICENSE.tencent-weixin`；协议文件中保留上游 attribution。
- qrcode-generator 的 MIT 声明保留于 `vendor/qrcode-generator.mjs`。
- QX 变更：本地包入口、`session.js` 的严格恢复、从上游提取并修复消息关联的 `qx-reply.js`、本人/路径约束、设置页与离线测试。
