# 群兴法律工作台

面向宋萌律师及约 10 名受邀试用者的 Windows 法律工作台。复用现有合同审查、接待、法律资料库及持衡工程，逐步贯通“对话或上传材料 → 辅助处理 → 原文核对 → 档案草稿 → 工作成果”。暂不建设收费、订阅或交易系统。

**当前状态（2026-10-20）：开发分支已完成内部法库检索、持久引用、调用回执及备份恢复切片；本机安装版仍是 0.4.1。** 对话首页、普通文字的受控主模型生成链和 Jev 独立账本已有工程验证；Jev 本机配置、后端逐请求许可及同一主任务内的可选辅助已接通。同一发送确认窗已区分主模型与可选辅助许可；真实辅助默认关闭。自动档案及完整业务技能编排仍待贯通。合成验证通过不代表真实模型、法律质量或生产验收通过。

## 协作者从这里开始

- [TODO：当前任务、依赖和认领入口](TODO.md)
- [协作约定：分支、验证和同步](CONTRIBUTING.md)
- [任务实际状态与逐阶段证据](docs/TASK_STATUS.md)
- [对话式前端、模块解耦与轻量化 v2.1](docs/plans/chat-first-architecture-v2.1.md)
- [下一步接线安排](docs/plans/2026-10-19-post-home-readiness.md)
- [Windows 安装版与开发版说明](desktop/README.md)
- [本次 GitHub 同步记录](docs/testing/GITHUB-CH06B1-20261020.md)

当前协作集成分支为 [`codex/contract-review-v2`](https://github.com/Qiu-Shu/qx-contract-workbench/tree/codex/contract-review-v2)。开始修改前先获取远端更新并查看 TODO；独立任务建议使用短分支和 PR，避免多人同时改动集成分支。每个完成阶段同步代码、实际验证记录、TODO 和 README。

## 已实现到哪里

| 模块 | 当前范围 | 证据 |
| --- | --- | --- |
| Windows 0.4.1 安装版 | 合同人工工作稿、原文定位、接待、本地法律资料检索、口令加密备份及只读恢复 | [安装说明](desktop/README.md) |
| 对话首页 | 持久草稿、技能卡选择、历史记录、事件续读、取消、切换清屏；Enter 发送、Shift+Enter 换行及中文输入保护 | [首页验证](docs/testing/chat-home/20261017/README.md) |
| 建案前附件 | 对话归属的 DOCX 收件、版本/摘要与原文核对、受控恢复；无需暗建合同案件 | [当前状态](docs/TASK_STATUS.md) |
| 主模型开发链 | DeepSeek 普通文字、系统保护凭据、日常配置、独立窗口确认具体文本、一次授权、费用记录和未知不重发 | [确认发送验证](docs/testing/native-send-confirmation/20261019/README.md) |
| Jev 辅助基础 | 独立凭据、配置、账本和恢复；后端独立逐请求许可、同任务可选辅助及同窗独立确认已接通；生产辅助预算默认未配置 | [适配](docs/testing/jev-adapter/20261020/README.md) · [账本](docs/testing/jev-ledger/20261020/README.md) · [配置](docs/testing/jev-native/20261020/README.md) · [本片确认](docs/testing/jev-confirmation/20261020/README.md) |
| 对话法库底座 | 受限检索、服务器持久引用、固定调用回执和8次工具额度；当前权限重核，历史快照可随备份恢复；尚未接聊天页面和模型编排 | [适配器](docs/testing/library-adapter/20261020/README.md) · [持久引用](docs/testing/library-ledger/20261020/README.md) |
| 解耦与资源 | 公共存储/请求边界及对话模块抽离，PDF 按需加载，Electron 语言资源筛选；长文检索按命中区间定位，去掉整篇坐标表 | [模块证据](docs/testing/chat-first/20261017/README.md) · [构建资源](docs/testing/chat-first/20261016/README.md) · [检索内存](docs/testing/library-memory/20261020/README.md) |

资源首片在同后端的未压缩构建目录中减少 **48,880,941 字节（46.62 MiB）**；这不是安装器、整机启动或内存的综合结论。当前仍需持续测量核心包体、可输入时间和进程占用。

最新 CH-06B1：完整 Python 回归3222项通过、0跳过，0失败/错误，exit0；473份输入前后稳定，四项开发检查通过。独立 Spec 复核发现并关闭1项引用内容摘要遗漏，Standards补审无待修问题；WorkBuddy本轮实际连接并完成4文件只读复核，意见由统筹另行核实。[本片证据与限制](docs/testing/library-ledger/20261020/README.md)

此前长文检索在同合成样本上的 Python 跟踪分配峰值下降约87.7%，小样本耗时增加约6–8%；这项取舍和185项分批验证仍以[原阶段证据](docs/testing/library-memory/20261020/README.md)为准，不冒充本轮资源测量。

下一片先接无需模型配置的本机检索与聊天引用面板，再补完整上下文的外发许可及有界多轮编排。当前一次文字许可不能自动扩大为资料或四轮调用；[接线准备](docs/plans/2026-10-20-library-b2-readiness.md)列出实际断点与顺序。

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

开发和普通 CI 只用独立虚构材料。开发检查通过不解除发布审批；`release` / `production` 检查仍可能按既有条件阻断，不能改门禁以得到绿色结果。测试、构建、原生 Windows 验证和法律验收分别记录；不用历史数量冒充本轮执行。

## 仓库与本地资料

- 本仓库保存可共享源码、锁文件、合成测试和已筛选工程证据。安装器、真实案件、密钥、运行数据库、完整法律资料库不进入 Git。
- 持衡接续仓库：[`Qiu-Shu/chiheng-legal-workbench`](https://github.com/Qiu-Shu/chiheng-legal-workbench/tree/codex/windows-native-continuation)。仓库存在不代表统一桌面接入已完成。
- 本地法库已具备索引与检索基础；1985—2024 年网盘数据尚未下载，阿里云在线资料库尚未部署。克隆本仓库不会自动获得这些数据。
- 原始合同规格见 [specification-v2.0.md](sources/specification-v2.0.md)，复用及许可见 [upstream.lock.json](sources/upstream.lock.json)。历史阶段记录保留在 [TASK_STATUS](docs/TASK_STATUS.md) 和 [docs/testing](docs/testing/)。
