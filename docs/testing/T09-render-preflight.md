# T09 渲染环境只读预检

2026-10-03；workspace `D:\Documents\ChatGPT\律所项目`。状态：**INVENTORY_COMPLETE / WORD_NOT_RUN / DOCUMENT_RENDER_NOT_RUN / LICENSE_APPROVAL_UNKNOWN**。

本记录仅核对现有组件，独立于 T09 候选依赖、业务实现及视觉验收。未启动 Word/COM、未打开或解码 DOCX/PDF、未加载字体、未生成业务文档、未安装组件、未修改环境或正式依赖。字体及 Office 文件未复制；没有外部请求。root 独占实际 Word 运行及页面视觉 QA。

## 实得组件

依赖定位来自 `load_workspace_dependencies`，bundle 26.930.11008，根目录为 `C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies`。下述版本分别来自文件元数据、静态包元数据或明确标出的版本命令，不能代替运行功能、许可证或版本认证。

| 项目 | 实际读取结果 | 证据与限制 |
|---|---|---|
| Word 文件 | `C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE`；FileVersion/ProductVersion 均为 `16.0.20430.20092` | 静态 FileVersionInfo；完整文件 SHA 在 inventory.json；未证明可启动、激活或成功导出 |
| COM 注册 | `Word.Application` CLSID `{000209FF-0000-0000-C000-000000000046}`；LocalServer32 为 `C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE /Automation` | 只读 Registry.OpenSubKey；没有 COM 对象创建；注册不能证明运行健康 |
| Poppler | `native\poppler\Library\bin\pdftoppm.exe` 与 `pdfinfo.exe` | 两者 `-v` 各 exit 0，报告 `26.07.0`，与 manifest 一致；无文档参数、未进行解码 |
| 包装入口 | `native\poppler\bin\pdftoppm.cmd`、`pdfinfo.cmd` | 静态读取确认委托相邻 Library/bin exe；建议直接绝对 exe 路径，省去 PATH 依赖 |
| pypdf | `pypdf-6.10.0.dist-info/METADATA` 与 package directory 存在 | 仅静态 metadata 和文件存在性；未导入或解码 |
| pdf2image | `pdf2image-1.17.0.dist-info/METADATA` 与 package directory 存在 | 静态；canonical render_docx.py 使用它 |
| pypdfium2 | `pypdfium2-5.13.0.dist-info/METADATA` 存在 | 静态；没有运行 native library |
| PyMuPDF | bundle site-packages 未找到对应 dist-info，`pymupdf`/`fitz` 目录均不存在 | 限当前 authoritative bundle 的标准 site-packages；不声称所有系统环境都未安装 |
| LibreOffice | `Get-Command soffice.exe` 结果 0；bundle native/bin 定向文件检索无 soffice | 所读 Windows render_docx.py 要求 PATH 上的 soffice.exe；当前不能声称该脚本已可用 |

## 中文字体静态记录

用 stdlib 解析 SFNT/TTC `name` 表，不调用字体 native API。实际读取 4 文件、7 face；哈希为完整原字体文件 SHA-256。许可 name 字段仅作来源数据存入 inventory，不将其解释为用户或项目许可批准。

| 文件（均在 `C:\Windows\Fonts`） | family / 静态版本 | 字节 | SHA-256 |
|---|---|---:|---|
| simsun.ttc | 宋体/新宋体，5.23 | 18070492 | `120a51d2b14eb588700a21e15fc301f0ea55d7c1a4e1f3ae61db83b7c8d42cd6` |
| msyh.ttc | 微软雅黑/Microsoft YaHei UI，6.31 | 19704352 | `d79c55e68b1131eea0cc1c47be4f572d964f28c682e143db2ad09c1e4cb07a3f` |
| msyhbd.ttc | 微软雅黑/UI Bold，6.31 | 16883552 | `4508821b3dffe01f0ef5e5326a3e60df705a44633858811f67b6982dce3f6ee6` |
| simhei.ttf | 黑体，5.03 | 9753388 | `aa4560dd8fe5645745fed3ffa301c3ca4d6c03cbd738145b613303961ba733b8` |

本机文件可读不证明字体来源授权、文档嵌入、复制或再分发许可。中文字符覆盖、Word 字体替换、PDF 输出及视觉布局均未测试。

## root 可执行的后续渲染路径（本轮未运行）

