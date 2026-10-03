# T03 独立安全审阅

审阅者只读业务实现，不修改 T03 实现或其正式测试。读取 AGENTS、当前 TASK_STATUS、v2.0 §5/6/T03、安全及锚点要求、T03 detail plan，以及 T01 统一 DTO、T02 权限/不可变原件/解析快照基础。仅使用独立虚构 OOXML/PDF；没有真实合同、QCC、外发、抓取、安装或提交。作者停止修改代码后实跑最终目标与独立探针，并再次实读最终源码。

采用 verification-before-completion 工作流：作者总结不能代替实读源码和运行结果。独立探针在被 Git 忽略的 `.audit-local/t03-review/test_review_probe.py`；依赖独立复核脚本在同目录 `verify_dependencies.py`。

## 已实跑证据

| 命令 | 退出码 | 实际数量与范围 |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t03-review/test_review_probe.py -q --tb=short --junitxml=.audit-local/t03-review/preliminary.xml` | 1 | 12 项：5 failed / 7 passed。DOCX 行内容器 2 项、PDF page Annots 3 项失败；没有收集错误 |
| 同探针，`--junitxml=.audit-local/t03-review/preliminary-expanded.xml` | 1 | 扩展 13 项：4 failed / 9 passed。作者修改后行内容器 2 项实测通过；新增 docProps binary 错报已读取 1 项与 Annots 3 项失败 |
| 同探针，`--junitxml=.audit-local/t03-review/preliminary-rendering.xml` | 1 | 扩展 14 项：5 failed / 9 passed。新增 PDF invisible rendering 1 项失败 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-review/verify_dependencies.py` | 0 | 从正式 manifest 实读 35 wheel SHA-256、35 requirements hash、35 已安装版本；wheel 内与仓库 60 份许可同字节；35 包审批为空，G06 runtime=true/审批为空；errors=[]；应用测试 0 项 |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_document_parts.py tests/security/test_upload.py tests/integration/test_parsing.py -q --tb=short --junitxml=.audit-local/t03-review/final-target.xml` | 0 | 最终正式 T03 目标 69 passed / 0 failed / 0 warnings，11.12s |
| `.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t03-review/test_review_probe.py -q --tb=short --junitxml=.audit-local/t03-review/final-probes.xml` | 0 | 最终独立 14 passed / 0 failed / 0 warnings，0.85s；现有四组 P2 的复现全部通过 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-review/verify_dependencies.py` 最终再次实读 | 0 | 同前 35 wheel、35 锁 hash、35 安装版本、60 份许可、35 未批准状态及 G06 运行标记，errors=[]；没有下载或安装 |

依赖只验证目标构件字节与已安装版本一致，不重新下载。阅读 T03-dependencies 及正式锁确认 developer/read_verified 不代表生产批准；PDFium/Pillow/OpenSSL 原生与构建供应链、完整许可使用范围仍阻断。没有把 PyPI vulnerabilities=[] 当作完整安全批准。

## 发现、复现与最终关闭

1. **P2，DOCX 行内容器静默遗漏（已关闭）。** 初版 `docx_adapter.blocks` 只取 `tr.findall(w:tc)`，行内 `w:sdt/w:sdtContent/w:tc` 或 `w:customXml/w:tc` 中付款900/担保700丢失，同时返回 `anchors=()`、`unsupported_parts=()`、`word/document.xml:read`。独立用例 `test_row_content_control_is_read_or_unsupported` / `test_row_custom_xml_is_read_or_unsupported` 两项先失败，作者调整后扩展运行及最终稳定运行两项均通过。
2. **P2，PDF 页注释没有覆盖（已关闭）。** `pdf_adapter` 初版只盘点 Catalog OpenAction/AA/AcroForm/Names，没有盘点页 `/Annots`。合法 FreeText、FileAttachment、Link 注释中的付款900/附加材料/外部链接都没有锚点或未读缺口，返回 `page:1:read`、`unsupported_parts=()`。独立参数用例 `test_pdf_page_annotation_has_coverage` 3 项先失败、最终通过。没有发出任何外部请求；问题是错误的读取覆盖声明。
3. **P2，docProps 下二进制错报 metadata_read（已关闭）。** 初版 `parse_docx` 用 `name.startswith('docProps/')` 把没有 XML 解析的 thumbnail.jpeg 或任意二进制一概报为 metadata_read，unsupported 为空。独立用例 `test_docprops_binary_is_unread_not_metadata_read` 先失败、最终通过。最终明确元数据允许清单；其他成员保留未读缺口。
4. **P2，不可见 PDF 文字层错报已读正文（已关闭）。** 独立合法 PDF 内容流 `BT /F1 12 Tf 72 720 Td 3 Tr (SYNTHETIC invisible payment 900) Tj ET` 使用不可见文字渲染模式，初版仍生成付款900锚点并报 `page:1:read`，没有 quality/unsupported。这违背 §6.3 对文字层与可见内容冲突的人工确认要求。独立用例 `test_pdf_invisible_text_requires_manual` 先失败、最终通过，最终识别非普通渲染模式并保留 manual/unsupported。

