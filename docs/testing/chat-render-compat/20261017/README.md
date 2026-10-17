# CH-02 本地 Markdown 浏览器制品准备

本仓库证据目录保留说明、制品清单、观察报告与证据摘要。下载制品、许可原文、复现脚本及截图仍在忽略目录`.local/chat-render-compat-20261017`；本次没有将它们纳入产品或安装包。

证据摘要对应上述本机原始文件字节；Git规范化文本副本换行不应被冒称原件仍逐字节相同。正式采用的浏览器JS仍须按原始制品摘要核对。

仅在隔离目录完成下载、许可/摘要核对和合成浏览器验证。没有改 src、tests、依赖清单、安装版或业务工作区；没有调用模型或处理真实资料。**这不是本产品已采用、CH-02 完成或全面安全审计。**

## 确定候选

2026-10-17 通过官方 NPM registry 的 `/latest` 核对当时稳定版本（均无预发布后缀），随后固定下载版本 tarball。不是沿用旧版本号：

| 包 | 稳定版本 | 本地浏览器制品 | 字节 | 许可 |
|---|---|---|---:|---|
| markdown-it | 15.0.3 | `markdown-it/dist/browser/markdown-it.umd.min.js` | 100,786 | MIT；内嵌依赖另保留许可 |
| DOMPurify | 3.4.17 | `dompurify/dist/purify.min.js` | 29,828 | MPL-2.0 OR Apache-2.0；建议采用 Apache-2.0 选项，原 LICENSE 已取得 |

两浏览器脚本合计 **130,614 字节**，不需安装 Node 生产依赖，不需动态 import/CDN。不能据此直接推算最终安装包变化。

主制品 SHA-256：

- markdown-it：`391f2aa638e75e6c7859d0a5c5650ef0956722a45998f17e05b83bc655778e1e`
- DOMPurify：`cd37898f9782adf54820c413191b5691803f0f137c799d6edcfd38523b4c2c31`

两个 tarball 都实际匹配 registry SHA-512 integrity 与 SHA-1；`manifest.json` 保存 URL、gitHead、大小、完整摘要及原始 registry integrity。摘要匹配确认下载内容对应 registry 声明，不等于独立验证发布者签名或全面供应链审计。

### 浏览器入口不能沿用旧版路径

markdown-it 15.0.3 没有旧版 `dist/markdown-it.min.js`。实际 package exports 的 `./browser` 对应上述 UMD 入口（ESM 另有文件，此次未采用）。浏览器验证使用普通本地 `<script defer src=...>`，全局 `window.markdownit` 和 `DOMPurify` 正常存在。

### 内嵌依赖许可

markdown-it 浏览器 bundle 已包含依赖，不需单独加载，但许可不能漏记。根据该 NPM gitHead `a8c00d474ec9b304fad9b71c16d6fa8b4909279e` 的 package-lock 和浏览器 source map 核对：

| 内嵌依赖 | 固定版本 | 许可 | source map 对应源文件相同数 |
|---|---|---|---:|
| entities | 8.1.0 | BSD-2-Clause | 5 / 5 |
| linkify-it | 6.1.0 | MIT | 1 / 1 |
| mdurl | 2.1.0 | MIT | 5 / 5 |
| punycode.js | 2.3.1 | MIT | 1 / 1 |
| uc.micro | 3.0.0 | MIT | 1 / 1 |

五个依赖 tarball 都匹配固定 lock 中 integrity；已保存许可到 `bundled/<包名>/LICENSE*`。对应的 13 个 source map 源文件与 tarball 内容逐字节一致。Argparse 属命令行入口，未见于浏览器 source map，不纳入本次浏览器制品。DOMPurify LICENSE 是完整 Apache-2.0 文本，保留现有制品头部双许可声明，不修改上游脚本。

## 真实运行结果

已有 Playwright + 项目 Chromium 153.0.8010.12，headless，740 × 700 视口；HTTP 服务仅绑定 127.0.0.1 随机端口。严格使用当前项目 CSP：

```text
default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'
```

Markdown 固定配置 `html:false, typographer:false, linkify:false`。解析后交给 **DOMPurify 自身**处理；没有编写自有净化器。试验限制允许标签为段落、标题、强调、列表、引用、代码、表格和链接；允许属性为 `href/title/start/align`，禁用 data/aria 属性扩展；返回净化后的 DocumentFragment，再用 `replaceChildren` 放入展示区。img/svg/script/iframe、事件和 style 属性不在白名单中。完整配置见 `fixture.js`。

13 组合成检查通过，进程退出码 **0**：

