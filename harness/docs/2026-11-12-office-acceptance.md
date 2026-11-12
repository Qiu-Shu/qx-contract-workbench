# 2026-11-12 Office 可选往返补查

## 结论与范围

本专项补查基线 `dab11f2` 上轮缺失的 Office 证据，只测试保留的上游 `plugins/wechat/office.js`。没有改产品代码、发行依赖或原有 Node/Python；没有安装到用户应用、读取真实材料、上传文件或调用模型。

- 官方 0.2.16 解包资源自带 python-docx、python-pptx 和 LibreOffice Kit。用包内 Python、Node、Office 模块和 Kit，DOCX/PPTX 写入回读及各自转换 PDF 均通过。
- 上轮 PDF 跳过原因是测试没有传 Kit 路径；显式设置 `DSH_OFFICE_KIT` 即可运行，主包无需新增转换器。
- 官方解包资源的主 Python 缺 `openpyxl` 和 `et_xmlfile`。在不补测试依赖时，独立七项得到 **5 通过、1 失败、1 跳过，exit 1**；失败是 XLSX 写入导入 openpyxl，跳过是对应 XLSX 未生成，因而未转换 PDF。
- 仅在 D 盘隔离测试目录补入锁定的两个 wheel，并通过本次进程的 `PYTHONPATH` 注入后，独立七项 **7 通过、0 失败、0 跳过，exit 0**；已有 `office.test.mjs` 内部 **12 通过、0 失败、0 跳过**，Node 包装 **1/1，exit 0**。

这证明上游兼容 Office 模块在上述明确依赖条件下可运行，**不表示原始发行包原生支持该模块的 XLSX 全链路**。默认 QX 入口 `qx-plugin.js` 不加载上游 `index.js` 的 `office_*` 工具，因此没有把该可选模块的依赖缺口等同于默认 QX 微信调用链故障。

0.2.17 **首轮候选（中文名称合入前）**与**中文工具名合入后的最终包**均已分别实测，证据各自保留：两轮原生均为 **5 通过、1 失败、1 跳过，exit 1**；只加既有隔离测试依赖后均为 **7 通过、0 失败、0 跳过，exit 0**。最终包身份为 SHA-256 `7d97e21085f3c873f21cb604232fa4f269a64dd056e99216fe9e223a326dcbdd`，其独立测试见“最终 0.2.17 包复核（中文工具名已合入）”。首轮 `3520...` 包及证据保留在前一节，不能混用。

## 实际资源与版本