初步和最终通过的独立范围：一致伪造 local/central usize 的实际 2MiB 膨胀、local/central CRC 同时伪造、损坏 raw deflate、未声明尾部数据；原生 PDF 四单元格提取与坐标；错案解析在 original read 前拒绝；撤销会话在 input read 前拒绝。正式目标回归最终 69 项同时覆盖宏、路径、DTD/实体、quota、修订选择授权、锚点字段和不可变原件等已实现边界。

最终四组 P2 关闭状态：行内 `sdt/customXml` 等未支持对象明确进入 unsupported；PDF 页 Annots 进入 annotations 缺口及 manual 状态，页级 AA/A/AF 等同时保留交互/嵌入缺口；docProps 二进制不再以目录前缀冒充已读元信息；PDF 采用真实内容解释器的 textstate 检查渲染模式，非 0/1/2 模式进入 text_rendering 缺口和人工确认。独立 14 探针不是通过删去失败断言或更改预期关闭；原先全部失败场景保留并最终通过。正式测试另补渲染模式 3/7、页数有界构造及包裹单元回归。

最终源码审阅还确认：ZIP raw inflater 对实际输出设置 `max_output+1` 上限并核对 eof/unused_data/CRC/local header/name，而不是依赖 ZipExtFile 根据中央 file_size 截断；受限 XML 禁止 DTD/entity/external；授权先于上传流、原件及缓存读取，parse/resolve 重取可信服务器版本，所有 anchor 字段精确比较；原件 DocumentVersion 没有被覆盖，解析结果追加存储；修订视图必须由律师权限明确选择，复杂修订仍有未读边界；PDF 逐页 native iterator 在超限即失败，未取前 N 页后返回全文完成。所有业务 DTO 仍来自 domain.py，新增 PDF aggregator 是解析实现而非另造业务模型。

`pyproject.toml` 只添加固定 pdfplumber/defusedxml 根；requirements 保留 T02 全部 28 包版本/hash 并添加 7 包。G06 runtime 标记、开发采用范围及生产批准阻断相符；G08 未伪称已安装，实际 DOCX 采用受限 OOXML/XML 提取。源/依赖差异审阅没有发现未经批准启用模型、QCC、联网识别、外链加载或付费操作。最后读取的 6 个 documents 源码及 4 个测试/helper 文件共 10 个 SHA-256 保存在 `.audit-local/t03-review/final-source-hashes.json`，标识本审阅实际版本；本地没有业务修改或提交。

结论：本次稳定 T03 的安全摄取、读取盘点与精确锚点 **独立工程审阅通过**，没有保留未修复的 P2 及以上发现。最终独立实跑分母为正式目标 69 与独立探针 14，不能相加冒充 84 项产品规格；根节点执行全套回归，本审阅者没有重复运行其 269 全套命令或将其结果记为自己的实际执行。

该结论限于独立虚构材料和当前支持对象。PDF 的 read 表示原生文字层提取，并非视觉语义一致性证明；透明度、遮挡、字体映射、完整渲染/OCR及流解码 CPU/内存沙箱未完成，保持 PDF limited/manual 使用边界与生产阻断。OCR 未部署、中文复杂渲染/真正扫描 OCR、真实律师金标准、试点批准、生产恢复、原生依赖许可使用范围及运行隔离均不在本次通过范围内，不能据此宣称生产完成。
