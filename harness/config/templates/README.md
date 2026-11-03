# 文档交付接口与模板来源

`bridge/docx_delivery.py` 独立实现文档函数，由业务 MCP 接线，不依赖旧项目的审批、数据库或合同审查架构。输出统一保存当前工作区 `drafts/`，同名文件另存；临时文件写完并验证 XML 后才发布，不覆盖原件。

## 原合同上的修订与批注

```python
inspect_docx(workspace, source, offset=0, limit=100)
write_review_docx(workspace, source, filename, edits, author='律师', source_sha256='', mode='comments')
```

`workspace` 为当前 `MaterialStore` 或工作区路径。`source` 只能在工作区内。先 inspect，按 `next_offset` 继续获取段落。每段含 `paragraph_id`、`text`、`location`、`editable`、`unsupported`。编号由段落顺序和原始段落 XML 摘要组成；用于当前原件，不能自行拼接。正文和常见表格段落都会列出；文本是可见文字视图，既有删除文字不混进编辑锚点，没有执行“接受全部修订”。

推荐将 inspect 的 `source_sha256` 原样传回 write，原件版本改变就拒绝输出。每条 edits 为：

```json
{"paragraph_id":"来自inspect的编号","old":"该段内唯一原文","new":"建议文字","comment":"修改理由"}
```

`old` 必填、非空且在指定段落中唯一；跨 run、多个文本节点、XML 特殊字符均按解码后的原文定位。默认 `mode='comments'` 保留正文，`comment` 写理由，`new` 写建议替换文字；空字符串new表示在批注中建议删除，不实际删除。只有用户明确要求修订正文时用 `mode='tracked_changes'`，此时new才写入正文的插入/删除修订。省略new只添加批注。相互重叠的修改全部退回，其他有效项继续输出。新批注追加到原批注部件，已有批注、修订和未修改部件保留；新 ID 从原文件已用数字 ID 之后分配。不会强制打开持续追踪修订开关。

返回 `status=draft/partial/not_written`、`applied`、`failed`、逐条 `results`。每个结果保留提交的 `edit`；失败含明确 `reason`，便于把未落入原文的建议继续展示。没有成功项时不产生文件；有成功项才返回绝对 `path`、`relative_path`、输出 `sha256`。部分完成不能作为全部成功展示。

暂不自动编辑包含既有文字／格式修订、域、超链接、图片、文本框、内容控件等复杂对象的段落，也不跨批注／书签范围边界修改。页眉、页脚、脚注、尾注作为原包内容保留，列入 `uneditable_parts`。数字签名文档拒绝修改。对这些情况应提供原建议和未应用说明，不能声称全合同已修订。该函数不实现接受修订、自动脱敏或删除原批注。

没有固定文件大小或页数门槛。因为 OOXML 修订需整体装入内存，处理前按 `reader.available_memory()` 的当前可用内存估算文件与解压部件容量；内存不足明确说明原件保留和释放内存后重试。重复 ZIP 部件、实体及异常 XML 会拒绝处理。

## 合同审查意见书

`write_contract_opinion(workspace, filename, title, subtitle='', sections=None)` 使用同一份正文生成HTML阅读版与可编辑Word版。MCP接口为 `write_contract_opinion(filename, title, sections, subtitle='')`。

章节使用heading、paragraphs，可选table（headers/rows）、subsections、references（label/url）。四列风险表采用“优先级、位置及原文、问题与影响、我方建议”。章节和字数不设固定门槛；未知字段与不匹配的表格结构明确返回原因，不截断有效正文。同名另存，返回两个实际路径。

布局沿用用户认可的浅灰背景、白纸、蓝灰标题及宽松行距；正文来自本案分析，不复用参考文件的客户事实。见 `docs/checks/contract-opinion/README.md` 的真实Word、移动屏幕和打印核验。

## 诉状与证据目录

```python
list_templates()
generate_template_document(workspace, template_id, filename, data, author='')
```

`list_templates()` 返回 `templates` 列表。模板 ID：

| 模板 ID | 内容 |
|---|---|
| complaint-sales | 买卖合同欠款起诉状 |
| complaint-service | 服务合同欠款起诉状 |
| complaint-loan | 民间借贷起诉状 |
| complaint-inheritance | 遗产继承起诉状 |
| evidence-sales | 买卖合同证据目录，段落版 |
| evidence-construction | 建设工程证据目录，段落版 |
| evidence-table | 证据目录，表格版 |

起诉状 `data`：`parties`、`claims`、`facts` 为必填非空文字列表，支持任意数量和长文本，按列表顺序逐项写入；`court`、`signature`、`date` 缺失时写明确待补标记并返回警告。`parties` 自带身份标签，例如“原告一：合成甲”，可加入多原告及代理人等任意当事人段落。可选 `title`。

证据目录 `data`：必填非空 `evidence` 列表，各项 `name` 必填；`content`、`purpose`、`page_range`、`source` 为文字。证据数量决定段落／表格行数，连续编号，不以原模板数量截断。缺 `content`／`purpose` 写待补；缺 `page_range` 写“待编页”并警告，不推算真实证据页码。外层可选 `title`、`submitter`、`date`。

返回文件信息、`status=draft`、逐类 `counts`、`warnings`、`template_source`。不会生成事实、利率、诉讼费用请求或其他未传入内容；模型应先依据已授权材料完成文字整理再调用。

## 来源与版式边界

版式参考用户提供的 `分发包-模板.zip` 内七份 DOCX；`catalog.json` 记录原 ZIP 与每个 DOCX 的 SHA-256、原包内路径和实测页面尺寸。原始文件保留在用户提供位置。当前产品内不复制原 DOCX、原脚本、示例案件正文或私人流程规则，也不宣称该分发包具备某种开源许可证。

生成器使用项目已安装的 python-docx 从干净文档起稿，沿用源模板 A4、页边距、标题字号及段落／四列表格结构。字体统一为 Windows 常见“仿宋”，替代源文件可能缺失的方正字体；行距使用最小值以适应长文字；不保留原固定页码、原作者／公司／打印时间等元信息。新文件没有模板中的示例金额、人名、默认比例、默认律师费诉请或固定证据页码。具体分页由目标 Word/WPS 渲染决定。

修订引擎为本项目自行实现，借鉴评估中的 OOXML 能力要求，没有执行或移植分发包脚本。合成测试覆盖跨 run、表格、XML 转义、旧修订与批注保留、原件不变、重复／重叠定位退回、同名另存、特殊文本节点以及所有模板的多项长文本完整性。测试不代替实际案件事实和法律审校。
