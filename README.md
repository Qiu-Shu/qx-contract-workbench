# 群兴法律工作台

面向宋萌律师及约 10 名受邀试用者的 Windows 法律工作台。复用现有合同审查、接待、法律资料库及持衡工程，逐步贯通“对话或上传材料 → 辅助处理 → 原文核对 → 档案草稿 → 工作成果”。暂不建设收费、订阅或交易系统。

**当前状态（2026-10-20）：开发分支已推进到 CH-05B；本机安装版仍是 0.4.1。** 对话首页、普通文字的受控主模型生成链和 Jev 独立后端账本已有工程验证；Jev 日常入口、自动档案及完整业务技能编排尚未贯通。合成验证通过不代表真实模型、法律质量或生产验收通过。

## 协作者从这里开始

- [TODO：当前任务、依赖和认领入口](TODO.md)
- [协作约定：分支、验证和同步](CONTRIBUTING.md)
- [任务实际状态与逐阶段证据](docs/TASK_STATUS.md)
- [对话式前端、模块解耦与轻量化 v2.1](docs/plans/chat-first-architecture-v2.1.md)
- [下一步接线安排](docs/plans/2026-10-19-post-home-readiness.md)
- [Windows 安装版与开发版说明](desktop/README.md)
- [本次 GitHub 同步记录](docs/testing/GITHUB-UPLOAD-20261020.md)

当前协作集成分支为 [`codex/contract-review-v2`](https://github.com/Qiu-Shu/qx-contract-workbench/tree/codex/contract-review-v2)。开始修改前先获取远端更新并查看 TODO；独立任务建议使用短分支和 PR，避免多人同时改动集成分支。每个完成阶段同步代码、实际验证记录、TODO 和 README。

## 已实现到哪里

| 模块 | 当前范围 | 证据 |
| --- | --- | --- |
| Windows 0.4.1 安装版 | 合同人工工作稿、原文定位、接待、本地法律资料检索、口令加密备份及只读恢复 | [安装说明](desktop/README.md) |
| 对话首页 | 持久草稿、技能卡选择、历史记录、事件续读、取消、切换清屏；Enter 发送、Shift+Enter 换行及中文输入保护 | [首页验证](docs/testing/chat-home/20261017/README.md) |
| 建案前附件 | 对话归属的 DOCX 收件、版本/摘要与原文核对、受控恢复；无需暗建合同案件 | [当前状态](docs/TASK_STATUS.md) |
| 主模型开发链 | DeepSeek 普通文字、系统保护凭据、日常配置、独立窗口确认具体文本、一次授权、费用记录和未知不重发 | [确认发送验证](docs/testing/native-send-confirmation/20261019/README.md) |
| Jev 后端 | 薄提供器、纯路由、独立政策/调用/回执/待核建议账本、升级和恢复；当前账本仅完整普通文字意图判断 | [CH-05A](docs/testing/jev-adapter/20261020/README.md) · [CH-05B](docs/testing/jev-ledger/20261020/README.md) |
| 解耦与资源 | 公共存储/请求边界及对话模块抽离，PDF 按需加载，Electron 语言资源筛选 | [模块证据](docs/testing/chat-first/20261017/README.md) · [资源证据](docs/testing/chat-first/20261016/README.md) |

资源首片在同后端的未压缩构建目录中减少 **48,880,941 字节（46.62 MiB）**；这不是安装器、整机启动或内存的综合结论。当前仍需持续测量核心包体、可输入时间和进程占用。

最新 CH-05B 的 **703 个不同关联 Python 用例**和 Windows 源码/冻结后端恢复验证已完成；这是该片关联回归，不能与历史测试数量累加或称为当前全仓重跑。本次同步只更新协作文档，不重跑已完成且未改变的产品验证。

## 架构与边界

沿用 **Electron + FastAPI + Jinja2/静态 JavaScript + Python 业务引擎**，不为首页重写全部框架。采用模块化单体和现有隔离 worker；业务 DTO 统一放在 `src/cn_contract/domain.py`，权限、费用、版本、锚点和批准由后端核验。合同与持衡保留独立环境，经受控材料及动作接口衔接。

DeepSeek Harness 提供交互组织参考，Impeccable 主导工作界面，Taste 辅助视觉表达。主模型负责生成，Jev 只辅助小判断；点选技能优先，辅助未配置、未获许可或失败时不能扩大主模型权限。当前 Jev 尚未接入日常设置及主任务前置。

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

开发和普通 CI 只用独立虚构材料。开发检查通过不解除发布审批；`release` / `production` 检查仍可能按既有条件阻断，不能改门禁以得到绿色结果。测试、构建、原生 Windows 验证和法律验收分别记录；不用历史数量冒充本轮执行。

## 仓库与本地资料

- 本仓库保存可共享源码、锁文件、合成测试和已筛选工程证据。安装器、真实案件、密钥、运行数据库、完整法律资料库不进入 Git。
- 持衡接续仓库：[`Qiu-Shu/chiheng-legal-workbench`](https://github.com/Qiu-Shu/chiheng-legal-workbench/tree/codex/windows-native-continuation)。仓库存在不代表统一桌面接入已完成。
- 本地法库已具备索引与检索基础；1985—2024 年网盘数据尚未下载，阿里云在线资料库尚未部署。克隆本仓库不会自动获得这些数据。
- 原始合同规格见 [specification-v2.0.md](sources/specification-v2.0.md)，复用及许可见 [upstream.lock.json](sources/upstream.lock.json)。历史阶段记录保留在 [TASK_STATUS](docs/TASK_STATUS.md) 和 [docs/testing](docs/testing/)。
