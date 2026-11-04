# GitHub 增量更新

发布仓库：`Qiu-Shu/qx-contract-workbench`。客户端启动约 15 秒后检查，此后每 6 小时检查一次；也可从菜单“检查更新”手动检查。发现新版本只在律所知识库上方显示黄色按钮。点开小面板后由用户下载、取消或安装；退出软件不会自动安装，旧版不设置到期限制。

## 第一版接入

已发布 0.2.6 的差分范围是**下载**：重建完整安装器后仍执行全量卸载和展开。当前安装优化候选在此基础上增加**安装增量**：只处理变化文件并保留未变文件，支持中断恢复；首次安装允许选择目录。候选尚未发布，具体基线和实测范围见 [安装优化交接](../docs/2026-11-04-增量安装与目录选择.md)。不能把旧版差分下载称为增量安装。

0.2.2 及更早安装包没有更新模块，无法凭空收到软件内更新。已有用户需要手动安装一次带更新模块的新版（当前为 0.2.4）；新用户也使用此完整安装包。后续从有更新模块的版本开始下载增量。首次完整安装和后续增量更新须明确区分。

NSIS 在安装时保留原安装器供差分复用。不要清理 `%LOCALAPPDATA%/qunxing-harness-desktop-updater/installer.exe`。差分基线缺失、旧 blockmap 不可用、网络不支持 Range 或校验失败时，停止更新并保留旧版，绝不自动下载整包。

## 发布文件

每个正式版本使用 `v版本号` 标签，上传构建目录中的以下三个文件：

1. `Qunxing-Workbench-版本号-Setup.exe`
2. `Qunxing-Workbench-版本号-Setup.exe.blockmap`
3. `latest.yml`（已经签名，不能手工改动）

必须保留历次 Release 的安装包和 blockmap，不删除、不覆盖同版本资产。先上传全部文件再将草稿转成正式 Release，避免客户端看到尚未上传完整的更新。不要上传 `win-unpacked`、中间 `.7z`、测试安装器或任何私钥。本地构建显式禁用自动发布。

程序依赖固定的 `electron-updater@6.8.11`。签名覆盖版本、安装器名、长度、SHA-512 和更新说明；客户端下载后、安装前分别验签和校验完整文件。这里的更新签名不等同于 Windows 商业代码签名，安装器仍可能显示未知发布者。

## 构建与签名

首次签名身份已经建立。`desktop/update-config.json` 包含可公开的源配置及公钥；`.qx-private/update-signing-key.pem` 是签名私钥，已经忽略，不进 Git、不打包。请把私钥单独安全备份，不能随意重新生成，否则已安装客户端无法验证新发布。也可通过构建环境变量 `QX_UPDATE_SIGNING_KEY` 指定另一处保存的同一私钥。

构建前更新 `packaging/update-notes.txt`。刷新暂存区并设置新版本，然后运行：

```powershell
python packaging/refresh-stage.py .local/<暂存目录> <版本号>
$env:QX_BASE_DIR='D:/<已发布版本的原始程序目录>'
$env:QX_BASE_VERSION='<基线版本号>'
node packaging/build.cjs .local/<暂存目录> .local/<发布目录>
```

构建自动生成 blockmap、`latest.yml`，再签名。发布前须重新核对 `latest.yml` 与最终 EXE 的大小和 SHA-512，并在独立测试目录验证。生产安装标识、程序名及资料目录继续沿用，避免升级变成另一套软件。

## 国内网络与后续 OSS

2026-11-03 本机显式不使用代理的检查中，GitHub 首页/API 返回 200，已有 Release 安装包的 Range 请求返回 206、读取 1024 字节。该结果只说明本机当时线路可用，不能保证其他地区、运营商或时段。

后续可把 feed 改为 `{"provider":"generic","url":"https://你的下载域名/updates/","useMultipleRangeRequest":false}`，重新构建带新配置的版本。OSS/下载服务器必须提供 HTTPS、正确的单段 Range/206、全部历史安装器及 blockmap；新版本文件先上传，最后更新签名的 `latest.yml`。这不是远程即时切换：已安装 GitHub 版需先从 GitHub 获取一次带新源配置的版本，或手动安装。

安装前提醒用户保存并结束文档、模型回答和微信任务；目前不自动判断这些任务是否完成。确认后停止本实例后台，再启动安装器；启动失败尝试恢复旧后台。不升级时工作台功能不受更新源连接失败影响。

## 验证入口

- `node --test desktop/updates.test.cjs desktop/update-download.test.cjs`：验签、防篡改、拒绝降级、取消/重复操作、真实 HTTP Range、缺少缓存/服务器返回 200/损坏数据、安装启动失败。
- `python desktop/check_update_ui.py`：实际客户端、隔离浏览器、合成更新状态；黄色入口位置、小面板、进度/取消、说明按文字显示、老环境无桥兼容。
- `node packaging/check-delta-packages.cjs`：独立安装标识的两个微型真实 NSIS 包，差分重建后实际安装升级，检查中文与空格路径及外部资料保留。测试产物不得发布；不把微型包验收表述为完整生产包安装验收。

完整生产包未在另一台干净的大陆电脑验收前，不承诺所有网络与系统环境均可用。