所读 `docs/superpowers/plans/2026-10-03-T09-word-reference.md` 是 PUBLIC_REFERENCE_READ / WORD_NOT_RUN；Microsoft API 参数参考不等于本机功能验收。documents 技能已读取；实际 Windows render_docx.py 依赖 soffice，而本轮未找到它。

root 可创建唯一的 ASCII 临时工作目录，例如 `C:\Users\Administrator\AppData\Local\Temp\t09-word-qa-<uuid>\`，只放独立虚构测试件及派生输出，不改全局环境。Word 在 root 独立隐藏实例中只读打开虚构原件，关闭 recent/自动修复路径，导出 body/markup PDF；接受/拒绝修订分别在复制件中操作并另存输出。需分别验证这些状态，不能把 body PDF 当修订保留证据。

固定 bundle exe 的版本入口已成功，以下文档命令是**方案，NOT_RUN**。路径均为 ASCII，PowerShell 使用绝对引用，无需改 PATH：

```powershell
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdfinfo.exe' 'C:\Users\Administrator\AppData\Local\Temp\t09-word-qa-<uuid>\body.pdf'
& 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe' -png -r 150 'C:\Users\Administrator\AppData\Local\Temp\t09-word-qa-<uuid>\body.pdf' 'C:\Users\Administrator\AppData\Local\Temp\t09-word-qa-<uuid>\body-page'
```

后续需记录实际转换 exit/page count，逐页查看 PNG；发现分页、字形、表格、修订或批注异常再修复。版本命令成功仅证明该 executable 及其启动依赖在当前进程可执行，不证明 PDF 解码或视觉 QA 成功。只读预检不能推进 native/字体许可或正式法律签发状态。

## 实际命令及数量

全部命令在 workspace 下运行；脚本仅写本审计目录。证据位置 `.audit-local/t09-render-environment/`。

| 命令 | exit | 实际数量/结果 |
|---|---:|---|
| 读取 documents/SKILL.md + 初次尝试 `docs/reuse/T09-word-reference.md` | 1 | 初次参考路径不存在；辅助路径错误，不是业务/功能 RED。随后使用实际 plan 路径 |
| 读取实际 `docs/superpowers/plans/2026-10-03-T09-word-reference.md`、render_docx.py，`rg --files` 定向检索 native/bin | 0 | 定位 2 Poppler exe；较宽 poppler 关键词输出截断，未用截断输出当完整目录证明 |
| 只读注册/Word 文件元数据/4 字体文件信息 | 0 | 1 CLSID、1 Word exe、4 字体 |
| 读 Poppler manifest；分别执行 pdftoppm.exe/pdfinfo.exe `-v` | 0 | 各版本命令 exit 0；26.07.0 |
| Get-ChildItem bundle python；Get-Command soffice.exe；定向 rg 可执行/包装路径 | 0 | soffice PATH 0；2 exe + 2 cmd |
| 读 2 Poppler .cmd，rg 指定 package METADATA/入口 | 0 | 包装脚本 2；实际包元数据由 inventory 再完整扫描 |
| `& '<bundle>\python\python.exe' -B -S -X utf8 '.audit-local/t09-render-environment/inventory.py'` | 0 | 4 字体/7 face、6 component SHA、3 metadata 匹配、PyMuPDF 0、2 version exit 0 |
| `& '.audit-local/t09-render-environment/word-static.ps1'` | 0 | 持久化注册/版本；COM/Word launch 各 0 |
| bundle Python `-B -S -X utf8 -c` 读取 inventory.json 摘要 | 0 | 核验包版本/目录、4 字体版本及 SHA；无目标包导入 |
| `& '<bundle>\python\python.exe' -B -S -X utf8 '.audit-local/t09-render-environment/seal.py'` | 0 | 13 源文件 SHA 复核、drift 0；6 个审阅自产文件封 SHA（含此文档），seal.json 自身不纳入循环哈希 |

`inventory.json` 保存组件/包元数据/字体完整 SHA 和 Poppler 原始版本 stdout/stderr；`word-static.json` 保存静态注册和文件版本；`inventory.py` 与 `word-static.ps1` 为可复核只读采集脚本，`seal.json` 为最终来源核对和审阅文件清单。功能测试 0，DOCX/PDF 解码 0，页面截图/视觉检查 0，安装 0，外部请求 0。
