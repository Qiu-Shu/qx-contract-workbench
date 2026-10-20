# 群兴法律工作台

面向宋萌律师及约 10 名受邀试用者的 Windows 法律工作台。复用现有合同审查、接待、法律资料库及持衡工程，逐步贯通“对话或上传材料 → 辅助处理 → 原文核对 → 档案草稿 → 工作成果”。暂不建设收费、订阅或交易系统。

**当前状态（2026-10-20）：开发分支已有对话内本机检索、历史原文面板，并新增选定引用的完整本机预览接口；安装版仍是0.4.1。** 新预览保留问题、引用版本、位置和待核状态，暂未接律师操作界面或资料发送。普通文字受控生成、Jev独立配置与同窗许可已有工程验证；自动档案、资料辅助回答及完整技能编排仍待贯通。合成验证不代表真实模型、法律质量或生产验收。

开发分支已修复 Windows 深中文目录下旧合同原件的保存、读取和回滚清理；424项关联测试及实际HTTP备份恢复链通过。该修复尚未进入新的安装包；[实测与范围](docs/testing/contract-long-path/20261020/README.md)。

## 协作者从这里开始

- [TODO：当前任务、依赖和认领入口](TODO.md)
- [协作约定：分支、验证和同步](CONTRIBUTING.md)
- [任务实际状态与逐阶段证据](docs/TASK_STATUS.md)
- [对话式前端、模块解耦与轻量化 v2.1](docs/plans/chat-first-architecture-v2.1.md)
- [下一步接线安排](docs/plans/2026-10-19-post-home-readiness.md)
- [Windows 安装版与开发版说明](desktop/README.md)
- [本次 GitHub 同步记录](docs/testing/GITHUB-WINPATH01-20261020.md)