实际工作区：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`。

证据根目录：`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/office-qa`，下文日志和脚本均相对此目录。所有新下载、虚构文件、PDF、临时目录均在此根目录下。

先按上轮 `harness/.local/audit-0216/build/test-env.ps1` 复现；未编辑此脚本，也未把其 `stage/base` 目录声明为干净发行来源。随后切换到只读的官方解包资源：

`D:/Documents/ChatGPT/律所项目/.local/release-0216/release-extracted-final/application/resources/workbench`

主代理本轮独立核验其对应的 0.2.16 安装器 SHA-256 为 `0f798a3721e092866f226bf17aad70d93e1ae1cebd52b749da1bd2acef022030`。安装器签名、整树摘要及新候选包的结论由主验收记录负责；本专项不越过该证据范围。

| 组件 | 实际版本及来源 |
| --- | --- |
| Python | 包内 `runtime/python/python.exe`，3.12.14 |
| python-docx | 包内主 Python，1.2.0 |
| python-pptx | 包内主 Python，1.0.2 |
| LibreOffice Kit | 包内 `node_modules/@deepseek-ai/libreoffice-kit` 与 win32-x64 程序，0.1.5 |
| 最终专项 Node | 包内 `runtime/node.exe`，24.22.1 |
| 初始复现 Node | 既有 `C:/Program Files/nodejs/node.exe`，24.20.0；未改动 |
| pypdf | 包内 `runtime/scrapling/Lib/site-packages`，6.19.0；仅用于测试端检查 PDF 正文与页数 |
| openpyxl / et-xmlfile | 隔离 `office-qa/python-test-deps`，3.1.5 / 2.0.0；没有加入主 Python 或主包 |

`03-release-dependencies.log` 记录不设置 `PYTHONPATH` 时的模块发现：docx/pptx 存在，openpyxl/et_xmlfile/pypdf 不存在于主 Python。`08-effective-dependencies.json` 记录测试接线后的版本和每个模块的实际导入路径。

当前源码与官方解包的 `plugins/wechat/office.js` SHA-256 都是 `d4e8f8c75ea9ccddd9350e32746087c9e4cbf5b559823b9ed280c82b81a9089b`；其他实际运行文件摘要在 `09-runtime-hashes.json`。

## 隔离依赖与来源

从项目已跟踪的 `harness/packaging/case-memory-requirements.lock` 取两个既有固定 URL 和 SHA-256，经下载、摘要核对后，使用已有 Python 的标准库 zipfile 解压到 `office-qa/python-test-deps`。没有运行 pip，没有安装、升级或修改全局及产品 Python。

| wheel | 字节数 | SHA-256 |
| --- | ---: | --- |
| openpyxl-3.1.5-py2.py3-none-any.whl | 250910 | `5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2` |
| et_xmlfile-2.0.0-py3-none-any.whl | 18059 | `7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa` |

完整官方 `files.pythonhosted.org` URL、下载路径及摘要在 `04-wheel-provenance.jsonl`。两份下载合计 268969 字节；下载、核验与解压命令 exit 0。主包没有因此获得这两个模块。

## 用例与实际执行

`office-roundtrips.mjs` 是保留在 D 盘的独立测试脚本，直接导入指定 payload 的 `office.js`。三个格式分别执行，避免 XLSX 失败遮蔽 PPTX。

1. DOCX 写入后回读，核对中文正文、项目符号、表格。
2. XLSX 写入后回读，核对中文工作表、中文单元格、120 和 0。
3. PPTX 写入后回读，核对两页标题、要点和英文哨兵文本。
4. 缺失文件返回明确中文错误。
5. DOCX 转 PDF，检查文件头、正文、页数和源文件 SHA-256 不变。
6. XLSX 转 PDF，同上；如果前置 XLSX 根本未生成，明确跳过。
7. PPTX 转 PDF，同上，另要求 PDF 为两页。

PDF 正文核对同时包括预期英文哨兵和中文词句，不能仅凭 `%PDF-` 头或非零文件大小通过。每次成功生成 3 个 Office 文件和 3 个 PDF；PDF 共 4 页（1、1、2）。每次输出目录中的 `artifacts.json` 保存路径、大小、摘要、结构化回读和 PDF 提取正文。

| 实际命令/条件 | 日志 | 实际结果 |
| --- | --- | --- |
| 原 test-env + `DSH_OFFICE_PYTHON`，`node --test plugins/wechat/test/office.test.mjs` | `01-original-red.log` | 内部 10 通过、1 失败、1 跳过；Node 文件失败；exit 1 |
| 同上，仅补 `DSH_OFFICE_KIT` 指向 payload CLI | `02-kit-wired-red.log` | 内部 11 通过、1 失败、0 跳过；PDF 真转换通过；exit 1 |
| 官方解包 Python/模块/Kit，原有 Node 24.20.0，未加隔离 XLSX 依赖；`node --test office-roundtrips.mjs` | `05-release-separated-red.log` | 5 通过、1 失败、1 跳过；exit 1 |
| 上一行仅加隔离 XLSX 依赖 | `06-release-separated-green.log` | 7 通过、0 失败、0 跳过；exit 0 |
| 官方解包 Python/Kit + 隔离 XLSX 依赖；源码 `office.test.mjs` | `07-original-green.log` | 内部 12 通过；Node 顶层 1 通过；exit 0 |
| 改为官方解包内 Node 24.22.1，仍加隔离 XLSX 依赖；`Run-OfficeQa.ps1 ... -WithIsolatedXlsxDependencies` | `10-release-bundled-node-green.log` | 7 通过、0 失败、0 跳过；exit 0 |
| 同一包内 Node，撤去隔离 XLSX 依赖，再次验证原生边界 | `11-release-bundled-node-native.log` | 5 通过、1 失败、1 跳过；exit 1 |

所有失败日志保留。测试接线的 RED→GREEN 来自明确的环境依赖变化，没有把测试弱化、屏蔽失败或修改产品结果。

## 复跑与后续候选包

专项脚本可直接指向新候选解包资源；它使用该目录内的 Node、Python、Office 模块和 Kit，不隐式复用旧 payload 程序。`RunName` 必须是尚不存在的新目录名，以保留既有证据。以下是本轮已执行的两条命令，若复跑需更换 `RunName`：

```powershell
$officeQa='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/office-qa'
$officePayload='D:/Documents/ChatGPT/律所项目/.local/release-0216/release-extracted-final/application/resources/workbench'
& "$officeQa/Run-OfficeQa.ps1" -Payload $officePayload -RunName '10-release-bundled-node-green' -WithIsolatedXlsxDependencies
& "$officeQa/Run-OfficeQa.ps1" -Payload $officePayload -RunName '11-release-bundled-node-native'
```

入口设置仅对本次进程生效：

```powershell
$env:DSH_OFFICE_PYTHON=Join-Path $officePayload 'runtime/python/python.exe'
$env:DSH_OFFICE_KIT=Join-Path $officePayload 'node_modules/@deepseek-ai/libreoffice-kit/lib/cli.js'
$env:QX_OFFICE_MODULE=Join-Path $officePayload 'plugins/wechat/office.js'
$env:PYTHONPATH=Join-Path $officePayload 'runtime/scrapling/Lib/site-packages'
# 只有条件性 XLSX 试验才前置本行；原生依赖试验不加。
$env:PYTHONPATH=(Join-Path $officeQa 'python-test-deps')+';'+$env:PYTHONPATH
```

`office-roundtrips.mjs` SHA-256：`58a32f2cabe749bdbb992a366243a26d3be695d4cd490593da58fe25aecb9ccd`。

`Run-OfficeQa.ps1` SHA-256：`cc30436ff77baf764dd3bfb352e448600de3a46857fb9c2bd3502683ffa75ad9`。

日志及辅助元数据的摘要清单为 `evidence-hashes.json`。

## 0.2.17 首轮候选复核（中文名称合入前）

本节保留中文工具名合入前的首轮候选证据。该轮候选已由主验收完成构建、解包与输入逐项比对，本专项只读使用：

`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-extracted/application/resources/workbench`

主验收提供的首轮安装器身份：590844602 字节，SHA-256 `3520f52f10754c2624a967e5c1059224bbd3e9766916950362441b697383be5f`；53233 个包内文件逐项与构建输入相同。此安装器不是中文工具名合入后的最终包。这些安装器与整树结论由主验收负责，本专项独立验证以下实际运行内容。

使用未修改的 `Run-OfficeQa.ps1` 和 `office-roundtrips.mjs`，新建两组 D 盘输出目录，启用 `PYTHONDONTWRITEBYTECODE=1`；Node、Python、Office 模块、Kit、PDF 核验用 pypdf 全部取自候选 payload。只有第二组前置既有隔离 `openpyxl` / `et_xmlfile` 测试目录。没有修改 payload、主包依赖或原有运行环境。

```powershell
$officeQa='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/office-qa'
$officeCandidate='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-extracted/application/resources/workbench'
& "$officeQa/Run-OfficeQa.ps1" -Payload $officeCandidate -RunName '12-candidate-native'
& "$officeQa/Run-OfficeQa.ps1" -Payload $officeCandidate -RunName '13-candidate-isolated-green' -WithIsolatedXlsxDependencies
```

| 条件 | 日志 / 输出目录 | 实际结果 |
| --- | --- | --- |
| 候选包原生依赖 | `12-candidate-native.log` / `12-candidate-native/` | 5 通过、1 失败、1 跳过；7.89 秒；exit 1。DOCX/PPTX 写入回读、缺失文件错误、DOCX/PPTX 转 PDF 均通过；XLSX 因缺 openpyxl 失败，对应 PDF 明确跳过。 |
| 候选包 + 隔离 XLSX 测试依赖 | `13-candidate-isolated-green.log` / `13-candidate-isolated-green/` | 7 通过、0 失败、0 跳过；9.13 秒；exit 0。3 个 Office 文件、3 个 PDF；PDF 页数为 1、1、2，均含预期中英文，3 个源文件转换前后 SHA-256 一致。 |

候选实际运行版本仍为 Node 24.22.1、Python 3.12.14、python-docx 1.2.0、python-pptx 1.0.2、LibreOffice Kit 0.1.5。不注入外部路径时，候选主 Python 对 openpyxl、et_xmlfile、pypdf 的发现结果均为空；PDF 检查单独复用候选的 Scrapling 环境中的 pypdf。

`14-candidate-runtime.json` 保存上述模块探测及 5 个实际运行文件的大小和 SHA-256。候选 `office.js`、Python 程序、Kit CLI 与 Kit 原生程序的摘要和上文 0.2.16 对应文件一致；候选 Node SHA-256 为 `86f361a88f4cc3ecaf1ea93236b0d8edf07bf00fe87ad9f60305513f58fc2c17`。

`candidate-evidence-hashes.json` 保存新增候选日志、运行文件元数据、两组虚构材料及回读 JSON 的摘要；原 `evidence-hashes.json` 的 13 项摘要重新核对一致，原失败/成功证据未覆盖。

候选结论仍只针对保留的上游可选 Office 模块：DOCX/PPTX 与转换器的上述场景可直接运行，XLSX 往返须有明确依赖条件。不能据此称整个主产品 XLSX 不可用，也不能把隔离依赖成功写成候选主包已包含该依赖。

## 最终 0.2.17 包复核（中文工具名已合入）

中文工具名合入后重新构建的最终 payload：

`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-final-extracted/application/resources/workbench`

主验收提供的最终安装器身份为 **590859223 字节**，SHA-256 **`7d97e21085f3c873f21cb604232fa4f269a64dd056e99216fe9e223a326dcbdd`**。主验收报告构建与完整解包比对 exit 0，53234 个包内文件、3395 个来源文件。这里保留该来源说明；以下 Office 结果由本专项重新执行，并非沿用首轮候选结果。

复用原测试脚本和原隔离 wheel，没有重复下载依赖。两组命令均取最终 payload 自带的 Node、Python、Office 模块和 Kit，启用 `PYTHONDONTWRITEBYTECODE=1`，新建 D 盘输出目录，保持 payload 只读：

```powershell
$officeQa='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/office-qa'
$officeFinal='D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/candidate-final-extracted/application/resources/workbench'
& "$officeQa/Run-OfficeQa.ps1" -Payload $officeFinal -RunName '16-final-native'
& "$officeQa/Run-OfficeQa.ps1" -Payload $officeFinal -RunName '17-final-isolated-green' -WithIsolatedXlsxDependencies
```

| 最终包条件 | 日志 / 输出目录 | 实际结果 |
| --- | --- | --- |
| 原生依赖 | `16-final-native.log` / `16-final-native/` | 5 通过、1 失败、1 跳过；7.08 秒；exit 1。上游可选模块 XLSX 写入因缺 openpyxl 失败，未生成 XLSX，故对应 PDF 跳过；其余 5 项通过。 |
| 仅加隔离 XLSX 测试依赖 | `17-final-isolated-green.log` / `17-final-isolated-green/` | 7 通过、0 失败、0 跳过；9.29 秒；exit 0。DOCX/XLSX/PPTX 各自写入回读、缺失文件错误、三格式 PDF 转换均通过。 |

最终成功组生成 3 份 Office 文件和 3 份 PDF，PDF 页数为 1、1、2；三份 PDF 的中英文文本均匹配预期，三个源文件在转换前后的 SHA-256 均相同。每组的 `artifacts.json` 保留实际内容回读与文件摘要。

`18-final-runtime.json` 记录原生模块发现、有效依赖版本/路径及实际运行文件摘要。最终运行版本为 Node 24.22.1、Python 3.12.14、python-docx 1.2.0、python-pptx 1.0.2、LibreOffice Kit 0.1.5；PDF 检查使用最终包 `runtime/scrapling/Lib/site-packages` 中的 pypdf 6.19.0。第二组仅增加 `office-qa/python-test-deps` 中既有 openpyxl 3.1.5 与 et-xmlfile 2.0.0。原生主 Python 仍未包含这两个模块。

已逐项核对最终 Node、Python、`office.js`、Kit CLI 和 Kit 原生程序 **5 个运行文件**，摘要与首轮对应文件一致；Office 模块 SHA-256 仍为 `d4e8f8c75ea9ccddd9350e32746087c9e4cbf5b559823b9ed280c82b81a9089b`。

最终证据清单：

`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/office-qa/final-evidence-hashes.json`

该清单包含 **17 项**：两份最终日志、最终运行元数据、两个复用测试脚本、两组虚构成果及回读 JSON。早期 `evidence-hashes.json` 的 13 项和首轮 `candidate-evidence-hashes.json` 的 15 项重新核对一致；没有覆盖、删除或弱化失败证据。

本次最终包复核仍不改变依赖边界：只确认上游可选 Office 模块在记录的条件下运行；不将其 XLSX 原生失败扩展为整个主产品 XLSX 不可用，不将隔离依赖成功宣称为最终包已含这些依赖。

## 未验证

本记录涵盖官方 0.2.16 资源、基线源码、中文名称合入前的 0.2.17 首轮候选及中文工具名合入后的最终包的可选 Office 模块。专项不替代整个安装包及产品的主验收。未验证真实 Microsoft Office GUI、复杂格式保真、宏、公式重新计算、加密文档、图片版式或所有字体；没有进行视觉排版验收。未运行默认 QX 工具调用链的模型任务或真实微信收发。主产品默认解析器的 XLSX 能力与本上游可选模块分属不同入口，不能根据此专项相互推定。
