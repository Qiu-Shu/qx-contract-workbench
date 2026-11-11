# 2026-11-11 R04 / R05 构建与测试可靠性验证

基线 `b802e214`，分支 `codex/audit-0216-fixes`。实际工作区：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`。本记录覆盖媒体源源码补齐、现行打包转发入口和统一测试入口；知识与微信生产修改另见本日专项记录。

## R04：媒体源进入源码和清单

当前 `MediaService` 启动需要 `sources/media-source-registry.json`，此前 checkout 缺失该文件。先运行源码启动和空 payload 启动测试，得到两项失败；新增校验测试也因缺少显式复制函数失败。

本地已有 `stage/base` 的整树校验失败（`baseline-verify.log`），故没有把此目录当作干净来源。实际核验并只提取官方安装器的程序资源：

- 安装器：`D:/Documents/ChatGPT/律所项目/.local/release-0216/release-final/Qunxing-Workbench-0.2.16-Setup.exe`，590674132 字节。
- 安装器 SHA-256：`0f798a3721e092866f226bf17aad70d93e1ae1cebd52b749da1bd2acef022030`，与已跟踪的 `docs/2026-11-10-0.2.16发布.md` 一致。
- 内层 `$PLUGINSDIR/app-64.7z` 中的 `resources/workbench/sources/media-source-registry.json`：799 字节，SHA-256 `eb343519fc02c09b08651a33418d59d7241bdea99fa7edffeebe048563b3a6334`。
- 文件完整复制到 `harness/sources/`，保留三个原来源和原检查日期；本轮未联网重新确认来源内容或新鲜度。

`stage.cjs` 先校验 registry，再显式覆盖 payload 对应路径并登记 source/target/hash。无效版本、空列表、重复 ID、不匹配域名或非法刷新周期均拒绝覆盖。干净 payload 测试真实叠加当前 bridge 和 registry 后，独立 Python 进程成功初始化服务，返回三个来源、空任务、空健康记录、未配置模型。

此验证不是完整包重建：本轮没有重建干净官方 0.2.14 基线，没有执行完整 ASAR/NSIS 构建、签名、发布或安装。

## R05：入口及旧测试迁移

`npm test` 默认运行离线组；Windows 集成及真实模型评测显式选择。发现文件、依赖和完整说明见 [TESTING.md](TESTING.md)。没有恢复已删除的 `bundle_node`、`portable_config` 等 Python 打包实现。`test_stage.py` 转而验证现行兼容入口的参数转发、Node 选择、子进程退出码和缺 Node 错误。

迁移还包括旧机器 Node/Python 路径、对 `.pnpm` 内部布局的依赖、生成目录和历史私有评测夹具、过期的上游事件格式/返回码。`library-upload.test.mjs` 已去除把候选 bridge 复制回源码的行为，使用当前源码、临时虚构工作区和显式解释器。临时 Windows 根路径采用 canonical realpath，保留产品拒绝 junction/reparse-point 的检查。

升级测试按当前 Cordis 多 patch entry 合并语义读配置，并用当前跟踪的 config、workspace-seed 和 lazy-mcp 构建受控临时 payload；只链接已有 Node 程序依赖。合成初始化 ID 保证实际覆盖旧 schema 升级、强制初始化、自定义技能目录保留、禁用偏好保留和幂等性，不依赖旧 base 是否具有最新初始化标记。

统一入口清空模型/远程记忆密钥，不运行真实模型脚本。质量模式需明确 opt-in、Electron 和场景文件；子进程失败、缺结果或非完整响应都返回非零。仅测试此入口的拒绝条件、错误传播和结果完整性，没有消耗模型费用。

## 实际运行环境与复跑

使用 Node 24.20.0 和已存在的 Python 3.12.14 业务环境。没有联网安装依赖。历史 `D:/qx-*` 路径在本机不存在；没有重建这些机器专用路径。

从 `harness` 目录可在本机复跑：

```powershell
. ./.local/audit-0216/build/test-env.ps1
npm test
npm run test:windows
```

被忽略的环境脚本等价于：

```powershell
$env:QX_TEST_APP='D:/Documents/ChatGPT/律所项目/.local/release-0216/stage/base/resources/workbench'
$env:QX_TEST_PYTHON=Join-Path $env:QX_TEST_APP 'runtime/python/python.exe'
$env:PYTHONPATH=(Join-Path (Get-Location) '.local/audit-0216/build/python-test-deps')+';'+(Join-Path $env:QX_TEST_APP 'runtime/scrapling/Lib/site-packages')
$env:PYTHONDONTWRITEBYTECODE='1'
$env:NODE_PATH=(Join-Path $env:QX_TEST_APP 'node_modules')+';D:/Documents/ChatGPT/律所项目/.local/release-0216/stage/app/node_modules;C:/Users/Administrator/.codex/worktrees/release-0215/律所项目/harness/packaging/node_modules'
$env:QX_BUILD_MODULES='C:/Users/Administrator/.codex/worktrees/release-0215/律所项目/harness/packaging/node_modules'
$env:QX_HDIFFPATCH_DIR='C:/Users/Administrator/.codex/worktrees/release-0215/律所项目/harness/.local/build-tools/hdiffpatch/5.1.3/windows64'
```

`python-test-deps` 只复用原项目 `.venv/Lib/site-packages` 的 pytest 及纯 Python 支持模块（pytest、_pytest、pluggy、packaging、iniconfig、pygments、colorama、py.py）。业务依赖来自已有程序 Python，Scrapling 只用于模拟 transport 测试。这里的 base 用作已有依赖位置，不被声明为通过完整构建基线校验。新机器应准备自身运行环境，不能照抄上述绝对路径。

## 命令与结果

原始输出保存在被 Git 忽略的 `harness/.local/audit-0216/build/`。表格中的组别存在重叠，不能相加作为独立用例总数。

| 命令/检查 | 原始日志 | 结果 |
| --- | --- | --- |
| 原样 `pytest packaging/test_stage.py` | `packaging-stale-red.log` | exit 2，导入删除函数导致 1 个收集错误 |
| 媒体源码及空 payload 启动 RED | `media-red.log` | 2 失败，exit 1 |
| registry 校验 RED | `media-validation-red.log` | 1 失败，exit 1 |
| 统一入口自测 RED | `runner-red.log` | 3 失败，入口尚不存在 |
| 媒体启动 GREEN | `media-green.log` | 2 通过，exit 0 |
| `pytest packaging/test_stage.py packaging/test_agent_desktop.py packaging/test_media_payload.py` | `packaging-green.log` | 7 通过，exit 0 |
| registry/打包校验/入口目标回归 | `node-targeted-green.log` | 7 通过，exit 0 |
| 第一次 `npm test` | `offline-01.log` | Node 283 通过、21 失败、2 跳过；Python pytest 缺 py 模块；exit 1 |
| 第二次 `npm test` | `offline-02.log` | Node 350 通过、15 失败、2 跳过；Python 选错工具解释器，9 个依赖收集错误；exit 1 |
| 第三次 `npm test` | `offline-03.log` | Node 352 通过、17 失败、2 跳过；Python 450 通过、8 失败、1 跳过、36 子测试通过；exit 1 |
| Python 迁移目标回归 | `migrated-python-green.log` | 98 通过、1 跳过、28 子测试通过；exit 0 |
| 第四次 `npm test`（109 Node 文件、34 Python 文件） | `offline-04.log` | Node 371 通过、2 跳过；Python 458 通过、1 跳过、36 子测试通过；exit 0 |
| 入口新增结果完整性测试后单跑 | `runner-final-green.log` | 4 通过，exit 0 |
| 初次 `npm run test:windows`（父代理） | `windows-final.log` | Node 35 通过、21 失败、0 跳过；Python 57 通过；exit 1 |
| canonical 路径修正后首次窄回归 | `windows-fixtures-green.log` | 原生 21 通过；升级 1 通过、2 失败（旧 base 缺初始化 marker）；exit 1 |
| `node --test packaging/incremental-install.test.cjs tests/audit-upgrade.test.cjs` | `windows-fixtures-final.log` | 24 通过、0 跳过，exit 0 |
| 最终 `npm run test:windows`（父代理；11 Node 文件、3 Python 文件） | `windows-green.log` | Node 56 通过、0 跳过；Python 57 通过；exit 0 |
| 上游兼容 Office 显式 Python 实测 | `office-live.log` | 内部 10 通过、1 失败、1 跳过，Node 文件包装失败；exit 1 |
| Office 静态测试补齐等待后单跑 | `../wechat/office-await-after.log` | 内部 9 通过、0 失败、1 跳过；exit 0 |
| 最终 `npm test`（全部源码/测试冻结后，父代理） | `offline-final.log` | Node 372 通过、2 跳过；Python 458 通过、1 跳过、36 子测试通过；exit 0 |

早期失败归因：Node 包含旧 WeChat 沙箱/凭据/分发夹具、旧知识行为及同时新增的 RED 场景，由各责任代理修复；Python 八项分别是三项 Scrapling 依赖、缺失历史评测输入、更新后的来源位置字段、MCP 子进程 legacy 根目录、技能 seed 目录和固定机器配置路径。各次原始失败日志均保留，没有删掉失败文件来获得通过。

首次 Windows 失败中的 19 项来自 `os.tmpdir()` 的 `ADMINI~1` 短路径与产品 canonical 安装根检查不一致；另外两项升级测试误取无 config 的 Cordis selector。修正后又发现旧 base 初始化标记假设，改为上述完整受控 payload。产品安全检查未放宽。

最终统一 Windows 已实跑通过：Node 用时 40.96 秒，Python 用时 68.41 秒。最终离线在全部代码和测试冻结后由父代理实跑通过：Node 用时 27.37 秒，Python 用时 105.84 秒；完整入口 exit 0。此后仅补齐交付文档与本地提交。

## 跳过与验证边界

`offline-final.log` 中 Node 顶层两项跳过是 `desktop/skill-quality-migration.test.cjs` 的历史发行证据：缺 `docs/checks/candidate-install/routes-changes.json`，以及缺 `docs/checks/skills-quality/backups/legal-before`。Python 一项跳过是缺原始 `D:/qx-contract-workbench-20261102` 来源副本，无法核对旧版本源字节；这三项均未声称通过。

另有 **Node 包装内部一项跳过**：`plugins/wechat/test/office.test.mjs` 未发现工具 Python，真实文档往返未跑，不包含在上述顶层 skip 数内。原文件的九个异步静态测试没有等待便退出，导致输出 `0 passed`；补齐等待后的目标回归及最终离线整组均实际执行 9 项静态测试，0 失败，保留 1 项真实往返跳过。

独审对微信目录 62 个 JS 测试文件补查后，另确认 plain-text、QQ 的尾部异步断言会漏报失败，Feishu、retry 尾部调用会漏计成功数；均已补齐等待，QQ 另补原测试遗漏的局部 `node:fs` 导入。四个测试的失败注入副本修复前错误退出 0，修复后均正确退出 1；正常目标回归内部 62 项通过，Node 顶层 4/4，exit 0。详见同日微信验证记录及 `wechat/await-probes/`、`wechat/final-tail-await.log`。

额外设置 `DSH_OFFICE_PYTHON=$env:QX_TEST_PYTHON` 的真实可选测试确实通过 DOCX 往返，但 XLSX/PPTX 场景失败于缺 `openpyxl`，PPTX 步骤未执行到，PDF 转换跳过于缺 LibreOffice Kit；保留 exit 1，未安装新依赖。该 `office.js` 仅由保留的上游 `plugins/wechat/index.js` 引用并注册 `office_*`，当前默认 `packaging/payload-config/portable.json` 和插件 package main/exports 均指向 `qx-plugin.js`，后者不加载此上游 Office 模块。此结果不等同于当前 QX 默认微信调用链故障，也不等同于 Office 兼容功能已完整验收。

本轮未运行真实模型质量、真实微信收发、完整发行包构建、NSIS 安装、用户应用迁移或 Linux/macOS 测试。仅访问程序资源、当前源码和独立虚构工作区；没有把用户合同、凭据或安装数据复制入仓库。
