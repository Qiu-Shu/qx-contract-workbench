# 群兴桌面窗口

复用已安装的 Electron 44 与官方 Harness Web UI，无上游源码构建。
入口是 `desktop/main.cjs`。默认读取 `.local/runtime.json` 的 `url`（含本机临时访问凭据，不输出到日志）；
也支持 `QX_HARNESS_URL`。桌面独立数据在 `.local/desktop-data`，与旧工作台隔离。

`desktop/integration` 是官方客户端插件包 `@qunxing/desktop-session`。
由运行配置加载后，它只读 `/qx-wechat/state` 的 `sessionId`，再用官方
`ctx.uiWorkspace.openSession(sessionId)` 打开当前微信共用事项。用户仍可切换其他会话；
插件不会写微信绑定、创建同名历史或在热载时切换正在工作的窗口。host 应预先 prepare 此会话。

附件选择、拖入和图片粘贴沿用官方上传与附件卡。
桌面不暴露把外部文件转为 `@绝对路径` 的 `__DSH_HOST_PATHS__`，以便上传副本进入工作区。
运行配置的 attachment-local.dshHome 应指向 `workspace/inbox/.harness`。
资源管理器文件粘贴优先使用浏览器原生 File；只有真实粘贴事件没有提供 File/文本时，
才读取 Windows FileDropList 并交给当前会话的文件输入控件。不会启动时或轮询读取剪贴板，
不会先把整个文档读入 JavaScript 内存，也不自动发送消息。

Windows 文件夹不作为单个附件上传；文件原件保持不变。
关闭窗口只退出桌面，已启动的 Harness host 仍可为微信服务。
