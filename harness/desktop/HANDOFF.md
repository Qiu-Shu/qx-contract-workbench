# 桌面与 Skill 接入交接（2026-11-03）

首页能力卡片（21:55）：`desktop/integration/client.js` 新增四张业务卡片，走官方 `conversation.input.dock` 和草稿插入接口；悬停放大、移开回弹，点击只填词。已同步当前安装版三份客户端副本，不重启服务。实际安装版独立浏览器验收通过，见 `docs/2026-11-03-首页能力卡片.md` 与 `desktop/checks/20261103-215444-capabilities/report.json`。下次打包需保留当前 integration 源文件。

当前使用官方 Harness 0.2.2-alpha.2 的 Web UI，Electron 44 薄壳入口 `desktop/main.cjs`。
服务地址与临时访问凭据只从 `.local/runtime.json` 读取，不应复制到文档或日志。
用户数据为 `.local/desktop-data`；关闭窗口保留独立后台服务，供微信继续运行。

- `desktop/preload.cjs` 保留官方文件选择、拖放、图片粘贴；只有真实 Ctrl+V 且浏览器未提供 File/文本时，读取 Windows FileDropList，通过原生 file input 进入官方上传。不会轮询剪贴板，不把外部路径伪装成工作区材料。
- `desktop/integration/client.js` 启动只读 `/qx-wechat/state.sessionId`，使用官方 `uiWorkspace.openSession` 选择对应历史；不写微信绑定、不创建历史。已有页面的热加载不强制切换当前会话。
- 菜单有“手机微信”“打开材料文件夹”和“关闭窗口（微信继续运行）”；`--wechat` 只打开同一微信管理窗口，不自动扫码。
- 上传副本位置由根配置的 `attachment-local.dshHome=workspace/inbox/.harness` 决定。UI file input 无扩展名 accept 限制；BMP/TIFF 作为普通文件上传。容量由根配置管理，不在薄壳添加旧配额。
- Word 成果使用官方“用 WPS Office 打开”按钮，真实本机打开已通过。当前未安装可选 LibreOffice 渲染包，因此内嵌 Office 预览会显示不可用，不能宣称内嵌预览成功。

验收证据均为合成材料，未发送额外模型消息：

| 项目 | 结果与位置 |
| --- | --- |
| 文件选择、资源管理器文件 Ctrl+V、位图 Ctrl+V | `desktop/checks/20261103-111817/report.json`；三个实际上传 200，图片已解码 |
| 已生成 Word 成果打开 | `desktop/checks/20261103-112616-output/report.json`；匹配到 WPS 合成文档窗口 |
| 跟随已持久化微信会话启动、拖放 | `desktop/checks/20261103-113438/report.json`；使用真实 File/DataTransfer drop，实际上传 200，附件卡可见，无页面错误 |

Skill 部分：`scripts/prepare_legal_skills.py` 保留两套原始库与许可证，生成 18 个领域入口、157 个唯一中文技能；引用路径和完整正文按需加载。`scripts/check_legal_skills.mjs` 用真实官方 FileSystemSkillProvider 验证发现 175 项，并加载一项合同审查完整正文与引用。证据 `docs/checks/legal-skills/report.json`。这不等于逐项跑过 157 个模型任务。

用户已在真实主窗口处理合同。后续不要为验收重启服务、关闭窗口或切换真实会话；如需重复桌面验收，现有 `check_ui.py` 会先只核启动会话 ID，然后切至既有合成会话才操作附件。`--drop-only` 仅运行拖放检查，不改剪贴板。脚本使用独立隐藏 Electron 数据目录。

## 侧栏精简与余额（11:56 更新）

用户确认先用“群兴”文字标识。`desktop/integration/client.js` 覆盖官方 `sidebar.brand.mark/name`、`conversation.hero.brand.mark` 和 `settings.launcher` 插槽；上方全局导航仅通过官方 `data-slot="sidebar"` / `sidebar.panellist` 锚点隐藏，不匹配文字、哈希 class 或修改 node_modules。新会话、工作区、会话列表、收起侧栏和设置快捷键的原模块保持。

左下使用 `sidebar.footer.action` 显示“DeepSeek 余额”，读取已认证同源 `/api/qx-account/balance`。可见时每分钟更新，手动刷新追加 `?refresh=1`，服务端负责缓存。金额保持接口字符串及币种；初次失败不显示金额，刷新失败保留上次金额并注明，已取消配置则清空金额。当前真实 CNY、USD 均已显示，真实零值可正常展示。

- 完整隔离 UI 验收：`desktop/checks/20261103-115345-chrome/report.json`，含真实余额及明确标注的模拟状态验证。
- 根重启服务后的新凭据实际快检：`desktop/checks/20261103-115555-chrome/report.json`、`actual-account-sidebar.png`。无模型调用、无模拟余额，记录了当次 host PID。
- `impeccable context` 已针对当前项目运行；完成后 detector 返回空问题数组。JS 语法检查通过。
- 无额外 profile 改动要求；余额服务挂载由根完成。用户主窗口更新请在空闲时用菜单“工作台 → 重新连接”，该操作读取新 runtime URL；不要只用旧页面普通刷新。若有未发送输入，先保留草稿。未主动操作用户窗口。

## 微信连接弹窗（13:24 更新，替代 12:36 网页入口）

`desktop/integration/client.js` 在原 `sidebar.footer.action` 底部组件内，将“微信连接”放在 DeepSeek 余额正上方。展开显示文字，收起显示手机图标并保留可访问名称与提示。现在是按钮，打开同页原生 dialog，不跳网页。会话名称下拉支持切换和新建绑定；重新扫码可切换微信，取消后可恢复原连接。`desktop/main.cjs` 的菜单和 `--wechat` 通过 `qx-open-wechat` 打开同一弹窗。打开本身不扫码、不修改绑定。

`desktop/check_wechat_entry.py` 与 `desktop/check_wechat_dialog.py` 使用独立无头 Chrome，余额、微信状态、会话和二维码使用明确的合成数据。证据：`desktop/checks/20261103-131930-wechat-entry/report.json`、`desktop/checks/20261103-132346-wechat-dialog/report.json`。覆盖入口位置、会话切换和新建、扫码取消恢复验证码、菜单事件、错误、焦点约束及返回、侧栏收起和窄屏；无真实微信操作。JavaScript 语法检查、微信相关测试和 Impeccable JS 静态检测通过。

本次更新了微信插件，并在所有会话和微信队列空闲时重载当前开发服务，实际 `/qx-wechat/settings` 返回 200，原微信连接恢复。现有窗口保留草稿后“重新连接”即可加载左下弹窗；菜单逻辑需重开桌面壳。未重新构建安装包。详细行为、持久化和验证见 `docs/2026-11-03-微信连接弹窗.md`。
