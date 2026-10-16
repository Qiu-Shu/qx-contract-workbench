# Windows 本机验证版 0.2.0

本轮复用现有合同工作台；Electron 只承担窗口、首次账户设置、受控导出及自有后台进程。原有 Python 业务、登录、权限和原文核验继续使用。本轮属于 WIN02 安装路径验证，不代表统一应用或生产交付完成。

## 使用

运行 `Qunxing-Workbench-0.2.0-Setup.exe`，按安装向导选择当前用户安装。首次打开设置本机用户名和 6–12 位密码；其后仍需在既有工作台登录。密码不写入命令行或设置文件。当前没有找回密码服务，请自行妥善保存。

菜单“工作台 → 连接法律资料库…”选择已完成索引的库根目录。本机已验收的库为 `D:\Documents\群兴法律资料库`，不是 F 盘原始文件目录。连接后需重新登录。法规、案例的命中及原文仍显示待核验状态；检索成功不等于官方效力已核验。

用户账户和案件保存在 `%APPDATA%\QunxingWorkbenchValidation\workspaces\main`，资料库仍保存在自己的目录。程序安装目录与资料分开；卸载选项不主动删除用户数据。资料库暂不可用时，菜单“断开资料库连接”后仍可使用案件工作台。已有或不完整工作区不会自动重建；错误时保留现场供维护处理。

菜单“视图”可调整字号。导出通过现有权限校验后打开 Windows 保存窗口。关闭程序会停止本程序启动的后台服务，不触碰源码版的 8767 服务。

## 已验证与限制

本机 Windows 10 x64：安装到中文带空格路径，首次设置、登录、合成 DOCX 导入、原文定位、人工候选与处置、Word 下载、重启保留资料、资料库设置失败恢复、全量法库连接与吉林检索、后台及主窗口异常退出已实测。详细证据见 `docs/testing/WINDOWS-DESKTOP-20261016.md`。

本次仅验证 DOCX 工作流。PDF.js/OCR 运行资产尚未纳入此最小包；仍需这些能力时保留原源码工作台。手机号/验证码、邀请、设备会话、自助找回、签名及在线升级尚未交付。安装包未签名；本次未购买证书。测试电脑用户为 Administrator，未验证另一中文 Windows 用户、实际系统 DPI 切换或干净第二台电脑。100/125/150% 指应用渲染缩放。

## 重建

前提：固定项目 `.venv` 依 `requirements.lock` 建立；Python 3.12.14、Node 24.19.0。本机原有环境保持不变，构建工具单独放 `.local/desktop-tools`。

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_desktop.py
.\scripts\build_desktop.ps1
```

Electron 44.8.0 / electron-builder 26.15.3 由 `package-lock.json` 固定，npm 12.2.0 tarball 用固定 SHA512 校验；Electron 官方 GitHub zip 对照 npm 包内 SHA256 校验。PyInstaller 6.22.3 及构建依赖由 `requirements-build.lock` 固定并校验哈希。NSIS 和 7-Zip 由固定 electron-builder 的构建工具配置下载校验。无签名账号或付费服务。

打包仅包含显式代码、界面、固定配置、已登记虚构样本、规则草稿及依赖许可文本；不会收录 `.local` 工作区、法律库、密钥或真实案件。Python 的第三方许可放在安装目录 `resources/backend/_internal/third-party-licenses`，Electron 的许可随运行组件附带。

`QX_DESKTOP_DATA_PARENT` 仅供由操作系统启动的维护/验收进程指定隔离资料目录，网页不能修改。合成验收脚本位于 `desktop/tests`，使用本机 Playwright Electron 驱动；`PLAYWRIGHT_MODULE` 可指向已安装模块绝对路径。无需最终用户安装 Python、Node 或设计技能。
