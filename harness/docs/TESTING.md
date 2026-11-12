# 源码测试入口

从 `harness` 目录运行。测试只使用独立虚构材料；默认入口不读取模型凭据、不调用真实模型，也不下载或安装依赖。部分协议测试启动本机 HTTP 服务。

| 命令 | 范围 |
| --- | --- |
| `npm test` 或 `npm run test:offline` | 可移植源码回归：自动发现 Node 与 Python 测试，包括知识恢复、受控 OS 边界的凭据测试、媒体源和打包入口 |
| `npm run test:windows` | 显式 Windows 集成：真实 DPAPI、原生增量程序、候选程序资源、现有 Windows 文档工具 |
| `npm run eval:workflow` | 独立开发依赖下的 24 案离线 Harness/技能/真实 MCP/Word 基线；不等同真实模型或法律质量验收 |
| `npm run test:quality -- <phase> <synthetic-scenarios.json> [...]` | 显式付费模型指令评测；还必须设置 `QX_REAL_MODEL_TEST=1` 和 `QX_TEST_ELECTRON` |

`npm run test:offline -- --list` 和 `npm run test:windows -- --list` 只输出选中的文件。自动发现覆盖 `desktop`、`plugins`、`packaging`、`scripts`、`bridge`、`tests`、`evals` 中的测试文件，排除缓存、依赖、符号链接及专用评测脚本。原生组文件在 `scripts/test-suite.cjs` 中明确分类。增加测试后应核对分组。

新增工作流基线的环境、独立锁文件、离线/真实模式和预算边界见 [评测 README](../evals/quality-baseline/README.md)。`npm test` 只运行其无网络断言和预算测试，不自动启动 Promptfoo 或安装其依赖。

Node 与 pytest 两组都会执行；任一子进程失败，统一入口返回非零退出码。依赖缺失也是失败。不能只看最后一组，也不能把跳过算作通过。部分旧测试有自定义内部计数，需同时读取其输出和 Node 文件包装结果。

## 运行环境

需要 Node 24.9+、现有项目 Node 依赖，以及包含 pytest 和业务依赖的 Python。测试入口不负责安装这些依赖；可复用经核验的构建缓存。不要把依赖目录提交到 Git。

| 变量 | 用途 |
| --- | --- |
| `QX_TEST_PYTHON` | 测试用 Python；默认 Windows 为 `python`，其他系统为 `python3` |
| `NODE_PATH` | 可选，复用已有 Node 依赖目录；分隔符使用本机格式 |
| `PYTHONPATH` | 可选，现有 pytest/业务依赖位置；入口自动前置当前 `bridge` 与 `legacy/src` |
| `QX_BUILD_MODULES` | 可选，现有打包工具依赖目录 |
| `QX_TEST_APP` | Windows 集成必需，受控候选程序 `resources/workbench`；仅复用程序资源 |
| `QX_HDIFFPATCH_DIR` | Windows 集成必需，已有匹配版本 `hdiffz.exe` 与 `hpatchz.exe` 的目录 |

入口设置 `QX_TEST_NODE` 为当前 Node，设置源码 `QX_LEGACY_ROOT`，禁用 Python 字节码与 pytest 自动加载外部插件，并清空模型和远端记忆的测试环境密钥。单独运行 Python 子测试时，可自行设置 `QX_TEST_NODE`，否则使用 PATH 的 `node`。历史 `packaging/stage.py` 仍是 Node 打包器的兼容转发入口，其 Node 选择变量是 `QX_BUILD_NODE`。

本次 Windows 验证复用的准确路径与环境脚本见 [2026-11-11 验证记录](2026-11-11-build-test-verification.md)。可移植分组在 Windows 实跑通过；本轮没有运行 Linux/macOS，因此不把分组名称当作跨平台验收证明。

上游兼容模块 `plugins/wechat/test/office.test.mjs` 的真实文档往返另需 `DSH_OFFICE_PYTHON`（含 python-docx、openpyxl、python-pptx），PDF 转换另需 `DSH_OFFICE_KIT`。缺工具时会明确跳过真实部分。当前 QX 默认插件入口为 `qx-plugin.js`，不加载上游 `index.js` 的 `office_*` 工具。

合同 UI 烟测入口 `tests/check_contract_compare_ui.py` 默认验证当前源码集成；验收实际安装包时须设置 `QX_TEST_PACKAGED=1`，使集成模块、材料解析和旧业务依赖都取自 `QX_TEST_APP` 指向的解包资源。`QX_TEST_OUTPUT_ROOT` 可将独立合成工作区、日志及截图放到其他磁盘。烟测报告的 `packagedIntegrationAndParser` 记录实际模式，不能用源码模式代替包内验证。不得在正在构建的候选目录内运行任何测试。

`tests/check_tool_labels_ui.py` 从 `QX_TEST_APP` 加载真实包内 React 工具卡片，以合成记录检查具体中文标题、未知名称回退、参数/结果展开及查看回调；须显式指定绝对路径 `QX_TEST_OUTPUT_ROOT`。它复用上述隔离宿主、Playwright 与本机 Chrome，不调用模型、不执行业务工具，不证明会话持久化或法律质量。日志及完整截图保存在独立输出目录。

## 媒体源与打包回归

`sources/media-source-registry.json` 是应用源码配置。`packaging/stage.cjs` 验证其版本、条目、来源 URL/允许域名和刷新周期后，明确覆盖 `resources/workbench/sources/media-source-registry.json`，并加入源码清单；不再依赖旧发行包偶然携带该文件。

`packaging/test_media_payload.py` 分别从当前源码和没有继承源配置的空 payload 启动真实 `MediaService`；`packaging/stage.test.cjs` 验证无效配置不能覆盖已有 payload 文件。它们不抓取新闻，不调用模型，也不等同于完整发行包或安装验收。

## 真实模型质量评测

仅在另行授权预算和数据范围后使用第三个入口；传入明确的虚构场景 JSON。它复用 `scripts/evaluate_skills.cjs` 的 Electron 安全存储、既有预算和输出目录，并会使用当前 Windows 用户已保存的模型凭据访问真实服务。`phase` 遵循原评测器的命名，例如 `smoke`、`retest`、`repair-<name>`。输出目录必须尚不存在，避免把旧结果当作本次结果。

缺少结果、请求失败或截断响应都使入口失败，即使原评测器进程返回零。所有场景收到完整响应，也仅代表收集成功；法律与语义质量仍需人工审阅。本轮没有调用此入口的真实模型分支。
