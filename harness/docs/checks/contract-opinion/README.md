# 意见书与默认批注合成核验

日期：2026-11-03。所有意见、条款和合同均为合成数据，未调用模型或外网，也未打开真实客户合同进行写入。

## 交付接口

```python
from contract_opinion import write_contract_opinion

write_contract_opinion(workspace, filename, title, subtitle='', sections=None)
```

`workspace` 可为当前 `MaterialStore` 或工作区路径。`filename` 接普通文件名基名，也可带 `.html`／`.docx`，统一按基名输出到 `drafts/`。已有文件一律保留，同名另存。

每个 section 支持：

- `heading`：章节标题，可为空。
- `paragraphs`：文字列表，按顺序完整写入。
- `table`：可选 `{headers: list[str], rows: list[list[str]]}`。每行与表头列数一致；四列表格采用风险表列宽。
- `subsections`：可选章节列表，结构相同，可用于替换条款标题及正文。
- `references`：可选 `[{label, url}]`，只接受完整 HTTP(S) 链接。标签和所有正文按纯文本转义，不能注入脚本。

章节数与正文长度没有固定门槛，不校验或生成法律结论。结构不匹配、非法链接等明确报错，不丢弃多余单元格或默默截断内容。

返回 `status`、`html`、`word`、`html_path`、`word_path`、`counts`、`notice`。其中 `html`／`word` 均含 `path`、`relative_path`、`bytes`、`sha256`；`counts` 包含所有层级的章节数、正文段数、表格数、数据行数和链接数。

## 参考版式边界

仅从用户指定的 `慧仁学校技术服务合同乙方审查意见.html` 提取 CSS 和标签布局。保留 1050px 阅读幅宽、浅灰背景、白纸、蓝灰标题、宽松字号行距、四列风险表、响应式和打印样式。不复制其中的真实客户事实、法律结论、旧日期、审计声明和浏览器注入的 Bing blob 样式。原文件摘要记录在 `reference-layout.json`，原件未写入。

Word 与 HTML 使用同一份经过结构检查的正文。Word 的普通短表格行尽量同页，较长行允许跨页，表头在续页重复；没有逐项强制分页或定长截断。

## 实测证据

最新全套 `pytest -q`：**140 passed，21 subtests passed**。意见书专项 12 项通过，覆盖 HTML/XML 转义、八种恶意或非法链接、长 Unicode 正文、完整表格与子章节、原件与同名文件保护，以及错误结构不静默丢弃。

使用独立无登录 Chrome 无头实例检查本地生成 HTML，未打开个人浏览器会话、未发生 HTTP(S) 请求。桌面主体实测 `max-width:1050px`，脚本节点数为 0；390px 手机视口无整页横向溢出，四列表在自身容器内滚动。桌面、手机与打印页面均已截图检查。

使用独立隐藏 Microsoft Word COM 实例只读打开 DOCX，禁用宏、不写入最近文件、不启用修复；导出 PDF 后关闭本实例。每份 DOCX 打开前后 SHA-256 相同。

| 样稿 | 实际结果 |
|---|---|
| `drafts/synthetic-opinion.html` / `.docx` | 普通意见书。Word 2 页，HTML 打印 2 页；四列表、章节与来源链接正常 |
| `drafts/long-flow.html` / `.docx` | 长段落与长表格。Word 连续 6 页，末项完整；去除 PDF 提取中的重复表头后，70 段合成重复语句全部匹配 |
| `default-comments-source.docx` | 本次新建的普通合成合同原件，生成前后字节不变 |
| `drafts/default-comments.docx` | 不传 mode，使用新的默认批注模式。Word 实测 2 个批注、0 个修订；正文逐段与原件相同，两处建议均只出现在批注中 |

Word PDF 共 9 页，HTML 打印 PDF 2 页，全部转换 PNG 并逐页视觉检查，未见裁切、乱码或文字重叠。长表格可跨页且重复表头，短行保留同页。

`manifest.json` 为样稿返回值和原件保护结果；`word-render-check.json` 记录 Word 页数、批注数、修订数和摘要；`browser-check.json` 记录桌面／移动页面尺寸和请求记录；`content-check.json` 记录导出 PDF 内容完整性；`render-pages.json` 为页面图记录。PDF、PNG 均为核验材料。

未实测 WPS、其他平台字体及实际案件意见的法律正确性。样稿通过不代表传入正文已完成事实或法律审校；真实内容质量由主流程按授权材料形成。