1. 正常中文、标题、强调和列表保留。
2. 原生 HTML/script/img/svg 按原文字符显示，不生成活动节点。
3. javascript 链接及实体混淆没有活动 href。
4. vbscript 链接没有活动 href。
5. data:text/html 链接没有活动 href。
6. file 链接没有活动 href。
7. Markdown 远程图片最终无 img 节点，也未请求图片。
8. Markdown data 图片最终无 img 节点。
9. 裸 URL 保持文本，未自动 linkify。
10. 原话引号、(c)、省略号、连字符不被 typographer 改写。
11. 明确 HTTPS 链接与页内锚点保留 href；**只观察 DOM，没有点击导航**。
12. 中文表格及 2500 字符长 URL 保留；在此次视口没有整页横向溢出（配合本地 CSS 表格容器滚动与正文换行）。
13. 直接调用 DOMPurify 的额外纵深检查移除活动脚本、图片、SVG、iframe、onclick 和 javascript href；此项明确不冒充模型 Markdown 正常通路。

所有样本执行计数为 0，0 JS 错误、0 CSP 违规、0 外部请求尝试；实际 network 只有首页、本地 CSS、本地试验 JS 与两个本地库脚本，共 5 项。localStorage/sessionStorage 均为空。样本中的 `example.invalid` 只是合成链接/图片地址，没有发出网络请求。

## 产品接线边界

- 净化后保留 HTTPS href **不代表桌面已支持点击外链**。主任务核对当前 `desktop/main.cjs:173-175` 对新窗口全部 deny，导航仍限制本机同源 http/setup，也没有 shell.openExternal；本试验没有改变或验收导航策略。
- 原文引用应由后端受控资源 ID/版本生成，不能信任模型自行生成的文件路径或原件 URL。外部链接点击、提示和打开策略留给产品接线处理。
- 服务权限、跨案件隔离、消息版本、流取消/重连等不是净化库职责；仍需既有业务状态和接口适配。
- 本次是限定合成样本，不代表枚举所有 XSS/浏览器漏洞。未测 Electron 实装、其他浏览器或全部极端 Markdown 规模；正式接入后仍需目标集成测试和最新安全通告核对。
- 主代理另查看实际长URL截图：虽然没有整页横向溢出，首列已收窄到中文逐字换行。因此本次只证明容器边界，没有证明表格阅读体验达标。产品样式需保留可读列宽并在表格区域横向滚动，不能把无整页溢出当作视觉验收通过。

## 最小正式采用登记

正式采用时仅需把以下内容纳入既有 vendor/source/runtime 绑定机制，保持当前原生前端框架：

1. 两个上述浏览器 JS 原字节文件（固定版本与 SHA-256，不从 CDN 加载）。
2. markdown-it 主许可、DOMPurify 的 Apache-2.0 LICENSE，以及五个内嵌依赖许可，共 7 份许可；保留上游版权与制品头部声明。
3. 一份本项目来源清单：两个 npm 包的版本/tarball/integrity/gitHead/制品 hash、五个内嵌依赖的版本与许可，以及实际纳入文件路径。
4. 现有页面自己的窄渲染适配与目标测试：固定上述 Markdown 配置及允许标签/属性；不要直接把模型输出写入 innerHTML，不要在净化后增加未核对 HTML。

Source map 与 tarball 可留开发证据；无需放入安装包。若删除 source map 的注释来减少开发者工具 404，应记录为本地改动并另计 hash，本次原始制品未修改。

## 来源与证据

- [markdown-it registry latest](https://registry.npmjs.org/markdown-it/latest)
- [DOMPurify registry latest](https://registry.npmjs.org/dompurify/latest)
- [markdown-it 固定提交](https://github.com/markdown-it/markdown-it/tree/a8c00d474ec9b304fad9b71c16d6fa8b4909279e)
- [DOMPurify 3.4.17 发布](https://github.com/cure53/DOMPurify/releases/tag/3.4.17)
- `manifest.json`：制品与许可来源、完整性结果、内嵌依赖核对。
- `report.json`：13 组每项 DOM/文本/href/执行计数，以及全部 network URL、CSP 和浏览器版本。
- `probe.py`、`fixture.js`、`index.html`、`fixture.css`：可复现实验。
- `table-long-url.png`：长链接表格截图。
- `evidence-manifest.json`：证据文件摘要与实际退出码。

复现：在仓库根目录用已有 `.venv/Scripts/python.exe -X utf8 .local/chat-render-compat-20261017/probe.py` 运行。无需新安装依赖或启动业务应用。
