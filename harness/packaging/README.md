# 0.2.18 Windows 安装包

0.2.18 已正式发布并在本机原目录升级，沿用原更新签名身份；公开安装包完整下载、签名与摘要核验通过。[下载正式版](https://github.com/Qiu-Shu/qx-contract-workbench/releases/tag/v0.2.18) · [发布记录](../docs/2026-11-13-0.2.18发布.md)。

Windows 10/11 x64，当前 Windows 用户安装；自带 Node、Python、文档与浏览器工具运行环境。首次运行填写自己的模型配置。资料与加密设置位于 `%APPDATA%/QunxingHarness`，程序目录可自选；业务代码从运行配置取得根目录。

安装流程：新用户选择空文件夹；已有固定的官方 0.2.14、0.2.15、0.2.16 或已验收的 0.2.17 候选版沿原目录升级，只替换变化的程序文件；更早版本按 0.2.6 → 0.2.7 → 0.2.9 → 0.2.10 → 0.2.14 → 0.2.18 顺序继续升级，0.2.5 及以前先手动安装 0.2.6。若程序文件曾被手工修改，严格基线核验会拒绝覆盖。当前安装器不是任意旧版本的全量修复器。

旧版增量下载失败时，可手动下载本版安装器并沿原目录安装一次，无需卸载。新下载器支持有限重试与完整包接续；完整包校验和资料隔离继续有效。

## 从源码打包

在 Windows x64 上准备 Node 24.9+、npm、Git，建议构建与验证磁盘剩余 30 GB。以下均从 `harness` 目录执行，输出路径由你自行选择，不必安装到固定盘符。

```powershell
npm ci --prefix packaging
node packaging/stage.cjs ../.local/release-stage
node packaging/build.cjs ../.local/release-stage ../.local/release-output
```

`stage.cjs` 下载并核验 `bootstrap.lock.json` 固定的官方 0.2.14 安装包和 7-Zip。也可在第二参数提供已下载的官方安装包；仍必须通过摘要校验。它提取基线、复制候选目录，然后叠加本仓库应用代码、默认 Skill、配置和三处第三方依赖修补，生成 ASAR 与 `source-manifest.json`。新建阶段拒绝覆盖已有目录；源码更改后可用 `node packaging/stage.cjs <stage> --refresh`，随后使用新的输出目录构建。

**重建边界：** 此流程重建本项目应用代码对应的发行包，第三方 Node/Python/Electron/Office/browser 依赖复用已校验官方 0.2.14 二进制。不是对全部第三方组件的源码编译；不会读取开发者安装目录或用户资料。`legacy/` 为当前运行所需旧业务模块快照，仓库根旧工程不参与本入口。

构建工具固定版本在 `packaging/package-lock.json`。可通过 `QX_BUILD_MODULES` 指向已安装的构建依赖目录，`QX_BUILD_CACHE` 指定工具缓存；默认使用项目内目录。`QX_HDIFFPATCH_DIR` 如有指定也会核验摘要。历史 Python 打包入口已转发到新入口。

额外升级基线记录于同一锁文件的 `upgradeBases`，暂存时按摘要下载、解包，并校验整个目录。`QX_RELEASE_CACHE` 可指向存放官方安装器的缓存目录，文件名保持发布名；复用前仍验证摘要。0.2.17 候选以原始字节归档在 v0.2.18 附件 `Qunxing-Workbench-0.2.17-baseline-archive.exe`，仅作重建基线；普通用户不要选择该文件安装。构建时为每个已固定基线生成独立差异，安装时按实际程序标记摘要选择对应计划，以兼容注册表已更新而文件事务未完成的中断恢复；路径由暂存与实际安装目录推导。

## 签名与发布

正式发布者设置 `QX_UPDATE_SIGNING_KEY` 为原更新私钥的位置，再构建或运行 `node packaging/update-release.cjs sign <output> packaging/update-notes.txt`。私钥必须匹配 `desktop/update-config.json` 公钥，不能提交或上传。未提供私钥时仅生成 `latest.unsigned.yml`，不能作为自动更新元数据发布。这里的 Ed25519 更新签名不是 Windows Authenticode 证书。

正式附件为安装器、`.blockmap`、已签名 `latest.yml` 与 `SHA256SUMS.txt`；Git 标签必须指向对应源码。发布前核对附件摘要、公钥验证和发布标签。

## 验证

设 `QX_TEST_APP` 为候选目录的 `resources/workbench`，设置 `PYTHONDONTWRITEBYTECODE=1`，以其 `runtime/node.exe` 执行 `--test tests/*.test.mjs tests/*.test.cjs desktop/host-recovery.test.cjs desktop/installed-runtime.test.cjs packaging/incremental-package.test.cjs packaging/incremental-install.test.cjs packaging/verify-stage.test.cjs`。原生增量测试需设置 `QX_HPATCHZ_TEST_EXE` 为已校验 hpatchz.exe；跳过不算通过。不要在打包期间运行任何候选程序或测试。

构建前核验整个基线目录摘要、全部仓库来源、生成物和未修改依赖；额外缓存/文件会阻止打包。归档前后再次比较整个候选目录，防止全量安装与增量计划不一致。

下载链路另执行 `node --test desktop/update-download.test.cjs desktop/updates.test.cjs`，覆盖真实本地HTTP、缓存错配、连接中断、完整包损坏、取消及错误分类；不能只验证安装差异而跳过下载器。`check-production-delta.cjs <old-release> <new-release>` 使用正式安装器与blockmap回放下载重建并核对签名，临时目录可由系统TEMP指定。

`check-incremental-installer.cjs` 和 `check-fresh-installer.cjs` 用隔离 QA 安装标识与虚构数据验证真实 NSIS；`QX_INSTALL_TEST_ROOT` 指定测试目录。`check-full-incremental.cjs <stage/base> <output> <test-output-parent>` 对完整发行差异进行隔离回放，检查未变文件与自加文件保留。不能在用户真实目录运行测试安装。
