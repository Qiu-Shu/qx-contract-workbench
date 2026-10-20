# CH-06B2a 前端证据

2026-10-20。此目录只包含可共享源码、独立合成验证日志和截图；没有运行数据库、原件、真实账号、密钥、安装产物或浏览器缓存。测试脚本的 `fixture123` 是专门创建的合成用户密码，不是任何现有用户凭据。

## 命令与实际结果

工作目录：`D:\Documents\ChatGPT\律所项目`。

```powershell
node --test scripts/test_assistant_state.mjs scripts/test_assistant_material_state.mjs scripts/test_assistant_material_dom.mjs scripts/test_assistant_generation_state.mjs scripts/test_assistant_generation_render.mjs scripts/test_assistant_generation_entry.mjs scripts/test_assistant_transport_input.mjs scripts/test_assistant_research_state.mjs scripts/test_assistant_citations.mjs
```

[Node 原始输出](frontend-node-final.log)、[退出码](frontend-node-final.exit)：55 个顶层测试，55 通过、0 失败、退出码 0。其中三个旧脚本内分别包含 36 个生成状态组、28 个草稿状态检查、4 个材料状态组；不将嵌套组数与顶层数量相加。新增本机研究10项、引用/渲染8项计入55项。

```powershell
.venv/Scripts/python.exe -X utf8 .local/library-chat-20261020/frontend_browser.py .local/library-chat-20261020/frontend-browser-final
```

[浏览器脚本副本](frontend-browser.py)、[最终报告](frontend-browser-final/report.json)：真实源码 FastAPI、独立合成 SQLite 法规库、真实 Chromium，8 组检查通过，进程退出码 0。产生3条回执、2条引用；主模型 attempt/output、Jev attempt 均0，外部请求0，浏览器错误0。已退出进程，没有保留后台任务。脚本副本与当时执行脚本字节一致，重新运行应指定一个**不存在的新合成输出目录**；此文没有再次运行它。

[桌面 1366×900](frontend-browser-final/desktop-saved-citation.png)、[窄窗 390×844／20px](frontend-browser-final/narrow-large-citation.png)、[小窗 800×600／20px](frontend-browser-final/small-window-results.png) 已逐张读取检查：文字可读，无横向溢出；引用按纯文本显示，键盘打开/关闭恢复焦点，切换后清空。

## 失败记录与修复范围

- [状态测试 RED](frontend-state-red.log)：接线前10项中8项断言失败、2项通过。第一次 PowerShell 包装命令随后读取日志末尾而最终返回0，故只把 Node 失败输出视作 RED，不把包装退出码视作测试通过。
- [首次浏览器报告](frontend-browser-first-report.json)：标题命中返回标题片段，脚本却错误断言片段含查询词；修改独立合成文件名使关键词只命中正文。产品行为未因这个错误预期而改变。
- [第二次浏览器报告](frontend-browser-second-report.json)：实际查询、离线回查、不可用和空命中已通过；800×600窗口的大输入区遮挡历史按钮，点击超时。修复为来源面板开启或窗口高度≤800时采用自然滚动，最终报告8组全部通过。
- 旧生成回归曾暴露 refreshGeneration 的 async 包装改变在途 Promise 身份，修复后全部36组通过；最终日志保留结果，不伪造未单独保存的失败日志。

## 机械检查及证据边界

```powershell
C:/Users/Administrator/.codex/skills/impeccable/scripts/impeccable.cmd detect --json src/cn_contract/web/static/assistant.css src/cn_contract/web/templates/assistant.html src/cn_contract/web/static/assistant-render.mjs src/cn_contract/web/static/assistant-citations.mjs
```

[检测输出](impeccable-detect.json) 为 `[]`，[退出码](impeccable-detect.exit) 为0。只执行一次，发生在最终5行响应式CSS修复之前；不声称机械检测或此前Node运行覆盖最后CSS，最后布局由真实浏览器确认。Node状态/渲染脚本及JavaScript在最后CSS修复后未再变化。

[前端冻结摘要与完整Node命令](frontend-freeze.json)、[代理复核记录](frontend-review.md) 记录来源。冻结摘要是本阶段时点证据，不代替仓库最终整体摘要。

本轮未验证安装版、冻结包、真实法库、真实模型、物理中文输入法或操作系统显示缩放。中文组合输入通过浏览器合成事件检查。已保存引用是有界历史片段，不能称保存全文或确认现行法效力。本文件不代表后端整体审计、备份验收或生产通过。
