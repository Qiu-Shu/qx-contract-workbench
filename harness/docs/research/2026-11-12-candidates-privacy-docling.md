# Presidio 与 Docling 的加入条件核验（2026-11-12）

**本轮结论：两者都没有达到直接加入默认产品运行包的证据要求。** Presidio 可以继续做补充识敏的条件试点；不宜替换现有规则。Docling 暂不加入 DOCX 默认解析链，PDF/OCR 留待单独试点。这里的“未达到”针对本项目当前边界、固定配置和已测样本，不是对项目整体能力的否定。本轮没有构建安装包、增加生产依赖、运行真实材料、下载新模型或调用在线推理。

| 候选与用途 | 当前判断 | 已确认的依据 | 进入下一阶段的条件 |
| --- | --- | --- | --- |
| Presidio：替换中文识敏规则 | 暂不加入 | 新增 12 条固定样本中，当前规则完整覆盖 6/11 个实体出现次数；候选覆盖 4/11，新增 3、退步 5 | 不能因无标签人名的局部收益丢掉已覆盖的组织与姓名；需独立样本验收 |
| Presidio：辅助提示、补充识敏 | 需条件试点 | 新增覆盖了 3 个无标签人名；识别层运行可离线，框架和本次中文模型许可证可追溯 | 保留现有规则及人工核对；先验证合并跨度、重叠实体、误遮、OCR 断行、可逆映射与取消/超时；本轮未实现组合方案 |
| Docling：替换 DOCX 引擎 | 暂不加入 | 前次横向合并 2 份与本次纵向/嵌套表 2 份均无结构净新增；新增 2 份文字与指定结构两边都保留 | 找到现有引擎处理不了且候选确有收益的文档，再验证来源锚点、修订视图和失败降级 |
| Docling：PDF 布局、跨页表格、OCR | 需条件试点，效果未验证 | 软件许可已核对；布局、表格、VLM 模型的许可声明各不相同，不能沿用软件 MIT 作整体结论 | 先确定一条具体管线及模型 revision、权重摘要/许可证/依赖清单、离线资源预算，再用扫描与跨页合成样本比较；本轮不下载这些模型 |

## 固定版本、一手来源和许可范围

2026-11-12 通过 GitHub 连接器重新查询稳定发布及 tag，结果与前次实验一致；两个官方仓库均为 public、`archived=false`，默认分支 main。这说明仓库没有归档，不等于承诺维护 SLA。候选代码、说明和网页内容均作为参考资料读取，没有运行其中的安装命令。[前次实验及锁文件](../2026-11-12-backup-candidate-experiments.md)继续复用。

