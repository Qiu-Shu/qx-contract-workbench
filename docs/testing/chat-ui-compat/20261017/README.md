# CH-02 Deep Chat 与原生输入兼容性实测

日期：2026-10-17；仅隔离目录、本机合成页面及假处理器。没有改产品/测试/依赖清单，没有访问真实资料或模型。项目继续使用已批准的 Jinja + 分文件 JS 路线；此结果是选型证据，不是 CH-02 产品交付。

## 决策

**首版维持原生 textarea + 本地通用消息渲染库方案，Deep Chat 保留候选。** 不是因为 Shadow DOM 必然违反 CSP：当前 Chromium 实测核心功能和构造样式表可用。Deep Chat 可通过少量适配解决本次输入问题，但没有替代本项目必须拥有的会话范围、持久草稿版本、失败/重连/去重状态；默认输入恢复又需要协调其内部消息历史。尚未证明显著减少状态代码，因此当前没有充分理由新增另一套呈现状态。

原生对照只验证输入与假发送，没有重写 Markdown 解析或流协议，不能按其短脚本推断完整聊天 UI 已完成或总维护成本已被精确测量。

## 制品与来源

- NPM `deep-chat@2.5.1`：https://registry.npmjs.org/deep-chat/-/deep-chat-2.5.1.tgz
- `package/LICENSE` 为 MIT，保留版权。tarball 的 registry SHA-512 integrity 与 SHA-1 均实际校验通过。
- 自托管浏览器 bundle：386,971 bytes，SHA-256 `6844eaf354e19d50dcdd8ee78968d6ae32ccd4b9f15a883902d60e93d69caf84`。
- 设计固定源码：https://github.com/OvidijusParsiunas/deep-chat/tree/1a79d507a94c3b8799e7a872b7e4afc2cad55cea
- NPM 声明 gitHead 为 `2168c8fd227b853097c8340942e57ddcc9f6e4cb`，**不同于设计固定提交**。本次运行结果只对实际下载的制品成立。另逐字节核对两提交的 textInput.ts、submitButton.ts、googleFont.ts，三文件相同；未声称完整提交或构建产物一致。
- 官方自定义连接说明：https://deepchat.dev/docs/connect/ 。实际用本地 `connect.handler`，无网络模型请求。
- `provenance.json` 保存具体 URL、大小和 SHA-256，`artifact-verification.json` 保存完整性与三文件比较。

## 运行环境与观察

使用项目已有 `.venv` Playwright + `.local/scrapling/browsers/chromium-1243/chrome-win64/chrome.exe`，浏览器版本 153.0.8010.12，headless。服务器只绑定随机 127.0.0.1 端口。实际响应 CSP：

```text
default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
```

| 项目 | 默认组件实测 | 少量适配实测 | 原生对照实测 |
|---|---|---|---|
| CSP 样式/JS | 可渲染；1 个 adopted stylesheet；无 JS 异常 | 可渲染；2 个 adopted stylesheet；无 JS 异常 | 外链本地 CSS/JS 正常 |
| 外部请求 | 尝试 Google Fonts，CSP 阻断，未加载外部字体 | 显式 `chatStyle.fontFamily` 系统字体后 0 外部请求、0 CSP 违规 | 0 外部请求、0 CSP 违规 |
| Enter / Shift+Enter | 发送 / 换行均符合 | 同左 | 同左 |
| 点技能保留文字 | 保留，未发送 | 保留，未发送 | 保留，未发送 |
| 失败保留草稿 | 输入立即清空，失败文字仍存在消息区 | 由应用设置 history + defaultInput 后文字和历史均恢复 | 输入仍为失败前文字 |
| 仅 defaultInput 恢复 | 文本恢复，但现有消息历史被清空 | 先同步 history 可避免历史消失；仍是组件重呈现 | 不需要重呈现 |
| compositionstart 后 Enter | 不发送 | 不发送 | 不发送 |
| compositionend 后 isComposing=true/keyCode=229 Enter | 意外发送 | 应用捕获守卫阻断 | 自有守卫阻断 |
| 只有 isComposing=true Enter | 意外发送 | 阻断 | 阻断 |
| repeat=true Enter | 意外发送 | 阻断 | 阻断 |
| 辅助功能树 | 可穿透 Shadow DOM 找到具名 textbox；发送按钮无名称 | 同左，尚需配置/修补发送按钮名称 | textbox 与发送按钮均有明确名称 |

Deep Chat 默认 localStorage/sessionStorage 均为空（未启用持久浏览器存储）。失败默认 console.error 输出传入错误字符串，本试验仅合成错误；真实接线必须使用白名单错误文案，不能直接输出模型/接口异常正文。

## 证据与复现

- `report.json`：默认组件 9 组观察；`probe-default.log`、`deep-chat-csp.png`。
- `report-adapted.json`：系统字体/捕获守卫/历史同步 9 组观察；`probe-adapted.log`、`deep-chat-adapted-csp.png`。
- `report-native.json`：原生 8 组观察；`probe-native.log`、`native-csp.png`。
- `verify_reports.py`：12 项结果断言通过。它确认观察结果（包括默认缺口），**不是宣布默认组件满足全部需求**。
- 首次试验脚本错误地按 classic script 加载 ES module，产生 export 语法异常；记录保留在 `report-first-harness-error.json`。改为标准模块导入后重新运行成功，此项不归咎组件/CSP。

本目录保留结论、来源清单和三个合成观察报告；未将下载制品加入产品。复现脚本、原始日志、截图及 npm 解包内容仍在忽略目录 `.local/chat-ui-compat-20261017`。以下命令只有本机保留该试验目录时可用，不能声称克隆仓库即已附带完整实验环境。

证据摘要对应本机原始文件字节；Git可能规范化所附文本副本的换行，不能将规范化副本直接当作原始字节核验。

在仓库根目录依次运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 .local/chat-ui-compat-20261017/probe.py
.\.venv\Scripts\python.exe -X utf8 .local/chat-ui-compat-20261017/probe-adapted.py
.\.venv\Scripts\python.exe -X utf8 .local/chat-ui-compat-20261017/probe-native.py
.\.venv\Scripts\python.exe -X utf8 .local/chat-ui-compat-20261017/verify_reports.py
```

## 未覆盖与限制

- IME 为实际浏览器接收的合成 composition/keydown 事件，未操作 Windows 物理中文候选窗；不能代替完整中文输入法实机验收。
- 未验证附件保留、附件类型限制、案件切换、流式恢复/取消、焦点/光标在重呈现后的保留、屏幕阅读器读出、Electron 版本差异或旧浏览器构造样式表回退。
- 默认组件失败清空与输入法边界已实测；不等于这些问题无法适配。设置 defaultInput 发生重呈现，进一步适配还需保护新输入版本和附件。
- 未做深度依赖/供应链安全审计；仅运行固定制品并记录 MIT/完整性，不将其纳入产品。未增加安装包大小、启动时间或内存改善的虚假数字。
