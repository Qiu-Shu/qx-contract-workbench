# 本机材料 MCP 桥

这部分提供材料读取与 Word 输出，供 Harness 的 Agent 按需调用。没有模型调用或外网识别，也不读取旧工作台数据库。

## 启动

```powershell
& 'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe' `
  'D:/qx-harness-workbench-20261102/bridge/server.py' `
  --workspace 'D:/qx-harness-workbench-20261102/workspace'
```

MCP 使用 stdio，服务名 `qx_materials`。使用当前已安装的 MCP SDK 2.2.0 的 `MCPServer` API；不要改用已经弃用的 `FastMCP` 导入路径。Harness 的工具调用超时建议设为 600 秒。

## 工具

| 工具 | 用法 |
|---|---|
| `list_materials(offset=0,limit=50)` | 分页列出工作区文件，包括尚未导入的附件 |
| `import_material(path)` | 注册工作区内文件，计算摘要；原件留在原位置、不覆盖 |
| `parse_material(path,start_page=1,page_count=20,force_ocr=false,revision_mode="original")` | 建索引；PDF 按返回的 `next_page` 继续，DOCX 可选 `accepted_view` |
| `read_material(path,start=0,limit=6,page=null)` | 按片段或 PDF 页读取；根据 `next_start` 继续 |
| `search_materials(query,path=null,offset=0,limit=10)` | 对已解析全文作中文/原词检索，返回短摘录与定位 |
| `write_word_draft(filename,title,content)` | 生成实际 `.docx`，返回绝对和相对路径；同名文件自动另取名称 |

典型执行顺序：列材料 → 导入 → 分批解析 → 搜索和按需读取 → 分析 → 生成 Word。不要为了分析多份材料而一次读取所有全文。PDF 中有图片的页会额外执行 OCR；识别内容需要核对数字、日期、否定词。

Harness 上传图片保存为 `inbox/.harness/attachments/v1/objects/<前缀>/<摘要>`，没有扩展名。材料桥按图片内容识别 JPEG/PNG/WebP/GIF/BMP/TIFF，可直接列出、导入、解析、读取及关联原路径；不会复制、改名或调用桌面工具。无扩展名的未知文件仍拒绝，工作区路径和链接限制保持。回归验证：`python -m pytest bridge/test_image_objects.py -q`。

支持 TXT、MD、CSV、TSV、JSON、HTML/HTM、RTF、DOC/DOCX、PDF、XLS/XLSX、PPT/PPTX、ODT/ODS/ODP、PNG、JPG/JPEG、WebP、GIF、BMP、TIF/TIFF。文档解析复用旧项目的 `documents` 模块和本机 OCR，输出使用 python-docx；不执行 Office 宏、表格公式或外部链接。

## 存储与实际边界

- 路径必须位于指定 workspace 内。拒绝跨目录访问、符号链接和 Windows 目录联接。工作区内的普通硬链接（包括 Harness 上传别名）可只读解析，不修改原件。工具不会读取旧项目的数据库或其他材料目录。
- 索引在 `workspace/.qx-materials/index.sqlite`，Word 在 `workspace/drafts/`。不要把索引目录作为附件。源文件变动后，重新导入会清理旧片段；读取旧索引会提示重新解析。
- 没有 20 个文件或 100 MB 会话总量限制。流式注册/文本读取不会把所有文件内容放入一次模型响应；PDF 每批单页加载并保存解析进度，重新调用可以接着处理。
- 这不是无限内存解析器。Office、HTML/RTF 和图片仍复用整体解析库；按当前空闲内存进行资源检查，原件始终保留。内存不足可释放内存，或将大型 Office 文件转成 PDF 分批处理。PDF 已完成批次可继续，单次超过十分钟会返回缩小批次的说明。磁盘不足/权限错误会明确反馈。
- 原词搜索目前使用 SQLite 顺序检索，适用于本机起步规模；大量文本下可能变慢，不宣称已有向量检索或语义召回。每次读取和搜索只返回有界片段。
- Word 为可编辑草稿，不等于事实和法律依据已核验。

## 运行依赖与自检

复用 `D:/qx-contract-workbench-20261102/.venv` 和其 `src`，不复制、不修改旧项目代码。依赖清单见本目录 `requirements.txt`；新环境还需安装旧项目本身，保留其配置文件。当前环境不需要再次安装。

```powershell
& 'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe' `
  'D:/qx-harness-workbench-20261102/bridge/selfcheck.py'
```

自检使用真实 MCP stdio 客户端及临时工作区：TXT、DOCX、两页中文扫描 PDF、PNG 导入/解析/分页/搜索；生成 Word 后重新打开检查正文；核对原件摘要不变和工作区外路径被拒绝。结果保存在 `selfcheck-result.json`，测试材料清理后不进入用户日常材料列表。没有模型请求。

## 持续业务服务 qx_legal

`business_server.py --workspace <路径>` 在同一材料索引中增加案件、版本关联、追加笔记、庭审和发言表；不读取或搬迁旧工作台数据库。四套方法及来源位于 `config/skills/qx-*`，通过 `get_workflow` 按需读取。工具保存自然语言，引用不匹配保留正文与待核说明，不以固定输出字段或业务字数拒收答案。

| 工具组 | 作用 |
|---|---|
| `get_workflow` | 接待、合同、办案、庭审方法及实际来源 |
| `create_case / list_cases / get_case` | 明确案件归属；分页读取当前或历史记录 |
| `link_case_materials / read_case_material / search_case_materials` | 绑定指定材料版本、案件内读取和搜索；搜索结果用 kind 区分原材料和笔记 |
| `record_case_note / read_case_note` | 追加自然语言、关联更正、完整分页回读；request_id 支持重复请求找回 |
| `export_case` | 实际 Word；客户版仅 client_reply，内部版带逐条引用版本与当前材料版本；同名另存 |
| `start_hearing / get_hearing / record_hearing_turn / get_hearing_role_context` | 民事原被告五阶段、11 个发言位置；实际保存后推进，冻结材料及输入笔记，补件后用 previous_id 关联新演练 |

正文存储不设业务长度上限；工具分页控制单次返回量。保存成功不等于法律结论已经核实，matched 仅表示在记录时找到对应原文。引用自身摘要与当前材料摘要分别显示。文件外部被覆盖后仍能发现变化和回查旧关联/摘录，但这不是任意原件的完整版本备份服务。

安装配置用 `scripts/deploy-legal-workflows.py` 增量挂载，复制四个 Skill 并插入业务路由；保留既有扩展和界面配置。当前脚本默认复用本机旧 Python，独立安装包需换成随包解释器，并包含 config/skills 参考资料。运行时模型无须访问旧方法源文件；旧路径仅用于来源记录和本机开发测试。

离线验证：`python -m pytest bridge/test_business_store.py bridge/test_workflows.py bridge/test_hearing.py bridge/test_business_export.py -q`；真实 stdio 验证：`python bridge/check_business_mcp.py`。`node scripts/check_legal_runtime.mjs --live` 会调用已配置模型，仅创建标题明确的虚构验收案件；不得把测试脚本当作启动自检或每次启动自动执行。