| 项目 | 固定版本 / tag 提交 | 许可与运行条件 |
| --- | --- | --- |
| [data-privacy-stack/presidio](https://github.com/data-privacy-stack/presidio/releases/tag/2.2.366) | 2.2.366；`211afc337241aee8bf495f282e83ef639a5d015f`；2026-10-27 发布 | [MIT](https://github.com/data-privacy-stack/presidio/blob/2.2.366/LICENSE)；[analyzer 要求 Python >=3.11,<3.15](https://github.com/data-privacy-stack/presidio/blob/2.2.366/presidio-analyzer/pyproject.toml)。本机独立环境 Python 3.12.10 满足该范围 |
| [docling-project/docling](https://github.com/docling-project/docling/releases/tag/v2.150.0) | 2.150.0；`6852c27fb87dafaaa1a564545a8ce78d4565b186`；2026-11-10 发布 | [MIT](https://github.com/docling-project/docling/blob/v2.150.0/LICENSE)；[docling-slim 要求 Python >=3.10,<4.0，DOCX/PDF/OCR 按模块拆分](https://github.com/docling-project/docling/blob/v2.150.0/pyproject.toml)。本轮仅已有 DOCX 环境 |
| spaCy 中文模型 | `zh_core_web_sm 3.8.0`，wheel SHA-256 `7de3bd267176b9b2a8defb6997c1cd296da16c57b5e712f72ea44a51755421c8` | [官方元数据](https://github.com/explosion/spacy-models/blob/master/meta/zh_core_web_sm-3.8.0.json)声明 MIT、spaCy >=3.8.0,<3.9.0 与 spacy-pkuseg >=1.0.0,<2.0.0。本轮另验已缓存 wheel SHA，读取 wheel 内两份 LICENSE，均为 MIT |

许可证 Git blob SHA：Presidio `9afc65b563ea7064fb04f68e3bbe31a15080f666`；Docling `6684a401bf0f700fd37104ab7c8da340036f7166`。中文模型版本元数据文件 blob SHA 为 `ee0f7e51dfd82eaaa8efb35f29da238285ed1c1a`，核对来源是版本命名文件与已下载固定 wheel，不把仓库的 master 当不可变 revision。模型元数据另外注明 OntoNotes 5 训练语料由 Explosion 商业授权；这与模型 wheel 的 MIT 声明是两个层次，不表示本项目获得训练语料再分发权。

Docling 的[固定版本模型目录](https://github.com/docling-project/docling/blob/v2.150.0/docs/usage/model_catalog.md)区分布局、OCR、TableFormer 与整页 VLM。此次只核对下列可能用于后续试点的模型卡声明，没有把它们安装或纳入许可完备的发行物清单：

| 可选模型 | 发布者模型卡的许可声明 | 当前证据与限制 |
| --- | --- | --- |
| [docling-layout-heron](https://huggingface.co/docling-project/docling-layout-heron) | Apache-2.0 | [官方文件页](https://huggingface.co/docling-project/docling-layout-heron/tree/main)列出约 172 MB 权重；是模型仓库尺寸，不是整条管线安装或内存成本 |
| [docling-models / TableFormer](https://huggingface.co/docling-project/docling-models) | CDLA-Permissive-2.0 与 Apache-2.0 双许可声明 | [官方文件页](https://huggingface.co/docling-project/docling-models/tree/main)列出约 358 MB；尚未逐文件下载与锁定本项目要用的权重 |
| [Granite-Docling-258M](https://huggingface.co/ibm-granite/granite-docling-258M) | Apache-2.0 | 官方 API 本轮返回 revision `982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe`；未运行，不推断中文准确率或桌面资源成本 |

未选择 OCR 引擎，因此不声称“所有 OCR 模型许可均通过”。软件 MIT、模型卡许可、训练数据来源和最终依赖再分发义务需要分别核对。发布前还需保留声明/许可证，并核对实际纳入的依赖与权重，而不是把本表当作完整的发行许可审查。

查询异常也保留了边界：读取 Docling pyproject 的首次 GitHub 连接请求传输失败，随后同一固定版本读取成功；两个 Hugging Face 模型 API 请求出现 TLS EOF，改为读取官方模型卡/文件页，因此二者没有声称拿到完整不可变 revision；尝试根目录 LICENSE URL 未取得文件，不把模型卡许可标记冒充已下载权重附带的许可证。上述模型均未加入运行时。

## 新增中文识敏补验

[样本文件](../../experiments/candidate-admission/privacy-docling-fixtures.json)先写入并计算 SHA-256，再运行两个实现。固定摘要为 `cdbb21b7ae38578642a2998852ccc158c635ab132e4f72abebd268fb2f850797`。12 条文本、11 个实体出现次数，均带“完全虚构”标识；包括无标签人名、重复人名、公司/研究院、OCR 换行、通用词与长金额负例。出现两次的姓名计两处；完整覆盖以每处全部非空白字符被识别为准，部分姓名不计完整覆盖。用脚本内 4 个自检断言核对重复实体、OCR 空白、事实破坏和额外字符计数。

[执行脚本](../../experiments/candidate-admission/privacy-docling-check.py)直接调用当前 `privacy._candidates` 与 `_redact`，没有复制产品规则。Presidio 配置与前次相同：`SpacyRecognizer`、中文、仅 PERSON/ORGANIZATION、阈值 0.5，无自定义人名/企业词典、无为样本调整规则。默认 Presidio 是英文，需要中文 NLP 和语言 recognizer 配置，见[官方多语言说明](https://github.com/data-privacy-stack/presidio/blob/2.2.366/docs/analyzer/languages.md)。

| 预先定义的样本组 | 当前规则完整覆盖 | Presidio 完整覆盖 |
| --- | --- | --- |
| 标签姓名 1 处 | 1/1 | 1/1 |
| 无标签姓名 3 处 | 0/3 | 3/3 |
| 标签企业、两家机构共 3 处 | 3/3 | 0/3 |
| OCR 换行姓名、企业共 2 处 | 0/2 | 0/2；姓名只识别“林晓”，留下“岚” |
| 重复姓名 2 处 | 2/2 | 0/2 |
| 总计 | **6/11** | **4/11；新增 3、退步 5** |

本次还发现现有规则的独立问题：`完全虚构：公司、学校和医院应在2026年12月31日前分别支付12000元。` 被识别出组织 `学校和医院`，实际 `_redact` 也遮住这 5 个非实体字符，导致通用词控制未保留。因此当前规则的完整事实控制为 11/12，Presidio 为 12/12；两者所有样本的金额、日期和比例控制均保留。此问题已报告给主任务；本子任务没有修改生产代码。

Presidio 单独替换会丢掉 5 处原本能识别的实体；简单并集从已有结果推算可覆盖 9/11，但会继承上述通用词误遮，两类 OCR 漏识仍在。**9/11 是现有跨度并集的推算，未实现产品组合方案，也未验证匿名化、可逆映射或用户界面。** 它支持继续研究补充识敏，不支持直接上线。

与前次 5 条/5 实体的边界样本相比，本轮用了新的姓名与机构、不同语境和负例，未重复把旧 2/5 当新结果。两批都是少量人为选择的边界集，不是抽样的业务准确率、盲测或总体召回率；当前事实不足以承诺匿名化安全。

## 新增 DOCX 结构补验

两份 DOCX 都由本轮脚本生成，当前解析器与候选读取的是同一 SHA-256 文件。预先规定文字/数字必须保留，并分别检查纵向合并及内表独立表示；没有借转换返回 SUCCESS 代替检查内容。

| 结构检查 | 当前解析器 | Docling 2.150.0 |
| --- | --- | --- |
| 首列第 2–3 行纵向合并 | 完整文字/金额保留；续行指向第 2 行 owner | 完整文字/金额保留；row_span=2，起止行 1–3（零基） |
| 表格单元格内嵌套小表 | 完整文字/金额保留；内表有独立网格与原始嵌套位置 | 完整文字/金额保留；内表有独立 table 对象 |
| 预定义结构增益/退步 | 基线 2/2 | **新增 0/2，退步 0/2** |

两份原件 SHA 运行前后一致。补充观察：Docling 的内表 parent 为 `#/body`，外层说明成为正文；当前解析器保留 `/tbl[1]/tr[1]/tc[1]/tbl[1]` 来源位置及 table_context。预先检查项没有要求保留父子层次，因此这不事后计入上述“退步”分数，但它是将 Docling 输出替换进本项目来源锚点链时必须解决的适配差异。

前次已核验的两份 DOCX 原始证据本轮重新校验摘要：现代横向合并两者保留，旧式 hMerge 两者仍未提取完整合并结构。两批共 4 份 DOCX 没有发现新增结构收益。这不证明 Docling 的 PDF、跨页表格、扫描 OCR 无收益；这些能力依赖不同组件/模型，**本轮仍未测量**。

## 资源与实际执行证据

实际工作区为 `C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目/harness`。所有新原件、SQLite 测试映射、原始结果和模型许可摘录均在 `D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/privacy-docling`。使用原有隔离环境，没有新装依赖或修改主锁文件。推理前启用 Hugging Face 离线、关闭遥测并拒绝 Python socket connect/connect_ex/create_connection；仅 CPU，OMP/MKL 线程提示为 2。未设置硬内存限制，没有把线程提示称为资源隔离。

| 项目 | 本轮实际数值 | 范围 |
| --- | --- | --- |
| 当前基线 | 2.156 秒，峰值工作集 166,453,248 bytes | 12 文本 + 2 DOCX + 导入/生成原件，不可与候选仅推理时间直接比较 |
| Presidio + 中文模型 | 模型加载 0.985 秒；12 条推理约 0.078 秒；脚本内总计 2.781 秒；峰值工作集 **470,376,448 bytes** | Windows / Python 3.12.10；spaCy 3.8.18；spacy-pkuseg 1.0.2；中文模型 3.8.0；单轮测量，不是长期并发指标 |
| Docling DOCX | 两份转换合计约 0.047 秒；脚本内总计 2.328 秒；峰值工作集 **158,089,216 bytes** | Windows / Python 3.12.10；无 PDF/OCR/VLM 权重；总计包含导入及初始化 |
| 复用的 Presidio 环境 | 54 wheel 共 98,429,472 bytes；既有安装目录 382,306,039 bytes | 来自前次实测固定清单，本轮未重新安装或称为新增安装量 |
| 复用的 Docling 环境 | 46 wheel 共 80,462,349 bytes；既有安装目录 352,749,203 bytes | 同上；只代表 DOCX 试验配置，不能用于估算 PDF 全管线 |

[结构化证据](../../experiments/candidate-admission/privacy-docling-evidence.json)包含源文件/样本/脚本摘要、新旧原始报告摘要、逐条识敏结果、实际退出码及未运行项。完整结果保留在上述 D 盘目录。实验脚本 SHA-256 为 `d5dc582b75e99bdb6760c8fe1c4aaab218e499985be9924307b7851884932999`。

以下命令均以实际 harness 为工作目录执行；已有证据文件拒绝覆盖，重复执行需为新轮次设置独立输出位置。

```powershell
. '.local/audit-0216/build/test-env.ps1'
& $env:QX_TEST_PYTHON 'experiments/candidate-admission/privacy-docling-check.py' baseline
& '.local/audit-followups/presidio-venv/Scripts/python.exe' 'experiments/candidate-admission/privacy-docling-check.py' presidio
& '.local/audit-followups/candidate-venv/Scripts/python.exe' 'experiments/candidate-admission/privacy-docling-check.py' docling
& '.local/audit-followups/presidio-venv/Scripts/python.exe' -m pip check
& '.local/audit-followups/candidate-venv/Scripts/python.exe' -m pip check
```

3 个试验进程均退出 0，两个 pip check 均退出 0、无依赖冲突。另一次核验进程退出 0：检查脚本 AST、4 个指标自检断言对应的运行脚本摘要、3 份新结果/3 份旧结果摘要、3 份生产源文件未改、2 份原件未改、中文 wheel SHA 与两份 MIT LICENSE，并确认本报告的 11/4/6/3/5 计数。**退出 0 表示实验完成及记录自洽，不表示候选质量达到了产品准入。**

未覆盖：真实材料/真实律师验收、Presidio anonymizer 和可逆字典整合、Docling PDF/OCR/跨页效果、恶意 Office 文件隔离、长期并发/超时取消、最终产品依赖漏洞扫描及完整再分发清单、安装包构建与正式发布。
