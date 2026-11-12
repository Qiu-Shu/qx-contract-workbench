# 审核后续：隔离实验

这里只生成虚构样本，调用现有识敏/解析器，并评估可选组件。没有生产入口；不修改主依赖、安装包、客户文件或已有工作区。结果与完整运行材料在忽略的 `harness/.local/audit-followups/`。结论见 [本次记录](../../docs/2026-11-12-backup-candidate-experiments.md)。

从仓库根目录执行。先检查脚本和固定来源；下载只需联网获取官方公开组件，推理与备份均在本地完成。

## restic

```powershell
python harness/experiments/audit-followups/backup_experiment.py --download
```

仅第一次需要 `--download`。固定 restic 0.19.1 Windows amd64 ZIP（11,237,567 bytes），下载尺寸和 SHA-256 不一致即拒绝执行；缓存 EXE 每次与已验证 ZIP 内字节比较。每轮创建新目录，不接收外部备份源或恢复目标参数。

样本包括 2 个文本文件、1 个 SQLite 数据库、2 个虚构凭据文件。只把明示允许的文本和 SQLite backup API 生成的数据库复制到快照，增加 manifest 后备份；原始 WAL/SHM、虚构凭据和随机口令不入快照。文件写入暂停，数据库存在 50 条已提交 WAL 记录和 1 条未提交记录时取一致视图。此方法没有实现真实工作台多个写入进程之间的协调。

每个 restic 命令超时 120 秒，`GOMAXPROCS=2`，禁用缓存；恢复使用新的独立目录和 `--overwrite never`。随机测试口令不进参数/报告，正常和异常退出均删除口令文件；因此保留的实验仓库不能再打开，应重新运行获得新实验结果。脚本不删除历史实验目录。

## 现有解析/识敏基线

需要现有产品的 Python 依赖；本次使用既有隔离测试环境，不对产品运行环境安装任何包。

```powershell
. ./harness/.local/audit-0216/build/test-env.ps1
& $env:QX_TEST_PYTHON harness/experiments/audit-followups/candidate_experiment.py
```

输出 `baseline.json` 的实际路径。每轮生成 5 条中文识敏样本、2 份 DOCX，并记录当前源码哈希、原件哈希、输出与期望。识敏指标是预先指定实体的全部非空白字符是否被覆盖，不用“某个词消失了”充当完整脱敏。生成的映射也是虚构数据，留在 `.local`。

## 可选 Docling DOCX 对比

仅适用于 Windows amd64 + Python 3.12。锁文件固定 46 个 wheel 的版本/哈希，清单 `docling-artifacts.json` 记录下载 URL、尺寸、摘要及包声明许可，总计 80,462,349 bytes；不包含 torch、OCR 或模型权重。它不是生产依赖锁文件。

```powershell
python -m venv harness/.local/audit-followups/candidate-venv
$env:PIP_CACHE_DIR = (Join-Path $PWD 'harness/.local/audit-followups/pip-cache')
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
& ./harness/.local/audit-followups/candidate-venv/Scripts/python.exe -m pip install --only-binary=:all: --require-hashes -r harness/experiments/audit-followups/docling-windows-py312.lock
$env:PYTHONDONTWRITEBYTECODE = '1'
& ./harness/.local/audit-followups/candidate-venv/Scripts/python.exe harness/experiments/audit-followups/candidate_experiment.py --docling-baseline '<本轮 baseline.json 路径>'
```

比较入口只接收本实验目录内生成的基线、两种固定文件名及匹配哈希；拒绝链接与 Windows reparse point。运行时配置 Hugging Face 离线并阻断 Python socket 连接，不下载模型、不调用外部服务。不同机器速度不同；本次外层进程超时设为 180 秒。

不能从这份 Docling 结果推断 PDF/OCR 效果。

## 可选 Presidio 中文对比

同样只适用于 Windows amd64 + Python 3.12，使用另一套独立环境。`presidio-windows-py312.lock` 与 `presidio-artifacts.json` 固定 54 个 wheel（包含中文模型），总计 98,429,472 bytes。模型 `zh_core_web_sm 3.8.0` 来自官方 Release，48,515,003 bytes，声明 MIT；显式准备步骤检查固定尺寸和 SHA-256，推理入口不会下载模型。

```powershell
python harness/experiments/audit-followups/presidio_experiment.py --download-model
python -m venv harness/.local/audit-followups/presidio-venv
$env:PIP_CACHE_DIR = (Join-Path $PWD 'harness/.local/audit-followups/pip-cache')
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
& ./harness/.local/audit-followups/presidio-venv/Scripts/python.exe -m pip install --only-binary=:all: --require-hashes --find-links harness/.local/audit-followups/downloads -r harness/experiments/audit-followups/presidio-windows-py312.lock
$env:PYTHONDONTWRITEBYTECODE = '1'
& ./harness/.local/audit-followups/presidio-venv/Scripts/python.exe harness/experiments/audit-followups/presidio_experiment.py --baseline '<本轮 baseline.json 路径>'
```

使用原基线的 5 条固定文本，显式配置中文 `SpacyRecognizer`、PERSON/ORGANIZATION、阈值 0.5，无样本专用规则；使用 CPU，在模型初始化前启用离线和 socket 连接阻断。本次外层进程超时 180 秒，峰值工作集约 470 MB；没有硬内存限制。实际识别跨度仅用中性标记遮盖来检查金额/日期保留，不代表验证了 Presidio anonymizer、可逆映射或产品接入。

实际覆盖仍为 2/5：补识别一个无标签姓名，同时漏掉现有规则能识别的公司；两个换行实体仍未完整覆盖。5/5 样本的事实控制保留。本轮没有支持直接替换现有识敏器的证据，更多盲测和组合策略属于后续工作。
