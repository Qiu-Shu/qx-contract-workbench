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

后台意外退出后，独立监督进程按 1、3、10 秒间隔最多重试三次，稳定五分钟后恢复重试额度。
启动超过两分钟仍未就绪会结束该子进程并记录原因。桌面每三秒检查后台；监督进程也退出时，
桌面最多重新启动三次。后台存活但检查失败时只提示断线，不强杀正在执行的任务。
主动停止、安装更新及保存密钥期间不会自动拉起；关闭桌面仍保留微信后台。

窗口中的状态条显示断线、恢复或失败，不自动刷新页面、发送消息或重放中断任务。
用户点击重新连接后会提醒先复制草稿。连续失败时可手动重试；更新后的后台身份即使在两次检查之间变化，也会显示重连提示。

“工作台 → 打开运行日志”打开用户资料目录的 `.local`：
`host-events.jsonl` 记录后台启动、退出码、信号、重试及主动停止；`desktop-events.jsonl` 记录桌面退出、连接状态和渲染进程退出。
每个日志超过 1 MiB 后轮换，仅保留当前文件和一个 `.1` 备份；不记录对话、密钥、访问令牌或原始错误对象。
操作系统强制结束整个进程时进程自身可能来不及写日志，此时桌面仍运行的话会记录观察到的退出和恢复。

验证：`node --test desktop/*.test.cjs`；`desktop/check_recovery_ui.py` 检查提示和草稿；
`desktop/check_recovery_electron.py` 在隔离数据目录用合成 HTTP 后台注入真实进程故障，不使用用户密钥或发送模型请求。