当前协作集成分支为 [`codex/contract-review-v2`](https://github.com/Qiu-Shu/qx-contract-workbench/tree/codex/contract-review-v2)。开始修改前先获取远端更新并查看 TODO；独立任务建议使用短分支和 PR，避免多人同时改动集成分支。每个完成阶段同步代码、实际验证记录、TODO 和 README。

## 已实现到哪里

| 模块 | 当前范围 | 证据 |
| --- | --- | --- |
| Windows 0.4.1 安装版 | 合同人工工作稿、原文定位、接待、本地法律资料检索、口令加密备份及只读恢复 | [安装说明](desktop/README.md) |
| 对话首页 | 持久草稿、技能卡选择、历史记录、事件续读、取消、切换清屏；Enter 发送、Shift+Enter 换行及中文输入保护 | [首页验证](docs/testing/chat-home/20261017/README.md) |
| 建案前附件 | 对话归属的 DOCX 收件、版本/摘要与原文核对、受控恢复；无需暗建合同案件 | [当前状态](docs/TASK_STATUS.md) |
| 主模型开发链 | DeepSeek 普通文字、系统保护凭据、日常配置、独立窗口确认具体文本、一次授权、费用记录和未知不重发 | [确认发送验证](docs/testing/native-send-confirmation/20261019/README.md) |
| Jev 辅助基础 | 独立凭据、配置、账本和恢复；后端独立逐请求许可、同任务可选辅助及同窗独立确认已接通；生产辅助预算默认未配置 | [适配](docs/testing/jev-adapter/20261020/README.md) · [账本](docs/testing/jev-ledger/20261020/README.md) · [配置](docs/testing/jev-native/20261020/README.md) · [本片确认](docs/testing/jev-confirmation/20261020/README.md) |
| 对话法库检索 | 选择“检索法律资料”，最多200字关键词、5条候选；原文片段/来源版本/待核状态可保存和回查；复用任务、当前权限及只读恢复，尚未接资料辅助生成 | [本机检索与引用面板](docs/testing/library-chat/20261020/README.md) · [持久化底座](docs/testing/library-ledger/20261020/README.md) |
| 资料上下文预览（开发接口） | 从当前草稿和1—8条已保存引用重建完整清单；有配置时显示完整请求及字节预算，超限不截断；所有状态均不发送、不读取密钥、不创建任务 | [预览证据](docs/testing/context-preview/20261020/README.md) |
| 合同原件长路径（开发分支） | 复用既有路径工具，保存/读取/事务清理支持深中文原件目录；qxbak恢复下载、二次备份及只读限制已验，逻辑引用不变 | [Windows实测](docs/testing/contract-long-path/20261020/README.md) |
| 解耦与资源 | 公共存储/请求边界及对话模块抽离，PDF 按需加载，Electron 语言资源筛选；长文检索按命中区间定位，去掉整篇坐标表 | [模块证据](docs/testing/chat-first/20261017/README.md) · [构建资源](docs/testing/chat-first/20261016/README.md) · [检索内存](docs/testing/library-memory/20261020/README.md) |

资源首片在同后端的未压缩构建目录中减少 **48,880,941 字节（46.62 MiB）**；这不是安装器、整机启动或内存的综合结论。当前仍需持续测量核心包体、可输入时间和进程占用。

最新 CH-06B2b1：644项关联Python与四开发检查通过，491份输入前后稳定；Windows实际HTTP通过9组检查、27次请求，主模型/Jev/密钥读取均为0。独立需求与规范复核无本片待修项，WorkBuddy完成2文件只读计划复核。广泛回归曾因过深目录中止，另有测试重名与测试脚本导入失败，均保留记录；本轮不称全套通过，旧合同长路径限制尚待修复。[实际证据与限制](docs/testing/context-preview/20261020/README.md)

此前长文检索在同合成样本上的 Python 跟踪分配峰值下降约87.7%，小样本耗时增加约6–8%；这项取舍和185项分批验证仍以[原阶段证据](docs/testing/library-memory/20261020/README.md)为准，不冒充本轮资源测量。

下一片CH-06B2b2将独立资料许可、不可变输入格式、既有调用账本、原生确认和备份迁移一起接通，再完成一次资料辅助回答；之后扩展有界多轮。旧一次文字许可保持原范围。[预览合同](docs/plans/2026-10-20-context-preview-execution.md)已实施；[发送与存储设计](docs/plans/2026-10-20-context-send-storage.md)仍是待实施方案。

## 架构与边界

沿用 **Electron + FastAPI + Jinja2/静态 JavaScript + Python 业务引擎**，不为首页重写全部框架。采用模块化单体和现有隔离 worker；业务 DTO 统一放在 `src/cn_contract/domain.py`，权限、费用、版本、锚点和批准由后端核验。合同与持衡保留独立环境，经受控材料及动作接口衔接。

DeepSeek Harness 提供交互组织参考，Impeccable 主导工作界面，Taste 辅助视觉表达。主模型负责生成，Jev 只辅助小判断；点选技能优先，辅助未配置、未获许可或失败时不能扩大主模型权限。当前Jev已接通后端独立逐请求许可与可选前置，日常发送确认已区分独立辅助选择；真实账户、价目与预算前提未落实时不启用真实辅助发送。

原件、来源、版本和审核状态必须保留。自动档案将保存可回查的草稿，不自动确认事实、覆盖律师更正或合并客户。客户回复与内部意见分别呈现和导出。真实资料外发、费用、QCC、正式签发及云端部署仍受独立条件约束。

## 开发与验证

Windows AMD64 / Python 3.12 的已有锁定环境可按下列方式重建；桌面构建另见 [desktop/README.md](desktop/README.md)。不要从本机复制虚拟环境、凭据或客户数据库给协作者。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

先运行与改动相关的测试，再执行开发检查；记录实际命令、退出码和数量：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli schema --check
.\.venv\Scripts\python.exe -X utf8 scripts/verify_defaults.py
.\.venv\Scripts\python.exe -X utf8 scripts/verify_sources.py --mode development
.\.venv\Scripts\python.exe -X utf8 scripts/verify_runtime_dependencies.py --mode development
```

运行包含 `tests/integration/test_library_pilot.py` 的测试时，须为当前命令设置 `QX_PILOT_PYTHON`，指向已安装 DuckDB 的独立 Python 解释器；未设置会明确跳过2项。当前本机可复用 `D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe`（DuckDB 1.5.6），协作者使用自己的绝对路径。测试只在临时目录新建虚构CSV及DuckDB，不读取既有试点数据。DuckDB是旧试点迁移测试的独立依赖，无需加入桌面核心运行包；若本机确实缺少，先建立隔离环境并安装与既有试点兼容的版本，再执行用例。用户已授权缺失依赖直接安装，优先复用现有可用环境。

法库测试临时目录所在盘须满足既有40 GiB可用空间保护。C盘不足时，用空间充足盘上的全新专属 `--basetemp` 目录运行；pytest会管理该目录，不得指向真实资料或已有共享目录。不得降低产品阈值来使测试通过。

开发和普通 CI 只用独立虚构材料。开发检查通过不解除发布审批；`release` / `production` 检查仍可能按既有条件阻断，不能改门禁以得到绿色结果。测试、构建、原生 Windows 验证和法律验收分别记录；不用历史数量冒充本轮执行。

## 仓库与本地资料

- 本仓库保存可共享源码、锁文件、合成测试和已筛选工程证据。安装器、真实案件、密钥、运行数据库、完整法律资料库不进入 Git。
- 持衡接续仓库：[`Qiu-Shu/chiheng-legal-workbench`](https://github.com/Qiu-Shu/chiheng-legal-workbench/tree/codex/windows-native-continuation)。仓库存在不代表统一桌面接入已完成。
- 本地法库已具备索引与检索基础；1985—2024 年网盘数据尚未下载，阿里云在线资料库尚未部署。克隆本仓库不会自动获得这些数据。
- 原始合同规格见 [specification-v2.0.md](sources/specification-v2.0.md)，复用及许可见 [upstream.lock.json](sources/upstream.lock.json)。历史阶段记录保留在 [TASK_STATUS](docs/TASK_STATUS.md) 和 [docs/testing](docs/testing/)。
