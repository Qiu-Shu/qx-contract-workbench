# 2026-11-12 独立 NSIS 安装验收

三组真实 NSIS 隔离测试通过，入口退出码均为 0。覆盖两条升级基线、已提交文件事务的中断恢复、首次安装、中文与空格目录、非空目录保护；共观察到 9 次场景安装器/卸载器执行，其中 8 次退出 0，非空目录拒绝按预期退出 1。QA 安装已卸载，测试注册表和进程均已清理。

**边界：这是复用现有安装代码的合成小载荷测试，不是完整 0.2.17 候选安装器实装。** 测试版本沿用夹具的 0.2.6、0.2.7、0.2.8，不能当作正式 0.2.14/0.2.15 升级验证；没有发布、推送或覆盖真实安装，没有运行真实模型或使用真实业务资料。

## 范围和隔离

- 源码工作区：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目/harness`；开始时 HEAD 为 `dab11f2bf6fa300e0b488e5f4c14a9c86411faed`。
- 测试运行时间：2026-11-12 15:26:16–15:27:32（Asia/Shanghai）；原始日志使用 UTC。
- QA `appId`：`cn.qunxing.install-speed-qa.20261104`；产品/进程名：`QunxingInstallQa`；包名：`qunxing-install-speed-qa`。
- NSIS 实际编译定义中的 GUID：`38f37133-0267-5420-a267-42c43fdc4e20`。开始时没有 QA 卸载项和 QA 进程；所有安装目标均位于下述测试根目录。
- 测试根：`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/installer-qa`；本次载荷目录：`nsis-1794468377358`。
- 安装器为当前用户、禁止提权、不创建桌面/开始菜单快捷方式、不运行安装后的应用。合成应用 EXE 是 Windows `where.exe` 的副本，ASAR 是固定测试文本。载荷不包含 `stop-installed.cjs`，不会调用真实工作台后台停止入口。
- 本验收没有修改产品源码；唯一仓库新增文件是本记录。主代理同期修改的候选版本/构建文件不属于本子任务。

## 工具与执行

复用 `.local/audit-0216/build/test-env.ps1` 的依赖位置，实际 Node 为 v24.22.1，SHA-256 为 `86f361a88f4cc3ecaf1ea93236b0d8edf07bf00fe87ad9f60305513f58fc2c17`。Node 来自已存在的 0.2.16 构建基线目录，仅作为工具和合成载荷来源；没有启动主代理的 stage/candidate。

构建使用 electron-builder 26.15.3、NSIS 3.0.4.1、nsis-resources 3.4.1、7zip 工具缓存 1.0.0，以及代码内摘要验证的 HDiffPatch 5.1.3。`TEMP`、`TMP`、`QX_BUILD_CACHE`、`ELECTRON_BUILDER_CACHE` 和 npm 缓存均设置为本次 D 盘测试根下的新目录。现有工具缓存复制后复用，未向共享缓存写入。构建日志中的“signing”阶段不等于已签名：对 QA 0.2.8 EXE 的 Authenticode 检查结果实际为 `NotSigned`。

按依赖顺序从 `harness` 执行以下入口，外层 `run-step.ps1` 留存每次命令、时间、退出码、QA 注册表和进程快照。D 盘内的只观察预加载脚本记录 `spawn`/`close` 与参数，不改变原始调用参数或返回对象。

| 顺序 | 实际入口（以上述 Node 执行） | 入口退出码 | 真实结果 |
| --- | --- | --- | --- |
| 1 | `packaging/check-incremental-installer.cjs` | 0 | 2 条基线升级；1 条中断恢复；两条路径均含中文和空格 |
| 2 | `packaging/check-fresh-installer.cjs` | 0 | 先卸载前一 QA 安装，再在不存在的中文空格目录首次安装 |
| 3 | `packaging/check-nonempty-installer.cjs` | 0 | 先卸载首次安装，再对含一个合成文件的非空目录运行安装器；安装器退出 1 |

中断场景通过真实 `applyUpdate` 提交 0.2.7 的文件事务，留下未 finalize 的事务，并把严格匹配该 QA 卸载路径的注册项 `DisplayVersion` 改为 0.2.8；随后重新运行同一个 QA 0.2.8 安装器。该状态注入验证恢复入口和按文件摘要选择基线，没有用模拟返回值代替安装执行，也不声称实测了断电。

代码图检查复用了 `harness/.codegraph`。最初对仓库根查询返回未索引，定位到实际子项目后成功取得三个入口及 `prepareIncrementalPackage`、`customizeInstaller`、`applyUpdate` 的调用关系（73 符号/8 文件），并补查 `recoverUpdate`、`recoverUnlocked`、`finalizeUpdate`、锁与清理路径。NSIS 宏及第三方模板另按实际源码核对，包括 QA 进程名、GUID 注册表、增量/全量分流与不启动应用的配置。图检索用于定位，不代表所有动态调用已被静态图证明。

## 数量和结果

每条合成基线和目标均为 185 个文件；两份差异计划分别对 0.2.6 和 0.2.7 生成。主计划记录 183 个未变文件、93,803,398 个未变字节、3 个变更路径（修改/新增/删除各一），差异包 233 字节。这里的约 94 MB 主要是复制的 Node 运行时，不是完整产品载荷。

两次升级均验证 Node 文件身份与纳秒修改时间未变，新增文件/ASAR 内容正确、旧文件被删除，用户自加的合成文件保持原内容。首次安装验证 Node、卸载器、7-Zip 许可证存在及旧文件不存在。非空目录保持唯一的 `保留资料.txt`，内容仍为 `synthetic user file`。

| 路径 | 基线安装耗时 | 升级/首次安装耗时 | 结果 |
| --- | ---: | ---: | --- |
| QA 0.2.6 → 0.2.8 | 4.052 秒 | 3.692 秒 | 通过 |
| QA 0.2.7 → 0.2.8，中断恢复 | 3.676 秒 | 5.008 秒 | 通过 |
| QA 0.2.8 首次安装 | — | 4.612 秒 | 通过 |

上述时间仅为本机合成场景观测，不能外推完整产品安装速度。

真实场景进程退出证据为：基线安装 PID 14140/17552 均 0；升级 PID 7268/5416 均 0；首次安装 PID 18348 为 0；卸载 PID 22460/1696/20360 均 0；非空目录安装 PID 3788 为 1。完整路径、参数、起止时间见 `nsis-launches.json`。

## 卸载和收尾

最终对 HKCU/HKLM、原生/WOW6432Node 两种视图的 QA GUID 安装项和卸载项共 8 个位置检查，全部不存在；QA 安装器/应用进程为 0。3 次卸载均成功。使用 `_?=` 的卸载调用留下各一份卸载器自身 EXE，已核对目录仅剩该文件后移至测试根的 `uninstalled-residues` 保留证据；3 个原 QA 安装目录均不存在。

Windows NSIS 的 `$LOCALAPPDATA` 使用系统已知目录，仍会写 QA 专属 `C:/Users/Administrator/AppData/Local/qunxing-install-speed-qa-updater`。测试前该 QA 缓存已有一份旧安装器，先保留到 D 盘；测试后将新缓存归档至 `test-qa-updater-cache`，再恢复旧缓存并核对文件数、长度和 SHA-256 一致。恢复旧文件为 24,696,531 字节，摘要 `bf5941ccb7ecb741613beb92b18e29491efe50b427cffd61998ca8976ad01636`。未删除或更改真实产品缓存。

完整原始证据保存在 [D 盘验收目录](D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/installer-qa)，包含 `preflight.json`、三个 `*-execution.json`、三个日志、`child-processes.jsonl`、`nsis-launches.json`、三份场景报告、`cleanup.json`、`codegraph-evidence.json`、差异计划、QA 安装器及 `evidence-manifest.json` 摘要清单。证据保持本地，不提交大型二进制。

完整候选的文件比对、官方 0.2.14/0.2.15/0.2.16 三条完整基线差异回放、候选运行时测试及发布边界由主任务单独记录；本记录不替代这些验收。
