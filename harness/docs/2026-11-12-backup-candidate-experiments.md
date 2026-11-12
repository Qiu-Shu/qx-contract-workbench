# 2026-11-12 本地备份与候选组件实验

本批完成了可重复的 restic 加密备份/恢复实验、现有中文识敏与 DOCX 解析基线、Docling 的 DOCX 对比，以及 Presidio 的中文同样本实测。结论是：备份方案可继续研究产品接入；两份 DOCX 没有显示更换解析器的收益；Presidio 补识别一个姓名，同时漏掉一个现有规则能识别的公司，实体覆盖没有净增加。未改主运行包、产品设置、现有解析器或真实工作区，未上传客户材料、调用付费模型或配置云备份。

## 来源与固定版本

核验日期为 2026-11-12。通过 GitHub 官方仓库发布 API、GitHub 连接器及官方文档核对；原 `microsoft/presidio` 已跳转至 `data-privacy-stack/presidio`。来源文件只作参考，未执行上游安装脚本。

| 候选 | 本次核验 | 来源及许可 | 本次使用 |
| --- | --- | --- | --- |
| restic | 稳定发布 0.19.1，2026-07-05 | [官方发布](https://github.com/restic/restic/releases/tag/v0.19.1)、[BSD-2-Clause 原文](https://github.com/restic/restic/blob/v0.19.1/LICENSE) | 官方 Windows amd64 ZIP，11,237,567 bytes |
| Docling | 稳定发布 2.150.0，2026-11-10 | [官方发布](https://github.com/docling-project/docling/releases/tag/v2.150.0)、[MIT 原文](https://github.com/docling-project/docling/blob/v2.150.0/LICENSE)、[分模块依赖声明](https://github.com/docling-project/docling/blob/v2.150.0/pyproject.toml) | 仅 `docling-slim` 的 DOCX 与转换基础依赖，不使用 PDF/OCR/模型 |
| Presidio | 稳定发布 2.2.366，2026-10-27 | [官方发布](https://github.com/data-privacy-stack/presidio/releases/tag/2.2.366)、[MIT 原文](https://github.com/data-privacy-stack/presidio/blob/2.2.366/LICENSE)、[Python 及依赖条件](https://github.com/data-privacy-stack/presidio/blob/2.2.366/presidio-analyzer/pyproject.toml) | 独立环境运行 analyzer、spaCy 3.8.18 与中文模型 3.8.0，CPU 离线 |

restic ZIP SHA-256：`da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d`，与官方 Release asset digest 一致；解压 EXE SHA-256：`b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830`。每次执行前重新与已校验 ZIP 内的字节比较，并检查实际 `version` 输出。没有进行 GPG 签名校验，不把 HTTPS 与摘要核对表述成独立签名验证。

许可证原文的 Git blob SHA：restic `29b2ee55a92ff2c5516d7b916224c85fa7e9139a`；Docling `6684a401bf0f700fd37104ab7c8da340036f7166`；Presidio `9afc65b563ea7064fb04f68e3bbe31a15080f666`。Docling 46 个 wheel 的固定版本、下载 URL、尺寸、摘要及包声明许可分别记录于 [锁文件](../experiments/audit-followups/docling-windows-py312.lock) 和 [组件清单](../experiments/audit-followups/docling-artifacts.json)。清单中的空许可字段不等于无许可，亦不是发行合规审查结论；本次不分发这些依赖。

## restic：实际结果

[实验脚本](../experiments/audit-followups/backup_experiment.py) 每次建立新的合成工作区。两份文本、50 条已提交 SQLite WAL 记录与文件 SHA-256 相互绑定；存在一条未提交事务时，使用 SQLite backup API 读取已提交视图，源文件写入保持停止。此方法遵循 [Python SQLite backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup) 的连接备份机制，未把裸复制活动数据库当成一致快照。

进入备份的是两份文本、备份后的 SQLite 和 manifest，共 4 个文件、17,057 bytes。两份带明确虚构标记的凭据文件、原始 WAL/SHM、随机测试口令没有进入快照。脚本不接收用户材料路径；口令只放在本轮私有实验目录，子进程通过 `RESTIC_PASSWORD_FILE` 读取，正常/异常清理均删除口令文件。

最终 24 项检查通过，运行约 6.3 秒；仓库 5,853 bytes，包含故障注入产生的第二个快照。恢复必须选取已记录的完整快照 ID，不能把缺失输入时产生的部分快照误当成完整备份。实际命令和退出码保存在 [结构化证据](../experiments/audit-followups/evidence-2026-11-12.json)。

| 检查 | 实际结果 |
| --- | --- |
| `version`、`init`、`backup --json`、`check --read-data` | 均退出 0；实际读取并检查全部备份包 |
| WAL 中的已提交记录、未提交记录隔离 | 恢复 50 条已提交记录，未提交的第 999 条不存在 |
| 错误口令 `snapshots --json` | 退出 12，明确 wrong password/no key |
| 加入缺失源路径的 `backup` | 退出 3，不当作完整成功；原始快照 ID 保持独立 |
| 恢复目录防覆盖 | 拒绝源目录、源子目录、快照目录、仓库目录、祖先目录、外部目录、已有非空目录、已有空目录，共 8 项 |
| `restore --overwrite never --verify` | 退出 0，仅恢复到新建独立目录；4 个文件逐个 SHA-256 一致 |
| SQLite 与业务文件对照 | `integrity_check=ok`，50 条记录及其引用文件摘要一致 |
| 错误注入 | 实际修改恢复副本字节、删除一份恢复副本均被对照器检测；随后恢复副本并再次对照通过 |
| 原件与凭据 | 源工作区字节不变；测试口令文件已删除 |

恢复不会直接使用 restic 默认覆盖行为；官方说明默认会覆盖目标文件，因此脚本额外要求全新目录，并传 `--overwrite never`。[恢复行为说明](https://restic.readthedocs.io/en/stable/050_restore.html)。错误口令及命令退出码按 [官方脚本接口](https://restic.readthedocs.io/en/stable/075_scripting.html) 与本次真实输出来处理。

开发中留下三次失败记录，未抹去：首次发现 SQLite 连接上下文不自动关闭，显式关闭后解决锁；第二次纠正错误口令的预期退出码为 12；第三次绝对目录树恢复形成 262 字符路径，当前 Python 文件 API 无法读取。最终改用相对 `snapshot` 目录备份，且文件枚举使用会报错的 `stat`，不再静默跳过不可读文件。完整原始失败和成功报告都在忽略的 `.local/audit-followups/runs/`，公开摘要不含本机用户名或口令。

这证明的是本地合成数据的一致快照与独立恢复。真实工作台尚需明确各数据库、文件写入进程和脱敏映射的协调方式，以及凭据恢复策略；没有新增生产备份按钮、定时任务或恢复入口，也没有做断电、海量数据、异机 ACL 或灾备验收。

## 中文识敏：可复现差距

[基线脚本](../experiments/audit-followups/candidate_experiment.py) 直接运行当前 `privacy._candidates` 与 `_redact`。5 条合成文本预先指定 5 个目标实体，以完整非空白字符覆盖计数：覆盖 2 个，遗漏 3 个；5 条样本中的金额、日期、通用词控制均保留。这个刻意选取的边界样本集不能当作总体召回率。

| 样本 | 当前规则实际结果 |
| --- | --- |
| 标签明确的中文姓名、公司全称 | 两个实体均覆盖 |
| 无“姓名”等标签的中文签收人 | 漏掉姓名 |
| 姓名被 OCR 换行切开 | 漏掉姓名 |
| 公司后缀被 OCR 换行切开 | 漏掉完整组织名称 |
| “学校应支付……”通用词负例 | 不误删学校、金额、日期 |

现有代码保留了自动识别可能遗漏及人工复核提示；本批没有改变规则或把参考识别结果自动上传。

Presidio 默认配置是英文；中文需要配置 NLP 模型和对应语言 recognizer/context，不能只安装框架就宣称支持本项目的中文材料。[固定版本多语言说明](https://github.com/data-privacy-stack/presidio/blob/2.2.366/docs/analyzer/languages.md)。

已经核验候选 `zh_core_web_sm 3.8.0`：模型声明 MIT，官方标示约 46 MB，要求 spaCy `>=3.8.0,<3.9.0` 与 `spacy-pkuseg>=1.0.0,<2.0.0`；模型元数据单独注明 OntoNotes 训练数据由发布者商业授权，不将训练语料许可与模型许可混为一谈。[官方模型元数据](https://github.com/explosion/spacy-models/blob/master/meta/zh_core_web_sm-3.8.0.json)。该 wheel 的官方 SHA-256 为 `7de3bd267176b9b2a8defb6997c1cd296da16c57b5e712f72ea44a51755421c8`。

现有测试运行环境未安装上述 NLP 组件；本次另建 `.local/audit-followups/presidio-venv`，运行 [独立比较脚本](../experiments/audit-followups/presidio_experiment.py)。模型官方 [Release wheel](https://github.com/explosion/spacy-models/releases/download/zh_core_web_sm-3.8.0/zh_core_web_sm-3.8.0-py3-none-any.whl) 实际为 48,515,003 bytes，下载后校验尺寸和摘要；全部 54 个 wheel（包含模型）共 98,429,472 bytes，固定版本/哈希与 URL/尺寸/声明许可见 [锁文件](../experiments/audit-followups/presidio-windows-py312.lock) 和 [组件清单](../experiments/audit-followups/presidio-artifacts.json)。Presidio、spaCy、spacy-pkuseg 与中文模型均声明 MIT；未把这些实验依赖接入主运行包。

配置固定为中文 `SpacyRecognizer`，仅识别 PERSON/ORGANIZATION，阈值 0.5；没有加入样本姓名、公司名或定制规则。使用与基线相同的 5 条原始文本，按实际识别跨度检查完整实体覆盖及事实保留。

| 样本 | 当前规则 | Presidio + 中文小模型 |
| --- | --- | --- |
| 标签姓名与公司 | 2/2 实体覆盖 | 姓名覆盖，公司遗漏：1/2 |
| 无标签中文签收人 | 姓名遗漏 | 姓名覆盖：新增 1 个 |
| OCR 换行姓名 | 完整姓名遗漏 | 仅识别“赵”，“明远”仍保留；完整姓名遗漏 |
| OCR 换行公司 | 完整组织名称遗漏 | 未识别，仍遗漏 |
| 通用词负例、金额与日期控制 | 5/5 样本事实保留 | 5/5 样本事实保留；非实体字符误遮为 0 |

最终覆盖 **2/5**，基线也是 **2/5**：新增覆盖 1 个、退步 1 个，没有净增加。无标签姓名有局部收益线索，但本轮未实现组合策略，不能据此推荐直接替换；两类换行差距仍在。此处只测试 analyzer 识别跨度，使用中性 `[PII]` 标记计算事实保留，未验证 Presidio anonymizer、可逆映射或生产脱敏流程。

实测 Python 3.12.10、spaCy 3.8.18、spacy-pkuseg 1.0.2，安装后 382,306,039 bytes / 9,882 files。模型加载 1.187 秒，5 条推理合计 0.032 秒，进程内总计 2.266 秒，Windows 峰值工作集 470,323,200 bytes。CPU 运行，OMP/MKL 线程提示为 2，外层超时 180 秒；无 GPU、无硬内存上限。在模型初始化前开启 Hugging Face 离线并阻断 Python socket 连接，推理未下载模型或调用外部服务。依赖体积远低于本轮约 1 GB 的停止阈值。更广的独立盲测、分词/换行预处理与组合策略尚未执行，不把这 5 条边界样本当作整体识敏质量评估。

## Docling：实际对比与资源

现有 `reader.parse` 与 Docling 读取相同 SHA-256 的两份 DOCX；两个文件都由脚本生成。基线调用真实解析器，不模拟文本结果。

| DOCX 样本 | 当前解析器 | Docling 2.150.0 |
| --- | --- | --- |
| 现代 `gridSpan` 表头横向合并 | 文字/数字保留，第 1–2 列合并关系保留 | 相同 |
| 旧式 `hMerge` 表头横向合并 | 文字/数字保留，合并关系未提取；明确发出网格警告 | 文字/数字保留，合并关系仍未提取 |

Docling 两份转换均返回 SUCCESS，原件哈希不变，但结构改善数为 **0/2**；SUCCESS 不能代表表格结构正确。没有发现足以支持替换现有引擎的收益，候选继续留在实验目录。

实测 Windows amd64、Python 3.12.10，独立虚拟环境 46 个固定依赖 wheel 共 80,462,349 bytes，安装后约 352,749,203 bytes / 12,445 files。2 份实际转换约 0.047 秒（不包含导入、初始化与下载），外层进程约 1.8 秒；CPU 线程提示为 2，外层超时 180 秒。没有设置或宣称硬内存上限。推理启用 Hugging Face 离线并阻断 Python socket 连接，未使用模型权重或真实模型 API。

该测试只覆盖 DOCX。Docling 的 PDF 布局、TableFormer、OCR 和 VLM 是不同组件/模型，许可及资源要求需分别核验；不能将软件 MIT 许可证泛化为全部模型权重的许可。[官方模型目录](https://docling-project.github.io/docling/usage/model_catalog/)。本次未下载这些模型，未比较扫描件、跨页表格或 PDF 阅读顺序。

## 命令与证据

复现命令见 [实验 README](../experiments/audit-followups/README.md)。本机工作目录为当前附加工作树，实验子任务未独立提交；由主任务统一集成记录，未推送。

| 实际操作 | 退出码 | 数量/边界 |
| --- | --- | --- |
| `python harness/experiments/audit-followups/backup_experiment.py` | 0 | 24 项检查、4 文件、50 行；已缓存并重新校验官方二进制 |
| 既有隔离 Python 运行 `candidate_experiment.py` | 0 | 5 条中文识敏样本、2 份 DOCX；Python 3.12.14 |
| 独立 venv 的 `pip install --only-binary=:all: --require-hashes -r .../docling-windows-py312.lock` | 0 | 46 包；仅 `.local` 虚拟环境，安装阶段缓存也定位 `.local` |
| 独立 venv 运行 `candidate_experiment.py --docling-baseline .../baseline.json`，外层超时 180 秒 | 0 | 2 份真实转换，0 项结构改善 |
| `python harness/experiments/audit-followups/presidio_experiment.py --download-model` | 0 | 显式校验官方中文模型，48,515,003 bytes |
| 独立 venv 的 `pip install --only-binary=:all: --require-hashes --find-links .../downloads -r .../presidio-windows-py312.lock` | 0 | 54 包含模型，仅 `.local` 环境；98,429,472 bytes |
| 独立 venv 运行 `presidio_experiment.py --baseline .../baseline.json`，外层超时 180 秒 | 0 | 同 5 条文本，2/5 实体覆盖，新增 1、退步 1 |
| Presidio 独立 venv 的 `python -m pip check` | 0 | No broken requirements found |
| 本地证据核对与 Python AST 解析 | 0 | 4 份原始报告摘要、3 份脚本、4 份依赖清单/锁文件、100 条固定组件记录全部一致；核对 24 项备份检查及 Presidio 结果 |

首次依赖规划的 `pip --dry-run --report` 会下载 wheel 到 pip 缓存；它不是零下载操作，未安装到全局。后续安装及复现命令显式把缓存放入 `.local`。不把这次试验称为产品升级或全部任务质量通过。

最终 [结构化证据](../experiments/audit-followups/evidence-2026-11-12.json) 保留命令退出码、逐项检查、样本结果、源码/原件/原始报告摘要和未运行项。完整原始报告路径在其 `local_evidence` 字段中，属于本机忽略目录，不承诺能从公开仓库下载。
