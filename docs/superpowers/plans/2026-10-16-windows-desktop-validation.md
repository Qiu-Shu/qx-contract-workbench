# WIN02 Windows 桌面验证实施计划

**Spec:** `docs/superpowers/specs/2026-10-16-windows-desktop-validation.md`
**Goal:** 可安装、可启动、可重启且保留既有业务控制的本机验证版。
**Architecture:** Electron 主进程拥有冻结 Python 子进程；窄账户设置 IPC；复用 FastAPI 页面。安装资源与 Windows userData 分离。资料库保留现有外部路径。
**Tech Stack:** 既有 Python 3.12/FastAPI/SQLite；Electron、electron-builder NSIS、PyInstaller 精确固定版本。

## Global Constraints

沿用户指定 `codex/contract-review-v2` 继续；不重建已有资料库、不操作真实案件、不上传。新依赖仅构建使用；资源清单显式列出，禁止打包 `.local`、凭据、真实材料。已有方向已确认且用户要求无人值守，本轮细节自主落实，不重复询问审批。

## Review Focus

1. 路径越界、重解析点、首次设置覆盖旧数据。
2. 登录/CSRF/案件权限或来源校验退化。
3. 桌面 IPC、导航、外部页面取得文件和进程权限。
4. 端口抢占、重复 worker、退出残留、异常恢复。
5. 冻结资源遗漏、安装覆盖数据、打包真实材料或秘密。

## Task 1 — 可迁移数据目录与独占后端

- 接口：`initialize_workspace(..., data_parent=None)`、`build_local_app(..., data_parent=None)` 默认行为不变；桌面仅从可信主进程传入专用父目录。
- 文件：`config.py`、`web/local_server.py`、新增 `desktop_entry.py`、`tests/test_desktop_runtime.py`。
- 先写失败测试：外部中文目录、越界拒绝、重复初始化拒绝、旧 CLI 范围仍限 `.local`；子进程初始化/就绪/EOF 退出及登录要求。
- 实现资产根目录冻结适配、标准输入协议、系统分配回环端口、退出监测。运行新测试及 local workbench/auth 关联回归。

## Task 2 — 桌面壳与首次设置

- 文件：`desktop/package.json`、锁文件、`main.cjs`、`backend.cjs`、`preload.cjs`、`setup.*`、`tests/*.test.cjs`。
- 先测试导航和 IPC 来源验证、进程启动/退出/错误状态；实现窄权限壳、首次设置、目录选择、打开既有登录页和固定错误反馈。
- 默认 sandbox/contextIsolation、关闭 Node、拒绝新窗口和外部导航、只接受本窗口设置页 IPC、会话只在内存；下载用系统保存对话框。
- UI 延续浅色操作页面；输入有标签和错误状态，可用键盘，窄窗口可用，无联网字体或图片。

## Task 3 — 打包与实机贯通

- 文件：`scripts/build_desktop.ps1`、冻结入口/spec、构建依赖锁及操作说明；打包清单仅必要程序和已登记合成样本。
- 安装隔离构建工具，固定版本和下载校验，构建 Python onedir 与 Electron NSIS。安装到独立中文测试目录。
- 冻结子进程和实际桌面验证首次账户、登录、样本导入、原文、导出、资料库、重启、异常退出；收集资源和显示比例证据。运行受影响回归。

## Task 4 — 复核与交付记录

- 新上下文独立 reviewer 审查上述五类风险；重要问题先证明失败再修复并回归。
- 更新 TASK_STATUS、测试记录、产物哈希与用户启动说明；保存本地提交和 Obsidian 状态。只在实际验收完成后标记 WIN02 验证版完成。

Self-review：各任务按接口依赖顺序执行；用户资料边界及失败恢复列为必验，不把最终生产要求混入本次完成标准。
